from datetime import datetime, timezone

from .client import get_client, number


def _chart(code, period, count, *, client=None):
    client = client or get_client()
    intraday = period in ('1m', '5m')
    inputs = {'market_cd': 'KRX', 'iem_cd': code, 'array_cnt': str(count),
              'gubun': {'D': '1', 'W': '2', 'M': '3', '1m': '5', '5m': '5'}[period],
              'view_main_yn': 'Y', 'out1_scale_change': '0', 'out2_scale_change': '0',
              'fake_tick': '1', 'today_cls_code': '0'}
    if intraday:
        inputs['xtick'] = '1' if period == '1m' else '5'
    candles = {}
    for page in client.pages('/krstock/quote/v1/period', {'Input_0': inputs}):
        for item in page.get('Output_1', []):
            values = {target: number(item.get(source)) for target, source in (
                ('open', 'stck_oprc'), ('high', 'stck_hgpr'), ('low', 'stck_lwpr'),
                ('close', 'stck_prpr'), ('volume', 'vol'), ('trading_value', 'tr_pbmn'))}
            if any(values[k] <= 0 for k in ('open', 'high', 'low', 'close')):
                continue
            date = str(item['bsop_date'])
            if period == 'M' and len(date) == 6:
                date += '01'
            if intraday:
                # The live API includes a non-clock 999900 row.
                if str(item.get('bsop_time')) == '999900':
                    continue
                # lightweight-charts renders UTC: encode Korean wall time as UTC,
                # matching the existing chart component's time formatter.
                timestamp = datetime.strptime(date + str(item['bsop_time']), '%Y%m%d%H%M%S')
                chart_time = int(timestamp.replace(tzinfo=timezone.utc).timestamp())
            else:
                chart_time = datetime.strptime(date, '%Y%m%d').strftime('%Y-%m-%d')
            candles[chart_time] = {'time': chart_time, **values}
        if len(candles) >= count:
            break
    result = [candles[key] for key in sorted(candles)]
    if intraday:
        recent_days = sorted({c['time'] // 86400 for c in result})[-5:]
        result = [c for c in result if c['time'] // 86400 in recent_days]
    return result[-count:]


def get_daily_chart(stock_code, days=250, period='D', *, client=None):
    return _chart(stock_code, period, min(max(days, 1), 1000), client=client)


def get_minute_chart(stock_code, interval=1, *, client=None):
    return _chart(stock_code, f'{interval}m', 2000 if interval == 1 else 400, client=client)
