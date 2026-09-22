from .client import NamuhError, get_client, number
from .portfolio import optional_number


def get_current_price(stock_code, *, client=None):
    client = client or get_client()
    data, _ = client.post('/krstock/quote/v1/currentPrice', {
        'Input_0': {'market_cd': 'KRX', 'iem_cd': stock_code}})
    output = data.get('Output_0', {})
    if not output or number(output.get('stck_prpr')) <= 0:
        raise NamuhError('조회 가능한 종목 시세가 없습니다.')
    change = number(output.get('prdy_vrss'))
    rate = optional_number(output.get('prdy_ctrt'))
    sign = str(output.get('prdy_vrss_sign') or '').strip()
    if sign in ('4', '5', '8', '9'):
        change, rate = -abs(change), -abs(rate) if rate is not None else None
    elif not sign and number(output.get('stck_prdy_clpr')) > 0:
        # Some live responses omit the sign and send absolute change/rate.
        difference = number(output['stck_prpr']) - number(output['stck_prdy_clpr'])
        direction = -1 if difference < 0 else 1 if difference > 0 else 0
        change, rate = direction * abs(change), direction * abs(rate) if rate is not None else None
    return {
        'code': stock_code, 'name': output.get('iem_nm', ''),
        'price': number(output.get('stck_prpr')), 'change': change, 'change_rate': rate,
        'volume': number(output.get('acml_vol')), 'high': number(output.get('stck_hgpr')),
        'low': number(output.get('stck_lwpr')), 'open': number(output.get('stck_oprc')),
        'w52_high': number(output.get('w52_hgpr')), 'w52_low': number(output.get('w52_lwpr')),
        'market_cap': number(output.get('hts_avls')),
        'per': output.get('per', ''), 'pbr': output.get('pbr', ''), 'eps': output.get('eps', '')}
