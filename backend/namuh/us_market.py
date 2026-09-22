"""A small, read-only US reference list for domestic stock investors."""
import math
import threading
import time
from datetime import datetime

from .client import NamuhError, get_client, number

INSTRUMENTS = {
    'DJI': ('다우 산업지수', '지수'),
    'SPY': ('S&P 500 참고', 'ETF'),
    'QQQ': ('나스닥 100 참고', 'ETF'),
    'SOXX': ('미국 반도체 참고', 'ETF'),
    'NVDA': ('엔비디아', '주식'),
    'AMD': ('AMD', '주식'),
    'MU': ('마이크론', '주식'),
}
_cache = {}
_locks = {code: threading.Lock() for code in INSTRUMENTS}


def get_quote(code, *, client=None):
    if code not in INSTRUMENTS:
        raise ValueError('Unsupported reference symbol')
    with _locks[code]:
        cached = _cache.get(code)
        if cached and time.monotonic() - cached[0] < 60:
            return dict(cached[1])
        client = client or get_client()
        if code == 'DJI':
            data, _ = client.post('/gbstock/quote/v1/symbolIndexFxPeriod', {'Input_0': {
                'iem_cd': '.DJI', 'end_dt': datetime.now().strftime('%Y%m%d'),
                'array_cnt': '2', 'maxavg': '', 'gubun': '1', 'xtick': '001',
                'today_cls': '0', 'scale_change': '0'}})
            output = data.get('Output_0', {})
            fields = ('ovrs_prpr', 'prdy_vrss', 'prdy_ctrt', 'prdy_vrss_sign', 'qry_date', 'qry_time')
        else:
            data, _ = client.post('/gbstock/quote/v1/current', {'Input_0': {'iem_cd': code}})
            output = data.get('Output_0', {})
            fields = ('trdprc', 'netchng', 'pctchng', 'netchng_cls', 'trade_date', 'quote_time')
        try:
            if any(output.get(field) is None or str(output.get(field)).strip() == '' for field in fields[:3]):
                raise ValueError('Missing quote field')
            price, change, rate = [number(output.get(field)) for field in fields[:3]]
            if price <= 0 or not all(math.isfinite(n) for n in (price, change, rate)):
                raise ValueError('Invalid quote')
        except (ValueError, TypeError, AttributeError):
            raise NamuhError('미국 참고 시세가 제공되지 않았습니다. 잠시 후 다시 조회해주세요.') from None
        if str(output.get(fields[3])) == '5':
            change, rate = -abs(change), -abs(rate)
        name, kind = INSTRUMENTS[code]
        result = {'code': code, 'name': name, 'kind': kind,
                  'price': price, 'change': change, 'change_rate': rate,
                  'unit': 'pt' if code == 'DJI' else 'USD',
                  'data_date': str(output.get(fields[4]) or ''),
                  'data_time': str(output.get(fields[5]) or ''),
                  'fetched_at': datetime.now().isoformat()}
        _cache[code] = (time.monotonic(), result)
        return dict(result)
