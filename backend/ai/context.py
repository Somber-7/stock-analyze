"""Only allowlisted NAMUH fields enter model inputs; credentials/accounts never do."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import re

from backend.namuh.chart import get_daily_chart
from backend.namuh.investors import get_investors
from backend.namuh.market import get_current_price
from backend.namuh.stocks import get_snapshot
from backend.namuh.us_market import get_quote
from backend.namuh.orders import korea_today
from backend.namuh.portfolio import optional_number
from backend.namuh.client import NamuhError
from .metrics import calculate_metrics
from .quality import HISTORY_BARS, prepare_daily


def stock_symbols():
    return [{'code': s['code'], 'name': s['name']} for s in get_snapshot()['stocks']]


def trading_day_active(code):
    bars = get_daily_chart(code, days=1)
    return bool(bars and bars[-1]['time'].replace('-', '') == korea_today() and bars[-1]['volume'] > 0)


def portfolio_snapshot(trading):
    state = trading.snapshot()
    if state['mode'] == 'paper':
        paper = trading.paper.snapshot()
        holdings = [dict(code=p['code'], quantity=p['quantity'], avg_price=p['average_price'])
                    for p in paper['positions']]
        available_cash = paper['available_cash']
        deposit_cash = paper.get('cash', available_cash)
        # Unpriced positions are not valued at their cost basis.
        quotes = paper.get('quotes', {})
        for row in holdings:
            price = optional_number(quotes.get(row['code'], {}).get('price'))
            row['eval_amount'] = row['quantity'] * price if price is not None and price > 0 else None
        total_assets = deposit_cash + sum(p['eval_amount'] for p in holdings) if all(p['eval_amount'] is not None for p in holdings) else None
        net_assets = total_assets
    else:
        if not state['account']:
            raise ValueError('설정에서 분석할 계좌를 선택하세요.')
        balance = trading.gateway.balance(state['account'])
        holdings = [{key: p[key] for key in ('code', 'name', 'quantity', 'avg_price', 'current_price', 'profit_rate', 'eval_amount')
                     if key in p} for p in balance['holdings']]
        summary = balance['summary']
        deposit_cash = optional_number(summary.get('cash'))
        available_cash = optional_number(summary.get('cash_orderable_100'))
        total_assets = optional_number(summary.get('total_assets'))
        net_assets = optional_number(summary.get('net_assets'))
    names = {s['code']: s['name'] for s in stock_symbols()}
    selected = [row for row in holdings if re.fullmatch(r'[0-9A-Z]{6}', row['code']) and row['code'] in names]
    excluded_count = len(holdings) - len(selected)
    non_stocks = [p for p in holdings if p not in selected]
    # This account's NHKRCMA product is its CMA cash management balance.
    cma = [p for p in non_stocks if p['code'].startswith('NHKRCMA')]
    cash_management_assets = [dict(name=p.get('name', 'CMA'), eval_amount=optional_number(p.get('eval_amount'))) for p in cma]
    other_assets = [dict(name=p.get('name', '기타 보유 항목'), eval_amount=optional_number(p.get('eval_amount'))) for p in non_stocks if p not in cma]
    cma_balance = sum(p['eval_amount'] for p in cash_management_assets) if all(p['eval_amount'] is not None for p in cash_management_assets) else None
    cash_balance = deposit_cash + cma_balance if deposit_cash is not None and cma_balance is not None else None
    holdings = selected
    for row in holdings:
        row['name'] = names.get(row['code'], row.get('name', row['code']))
    return dict(deposit_cash=deposit_cash, available_cash=available_cash,
                cash_management_assets=cash_management_assets, cma_balance=cma_balance, cash_balance=cash_balance,
                total_assets=total_assets, net_assets=net_assets, other_assets=other_assets,
                holdings=holdings, excluded_holdings_count=excluded_count,
                cash_source='모의 잔고의 미예약 현금' if state['mode'] == 'paper' else '나무 잔고 100% 주문가능금액 (orr_pbl_amt4)',
                assets_source='모의 계좌' if state['mode'] == 'paper' else '나무 국내주식 잔고 API 조회 계좌',
                fetched_at=datetime.now(timezone.utc).isoformat())


def load_context(config, trading):
    names = {s['code']: s['name'] for s in stock_symbols()}
    if any(code not in names for code in config['codes']):
        raise ValueError('나무 종목 목록에서 선택 종목을 확인할 수 없습니다. 종목을 다시 선택하세요.')
    fetched_at = datetime.now(timezone.utc).isoformat()
    trading_state = trading.snapshot()
    portfolio = portfolio_snapshot(trading)
    history_bars = HISTORY_BARS[config.get('investment_horizon', 'unspecified')]

    def collect(code):
        quote = get_current_price(code)
        stock = dict(code=code, name=names[code], quote=quote, daily=[], investors=None)
        stock['quote_fetched_at'] = datetime.now(timezone.utc).isoformat()
        notes = []
        # One extra baseline plus a possible unfinished current-session candle.
        try: stock['daily'] = get_daily_chart(code, days=history_bars + 2)
        except Exception: notes.append(f'{names[code]} 일봉을 조회하지 못했습니다.')
        stock['raw_daily'] = stock['daily']
        stock['daily'], stock['data_quality'] = prepare_daily(stock['daily'], history_bars + 1, datetime.fromisoformat(fetched_at))
        notes.extend(f'{names[code]}: {issue}' for issue in stock['data_quality']['issues'])
        try: stock['investors'] = get_investors(code)
        except Exception: notes.append(f'{names[code]} 투자자 수급을 조회하지 못했습니다.')
        capacity = dict(amount=None, quantity=None, reference_price=quote['price'], fetched_at=None, diagnostic=None)
        try:
            if trading_state['mode'] == 'paper':
                amount = max(0, portfolio['available_cash'])
                quantity = int(amount // quote['price'])
            else:
                value = trading.gateway.capacity(trading_state['account'], code, 'buy', quote['price'])
                amount, quantity = optional_number(value.get('amount')), optional_number(value.get('quantity'))
                if amount is None or quantity is None or amount < 0 or quantity < 0 or int(quantity) != quantity:
                    raise ValueError()
            capacity.update(amount=amount, quantity=quantity, fetched_at=datetime.now(timezone.utc).isoformat())
        except Exception as exc:
            capacity['diagnostic'] = exc.diagnostic if isinstance(exc,NamuhError) else dict(stage='fields' if isinstance(exc,ValueError) else 'unexpected',code=None,http_status=None)
            notes.append(f'{names[code]} 현금 주문가능금액·수량을 확인하지 못했습니다. 매수 실행 가능 여부는 미확인이며 투자 판단 및 매도 필요성과 구분하세요.')
        stock['buy_capacity'] = capacity
        stock['metrics'] = calculate_metrics(stock['daily'], stock['investors'])
        return stock, notes

    with ThreadPoolExecutor(max_workers=3) as pool:
        collected = list(pool.map(collect, config['codes']))
    warnings = ['호가 데이터는 포함되지 않습니다.']
    if not config.get('include_web', False): warnings.append('웹 검색을 사용하지 않아 뉴스·공시 자료는 포함되지 않습니다.')
    if config['include_us']:
        warnings.append('미국 시세는 참고 자료이며 종목별 거래일과 조회 시점이 다를 수 있습니다.')
    if portfolio['cash_management_assets']:
        warnings.append('CMA 발행어음은 계좌의 현금성 운용 잔액으로 반영했습니다. API 예수금(dca)과 구분하며, 총자산 및 주문가능금액에 중복 가산하지 않습니다. 실제 매수 여력은 주문가능금액을 기준으로 판단하세요.')
    if portfolio['other_assets']:
        warnings.append('기타 보유 자산은 이름·평가액을 제공합니다. 주식 매매 대상에서 제외하며 주문가능금액에 더하지 않습니다.')
    if portfolio['available_cash'] is None:
        warnings.append('계좌의 100% 주문가능금액을 확인하지 못했습니다. 예수금과 동일하다고 가정하거나 미확인 금액을 0원으로 해석하지 마세요.')
    if portfolio['total_assets'] is None:
        warnings.append('조회 계좌의 총자산이 미확인이라 계좌 총자산 대비 비중을 계산할 수 없습니다.')
    warnings.append('주문가능금액은 같은 계좌 자금에 대한 조회이며 종목별 금액을 합산할 수 없습니다. 매도 필요성은 매수 여력과 별도로 판단하세요.')
    stocks = []
    for stock, notes in collected:
        positions = [p for p in portfolio['holdings'] if p['code'] == stock['code']]
        values = [optional_number(p.get('eval_amount')) for p in positions]
        held_value = sum(values) if all(v is not None for v in values) else None
        stock['holding_eval_amount'] = held_value
        stock['account_weight_pct'] = round(held_value / portfolio['total_assets'] * 100, 4) if held_value is not None and portfolio['total_assets'] is not None and portfolio['total_assets'] > 0 else None
        stock['price_basis'] = dict(balance_price=optional_number(positions[0].get('current_price')) if len(positions)==1 else None,
            balance_at=portfolio['fetched_at'], quote_price=stock['quote']['price'], quote_at=stock['quote_fetched_at'],
            daily_close=stock['daily'][-1]['close'] if stock['daily'] else None,
            daily_date=stock['daily'][-1]['time'] if stock['daily'] else None,
            valuation_basis='잔고 평가액 / 같은 잔고 응답의 계좌 총자산', quote_trade_time=None)
        stocks.append(stock)
        warnings.extend(notes)
    references = []
    if config['include_us']:
        for code in ('SPY', 'QQQ', 'SOXX', 'NVDA'):
            try: references.append(get_quote(code))
            except Exception: warnings.append(f'{code} 미국 참고 시세를 조회하지 못했습니다.')
    benchmark = dict(code='069500', name='KODEX 200', daily=[], status='unavailable')
    try:
        raw = get_daily_chart('069500', days=history_bars + 2)
        bars, quality = prepare_daily(raw, history_bars + 1, datetime.fromisoformat(fetched_at))
        benchmark.update(daily=bars, data_quality=quality, status='ready' if bars and not quality['requires_defer'] else 'unavailable')
    except Exception: pass
    return dict(fetched_at=fetched_at, portfolio=portfolio, stocks=stocks, benchmark=benchmark,
                us_market=references, warnings=warnings, investment_horizon=config.get('investment_horizon', 'unspecified'))
