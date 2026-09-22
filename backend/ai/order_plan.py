"""Analysis-time arithmetic only. This preview never authorizes an order."""
import math


def amount(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def build_order_plan(decisions, portfolio):
    cash = amount(portfolio.get('available_cash'))
    assets = amount(portfolio.get('total_assets'))
    rows = []
    for decision in decisions:
        if decision.get('assessment') != 'supported':
            continue
        current, target = decision['current_quantity'], decision['target_quantity']
        delta = target - current
        if not delta:
            continue
        price = amount(decision.get('reference_price'))
        price = price if price else None
        value = abs(delta) * price if price is not None else None
        capacity = decision.get('buy_capacity') or {}
        capacity_qty, capacity_amount = amount(capacity.get('quantity')), amount(capacity.get('amount'))
        capacity_status = 'not_applicable'
        if delta > 0:
            exceeded = ((capacity_qty is not None and delta > capacity_qty) or
                        (capacity_amount is not None and value is not None and value > capacity_amount))
            capacity_status = 'exceeded' if exceeded else 'within_snapshot' if (
                capacity_qty is not None and capacity_amount is not None and value is not None) else 'unverified'
        rows.append(dict(code=decision['code'], name=decision.get('name', decision['code']),
                         side='buy' if delta > 0 else 'sell', quantity=abs(delta),
                         current_quantity=current, target_quantity=target, reference_price=price,
                         estimated_amount=value, capacity_status=capacity_status,
                         target_weight_pct=round(target * price / assets * 100, 2) if assets and price else None))

    def total(side):
        values = [row['estimated_amount'] for row in rows if row['side'] == side]
        return sum(values) if all(value is not None for value in values) else None

    buys, sells = total('buy'), total('sell')
    remaining = cash - buys if cash is not None and buys is not None else None
    shortfall = max(0, -remaining) if remaining is not None else None
    funding = ('no_buys' if buys == 0 else 'unverified' if shortfall is None else
               'shortfall' if shortfall > 0 else 'within_snapshot')
    return dict(rows=rows, buy_amount=buys, sell_amount=sells, available_cash=cash,
                cash_after_buys=remaining, shortfall=shortfall, funding_status=funding,
                capacity_exceeded_count=sum(r['capacity_status'] == 'exceeded' for r in rows),
                capacity_unverified_count=sum(r['capacity_status'] == 'unverified' for r in rows))
