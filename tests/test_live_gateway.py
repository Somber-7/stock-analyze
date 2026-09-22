import json
import tempfile
import unittest
from pathlib import Path
import httpx
from backend.namuh.client import NamuhClient, NamuhError, NamuhRejected
from backend.namuh.orders import OrderGateway


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sent = []
        def handle(request):
            if request.url.path == '/oauth2/token':
                return httpx.Response(200, json={'access_token': 'fake', 'expires_in': 86400})
            self.sent.append((request.url.path, json.loads(request.content)['Input_0']))
            path = request.url.path.rsplit('/', 1)[-1]
            responses = {
                'cashBuy': ('00048', {'mkt_orr_no': 21}),
                'cashSell': ('00047', {'mkt_orr_no': 22}),
                'modify': ('00164', {'mkt_orr_no': 23}),
                'cancel': ('00192', {'mkt_orr_no': 24}),
                'buyableQuantity': ('00221', {'csh_orr_pbl_qty': 3, 'csh_orr_pbl_amt': 30000, 'max_pbl_qty': 99}),
                'sellableQuantity': ('00166', {'sll_pbl_qty': 2}),
            }
            code, output = responses[path]
            return httpx.Response(200, json={'rsp_cd': code, 'Output_0': output})
        http = httpx.Client(transport=httpx.MockTransport(handle))
        self.addCleanup(http.close)
        self.gateway = OrderGateway(NamuhClient('fake', 'fake', Path(self.tmp.name)/'token', http=http, min_interval=0))

    def test_order_success_codes_and_cash_krx_payload(self):
        self.assertEqual(self.gateway.send('buy', 'acct', code='005930', quantity=2, price=10000)['broker_id'], '21')
        self.assertEqual(self.sent[-1][1], {'act_no': 'acct', 'iem_cd': '005930', 'orr_qty': 2,
                         'orr_pr': 10000, 'orr_amt': 20000, 'nmn_pr_tp_cd': '01', 'orr_cnd_dit_cd': '00',
                         'ssl_nmn_pr_dit_cd': '00', 'rmt_mkt_cd': 'KRX', 'sor_mkt_sli_yn': 'N'})
        self.assertEqual(self.gateway.send('sell', 'acct', code='005930', quantity=1, price=10000)['broker_id'], '22')

    def test_modify_cancel_use_original_number_and_remaining_quantity(self):
        self.assertEqual(self.gateway.send('modify', 'acct', code='005930', quantity=3, price=9000, original='21')['broker_id'], '23')
        self.assertEqual(self.sent[-1][1]['org_mkt_orr_no'], 21)
        self.assertEqual(self.sent[-1][1]['cor_qty'], 3)
        self.assertEqual(self.gateway.send('cancel', 'acct', code='005930', quantity=3, original='23')['broker_id'], '24')
        self.assertEqual(self.sent[-1][1]['all_pat_dit_cd'], '2')

    def test_capacity_uses_cash_not_margin_quantity(self):
        self.assertEqual(self.gateway.capacity('acct', '005930', 'buy', 10000)['quantity'], 3)
        self.assertEqual(self.sent[-1][1]['sby_dit_cd'], '2')
        self.assertEqual(self.gateway.capacity('acct', '005930', 'sell', 10000)['quantity'], 2)

    def test_capacity_serializes_whole_won_float_as_integer(self):
        self.gateway.capacity('acct', '005930', 'buy', 248500.0)
        self.assertIs(type(self.sent[-1][1]['orr_pr']), int)
        before = len(self.sent)
        for price in (1.5, float('nan'), True, 0):
            with self.assertRaises(NamuhError): self.gateway.capacity('acct', '005930', 'buy', price)
        self.assertEqual(len(self.sent), before)

    def test_http_error_preserves_safe_code_without_upstream_text(self):
        http = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(400,
            json={'rsp_cd': 'IGW40011', 'rsp_msg': 'secret account and token'})))
        self.addCleanup(http.close)
        self.gateway.client.http = http
        self.gateway.client.get_access_token = lambda: 'fake'
        with self.assertRaises(NamuhError) as caught:
            self.gateway.capacity('acct', '005930', 'buy', 100)
        self.assertEqual(caught.exception.diagnostic, dict(stage='http', code='IGW40011', http_status=400))
        self.assertNotIn('secret', str(caught.exception))

    def test_missing_order_number_is_uncertain_failure(self):
        http = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={'rsp_cd': '00048', 'Output_0': {}})))
        self.addCleanup(http.close)
        self.gateway.client.http = http
        self.gateway.client.get_access_token = lambda: 'fake'
        with self.assertRaises(NamuhError):
            self.gateway.send('buy', 'acct', code='005930', quantity=1, price=10000)

    def test_last_moment_guard_prevents_actual_http_order(self):
        def stop(): raise NamuhRejected('stopped before send')
        with self.assertRaises(NamuhRejected):
            self.gateway.send('buy', 'acct', code='005930', quantity=1, price=10000, before_send=stop)
        self.assertEqual(self.sent, [])

    def test_unrecognized_numeric_order_code_is_not_definite_rejection(self):
        http = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={'rsp_cd': '99999'})))
        self.addCleanup(http.close)
        self.gateway.client.http = http
        self.gateway.client.get_access_token = lambda: 'fake'
        with self.assertRaises(NamuhError) as error:
            self.gateway.send('buy', 'acct', code='005930', quantity=1, price=10000)
        self.assertNotIsInstance(error.exception, NamuhRejected)

    def test_observed_empty_history_code_is_empty_list_not_error(self):
        http = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={'rsp_cd': '11512', 'Output_0': []})))
        self.addCleanup(http.close)
        self.gateway.client.http = http
        self.gateway.client.get_access_token = lambda: 'fake'
        self.assertEqual(self.gateway.history('acct', '20260911'), [])
