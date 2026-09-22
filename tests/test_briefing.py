import copy
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from backend.briefing import build_briefing
from backend.ai.comparison import comparison_scope


class BriefingTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 15, 0, 1, tzinfo=timezone.utc)
        self.watch = Mock()
        self.watch.snapshot.return_value = dict(items=[
            dict(code='005930', name='삼성전자', quote=dict(price=100, change_rate=2, retrieved_at='2026-09-15T00:00:30Z')),
            dict(code='000660', name='SK하이닉스', quote=dict(price=100, change_rate=99, retrieved_at='2026-09-14T23:00:00Z'))])
        self.watch.read.return_value = dict(alerts=[
            dict(code='005930', name='삼성전자', status='triggered', notified=True, triggered_at='2026-09-14T15:30:00Z', threshold=100),
            dict(code='000660', status='triggered', triggered_at='2026-09-14T14:59:59Z')])
        self.trade_state = dict(mode='live', account='account-A', version=1, operations=[
            dict(account='account-A', status='unknown'), dict(account='account-B', status='sending')])
        self.trading = Mock()
        self.trading.read.side_effect = lambda: copy.deepcopy(self.trade_state)
        self.trading.gateway.history.return_value = [dict(code='005930', name='삼성전자', side='buy', remaining=3, price=100),
                                                     dict(code='000660', remaining=0)]
        self.operation = Mock()
        self.config = dict(codes=['005930'], objective='목표', include_web=False, include_dart=False)
        scope = comparison_scope(self.config, self.trade_state)
        self.operation.settings.snapshot.return_value = dict(version=1, tools={})
        self.ai_state = dict(version=1, config=self.config, runs=[dict(id='same', status='ready', mode='live',
            comparison_scope=scope, completed_at='2026-09-14T00:00:00Z', comparison=dict(changed_count=1),
            decisions=[dict(assessment='defer')]), dict(id='other', status='ready', comparison_scope='other-account')])
        self.operation.read.side_effect = lambda: copy.deepcopy(self.ai_state)

    def load(self):
        return build_briefing('account-A', self.watch, self.trading, self.operation, now=self.now)

    def test_cached_changes_today_alerts_and_same_account_only(self):
        result = self.load()
        self.assertEqual([r['code'] for r in result['watch']['movers']], ['005930'])
        self.assertEqual(result['watch']['stale_count'], 1)
        self.assertEqual(result['watch']['alert_count'], 1)
        self.assertEqual(result['orders']['pending_count'], 1)
        self.assertEqual(result['orders']['unresolved_count'], 1)
        self.assertEqual(result['analysis']['defer_count'], 1)
        self.assertEqual(result['analysis']['changed_count'], 1)
        self.assertEqual(result['analysis']['run_id'], 'same')
        self.watch.snapshot.assert_called_once_with(viewed=False)
        self.trading.gateway.history.assert_called_once_with('account-A', '20260915')
        self.assertNotIn('account-A', str(result))
        self.assertNotIn('comparison_scope', str(result))

    def test_paper_and_other_account_do_not_query_live_history_or_mix_analyses(self):
        for mode, account in [('paper', 'account-A'), ('live', 'account-B')]:
            self.trade_state.update(mode=mode, account=account)
            result = self.load()
            self.assertEqual(result['orders']['status'], 'unavailable')
            self.assertIsNone(result['orders']['pending_count'])
            self.assertEqual(result['analysis']['status'], 'unavailable')
        self.trading.gateway.history.assert_not_called()

    def test_history_failure_is_unknown_not_zero_and_does_not_leak_error(self):
        self.trading.gateway.history.side_effect = RuntimeError('secret account-A')
        result = self.load()
        self.assertEqual(result['orders']['status'], 'error')
        self.assertEqual(result['orders']['unresolved_count'], 1)
        self.assertIsNone(result['orders']['pending_count'])
        self.assertNotIn('secret', str(result))
        self.assertEqual(result['analysis']['status'], 'ready')

    def test_account_change_during_read_discards_account_sections(self):
        def history(*args):
            self.trade_state.update(account='account-B', version=2)
            return []
        self.trading.gateway.history.side_effect = history
        result = self.load()
        self.assertEqual(result['orders']['status'], 'changed')
        self.assertIsNone(result['orders']['pending_count'])
        self.assertEqual(result['analysis']['status'], 'changed')

    def test_changed_analysis_settings_do_not_reuse_old_comparison(self):
        self.ai_state['config']['objective'] = '새로운 목표'
        result = self.load()
        self.assertEqual(result['analysis']['status'], 'empty')
        self.assertIsNone(result['analysis']['changed_count'])

    def test_future_invalid_or_failed_quotes_are_not_current_movers(self):
        self.watch.snapshot.return_value['items'] = [dict(code=str(i), quote=quote) for i, quote in enumerate([
            dict(price=1, change_rate=float('nan'), retrieved_at=self.now.isoformat()),
            dict(price=1, change_rate=3, retrieved_at='2026-09-16T00:00:00Z'),
            dict(price=1, change_rate=3, retrieved_at=self.now.isoformat(), error='failed')])]
        result = self.load()
        self.assertEqual(result['watch']['movers'], [])
        self.assertEqual(result['watch']['stale_count'], 3)
