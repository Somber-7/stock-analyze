import unittest
from unittest.mock import patch

from backend.namuh import investors
from backend.namuh.client import NamuhError


class Provider:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def post(self, path, payload):
        self.calls += 1
        assert path == '/krstock/quote/v1/currentInvestor'
        assert payload == {'Input_0': {'market_cd': 'KRX', 'iem_cd': '005930', 'array_cnt': '20'}}
        if isinstance(self.rows, Exception):
            raise self.rows
        return {'Output_0': self.rows}, {}


class InvestorsTests(unittest.TestCase):
    def setUp(self):
        investors._cache.clear()

    def test_preserves_provider_quantities_and_uses_invest_not_shareholding_change(self):
        client = Provider([{'bsop_date1': '20260911', 'person': 3643746,
                            'gigwan': -2208594, 'invest': -3550438, 'frgn_ntby_qty': -3970955}])
        result = investors.get_investors('005930', client=client)
        self.assertEqual(result['rows'], [{'date': '2026-09-11', 'personal': 3643746,
                                          'institutional': -2208594, 'foreign': -3550438}])
        self.assertEqual(result['data_date'], '2026-09-11')
        self.assertEqual(result['summary'], result['rows'][0])
        self.assertIsNone(result['unit'])

    def test_alphanumeric_domestic_code_is_forwarded_unchanged(self):
        class AlphanumericProvider:
            def post(inner, path, payload):
                self.assertEqual(path, '/krstock/quote/v1/currentInvestor')
                self.assertEqual(payload, {'Input_0': {'market_cd': 'KRX', 'iem_cd': '0011T0', 'array_cnt': '20'}})
                return {'Output_0': [{'bsop_date1': '20260911', 'person': 12}]}, {}

        result = investors.get_investors('0011T0', client=AlphanumericProvider())
        self.assertEqual(result['code'], '0011T0')
        self.assertEqual(result['summary']['personal'], 12)

    def test_missing_and_unverified_aliases_are_not_reported_as_zero(self):
        client = Provider([{'bsop_date1': '20260911', 'personz10': 40, 'gigwanz10': 0, 'investz10': -40},
                           {'bsop_date1': '20260910', 'person': '0', 'gigwan': '', 'invest': None}])
        result = investors.get_investors('005930', client=client)
        self.assertEqual(result['rows'][0], {'date': '2026-09-11', 'personal': None,
                                            'institutional': None, 'foreign': None})
        self.assertEqual(result['data_date'], '2026-09-10')
        self.assertEqual(result['summary']['personal'], 0)
        self.assertTrue(result['notes'])

    def test_sorts_deduplicates_and_limits_to_twenty_valid_dates(self):
        rows = [{'bsop_date1': f'202608{day:02}', 'person': day} for day in range(1, 26)]
        rows += [{'bsop_date1': '20260825', 'person': 999}, {'bsop_date1': '20260230', 'person': 3}]
        result = investors.get_investors('005930', client=Provider(rows))
        self.assertEqual(len(result['rows']), 20)
        self.assertEqual(result['rows'][0]['date'], '2026-08-25')
        self.assertEqual(result['rows'][-1]['date'], '2026-08-06')

    def test_invalid_numeric_values_remain_missing_and_empty_response_has_no_summary(self):
        result = investors.get_investors('005930', client=Provider([
            {'bsop_date1': '20260911', 'person': 'NaN', 'gigwan': True, 'invest': 'Infinity'}]))
        self.assertIsNone(result['data_date'])
        self.assertIsNone(result['summary'])
        empty = investors.get_investors('005930', client=Provider([]))
        self.assertEqual(empty['rows'], [])

    def test_cache_reuses_response_until_expiry_and_returns_independent_values(self):
        client = Provider([{'bsop_date1': '20260911', 'person': 8}])
        with patch.object(investors.time, 'monotonic', return_value=100) as clock:
            result = investors.get_investors('005930', client=client)
            result['rows'][0]['personal'] = 999
            self.assertEqual(investors.get_investors('005930', client=client)['rows'][0]['personal'], 8)
            self.assertEqual(client.calls, 1)
            clock.return_value = 161
            investors.get_investors('005930', client=client)
            self.assertEqual(client.calls, 2)

    def test_cache_is_bounded_and_does_not_mix_clients(self):
        first = Provider([])
        investors.get_investors('005930', client=first)
        for _ in range(128):
            investors.get_investors('005930', client=Provider([]))
        investors.get_investors('005930', client=first)
        self.assertEqual(first.calls, 2)

    def test_provider_errors_propagate_and_are_not_cached_as_empty_data(self):
        client = Provider(NamuhError('조회 실패'))
        with self.assertRaises(NamuhError):
            investors.get_investors('005930', client=client)
        client.rows = [{'bsop_date1': '20260911', 'person': 12}]
        self.assertEqual(investors.get_investors('005930', client=client)['summary']['personal'], 12)

    def test_rejects_invalid_code_and_malformed_output(self):
        for code in ('../005930', 'AAPL', '', '0059300'):
            with self.subTest(code=code), self.assertRaises(ValueError):
                investors.get_investors(code, client=Provider([]))
        with self.assertRaises(NamuhError):
            investors.get_investors('005930', client=Provider({}))
