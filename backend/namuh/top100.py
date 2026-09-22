"""Previous market-cap ranking from the NAMUH master; quotes update separately."""
import threading
import time
from datetime import datetime

from .market import get_current_price
from .stocks import get_snapshot

_lock = threading.Lock()
_quotes = {}
_worker = None
_active_codes = ()
_last_viewed = 0.0
_next_cycle = 0.0
_completed = 0
_last_completed_at = ''


def _refresh_prices(codes):
    global _completed, _next_cycle, _last_completed_at
    failures = 0
    for code in codes:
        with _lock:
            if time.monotonic() - _last_viewed > 15 or codes != _active_codes:
                return
        try:
            quote = get_current_price(code)
            value = {key: quote[key] for key in ('price', 'change', 'change_rate', 'volume')}
            value.update(retrieved_at=datetime.now().isoformat(), error='')
            failures = 0
        except Exception:
            # Preserve the timestamp on a retained quote, never fabricate a new price.
            with _lock:
                value = dict(_quotes.get(code, {}))
            value['error'] = '현재가 조회 실패'
            failures += 1
        with _lock:
            _quotes[code] = value
            _completed += 1
        if failures >= 3:
            # Authentication/network outages must not trigger 100 failing requests.
            with _lock:
                for pending in codes[_completed:]:
                    previous = dict(_quotes.get(pending, {}))
                    previous['error'] = '연속 오류로 갱신 대기 · 다음 주기에 재시도'
                    _quotes[pending] = previous
                _next_cycle = time.monotonic() + 60
            return
        time.sleep(0.05)  # Yield between requests; the shared NAMUH client enforces TPS.
    with _lock:
        _last_completed_at = datetime.now().isoformat()
        _next_cycle = time.monotonic() + 60


def get_top100():
    global _worker, _active_codes, _last_viewed, _completed
    master = get_snapshot()
    candidates = [item for item in master['stocks']
                  if item.get('market') in ('KOSPI', 'KOSDAQ')
                  and not item.get('is_etf') and item.get('previous_market_cap', 0) > 0]
    ranked = sorted(candidates, key=lambda item: (-item['previous_market_cap'], item['code']))[:100]
    codes = tuple(item['code'] for item in ranked)
    with _lock:
        _active_codes = codes
        _last_viewed = time.monotonic()
        if codes and (_worker is None or not _worker.is_alive()) and time.monotonic() >= _next_cycle:
            _completed = 0
            _worker = threading.Thread(target=_refresh_prices, args=(codes,), daemon=True)
            _worker.start()
        rows = [{**item, 'rank': rank, 'quote': dict(_quotes[item['code']]) if item['code'] in _quotes else None}
                for rank, item in enumerate(ranked, 1)]
        return {'rows': rows, 'downloaded_at': master.get('downloaded_at', ''),
                'master_stale': master.get('stale', False),
                'loading': master.get('loading', False), 'error': master.get('error', ''),
                'refreshing': bool(_worker and _worker.is_alive()), 'completed': _completed,
                'last_completed_at': _last_completed_at,
                'next_refresh_seconds': max(0, int(_next_cycle - time.monotonic()))}
