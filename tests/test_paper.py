import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from backend.trading.paper import PaperEngine, PaperError


class PaperTests(unittest.TestCase):
    def test_alphanumeric_stock_order_and_rule_preserve_code(self):
        order = self.engine.submit(client_id='chaevi', code='0011T0', side='buy', quantity=1, limit_price=10000)
        self.assertEqual(order['code'], '0011T0')
        rule = self.engine.add_rule(client_id='chaevi-rule', code='0011T0', side='buy', quantity=1,
                                   limit_price=10000, comparison='lte', threshold=1)
        self.assertEqual(rule['code'], '0011T0')
        self.engine.start()
        self.engine.tick()
        self.assertEqual(self.engine.snapshot()['positions'][0]['code'], '0011T0')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'paper.sqlite3'
        self.price = 9000
        self.engine = PaperEngine(self.path, lambda code: {'price': self.price, 'name': '테스트'})

    def order(self, key='a', **kw):
        return self.engine.submit(client_id=key, code='005930', side='buy', quantity=20,
                                  limit_price=10000, **kw)

    def test_reserve_partial_fill_cancel_and_realized_profit(self):
        order = self.order()
        self.assertEqual(self.engine.snapshot()['available_cash'], 9800000)
        self.engine.start()
        self.engine.tick()
        s = self.engine.snapshot()
        self.assertEqual(s['orders'][0]['status'], 'partial')
        self.assertEqual(s['cash'], 9910000)
        self.assertEqual(s['available_cash'], 9810000)
        self.engine.cancel(order['id'])
        self.assertEqual(self.engine.snapshot()['available_cash'], 9910000)
        self.engine.submit(client_id='sell', code='005930', side='sell', quantity=10, limit_price=9500)
        self.price = 9600
        self.engine.tick()
        s = self.engine.snapshot()
        self.assertEqual(s['cash'], 10006000)
        self.assertEqual(s['realized_pnl'], 6000)
        self.assertEqual(s['positions'], [])

    def test_same_request_is_atomic_and_conflicting_reuse_rejected(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            orders = list(pool.map(lambda _: self.order(), range(8)))
        self.assertEqual(len({o['id'] for o in orders}), 1)
        with self.assertRaises(PaperError):
            self.engine.submit(client_id='a', code='005930', side='sell', quantity=20, limit_price=10000)
        self.assertEqual(len(self.engine.snapshot()['orders']), 1)

    def test_orders_above_old_amount_limits_still_reserve_cash_and_shares(self):
        large = self.engine.submit(client_id='large', code='005930', side='buy', quantity=600, limit_price=10000)
        self.engine.submit(client_id='remaining-cash', code='005930', side='buy', quantity=400, limit_price=10000)
        self.assertEqual(self.engine.snapshot()['available_cash'], 0)
        with self.assertRaises(PaperError):
            self.order()
        self.engine.cancel(large['id'])
        self.assertEqual(self.engine.snapshot()['available_cash'], 6000000)
        self.engine.start()
        self.engine.tick()
        self.engine.submit(client_id='s1', code='005930', side='sell', quantity=10, limit_price=20000)
        with self.assertRaises(PaperError):
            self.engine.submit(client_id='s2', code='005930', side='sell', quantity=1, limit_price=20000)

    def test_modify_preserves_fills_and_revalidates_reservation(self):
        o = self.order()
        self.engine.start()
        self.engine.tick()
        self.engine.modify(o['id'], 8000)
        self.engine.tick()
        s = self.engine.snapshot()
        self.assertEqual(s['orders'][0]['filled'], 10)
        self.assertEqual(s['reserved_cash'], 80000)
        with self.assertRaises(PaperError):
            self.engine.modify(o['id'], 1000001)
        self.assertEqual(self.engine.snapshot()['reserved_cash'], 80000)

    def test_restart_preserves_book_but_stops_execution(self):
        self.order()
        self.engine.start()
        self.engine.tick()
        restored = PaperEngine(self.path, lambda _: {'price': 1})
        restored.tick()
        s = restored.snapshot()
        self.assertFalse(s['running'])
        self.assertEqual(s['orders'][0]['filled'], 10)
        self.assertEqual(s['cash'], 9910000)

    def test_rule_fires_once_and_rejected_rule_does_not_retry(self):
        self.engine.add_rule(client_id='r', code='005930', side='buy', quantity=2,
                             limit_price=10000, comparison='lte', threshold=9500)
        self.engine.add_rule(client_id='s', code='000660', side='sell', quantity=2,
                             limit_price=10000, comparison='lte', threshold=9500)
        self.engine.start()
        self.engine.tick()
        self.engine.tick()
        s = self.engine.snapshot()
        self.assertEqual(len(s['orders']), 1)
        self.assertEqual({r['status'] for r in s['rules']}, {'fired', 'rejected'})
        self.assertEqual(s['positions'][0]['quantity'], 2)

    def test_quote_failure_does_not_fill_and_recovery_works(self):
        self.order()
        self.engine.start()
        self.engine.quote = lambda _: (_ for _ in ()).throw(RuntimeError('private detail'))
        self.engine.tick()
        s = self.engine.snapshot()
        self.assertEqual(s['orders'][0]['filled'], 0)
        self.assertTrue(s['quotes']['005930']['error'])
        self.assertNotIn('private detail', str(s))
        self.engine.quote = lambda _: {'price': 9000}
        self.engine.tick()
        self.assertEqual(self.engine.snapshot()['orders'][0]['filled'], 10)

    def test_stop_during_quote_discards_inflight_result_and_emergency_cancels(self):
        self.order()
        self.engine.add_rule(client_id='r', code='005930', side='buy', quantity=1,
                             limit_price=10000, comparison='gte', threshold=1)
        self.engine.start()
        def delayed(_):
            self.engine.stop(emergency=True)
            self.engine.start()
            return {'price': 9000}
        self.engine.quote = delayed
        self.engine.tick()
        s = self.engine.snapshot()
        self.assertEqual(s['orders'][0]['status'], 'cancelled')
        self.assertEqual(s['rules'][0]['status'], 'cancelled')
        self.assertEqual(s['cash'], 10000000)

    def test_invalid_quote_never_changes_cash(self):
        self.order()
        self.engine.start()
        for value in [float('nan'), float('inf'), 0, -1, None, 1.5]:
            self.engine.quote = lambda _, v=value: {'price': v}
            self.engine.tick()
        self.assertEqual(self.engine.snapshot()['cash'], 10000000)

    def test_price_condition_and_limit_both_must_match(self):
        self.engine.add_rule(client_id='r', code='005930', side='buy', quantity=1,
                             limit_price=8500, comparison='lte', threshold=9500)
        self.engine.start()
        self.engine.tick()
        self.assertEqual(self.engine.snapshot()['orders'][0]['filled'], 0)
        self.price = 8000
        self.engine.tick()
        self.assertEqual(self.engine.snapshot()['orders'][0]['filled'], 1)

    def test_pending_items_remain_visible_after_many_completed_items(self):
        pending = self.order()
        armed = self.engine.add_rule(client_id='waiting', code='005930', side='buy', quantity=1,
                                     limit_price=10000, comparison='lte', threshold=1)
        for i in range(201):
            order = self.order(str(i))
            self.engine.cancel(order['id'])
            rule = self.engine.add_rule(client_id=str(i), code='005930', side='buy', quantity=1,
                                        limit_price=10000, comparison='lte', threshold=1)
            self.engine.cancel_rule(rule['id'])
        s = self.engine.snapshot()
        self.assertIn(pending['id'], [o['id'] for o in s['orders']])
        self.assertIn(armed['id'], [r['id'] for r in s['rules']])

    def test_manual_requests_cannot_impersonate_a_rule(self):
        with self.assertRaises(PaperError):
            self.order('rule:internal-id')
        self.assertEqual(self.engine.snapshot()['orders'], [])

    def test_emergency_rejects_older_start_and_order_requests_even_after_restart(self):
        version = self.engine.snapshot()['version']
        self.engine.stop(emergency=True)
        with self.assertRaises(PaperError):
            self.engine.start(expected_version=version)
        with self.assertRaises(PaperError):
            self.order(expected_version=version)
        restored = PaperEngine(self.path, lambda _: {'price': 9000})
        with self.assertRaises(PaperError):
            restored.start(expected_version=version)
        self.assertFalse(restored.snapshot()['running'])
        self.assertEqual(restored.snapshot()['orders'], [])


if __name__ == '__main__':
    unittest.main()
