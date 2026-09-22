import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs

import httpx


class NamuhTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('backend.namuh'),
                             'Namuh integration has not been implemented')
        from backend.namuh.client import NamuhClient
        self.client_type = NamuhClient
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name) / 'token.json'

    def client(self, handler, key='test-key'):
        http = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(http.close)
        return self.client_type(key, 'test-secret', self.cache, http=http,
                                min_interval=0)

    def token(self, request):
        self.assertEqual(request.url.host, 'api.nhplug.com')
        self.assertEqual(parse_qs(request.content.decode()), {
            'appkey': ['test-key'], 'appsecretkey': ['test-secret'],
            'grant_type': ['client_credentials'], 'scope': ['oob']})
        return httpx.Response(200, json={'access_token': 'test-token', 'expires_in': 86400})

    def test_token_is_reused_across_client_instances(self):
        self.assertEqual(self.client(self.token).get_access_token(), 'test-token')
        def no_network(request):
            self.fail('A valid cached token must prevent another token request')
        self.assertEqual(self.client(no_network).get_access_token(), 'test-token')

    def test_different_credentials_do_not_reuse_token(self):
        self.client(self.token).get_access_token()
        def handler(request):
            self.assertIn(b'new-key', request.content)
            return httpx.Response(200, json={'access_token': 'new-token', 'expires_in': 86400})
        self.assertEqual(self.client(handler, key='new-key').get_access_token(), 'new-token')

    def test_corrupt_cache_can_recover(self):
        self.cache.write_text('{broken', encoding='utf-8')
        self.assertEqual(self.client(self.token).get_access_token(), 'test-token')

    def test_balance_uses_last_page_totals_and_preserves_separate_lots(self):
        from backend.namuh.portfolio import get_balance
        def handler(request):
            if request.url.path == '/oauth2/token':
                return self.token(request)
            self.assertEqual(request.url.path, '/krstock/inquiry/v1/balance')
            self.assertEqual(json.loads(request.content)['Input_0']['act_no'], '12345678')
            if request.headers.get('cts_flag') != 'Y':
                return httpx.Response(200, headers={'cts_flag': 'Y', 'cts': 'next'}, json={
                    'rsp_cd': '00136', 'Output_0': {}, 'Output_1': [{
                        'iem_cd': '005930', 'iem_nm': 'Samsung', 'rsdl_qty': 2,
                        'phs_pr': 100, 'now_pr': 90, 'eal_amt': 180,
                        'eal_pls_amt': -20, 'pft_rt': -10, 'tp_cd_nm': 'cash'}]})
            self.assertEqual(request.headers['cts'], 'next')
            return httpx.Response(200, headers={'cts_flag': 'N'}, json={
                'rsp_cd': '00166', 'Output_0': {'tot_eal_amt': 270, 'tot_byn_amt': 300,
                    'tot_eal_pls': -30, 'pft_rt': -10, 'dca': 1000,
                    'orr_pbl_amt4': 8000, 'tot_aet_amt': 9270, 'nas_amt': 9000},
                'Output_1': [{'iem_cd': '005930', 'iem_nm': 'Samsung', 'rsdl_qty': 1,
                    'phs_pr': 100, 'now_pr': 90, 'eal_amt': 90,
                    'eal_pls_amt': -10, 'pft_rt': -10, 'tp_cd_nm': 'credit'}]})
        result = get_balance('12345678', client=self.client(handler))
        self.assertEqual(result['summary'], {'total_eval': 270, 'total_purchase': 300,
            'total_profit_loss': -30, 'total_profit_rate': -10, 'cash': 1000,
            'cash_orderable_100':8000, 'total_assets':9270, 'net_assets':9000})
        self.assertEqual([h['quantity'] for h in result['holdings']], [2, 1])
        self.assertNotEqual(result['holdings'][0]['id'], result['holdings'][1]['id'])

    def test_api_error_is_not_treated_as_empty_success(self):
        from backend.namuh.client import NamuhError
        def handler(request):
            if request.url.path == '/oauth2/token': return self.token(request)
            return httpx.Response(200, json={'rsp_cd': '99999', 'rsp_msg': 'secret data'})
        with self.assertRaises(NamuhError) as raised:
            self.client(handler).post('/krstock/quote/v1/currentPrice', {})
        self.assertNotIn('secret data', str(raised.exception))

    def test_repeated_continuation_key_fails_instead_of_returning_partial_balance(self):
        from backend.namuh.client import NamuhError
        def handler(request):
            if request.url.path == '/oauth2/token': return self.token(request)
            return httpx.Response(200, headers={'cts_flag': 'Y', 'cts': 'same'},
                                  json={'rsp_cd': '00136', 'Output_1': []})
        with self.assertRaises(NamuhError):
            list(self.client(handler).pages('/krstock/inquiry/v1/balance', {}))

    def test_chart_sorts_deduplicates_and_preserves_korean_wall_time(self):
        from backend.namuh.chart import get_minute_chart
        row = {'bsop_date': '20260910', 'bsop_time': '090000',
               'stck_oprc': '100', 'stck_hgpr': '120', 'stck_lwpr': '90',
               'stck_prpr': '110', 'vol': '5', 'tr_pbmn': '550'}
        def handler(request):
            if request.url.path == '/oauth2/token': return self.token(request)
            body = json.loads(request.content)['Input_0']
            self.assertEqual((body['gubun'], body['xtick']), ('5', '5'))
            self.assertEqual(body['out2_scale_change'], '0')
            return httpx.Response(200, json={'rsp_cd': '00000', 'Output_1': [
                {**row, 'bsop_time': '090500'}, row, row]})
        result = get_minute_chart('005930', interval=5, client=self.client(handler))
        self.assertEqual(len(result), 2)
        self.assertEqual(datetime.fromtimestamp(result[0]['time'], timezone.utc).isoformat(),
                         '2026-09-10T09:00:00+00:00')
        self.assertEqual(result[0]['trading_value'], 550)
        self.assertEqual(result[1]['time'] - result[0]['time'], 300)

    def test_daily_chart_returns_frontend_contract(self):
        from backend.namuh.chart import get_daily_chart
        def handler(request):
            if request.url.path == '/oauth2/token': return self.token(request)
            self.assertEqual(json.loads(request.content)['Input_0']['gubun'], '2')
            return httpx.Response(200, json={'rsp_cd': '00000', 'Output_1': [{
                'bsop_date': '20260907', 'bsop_time': '', 'stck_oprc': 100,
                'stck_hgpr': 120, 'stck_lwpr': 90, 'stck_prpr': 110,
                'vol': 500, 'tr_pbmn': 55000}]})
        self.assertEqual(get_daily_chart('005930', period='W', client=self.client(handler)), [{
            'time': '2026-09-07', 'open': 100, 'high': 120, 'low': 90,
            'close': 110, 'volume': 500, 'trading_value': 55000}])

    def test_minute_chart_skips_non_clock_summary_row(self):
        from backend.namuh.chart import get_minute_chart
        def handler(request):
            if request.url.path == '/oauth2/token': return self.token(request)
            row = {'bsop_date': '20260911', 'stck_oprc': 100, 'stck_hgpr': 120,
                   'stck_lwpr': 90, 'stck_prpr': 110, 'vol': 10}
            return httpx.Response(200, json={'rsp_cd': '00000', 'Output_1': [
                {**row, 'bsop_time': '999900'}, {**row, 'bsop_time': '153000'}]})
        result = get_minute_chart('005930', interval=5, client=self.client(handler))
        self.assertEqual(len(result), 1)
        self.assertEqual(datetime.fromtimestamp(result[0]['time'], timezone.utc).hour, 15)

    def test_month_chart_uses_first_day_of_each_month(self):
        from backend.namuh.chart import get_daily_chart
        def handler(request):
            if request.url.path == '/oauth2/token': return self.token(request)
            row = {'stck_oprc': 100, 'stck_hgpr': 120, 'stck_lwpr': 90, 'stck_prpr': 110}
            return httpx.Response(200, json={'rsp_cd': '00000', 'Output_1': [
                {**row, 'bsop_date': '202611'}, {**row, 'bsop_date': '202609'}]})
        result = get_daily_chart('005930', period='M', client=self.client(handler))
        self.assertEqual([c['time'] for c in result], ['2026-09-01', '2026-11-01'])

    def test_price_maps_downward_sign_to_negative_change(self):
        from backend.namuh.market import get_current_price
        def handler(request):
            if request.url.path == '/oauth2/token': return self.token(request)
            return httpx.Response(200, json={'rsp_cd': '00000', 'Output_0': {
                'stck_prpr': '90000', 'prdy_vrss': '1000', 'prdy_ctrt': '1.1',
                'prdy_vrss_sign': '5', 'acml_vol': '5000'}})
        result = get_current_price('005930', client=self.client(handler))
        self.assertEqual((result['price'], result['change'], result['change_rate']), (90000, -1000, -1.1))

    def test_empty_direction_uses_previous_close_from_same_quote(self):
        from backend.namuh.market import get_current_price
        def handler(request):
            if request.url.path == '/oauth2/token': return self.token(request)
            return httpx.Response(200, json={'rsp_cd': '00000', 'Output_0': {
                'stck_prpr': 259500, 'stck_prdy_clpr': 269000,
                'prdy_vrss': 9500, 'prdy_ctrt': 3.53, 'prdy_vrss_sign': ''}})
        result = get_current_price('005930', client=self.client(handler))
        self.assertEqual((result['change'], result['change_rate']), (-9500, -3.53))

    def test_missing_quote_rate_is_not_reported_as_flat(self):
        from backend.namuh.market import get_current_price
        for rate in (None, '', 'NaN'):
            def handler(request):
                if request.url.path == '/oauth2/token': return self.token(request)
                return httpx.Response(200, json={'rsp_cd': '00000', 'Output_0': {
                    'stck_prpr': 90000, 'prdy_ctrt': rate, 'prdy_vrss_sign': '5'}})
            self.assertIsNone(get_current_price('005930', client=self.client(handler))['change_rate'])

    def test_accounts_exclude_paper_accounts_and_mask_labels(self):
        from backend.namuh.portfolio import get_accounts
        def handler(request):
            if request.url.path == '/oauth2/token': return self.token(request)
            return httpx.Response(200, json={'rsp_cd': '00000', 'Output_0': [
                {'acct_no': '12345678', 'acct_type': '01'},
                {'acct_no': '98765432', 'acct_type': '03'}]})
        self.assertEqual(get_accounts(client=self.client(handler)), [{'id': '12345678', 'label': '****5678'}])


if __name__ == '__main__':
    unittest.main()
