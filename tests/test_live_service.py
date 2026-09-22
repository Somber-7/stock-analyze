import tempfile
import unittest
from pathlib import Path
from backend.namuh.client import NamuhError, NamuhRejected
from backend.trading.live import TradingService, TradingError
from backend.trading.paper import PaperEngine


class FakeBroker:
    def __init__(self):
        self.sent = []
        self.rows = []
        self.failure = None
        self.available = 50
    def accounts(self): return [{'id': '12345678', 'label': '****5678'}]
    def balance(self, account): return {'summary': {'cash': 1000000}, 'holdings': []}
    def capacity(self, account, code, side, price): return {'quantity': self.available, 'amount': 1000000}
    def history(self, account, day): return self.rows.copy()
    def quote(self, code): return {'price': 9000}
    def send(self, kind, account, **kwargs):
        guard = kwargs.pop('before_send', None)
        if guard: guard()
        self.sent.append((kind, account, kwargs))
        if self.failure: raise self.failure
        return {'broker_id': str(len(self.sent)), 'response_code': '00048'}


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.paper = PaperEngine(self.base/'paper.db', lambda _: {'price': 1})
        self.broker = FakeBroker()
        self.service = TradingService(self.base/'live.db', self.paper, self.broker)
        self.service.session_open = lambda: True
    def version(self): return self.service.snapshot()['version']
    def configure(self):
        self.service.configure(mode='live', account='12345678', expected_version=self.version())
        self.service.start(self.version())
    def order(self, key='a', **kwargs):
        return self.service.order(client_id=key, code='005930', side='buy', quantity=10,
                                  price=10000, expected_version=self.version(), **kwargs)

    def test_mode_switch_stops_paper_and_requires_explicit_live_start(self):
        self.paper.start()
        self.service.configure(mode='live', account='12345678', expected_version=self.version())
        self.assertFalse(self.paper.snapshot()['running'])
        with self.assertRaises(TradingError): self.order()
        self.assertEqual(self.broker.sent, [])
        self.service.start(self.version())
        self.assertEqual(self.order()['status'], 'accepted')

    def test_request_id_prevents_duplicate_and_daily_budget_is_persisted(self):
        self.configure()
        first = self.order()
        self.assertEqual(self.order()['id'], first['id'])
        self.assertEqual(self.order('b')['status'], 'accepted')
        self.assertEqual(len(self.broker.sent), 2)
        restored = TradingService(self.base/'live.db', self.paper, self.broker)
        self.assertFalse(restored.snapshot()['running'])
        self.assertEqual(restored.snapshot()['daily_used'], 200000)

    def test_legacy_amount_limits_are_removed_without_losing_history(self):
        self.configure()
        first = self.order()
        with self.service.change() as state:
            state.update(order_limit=1, daily_limit=1)
        restored = TradingService(self.base/'live.db', self.paper, self.broker)
        snapshot = restored.snapshot()
        self.assertNotIn('order_limit', snapshot)
        self.assertNotIn('daily_limit', snapshot)
        self.assertEqual(snapshot['operations'][0]['id'], first['id'])
        restored.start(snapshot['version'])
        result = restored.order(client_id='large', code='005930', side='buy', quantity=50,
                                price=200000, expected_version=snapshot['version'])
        self.assertEqual(result['status'], 'accepted')
        restored.add_rule(client_id='large-rule', code='005930', side='buy', quantity=50,
                          price=200000, comparison='lte', threshold=1, expected_version=snapshot['version'])
        self.assertEqual(restored.snapshot()['rules'][0]['quantity'], 50)

    def test_unknown_transport_blocks_new_orders_and_is_not_retried(self):
        self.configure()
        self.broker.failure = NamuhError('uncertain')
        order = self.order()
        self.assertEqual(order['status'], 'unknown')
        self.assertEqual(self.order()['id'], order['id'])
        with self.assertRaises(TradingError): self.order('b')
        self.assertEqual(len(self.broker.sent), 1)
        self.service.resolve(order['id'], 'not_sent', None, True, self.version())
        self.assertEqual(self.service.snapshot()['daily_used'], 0)

    def test_known_rejection_is_not_unknown_and_capacity_prevents_send(self):
        self.configure()
        self.broker.available = 0
        with self.assertRaises(TradingError): self.order()
        self.assertEqual(self.broker.sent, [])
        self.broker.available = 50
        self.broker.failure = NamuhRejected('rejected')
        self.assertEqual(self.order()['status'], 'rejected')
        self.assertEqual(self.service.snapshot()['daily_used'], 0)

    def test_stale_request_and_stale_start_after_stop_never_send(self):
        self.configure()
        old = self.version()
        self.service.stop()
        with self.assertRaises(TradingError): self.service.start(old)
        with self.assertRaises(TradingError):
            self.service.order(client_id='x', code='005930', side='buy', quantity=1, price=1000, expected_version=old)
        self.assertEqual(self.broker.sent, [])

    def test_preflight_stop_cannot_be_followed_by_order_send(self):
        self.configure()
        def capacity(*args):
            self.service.stop()
            return {'quantity': 100, 'amount': 1000000}
        self.broker.capacity = capacity
        with self.assertRaises(TradingError): self.order()
        self.assertEqual(self.broker.sent, [])

    def test_modify_and_cancel_recheck_live_remaining_cash_and_krx(self):
        self.configure()
        self.broker.rows = [dict(broker_id='17', day='20260911', code='005930', side='buy', quantity=10,
                                price=9000, remaining=3, filled=7, market='KRX', split='N', reason='정상', order_type='보통')]
        self.service.manage('modify', 'm', '17', 10000, self.version())
        self.assertEqual(self.broker.sent[-1][2]['quantity'], 3)
        self.service.stop()
        self.service.manage('cancel', 'c', '17', 0, self.version())
        self.assertEqual(self.broker.sent[-1][0], 'cancel')
        self.broker.rows[0]['remaining'] = 0
        with self.assertRaises(TradingError): self.service.manage('cancel', 'c2', '17', 0, self.version())

    def test_rule_executes_once_only_in_selected_live_account(self):
        self.configure()
        self.service.add_rule(client_id='r', code='005930', side='buy', quantity=1, price=10000,
                              comparison='lte', threshold=9500, expected_version=self.version())
        self.service.tick()
        self.service.tick()
        self.assertEqual(len(self.broker.sent), 1)
        self.assertEqual(self.service.snapshot()['rules'][0]['status'], 'fired')

    def test_config_change_rejects_unknown_account_and_preserves_previous_mode(self):
        with self.assertRaises(TradingError):
            self.service.configure(mode='live', account='unknown', expected_version=self.version())
        self.assertEqual(self.service.snapshot()['mode'], 'paper')

    def test_cancellation_is_allowed_while_locked_after_settings_save(self):
        self.configure()
        self.order()
        self.service.configure(mode='live', account='12345678', expected_version=self.version())
        self.broker.rows = [dict(broker_id='1', code='005930', side='buy', quantity=10, price=10000,
                                remaining=10, filled=0, market='KRX', split='N', reason='정상', order_type='보통')]
        self.service.manage('cancel', 'cancel', '1', 0, self.version())
        self.assertEqual(self.broker.sent[-1][0], 'cancel')

    def test_stop_wins_over_concurrent_start_before_stop_commit(self):
        import threading
        from contextlib import contextmanager
        self.configure()
        entered, release = threading.Event(), threading.Event()
        original = self.service.change
        @contextmanager
        def delayed():
            if threading.current_thread().name == 'stopper':
                entered.set()
                release.wait(2)
            with original() as state: yield state
        self.service.change = delayed
        worker = threading.Thread(target=self.service.stop, name='stopper')
        worker.start()
        self.assertTrue(entered.wait(2))
        self.service.start(self.version())
        release.set()
        worker.join(3)
        self.assertFalse(self.service.snapshot()['running'])

    def test_emergency_reports_unknown_cancellation(self):
        self.configure()
        self.order()
        self.broker.rows = [dict(broker_id='1', code='005930', side='buy', quantity=10, price=10000,
                                remaining=10, filled=0, market='KRX', split='N', reason='정상', order_type='보통')]
        self.broker.failure = NamuhError('timeout')
        state = self.service.emergency()
        self.assertEqual(state['emergency_result']['uncertain'], 1)
        self.assertFalse(state['running'])

    def test_live_conditions_do_not_send_outside_execution_window(self):
        self.configure()
        self.service.add_rule(client_id='r', code='005930', side='buy', quantity=1, price=10000,
                              comparison='lte', threshold=9500, expected_version=self.version())
        self.service.session_open = lambda: False
        self.service.tick()
        self.assertEqual(self.broker.sent, [])
        self.assertEqual(self.service.snapshot()['rules'][0]['status'], 'armed')

    def test_condition_does_not_send_when_session_closes_during_capacity(self):
        self.configure()
        self.service.add_rule(client_id='r', code='005930', side='buy', quantity=1, price=10000,
                              comparison='lte', threshold=9500, expected_version=self.version())
        def capacity(*args):
            self.service.session_open = lambda: False
            return {'quantity': 100, 'amount': 1000000}
        self.broker.capacity = capacity
        self.service.tick()
        self.assertEqual(self.broker.sent, [])

    def test_management_rejects_previous_day_order_number(self):
        self.configure()
        with self.assertRaises(TradingError):
            self.service.manage('cancel', 'yesterday', '1', 0, self.version(), order_day='20000101')
        self.assertEqual(self.broker.sent, [])

    def test_repeated_emergency_does_not_release_inflight_guard(self):
        import threading
        self.configure()
        entered, release = threading.Event(), threading.Event()
        def history(*args):
            entered.set()
            release.wait(3)
            return []
        self.broker.history = history
        worker = threading.Thread(target=self.service.emergency)
        worker.start()
        self.assertTrue(entered.wait(2))
        # A second click must return without clearing the first sweep's guard.
        self.service.emergency()
        self.assertTrue(self.service.emergency_active.is_set())
        with self.assertRaises(TradingError): self.service.start(self.version())
        release.set()
        worker.join(4)

    def test_new_order_is_not_sent_if_date_changes_in_transport_queue(self):
        from unittest.mock import patch
        with patch('backend.trading.live.korea_today', return_value='20260911'):
            self.configure()
            original = self.broker.send
            def delayed(*args, **kwargs):
                with patch('backend.trading.live.korea_today', return_value='20260912'):
                    return original(*args, **kwargs)
            self.broker.send = delayed
            result = self.order()
        self.assertEqual(result['status'], 'rejected')
        self.assertEqual(self.broker.sent, [])
