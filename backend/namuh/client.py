import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

import httpx

from backend.config import base_dir

BASE_URL = 'https://api.nhplug.com:8443'


class NamuhError(Exception):
    """Safe to display: never includes upstream response bodies or credentials."""

    def __init__(self, message, *, stage='unknown', code=None, http_status=None):
        super().__init__(message)
        self.diagnostic = dict(stage=stage if stage in ('unknown','auth','http','transport','decode','business','fields','input') else 'unknown',
                               code=code if isinstance(code,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,16}',code) else None,
                               http_status=http_status if type(http_status) is int and 100 <= http_status <= 599 else None)


class NamuhRejected(NamuhError):
    """A complete, structured business rejection, rather than an uncertain transport result."""


def read_credentials():
    key = os.getenv('NAMUH_APP_KEY', '').strip()
    secret = os.getenv('NAMUH_APP_SECRET', '').strip()
    if key and secret:
        return key, secret
    path = Path(base_dir) / 'Api_Key.txt'
    if path.exists():
        values = {}
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            parts = re.split(r'\s*[:=]\s*', line.strip(), maxsplit=1)
            if len(parts) == 2:
                label = re.sub(r'[^a-z]', '', parts[0].lower())
                values[label] = parts[1].strip().strip('\"\'')
        # Use the pair from one source, never mix secrets from different apps.
        key = values.get('appkey', '')
        secret = values.get('appsecret', '') or values.get('appsecretkey', '')
    if not key or not secret:
        raise NamuhError('나무증권 App Key와 App Secret을 Api_Key.txt 또는 NAMUH 환경변수에 설정해주세요.')
    return key, secret


class NamuhClient:
    def __init__(self, app_key, app_secret, token_file, *, http=None, min_interval=0.25):
        self.app_key = app_key
        self.app_secret = app_secret
        self.token_file = Path(token_file)
        self.http = http or httpx.Client(base_url=BASE_URL, timeout=30)
        self.fingerprint = hashlib.sha256(f'{app_key}:{app_secret}'.encode()).hexdigest()
        self.token_lock = threading.Lock()
        self.rate_lock = threading.Lock()
        self.min_interval = min_interval
        self.last_request = 0.0

    def get_access_token(self):
        # One renewal per process; valid tokens are reused after app restart too.
        with self.token_lock:
            try:
                data = json.loads(self.token_file.read_text(encoding='utf-8'))
                if (data.get('fingerprint') == self.fingerprint
                        and float(data['expires_at']) > time.time() + 60
                        and data.get('access_token')):
                    return data['access_token']
            except (OSError, ValueError, KeyError, TypeError):
                pass
            try:
                response = self.http.post(BASE_URL + '/oauth2/token', data={
                    'appkey': self.app_key, 'appsecretkey': self.app_secret,
                    'grant_type': 'client_credentials', 'scope': 'oob'})
                response.raise_for_status()
                data = response.json()
                token = data['access_token']
                lifetime = int(data['expires_in'])
                if not token or lifetime <= 0:
                    raise ValueError('Invalid token response')
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                raise NamuhError('나무증권 인증 실패: 키·API 사용등록·접속 가능 여부를 확인해주세요.', stage='auth') from None
            cache = {'access_token': token, 'expires_at': time.time() + lifetime,
                     'fingerprint': self.fingerprint}
            try:
                self.token_file.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.token_file.with_suffix('.tmp')
                temporary.write_text(json.dumps(cache), encoding='utf-8')
                temporary.replace(self.token_file)
            except OSError:
                raise NamuhError('토큰 캐시를 저장할 수 없습니다. 설정 폴더 쓰기 권한을 확인해주세요.') from None
            return token

    def post(self, path, payload, *, cts='', success_codes=None, before_send=None):
        token = self.get_access_token()
        headers = {'Authorization': f'Bearer {token}',
                   'content-type': 'application/json;charset=utf-8',
                   'cts_flag': 'Y' if cts else 'N', 'cts': cts}
        with self.rate_lock:
            delay = self.min_interval - (time.monotonic() - self.last_request)
            if delay > 0:
                time.sleep(delay)
            self.last_request = time.monotonic()
            if before_send:
                before_send()
            try:
                response = self.http.post(BASE_URL + path, headers=headers, json=payload)
                if not response.is_success:
                    try:
                        body = response.json()
                        error_code = body.get('rsp_cd') or (body.get('message') or {}).get('msg_code') if isinstance(body,dict) else None
                    except (ValueError, AttributeError): error_code = None
                    raise NamuhError('나무증권 HTTP 요청에 실패했습니다. 연결 상태와 요청 형식을 확인해주세요.',
                                     stage='http', code=error_code, http_status=response.status_code)
                data = response.json()
            except httpx.HTTPError:
                raise NamuhError('나무증권 서버 요청에 실패했습니다. 잠시 후 다시 조회해주세요.', stage='transport') from None
            except ValueError:
                raise NamuhError('나무증권 응답을 해석하지 못했습니다.', stage='decode') from None
        if not isinstance(data, dict):
            raise NamuhError('나무증권 응답 형식이 올바르지 않습니다.')
        code = str(data.get('rsp_cd', ''))
        if code not in (success_codes or {'00000', '00136', '00166'}):
            safe_code = code if re.fullmatch(r'[A-Za-z0-9_-]{1,16}', code) else 'unknown'
            # A numeric code alone does not prove that an order was not accepted.
            # No verified rejection-code catalogue is published with these contracts.
            error_type = NamuhRejected if re.fullmatch(r'[0-9]{5}', code) and '/order/' not in path else NamuhError
            raise error_type(f'나무증권 요청 거절 (코드: {safe_code}). API 이용 설정과 주문 조건을 확인해주세요.', stage='business', code=safe_code)
        return data, response.headers

    def pages(self, path, payload, *, success_codes=None):
        cts = ''
        seen = set()
        for _ in range(100):
            options = {'success_codes': success_codes} if success_codes is not None else {}
            data, headers = self.post(path, payload, cts=cts, **options)
            yield data
            if headers.get('cts_flag', 'N') != 'Y':
                return
            cts = headers.get('cts', '')
            if not cts or cts in seen:
                raise NamuhError('나무증권 연속조회에 실패했습니다. 다시 조회해주세요.')
            seen.add(cts)
        raise NamuhError('나무증권 조회량이 한도를 초과했습니다.')


_client = None
_client_lock = threading.Lock()


def get_client():
    global _client
    with _client_lock:
        if _client is None:
            key, secret = read_credentials()
            _client = NamuhClient(key, secret, Path(base_dir) / '.namuh_token_cache.json')
        return _client


def number(value):
    return float(value or 0)
