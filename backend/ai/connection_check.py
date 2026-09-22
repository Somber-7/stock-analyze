"""Read-only Tavily authentication check; never executes a paid search."""
import json
import math
import re
import time

import httpx


class ConnectionCheckError(Exception):
    """Safe display text without credentials or upstream response content."""


def check_tavily(key, *, http=None):
    """Verify usage-endpoint access only, without claiming search availability.

    Official contract: https://docs.tavily.com/documentation/api-reference/endpoint/usage
    Injected clients belong to the caller; production clients ignore environment proxies.
    """
    if not isinstance(key, str) or not re.fullmatch(r'tvly-[A-Za-z0-9_-]{15,507}', key):
        raise ConnectionCheckError('Tavily API 키 형식을 확인하세요.')
    if http is None:
        with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client:
            return check_tavily(key, http=client)
    deadline = time.monotonic() + 15
    try:
        with http.stream('GET', 'https://api.tavily.com/usage',
                         headers={'Authorization':'Bearer '+key, 'Accept':'application/json'},
                         timeout=10, follow_redirects=False) as response:
            if response.status_code in (401, 403):
                raise ConnectionCheckError('Tavily API 키와 사용량 조회 권한을 확인하세요.')
            if response.status_code == 429:
                raise ConnectionCheckError('Tavily 요청 한도에 도달했습니다. 잠시 후 다시 확인하세요.')
            if response.status_code != 200:
                raise ConnectionCheckError('Tavily 사용량 조회에 실패했습니다.')
            raw = bytearray()
            for chunk in response.iter_bytes():
                if time.monotonic() > deadline:
                    raise ConnectionCheckError('Tavily 연결 확인 제한 시간을 초과했습니다.')
                if len(raw) + len(chunk) > 65536:
                    raise ConnectionCheckError('Tavily 응답 크기가 허용 범위를 초과했습니다.')
                raw.extend(chunk)
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get('account'), dict): raise ValueError()
        usage = payload.get('key')
        if not isinstance(usage, dict): raise ValueError()
        for field in ('usage', 'limit'):
            if field not in usage: raise ValueError()
            value = usage[field]
            # Tavily may omit a numeric key limit with explicit null. This proves
            # usage-endpoint access, without inferring any available search quota.
            if field == 'limit' and value is None: continue
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0: raise ValueError()
    except httpx.HTTPError:
        raise ConnectionCheckError('Tavily 서버에 연결하지 못했습니다. 네트워크를 확인하세요.') from None
    except (ValueError, TypeError, UnicodeError, OverflowError):
        raise ConnectionCheckError('Tavily 사용량 응답 형식을 확인하지 못했습니다.') from None
