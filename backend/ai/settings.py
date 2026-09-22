"""Local AI credentials encrypted with Windows user-scoped DPAPI. No trading calls."""
import base64
import ctypes
from ctypes import wintypes
import json
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

PROVIDERS = ('openai', 'anthropic', 'gemini')
SCOPES = dict(openai='models', anthropic='models', gemini='models', tavily='usage', dart='company')
SUCCESS_MESSAGES = dict(models='모델 목록 조회에 성공했습니다. 모델 생성 권한은 별도입니다.',
                        usage='사용량 조회에 성공했습니다. 검색 실행 결과는 별도입니다.',
                        company='기업 개황 조회에 성공했습니다.')


def connection(scope, status='unverified', checked_at=None, message=''):
    return dict(status=status, checked_at=checked_at, message=message, scope=scope)


def reset_connection(record, scope):
    record.update(checked_at=None, connection=connection(scope))
    record.pop('_check_id', None)


def safe_check_message(error, key):
    message = str(error)
    if not message or len(message) > 300 or not message.isprintable() or key in message:
        return '연결 확인에 실패했습니다. API 키와 조회 권한을 확인하세요.'
    return message


class SettingsError(Exception):
    """Safe display text: never includes credentials or raw upstream responses."""


def _crypt(data, decrypt=False):
    if os.name != 'nt': raise SettingsError('API 키 암호화 저장은 Windows에서 지원합니다.')
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    source_buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    dll = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = dll.CryptUnprotectData if decrypt else dll.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    # CRYPTPROTECT_UI_FORBIDDEN; no machine-wide flag, so credentials bind to this user.
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise SettingsError('암호화된 AI 설정을 처리하지 못했습니다. 저장한 Windows 계정을 확인하세요.')
    try: return ctypes.string_at(output.data, output.size)
    finally: kernel.LocalFree(ctypes.cast(output.data, ctypes.c_void_p))


def protect(data): return _crypt(data)
def unprotect(data): return _crypt(data, decrypt=True)


def initial():
    return dict(version=0, provider='openai', tools={
                    'tavily': dict(key='', checked_at=None, connection=connection('usage')),
                    'dart': dict(key='', enabled=False, checked_at=None, connection=connection('company'))},
                profiles={p: dict(key='', model='', models=[], checked_at=None, connection=connection('models'))
                                                        for p in PROVIDERS})


