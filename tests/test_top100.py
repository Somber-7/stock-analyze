import threading
import unittest
from unittest.mock import patch

from backend.namuh import top100


def snapshot():
    return {'stocks': [
        {'code': '005930', 'name': '삼성전자', 'market': 'KOSPI', 'is_etf': False,
         'previous_market_cap': 200, 'previous_close': 100},
        {'code': '000660', 'name': 'SK하이닉스', 'market': 'KOSPI', 'is_etf': False,
         'previous_market_cap': 300, 'previous_close': 200},
        {'code': '999999', 'name': 'ETF', 'market': 'KOSPI', 'is_etf': True,
         'previous_market_cap': 999, 'previous_close': 300},
    ], 'downloaded_at': '2026-09-11T09:00:00', 'error': '', 'loading': False}


class Top100Tests(unittest.TestCase):
    def setUp(self):
        for key, value in {'_quotes': {}, '_worker': None, '_active_codes': (),
                           '_last_viewed': 0, '_next_cycle': 0, '_completed': 0,
                           '_last_completed_at': ''}.items():
            p = patch.object(top100, key, value)
            p.start()
            self.addCleanup(p.stop)

    def test_rankings_use_master_cap_and_appear_before_any_price_request(self):
        with patch.object(top100, 'get_snapshot', return_value=snapshot()), \
             patch.object(top100.threading, 'Thread'):
            data = top100.get_top100()
        self.assertEqual([r['code'] for r in data['rows']], ['000660', '005930'])
        self.assertEqual(data['rows'][0]['previous_market_cap'], 300)
        self.assertIsNone(data['rows'][0]['quote'])

    def test_first_quote_is_visible_while_second_is_still_loading(self):
        entered, release = threading.Event(), threading.Event()
        def quote(code):
            if code == '005930':
                entered.set()
                release.wait(3)
            return {'price': 123, 'change': 3, 'change_rate': 2.5, 'volume': 100}
        with patch.object(top100, 'get_snapshot', return_value=snapshot()), \
             patch.object(top100, 'get_current_price', side_effect=quote):
            top100.get_top100()
            try:
                self.assertTrue(entered.wait(2))
                data = top100.get_top100()
                self.assertEqual(data['rows'][0]['quote']['price'], 123)
                self.assertIsNone(data['rows'][1]['quote'])
            finally:
                release.set()
                top100._worker.join(3)

    def test_failed_price_keeps_prior_price_and_exposes_error(self):
        from backend.namuh.client import NamuhError
        top100._quotes['000660'] = {'price': 120, 'retrieved_at': 'old'}
        with patch.object(top100, 'get_snapshot', return_value=snapshot()), \
             patch.object(top100, 'get_current_price', side_effect=NamuhError('조회 실패')):
            top100.get_top100()
            top100._worker.join(3)
            data = top100.get_top100()
        self.assertEqual(data['rows'][0]['quote']['price'], 120)
        self.assertEqual(data['rows'][0]['quote']['retrieved_at'], 'old')
        self.assertTrue(data['rows'][0]['quote']['error'])

    def test_empty_or_failed_master_does_not_start_price_worker(self):
        with patch.object(top100, 'get_snapshot', return_value={'stocks': [], 'error': '파일 실패', 'loading': False}), \
             patch.object(top100.threading, 'Thread') as thread:
            data = top100.get_top100()
        thread.assert_not_called()
        self.assertEqual(data['error'], '파일 실패')
        self.assertFalse(data['loading'])

    def test_leaving_view_stops_additional_price_requests(self):
        top100._active_codes = ('005930',)
        with patch.object(top100.time, 'monotonic', return_value=16), \
             patch.object(top100, 'get_current_price') as quote:
            top100._refresh_prices(('005930',))
        quote.assert_not_called()

    def test_connection_outage_stops_after_three_failures(self):
        from backend.namuh.client import NamuhError
        data = snapshot()
        data['stocks'] = [{**data['stocks'][0], 'code': f'{n:06d}'} for n in range(10)]
        with patch.object(top100, 'get_snapshot', return_value=data), \
             patch.object(top100, 'get_current_price', side_effect=NamuhError('통신 실패')) as quote:
            top100.get_top100()
            top100._worker.join(3)
        self.assertEqual(quote.call_count, 3)
        self.assertEqual(len(top100._quotes), 10)
        self.assertGreater(top100._next_cycle, 0)
