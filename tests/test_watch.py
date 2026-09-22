import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.watch.service import WatchService


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'watch.db'
        self.price = 5000
        self.calls = []
        def quote(code):
            self.calls.append(code)
            return dict(price=self.price, change_rate=1.2)
        self.quote = quote
        self.service = WatchService(self.path, quote, lambda code: {'code': code, 'name': '채비'})
        self.service.session_open = lambda: True
        self.service.add('0011T0')

    def alert(self, key='a', comparison='gte', threshold=5000):
        return self.service.add_alert('0011T0', comparison, threshold, key)

    def test_watchlist_and_alert_survive_restart_and_add_is_idempotent(self):
        self.service.add('0011T0')
        first = self.alert()
        self.assertEqual(first['id'], self.alert()['id'])
        restored = WatchService(self.path, self.quote, lambda code: {'code': code, 'name': '채비'})
        self.assertEqual(len(restored.snapshot()['items']), 1)
        self.assertEqual(restored.snapshot()['alerts'][0]['id'], first['id'])
        with self.assertRaises(ValueError): self.alert(threshold=6000)

    def test_one_shot_uses_fresh_quote_and_notification_ack_persists(self):
        alert = self.alert()
        self.service.tick()
        self.service.tick()
        self.assertEqual(self.service.snapshot()['alerts'][0]['status'], 'triggered')
        self.assertEqual(len(self.service.notifications()), 1)
        self.service.acknowledge([alert['id']])
        restored = WatchService(self.path, self.quote, lambda code: {'code': code, 'name': '채비'})
        self.assertEqual(restored.notifications(), [])

    def test_no_background_quotes_without_alert_or_active_page_lease(self):
        self.service.tick()
        self.assertEqual(self.calls, [])
        self.service.snapshot(viewed=True)
        self.service.tick()
        self.assertEqual(self.calls, ['0011T0'])

    def test_failure_or_closed_session_does_not_trigger(self):
        self.alert()
        self.service.session_open = lambda: False
        self.service.tick()
        self.assertEqual(self.service.notifications(), [])
        self.service.session_open = lambda: True
        for value in (None, 0, -1, float('nan'), float('inf')):
            self.price = value
            self.service.tick()
        self.assertEqual(self.service.notifications(), [])

    def test_cancel_during_quote_discards_inflight_trigger(self):
        alert = self.alert()
        def quote(code):
            self.service.cancel_alert(alert['id'])
            return {'price': 6000}
        self.service.quote = quote
        self.service.tick()
        self.assertEqual(self.service.notifications(), [])
        self.assertEqual(self.service.snapshot()['alerts'][0]['status'], 'cancelled')

    def test_remove_during_quote_cancels_alerts_and_does_not_resurrect_item(self):
        self.alert()
        def quote(code):
            self.service.remove(code)
            return {'price': 6000}
        self.service.quote = quote
        self.service.tick()
        self.assertEqual(self.service.snapshot()['items'], [])
        self.assertEqual(self.service.notifications(), [])

    def test_alert_added_during_quote_waits_for_next_observation(self):
        self.service.snapshot(viewed=True)
        def quote(code):
            self.alert()
            return {'price': 6000}
        self.service.quote = quote
        self.service.tick()
        self.assertEqual(self.service.notifications(), [])
        self.service.tick()
        self.assertEqual(len(self.service.notifications()), 1)

    def test_above_and_below_conditions_and_closed_session_after_quote(self):
        self.alert(comparison='lte', threshold=4000)
        self.service.tick()
        self.assertEqual(self.service.notifications(), [])
        self.price = 3900
        def quote(code):
            self.service.session_open = lambda: False
            return self.quote(code)
        self.service.quote = quote
        self.service.tick()
        self.assertEqual(self.service.notifications(), [])

    def test_below_threshold_triggers_and_late_response_does_not(self):
        self.alert(comparison='lte', threshold=5000)
        with patch('backend.watch.service.time.monotonic', side_effect=[100, 100, 100, 131, 132]):
            self.service.tick()
        self.assertEqual(self.service.notifications(), [])
        self.service.tick()
        self.assertEqual(len(self.service.notifications()), 1)

    def test_remove_and_readd_while_quote_is_inflight_discards_old_result(self):
        self.alert()
        def quote(code):
            self.service.remove(code)
            self.service.add(code)
            self.alert(key='new')
            return {'price': 6000}
        self.service.quote = quote
        self.service.tick()
        self.assertIsNone(self.service.snapshot()['items'][0]['quote'])
        self.assertEqual(self.service.notifications(), [])


if __name__ == '__main__': unittest.main()