class AISettings:
    def __init__(self, path, fetch_models=None):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.check_lock = threading.Lock()
        self.active_check_id = None
        self.fetch_models = fetch_models

    def _read(self):
        if not self.path.exists(): return initial()
        try:
            data = self.path.read_bytes()
            if not data.startswith(b'DPAPI1:'): raise ValueError()
            state = json.loads(unprotect(base64.b64decode(data[7:], validate=True)))
            if (type(state['version']) is not int or state['provider'] not in PROVIDERS or
                    set(state['profiles']) != set(PROVIDERS)): raise ValueError()
            for profile in state['profiles'].values():
                if not isinstance(profile['key'], str) or not isinstance(profile['model'], str): raise ValueError()
                if not isinstance(profile['models'], list): raise ValueError()
            # Older encrypted files have model profiles only; migrate in memory without losing them.
            state.setdefault('tools', {'tavily': {'key': ''}})
            state['tools'].setdefault('dart', {'key':'', 'enabled':False, 'checked_at':None})
            if not isinstance(state['tools']['tavily']['key'], str): raise ValueError()
            if not isinstance(state['tools']['dart']['key'],str) or type(state['tools']['dart']['enabled']) is not bool: raise ValueError()
            for name, record in {**state['profiles'], **state['tools']}.items():
                scope = SCOPES[name]
                record.setdefault('checked_at', None)
                if 'connection' not in record:
                    checked = record['checked_at'] if record['key'] else None
                    record['connection'] = connection(scope, 'success' if checked else 'unverified', checked,
                                                       SUCCESS_MESSAGES[scope] if checked else '')
                result = record['connection']
                if (not isinstance(result, dict) or result.get('status') not in ('unverified', 'checking', 'success', 'error')
                        or result.get('scope') != scope or not isinstance(result.get('message'), str)
                        or (result.get('checked_at') is not None and not isinstance(result['checked_at'], str))):
                    raise ValueError()
                # An interrupted process must not leave a permanent in-progress badge.
                if result['status'] == 'checking' and (not self.active_check_id or record.get('_check_id') != self.active_check_id):
                    reset_connection(record, scope)
                    record['connection']['message'] = '이전 연결 확인이 중단되었습니다. 다시 확인하세요.'
            return state
        except (OSError, ValueError, TypeError, KeyError, SettingsError):
            raise SettingsError('AI 설정을 읽지 못했습니다. 저장한 Windows 계정과 설정 파일을 확인하세요.') from None

    def _write(self, state):
        temporary = None
        try:
            data = b'DPAPI1:' + base64.b64encode(protect(json.dumps(state, ensure_ascii=False).encode('utf-8')))
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix='.ai-settings-', suffix='.tmp', delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(self.path)
        except OSError:
            raise SettingsError('AI 설정을 저장하지 못했습니다. 설정 폴더의 쓰기 권한을 확인하세요.') from None
        finally:
            if temporary and temporary.exists(): temporary.unlink(missing_ok=True)

    def _version(self, state, version):
        if state['version'] != version: raise SettingsError('AI 설정이 변경되었습니다. 설정을 다시 불러온 뒤 진행하세요.')

    def snapshot(self):
        with self.lock:
            state = self._read()
            return dict(version=state['version'], provider=state['provider'], profiles={
                name: dict(model=p['model'], has_key=bool(p['key']), models=p['models'], checked_at=p['checked_at'], connection=p['connection'])
                for name,p in state['profiles'].items()},
                tools={name: dict(has_key=bool(tool['key']), checked_at=tool['checked_at'], connection=tool['connection'],
                                 **({'enabled':tool['enabled']} if name == 'dart' else {}))
                       for name, tool in state['tools'].items()})

    def save_dart(self, key, enabled, version):
        if type(enabled) is not bool: raise SettingsError('DART 분석 포함 설정을 확인하세요.')
        if key is not None:
            key=key.strip()
            if key and not re.fullmatch(r'[A-Za-z0-9]{40}',key): raise SettingsError('DART 인증키는 영문·숫자 40자리로 입력하세요.')
        with self.lock:
            state=self._read()
            self._version(state,version)
            tool=state['tools']['dart']
            if key and key!=tool['key']:
                tool['key'] = key
                reset_connection(tool, 'company')
            if enabled and not tool['key']: raise SettingsError('DART 키를 먼저 입력하세요.')
            tool['enabled']=enabled
            state['version']+=1
            self._write(state)
            return self.snapshot()

    def delete_dart(self, version):
        with self.lock:
            state=self._read()
            self._version(state,version)
            state['tools']['dart']=dict(key='',enabled=False,checked_at=None,connection=connection('company'))
            state['version']+=1
            self._write(state)
            return self.snapshot()

    def dart_credentials(self):
        with self.lock:
            state=self._read()
            tool=state['tools']['dart']
            if not tool['enabled']: return None
            if not tool['key']: raise SettingsError('DART 키를 먼저 저장하세요.')
            return dict(version=state['version'],key=tool['key'])

    def check_dart(self, version):
        from .dart_client import check_key, DartError
        return self._check_connection('dart', version, check_key, (DartError, SettingsError))

    def check_tavily(self, version):
        from .connection_check import check_tavily, ConnectionCheckError
        return self._check_connection('tavily', version, check_tavily, (ConnectionCheckError, SettingsError))

    def save_tavily(self, key, version):
        if key is not None:
            key = key.strip()
            if key and not re.fullmatch(r'tvly-[A-Za-z0-9_-]{15,507}', key):
                raise SettingsError('Tavily API 키 형식을 확인하세요. tvly-로 시작하는 키를 입력하세요.')
        with self.lock:
            state = self._read()
            self._version(state, version)
            if key and key != state['tools']['tavily']['key']:
                state['tools']['tavily']['key'] = key
                reset_connection(state['tools']['tavily'], 'usage')
            state['version'] += 1
            self._write(state)
            return self.snapshot()

    def delete_tavily(self, version):
        with self.lock:
            state = self._read()
            self._version(state, version)
            state['tools']['tavily']['key'] = ''
            reset_connection(state['tools']['tavily'], 'usage')
            state['version'] += 1
            self._write(state)
            return self.snapshot()

    def tavily_credentials(self):
        """Server-only; never return a search key through the public API."""
        with self.lock:
            state = self._read()
            key = state['tools']['tavily']['key']
            if not key: raise SettingsError('웹 검색 설정에서 Tavily API 키를 먼저 저장하세요.')
            return dict(version=state['version'], key=key)

    def credentials(self):
        """Server-only connection snapshot. Never serialize this through an API."""
        with self.lock:
            state = self._read()
            profile = state['profiles'][state['provider']]
            if not profile['key'] or not profile['model']:
                raise SettingsError('설정에서 AI API 키와 사용할 모델을 먼저 저장하세요.')
            return dict(version=state['version'], provider=state['provider'],
                        model=profile['model'], key=profile['key'])

    def save(self, provider, model, key, version):
        if provider not in PROVIDERS: raise SettingsError('AI 제공사를 확인하세요.')
        model = model.strip()
        if model and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}', model):
            raise SettingsError('모델 ID 형식을 확인하세요.')
        if key is not None:
            key = key.strip()
            if key and (not 20 <= len(key) <= 512 or not re.fullmatch(r'[!-~]+', key)):
                raise SettingsError('API 키 형식을 확인하세요. 공백이나 줄바꿈 없이 입력하세요.')
        with self.lock:
            state = self._read()
            self._version(state, version)
            profile = state['profiles'][provider]
            # Never permit a credential accidentally pasted in the model field to reach the UI.
            if model.startswith(('sk-', 'AIza', 'AQ.', 'tvly-')) or (key and key in model) or (profile['key'] and profile['key'] in model):
                raise SettingsError('모델 ID 입력란에는 API 키를 입력할 수 없습니다.')
            if key and key != profile['key']:
                profile.update(key=key, models=[])
                reset_connection(profile, 'models')
            profile['model'] = model
            state.update(provider=provider, version=state['version']+1)
            self._write(state)
            return self.snapshot()

    def delete(self, provider, version):
        with self.lock:
            state = self._read()
            self._version(state, version)
            if provider not in PROVIDERS: raise SettingsError('AI 제공사를 확인하세요.')
            state['profiles'][provider].update(key='', models=[], checked_at=None)
            reset_connection(state['profiles'][provider], 'models')
            state['version'] += 1
            self._write(state)
            return self.snapshot()

    def import_openai(self, source, version):
        try:
            if Path(source).stat().st_size > 65536: raise ValueError()
            text = Path(source).read_text(encoding='utf-8-sig')
            keys = set(re.findall(r'(?<![\w-])sk-(?!ant-)[A-Za-z0-9_-]{20,}', text))
            if len(keys) != 1: raise ValueError()
        except (OSError, ValueError, UnicodeError):
            raise SettingsError('서버의 Api_Key.txt에서 OpenAI 키 하나를 찾지 못했습니다. 입력란에 직접 붙여넣으세요.') from None
        with self.lock:
            state = self._read()
            self._version(state, version)
            return self.save('openai', state['profiles']['openai']['model'], keys.pop(), version)

    def check(self, provider, version):
        from .providers import ProviderError, list_models
        if provider not in PROVIDERS: raise SettingsError('AI 제공사를 확인하세요.')
        fetch = self.fetch_models or list_models
        return self._check_connection(provider, version, lambda key: fetch(provider, key), (SettingsError, ProviderError))

    def _check_connection(self, name, version, fetch, errors):
        from .providers import ProviderError
        group = 'profiles' if name in PROVIDERS else 'tools'
        scope = SCOPES[name]
        if not self.check_lock.acquire(blocking=False): raise SettingsError('이미 연결을 확인하고 있습니다. 잠시 기다려주세요.')
        try:
            with self.lock:
                state = self._read()
                self._version(state, version)
                record = state[group][name]
                key = record['key']
                if not key: raise SettingsError('API 키를 먼저 저장하세요.')
                self.active_check_id = uuid4().hex
                record.update(checked_at=None, _check_id=self.active_check_id,
                              connection=connection(scope, 'checking', datetime.now(timezone.utc).isoformat(), '연결을 확인하고 있습니다.'))
                if group == 'profiles': record['models'] = []
                state['version'] += 1
                check_version = state['version']
                self._write(state)
            failure, result = None, None
            try: result = fetch(key)
            except errors as exc:
                message = safe_check_message(exc, key)
                failure = ProviderError(message) if isinstance(exc, ProviderError) else SettingsError(message)
            with self.lock:
                state = self._read()
                record = state[group][name]
                same_attempt = record.get('_check_id') == self.active_check_id and record['key'] == key
                if state['version'] != check_version and same_attempt:
                    reset_connection(record, scope)
                    record['connection']['message'] = '설정이 변경되어 연결 확인 결과를 적용하지 않았습니다.'
                    state['version'] += 1
                    self._write(state)
                self._version(state, check_version)
                if not same_attempt: raise SettingsError('AI 설정이 변경되었습니다. 연결을 다시 확인하세요.')
                checked_at = datetime.now(timezone.utc).isoformat()
                record.update(checked_at=None if failure else checked_at,
                              connection=connection(scope, 'error' if failure else 'success', checked_at,
                                                    str(failure) if failure else SUCCESS_MESSAGES[scope]))
                record.pop('_check_id', None)
                if group == 'profiles' and not failure: record['models'] = result
                state['version'] += 1
                self._write(state)
                if failure: raise failure
                return self.snapshot()
        finally:
            self.active_check_id = None
            self.check_lock.release()
