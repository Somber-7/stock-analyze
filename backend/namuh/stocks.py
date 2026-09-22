"""Name search using only NAMUH's official domestic stock master."""
import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from backend.config import base_dir

MASTER_URL = 'https://www.nhplug.com/instruments/m_new_stock.mst'
STOCKS_FILE = Path(base_dir) / '.namuh_stocks.json'
_refresh_lock = threading.Lock()
_schedule_lock = threading.Lock()
_next_attempt = 0.0
_last_error = ''


def parse_master(content: bytes) -> list[dict]:
    # Official m_new_stock.h: 237 bytes including LF, CP949 name at [7:48].
    if not content or len(content) % 237:
        raise ValueError('Invalid NAMUH stock master record size')
    result = []
    for offset in range(0, len(content), 237):
        record = content[offset:offset + 237]
        if record[-1:] != b'\n':
            raise ValueError('Invalid NAMUH stock master record boundary')
        code = record[:6].decode('ascii').strip()
        name = record[7:48].decode('cp949').strip().lstrip('*#')
        if len(code) != 6 or not code.isalnum() or not name:
            raise ValueError('Invalid NAMUH stock master fields')
        result.append({'code': code, 'name': name,
                       'market': {'1': 'KOSPI', '4': 'KOSDAQ', 'A': 'ETN'}.get(chr(record[6]), ''),
                       'is_etf': record[6:7] == b'1' and record[165:166] == b'8',
                       'previous_close': int(record[152:159].strip() or b'0'),
                       'previous_market_cap': int(record[174:186].strip() or b'0')})
    return result


def refresh_stocks(*, client=None):
    global _last_error
    if not _refresh_lock.acquire(blocking=False):
        return
    try:
        if client is None:
            with httpx.Client(timeout=20) as http:
                response = http.get(MASTER_URL)
        else:
            response = client.get(MASTER_URL)
        response.raise_for_status()
        data = {'schema': 2, 'stocks': parse_master(response.content),
                'downloaded_at': datetime.now().isoformat(),
                'source_modified': response.headers.get('last-modified', '')}
        temporary = STOCKS_FILE.with_suffix('.tmp')
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        temporary.replace(STOCKS_FILE)
        _last_error = ''
    except (httpx.HTTPError, OSError, ValueError):
        _last_error = '나무 종목파일 조회에 실패했습니다. 잠시 후 자동으로 다시 시도합니다.'
        print('[namuh stocks] 종목 목록 갱신 실패. 기존 나무 자료를 유지합니다.')
    finally:
        _refresh_lock.release()


def _cache_needs_refresh():
    if not STOCKS_FILE.exists():
        return True
    modified = datetime.fromtimestamp(STOCKS_FILE.stat().st_mtime)
    now = datetime.now()
    return modified.date() != now.date() or now - modified > timedelta(hours=1)


def ensure_fresh(*, force=False):
    global _next_attempt
    with _schedule_lock:
        if time.monotonic() < _next_attempt:
            return
        if not (force or _cache_needs_refresh()):
            return
        _next_attempt = time.monotonic() + 60
        threading.Thread(target=refresh_stocks, daemon=True).start()


def search(q: str, limit: int = 10) -> list:
    ensure_fresh()
    if not q.strip() or not STOCKS_FILE.exists():
        return []
    try:
        stocks = json.loads(STOCKS_FILE.read_text(encoding='utf-8'))
        if isinstance(stocks, dict):
            stocks = stocks['stocks']
        q = q.strip().casefold()
        return [{'code': s['code'], 'name': s['name'].lstrip('*#')} for s in stocks
                if q in s['name'].casefold() or q in s['code'].casefold()][:limit]
    except (OSError, ValueError, KeyError, TypeError):
        ensure_fresh(force=True)
        return []


def get_snapshot():
    ensure_fresh()
    try:
        data = json.loads(STOCKS_FILE.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or data.get('schema') != 2 or not isinstance(data.get('stocks'), list):
            raise ValueError('Old stock cache needs refresh')
        return {**data, 'error': _last_error, 'loading': False, 'stale': _cache_needs_refresh()}
    except (OSError, ValueError, TypeError):
        ensure_fresh(force=True)
        return {'stocks': [], 'error': _last_error, 'loading': not bool(_last_error)}


def trading_names(snapshot):
    """Decorate display records from one local master read, without changing the book."""
    names = {s['code']: s['name'] for s in get_snapshot()['stocks']}
    result = dict(snapshot)
    for key in ('orders', 'rules', 'operations', 'positions'):
        if key in result:
            result[key] = [{**row, 'name': row.get('name') or names.get(row['code'], '')}
                           for row in result[key]]
    return result
