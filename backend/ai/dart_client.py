"""Bounded official OpenDART requests. Never expose keyed URLs or upstream errors."""
import copy
import hashlib
import io
import json
import logging
import re
import threading
import time
import zipfile
from collections import OrderedDict
from xml.etree import ElementTree

import httpx


class _RedactDartKey(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        if 'crtfc_key=' in message:
            record.msg = re.sub(r'(crtfc_key=)[A-Za-z0-9]+', r'\1REDACTED', message)
            record.args = ()
        return True


logging.getLogger('httpx').addFilter(_RedactDartKey())


class DartError(ValueError): pass


class Cache:
    def __init__(self, limit=128):
        self.entries, self.lock, self.limit = OrderedDict(), threading.Lock(), limit

    def get(self, key):
        with self.lock:
            item = self.entries.get(key)
            if item and item[0] > time.monotonic():
                self.entries.move_to_end(key)
                return copy.deepcopy(item[1])
            self.entries.pop(key, None)

    def put(self, key, value, ttl):
        with self.lock:
            self.entries[key] = (time.monotonic()+ttl, copy.deepcopy(value))
            while len(self.entries) > self.limit: self.entries.popitem(last=False)


_responses, _codes = Cache(), Cache(2)
ERRORS = {'010':'등록되지 않은 DART 키입니다.', '011':'사용 중지된 DART 키입니다.',
          '012':'DART에서 허용하지 않은 IP입니다.', '020':'DART 요청 한도에 도달했습니다.',
          '800':'DART 점검 중입니다.', '901':'DART 인증키의 사용 기간을 확인하세요.'}


def status(payload):
    code = payload.get('status')
    if code not in ('000', '013'):
        raise DartError(ERRORS.get(code, 'DART 응답을 확인하지 못했습니다.'))


class DartClient:
    def __init__(self, key, *, http, cached=False, cancelled=lambda: False):
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9]{40}', key):
            raise DartError('DART 인증키는 영문·숫자 40자리로 입력하세요.')
        self.key, self.http, self.cached, self.cancelled = key, http, cached, cancelled
        self.deadline = time.monotonic()+90

    def guard(self):
        if self.cancelled() or time.monotonic() > self.deadline:
            raise DartError('DART 조회가 중단되었거나 제한 시간을 초과했습니다.')

    def raw(self, endpoint, params, limit=2*1024*1024):
        self.guard()
        if endpoint not in ('company.json', 'list.json', 'fnlttSinglAcntAll.json', 'corpCode.xml'):
            raise DartError('DART 요청 경로를 확인하세요.')
        try:
            with self.http.stream('GET', 'https://opendart.fss.or.kr/api/'+endpoint,
                    params=dict(params, crtfc_key=self.key), timeout=10, follow_redirects=False) as response:
                if response.status_code != 200: raise DartError('DART 서버 요청에 실패했습니다.')
                raw = bytearray()
                for chunk in response.iter_bytes():
                    self.guard()
                    if len(raw)+len(chunk) > limit: raise DartError('DART 응답 크기가 허용 범위를 초과했습니다.')
                    raw.extend(chunk)
            if self.key.encode() in raw: raise DartError('DART 응답 형식을 확인하지 못했습니다.')
            return bytes(raw)
        except httpx.HTTPError:
            raise DartError('DART 서버에 연결하지 못했습니다.') from None

    def json(self, endpoint, **params):
        self.guard()
        cache_key = hashlib.sha256((self.key+endpoint+json.dumps(params,sort_keys=True)).encode()).hexdigest()
        if self.cached:
            found = _responses.get(cache_key)
            if found is not None: return found
        try:
            payload = json.loads(self.raw(endpoint, params))
            if not isinstance(payload, dict): raise ValueError()
            status(payload)
            payload['_fetched_at'] = time.time()
            if self.cached: _responses.put(cache_key, payload, 900)
            return payload
        except (ValueError, TypeError) as exc:
            if isinstance(exc, DartError): raise
            raise DartError('DART 응답 형식을 확인하지 못했습니다.') from None

    def codes(self):
        self.guard()
        token = hashlib.sha256(self.key.encode()).hexdigest()
        found = _codes.get(token) if self.cached else None
        if found is not None: return found
        result = company_codes(self.raw('corpCode.xml', {}, 16*1024*1024))
        if self.cached: _codes.put(token, result, 86400)
        return result


def company_codes(raw):
    try:
        if raw.startswith(b'PK'):
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                files = [i for i in archive.infolist() if i.filename.upper() == 'CORPCODE.XML']
                if len(files) != 1 or files[0].file_size > 64*1024*1024: raise ValueError()
                raw = archive.read(files[0])
        if b'\x00' in raw or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper(): raise ValueError()
        root = ElementTree.fromstring(raw)
        if root.find('status') is not None:
            status({'status':root.findtext('status')})
            raise ValueError()
        result, ambiguous = {}, set()
        for row in root.findall('list'):
            code, corp = (row.findtext('stock_code') or '').strip(), (row.findtext('corp_code') or '').strip()
            if re.fullmatch(r'[0-9A-Z]{6}',code) and re.fullmatch(r'\d{8}',corp):
                if code in result and result[code] != corp: ambiguous.add(code)
                else: result[code] = corp
        for code in ambiguous: result.pop(code, None)
        if not result: raise ValueError()
        return result
    except (ValueError, KeyError, zipfile.BadZipFile, ElementTree.ParseError, RuntimeError) as exc:
        if isinstance(exc, DartError): raise
        raise DartError('DART 종목·기업 매핑 파일을 확인하지 못했습니다.') from None


def check_key(key):
    with httpx.Client(trust_env=False, follow_redirects=False) as http:
        result = DartClient(key, http=http).json('company.json', corp_code='00126380')
        if result.get('status') != '000' or result.get('stock_code') != '005930':
            raise DartError('DART 기업 조회로 연결을 확인하지 못했습니다.')
