"""NAMUH investor quantities, without inventing an undocumented unit scale."""

import copy
import math
import re
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone

from .client import NamuhError, get_client

_cache = OrderedDict()
_lock = threading.Lock()
_FIELDS = {'personal': 'person', 'institutional': 'gigwan', 'foreign': 'invest'}


def _quantity(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(str(value).strip().replace(',', ''))
    except (ValueError, TypeError):
        return None
    if not math.isfinite(parsed):
        return None
    return int(parsed) if parsed.is_integer() else parsed


def get_investors(code, client=None):
    if not isinstance(code, str) or not re.fullmatch(r'[0-9A-Z]{6}', code):
        raise ValueError('국내주식 6자리 종목코드가 필요합니다.')
    client = client or get_client()
    key = (client, code)
    # Coalesce simultaneous callers and share the existing client's TPS limiter.
    with _lock:
        cached = _cache.get(key)
        if cached and time.monotonic() - cached[0] < 60:
            _cache.move_to_end(key)
            return copy.deepcopy(cached[1])
        data, _ = client.post('/krstock/quote/v1/currentInvestor', {
            'Input_0': {'market_cd': 'KRX', 'iem_cd': code, 'array_cnt': '20'}})
        source_rows = data.get('Output_0')
        if not isinstance(source_rows, list):
            raise NamuhError('나무증권 투자자별 수급 응답 형식이 올바르지 않습니다.')
        rows = {}
        has_unknown_alias = False
        invalid_dates = False
        for item in source_rows:
            if not isinstance(item, dict):
                raise NamuhError('나무증권 투자자별 수급 응답 형식이 올바르지 않습니다.')
            raw_date = str(item.get('bsop_date1', ''))
            try:
                if not re.fullmatch(r'[0-9]{8}', raw_date):
                    raise ValueError()
                date = datetime.strptime(raw_date, '%Y%m%d').strftime('%Y-%m-%d')
            except ValueError:
                invalid_dates = True
                continue
            # The reference sample contains undocumented *z10 aliases. Their scale
            # is not specified, so never silently substitute them for these fields.
            has_unknown_alias |= any(source + 'z10' in item for source in _FIELDS.values())
            row = {'date': date, **{target: _quantity(item.get(source))
                                   for target, source in _FIELDS.items()}}
            rows.setdefault(date, row)
        ordered = [rows[date] for date in sorted(rows, reverse=True)[:20]]
        summary = next((row for row in ordered
                        if any(row[field] is not None for field in _FIELDS)), None)
        notes = ['제공 수량을 변환 없이 표시합니다. API 문서에 수량 배율이 명시되어 있지 않습니다.',
                 '외국인은 외국인투자자 순매수량(invest)이며 지분 변동주식수와 다릅니다.']
        if has_unknown_alias:
            notes.append('일부 응답의 미확인 필드(z10)는 단위를 확인할 수 없어 미제공으로 표시합니다.')
        if invalid_dates:
            notes.append('거래일자를 확인할 수 없는 응답 행은 제외했습니다.')
        result = {'code': code, 'source': '나무증권 · KRX', 'unit': None,
                  'unit_label': '제공 수량 · 원본값',
                  'data_date': summary['date'] if summary else None,
                  'fetched_at': datetime.now(timezone.utc).isoformat(),
                  'summary': summary, 'rows': ordered, 'notes': notes}
        _cache[key] = (time.monotonic(), result)
        _cache.move_to_end(key)
        while len(_cache) > 128:
            _cache.popitem(last=False)
        return copy.deepcopy(result)
