import unittest
from unittest.mock import Mock, patch

from backend.namuh.client import NamuhError
from backend.namuh import us_market


class UsMarketTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        mock = patch.object(us_market, '_cache', {})
        mock.start()
        self.addCleanup(mock.stop)

    def test_etf_remains_labeled_etf_and_negative_sign_is_preserved(self):
        self.client.post.return_value = ({'Output_0': {
            'trdprc': '700.5', 'netchng': '2.5', 'pctchng': '0.35', 'netchng_cls': '5',
            'trade_date': '20260910', 'quote_time': '160000', 'currency_unit': 'USD'}}, {})
        data = us_market.get_quote('QQQ', client=self.client)
        self.assertEqual(data['kind'], 'ETF')
        self.assertEqual(data['change'], -2.5)
        self.assertEqual(data['change_rate'], -0.35)
        self.assertEqual(data['data_date'], '20260910')
        self.client.post.assert_called_once_with('/gbstock/quote/v1/current', {'Input_0': {'iem_cd': 'QQQ'}})

    def test_index_uses_documented_period_api_and_provider_date(self):
        self.client.post.return_value = ({'Output_0': {
            'ovrs_prpr': '50000', 'prdy_vrss': '100', 'prdy_ctrt': '0.2',
            'prdy_vrss_sign': '2', 'qry_date': '20260910', 'qry_time': '200000'}}, {})
        data = us_market.get_quote('DJI', client=self.client)
        self.assertEqual(data['unit'], 'pt')
        self.assertEqual(data['data_date'], '20260910')
        self.assertEqual(self.client.post.call_args.args[1]['Input_0']['iem_cd'], '.DJI')

    def test_cache_prevents_repeated_upstream_calls(self):
        self.client.post.return_value = ({'Output_0': {'trdprc': 100, 'netchng': 1,
            'pctchng': 1, 'netchng_cls': '2', 'trade_date': '20260910'}}, {})
        first = us_market.get_quote('NVDA', client=self.client)
        self.assertEqual(us_market.get_quote('NVDA', client=self.client), first)
        self.assertEqual(self.client.post.call_count, 1)

    def test_missing_price_is_error_not_zero(self):
        self.client.post.return_value = ({'Output_0': {}}, {})
        with self.assertRaises(NamuhError):
            us_market.get_quote('SPY', client=self.client)

    def test_only_selected_reference_symbols_are_available(self):
        with self.assertRaises(ValueError):
            us_market.get_quote('AAPL', client=self.client)
        self.client.post.assert_not_called()

    def test_missing_change_is_not_reported_as_flat(self):
        self.client.post.return_value = ({'Output_0': {'trdprc': 100, 'netchng_cls': '5'}}, {})
        with self.assertRaises(NamuhError):
            us_market.get_quote('SPY', client=self.client)
