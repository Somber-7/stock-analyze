import unittest

from backend.ai.order_plan import build_order_plan


def decision(code, current, target, price=100, **extra):
    return dict(code=code, name=code, current_quantity=current, target_quantity=target,
                reference_price=price, assessment='supported', **extra)


class OrderPlanTests(unittest.TestCase):
    def test_shared_cash_is_counted_once_and_sales_do_not_fund_buys(self):
        rows = [decision('000001', 0, 8), decision('000002', 0, 7), decision('000003', 20, 0)]
        plan = build_order_plan(rows, dict(available_cash=1000, total_assets=4000))
        self.assertEqual(plan['buy_amount'], 1500)
        self.assertEqual(plan['sell_amount'], 2000)
        self.assertEqual(plan['cash_after_buys'], -500)
        self.assertEqual(plan['shortfall'], 500)
        self.assertEqual(plan['funding_status'], 'shortfall')
        self.assertEqual(plan['rows'][0]['target_weight_pct'], 20)

    def test_unknown_cash_does_not_fall_back_to_cma_or_capacities(self):
        plan = build_order_plan([decision('000001', 0, 8, buy_capacity=dict(amount=5000, quantity=50))],
                                dict(cma_balance=9000, cash=9000, available_cash=None))
        self.assertIsNone(plan['cash_after_buys'])
        self.assertIsNone(plan['shortfall'])
        self.assertEqual(plan['funding_status'], 'unverified')
        self.assertIsNone(plan['rows'][0]['target_weight_pct'])

    def test_capacities_and_missing_prices_do_not_claim_readiness(self):
        plan = build_order_plan([decision('000001', 0, 10, buy_capacity=dict(quantity=9, amount=2000)),
                                decision('000002', 0, 10, price=None)], dict(available_cash=9000))
        self.assertEqual(plan['rows'][0]['capacity_status'], 'exceeded')
        self.assertEqual(plan['rows'][1]['capacity_status'], 'unverified')
        self.assertIsNone(plan['buy_amount'])
        self.assertEqual(plan['funding_status'], 'unverified')

    def test_hold_defer_and_legacy_decisions_are_not_orders(self):
        deferred = decision('000002', 0, 10); deferred['assessment'] = 'defer'
        legacy = decision('000003', 0, 10); legacy.pop('assessment')
        plan = build_order_plan([decision('000001', 4, 4), deferred, legacy], dict(available_cash=0))
        self.assertEqual(plan['rows'], [])
        self.assertEqual(plan['buy_amount'], 0)
        self.assertEqual(plan['funding_status'], 'no_buys')

    def test_zero_and_invalid_cash_are_distinct(self):
        rows = [decision('000001', 0, 1)]
        self.assertEqual(build_order_plan(rows, dict(available_cash=0))['shortfall'], 100)
        for value in (float('nan'), float('inf'), -1, True):
            self.assertIsNone(build_order_plan(rows, dict(available_cash=value))['available_cash'])
