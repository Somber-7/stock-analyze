import io
import json
import logging
import unittest
import zipfile
from datetime import date

import httpx

from backend.ai.dart import research, financial_summary
from backend.ai.dart_client import DartClient, DartError, company_codes

KEY = 'a' * 40


class DartTests(unittest.TestCase):
    def client(self, handler):
        http = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
        self.addCleanup(http.close)
        return DartClient(KEY, http=http)

    def test_auth_errors_and_reflected_key_never_escape(self):
        for response in (dict(status='010', message=KEY), dict(status='000', name=KEY)):
            client = self.client(lambda req: httpx.Response(200, json=response))
            with self.assertRaises(DartError) as error: client.json('company.json', corp_code='00126380')
            self.assertNotIn(KEY, str(error.exception))

    def test_http_log_redacts_query_key(self):
        output=io.StringIO()
        handler=logging.StreamHandler(output)
        logger=logging.getLogger('httpx')
        previous=logger.level
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            self.client(lambda req:httpx.Response(200,json=dict(status='013'))).json('list.json')
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous)
        self.assertNotIn(KEY,output.getvalue())
        self.assertIn('REDACTED',output.getvalue())

    def test_redirect_does_not_forward_key(self):
        calls=[]
        def handler(req):
            calls.append(req)
            return httpx.Response(302,headers={'location':'https://example.com/steal'})
        with self.assertRaises(DartError): self.client(handler).json('company.json')
        self.assertEqual(len(calls),1)

    def test_zip_mapping_accepts_alphanumeric_and_rejects_ambiguous(self):
        out = io.BytesIO()
        xml = '<result><list><corp_code>00126380</corp_code><stock_code>0011T0</stock_code></list></result>'
        with zipfile.ZipFile(out, 'w') as z: z.writestr('CORPCODE.xml', xml)
        self.assertEqual(company_codes(out.getvalue()), {'0011T0':'00126380'})
        with self.assertRaises(DartError): company_codes(b'<!DOCTYPE x [<!ENTITY e "bad">]><result/>')

    def rows(self):
        return [dict(corp_code='00126380', bsns_year='2026', reprt_code='11012', rcept_no='20260814000001',
                     sj_div='IS', account_id='ifrs-full_Revenue', account_nm='매출액', currency='KRW',
                     thstrm_nm='제 57 기 반기', thstrm_amount='1,200', thstrm_add_amount='2,000',
                     frmtrm_q_nm='제 56 기 반기', frmtrm_q_amount='1,000', frmtrm_add_amount='1,800')]

    def test_quarter_and_ytd_are_distinct_and_missing_is_null(self):
        value = financial_summary(self.rows(), '00126380', '2026', '11012', 'CFS')
        revenue = value['accounts'][0]
        self.assertEqual(revenue['amount'],1200)
        self.assertEqual(revenue['ytd_amount'],2000)
        self.assertEqual(revenue['comparison_amount'],1000)
        self.assertEqual(revenue['period_basis'],'3개월')
        self.assertEqual(value['fs_div'],'CFS')
        rows=self.rows(); rows[0]['thstrm_amount']='-'
        self.assertIsNone(financial_summary(rows,'00126380','2026','11012','CFS')['accounts'][0]['amount'])

    def test_wrong_company_and_ambiguous_accounts_are_not_used(self):
        rows=self.rows(); rows[0]['corp_code']='99999999'
        with self.assertRaises(DartError): financial_summary(rows,'00126380','2026','11012','CFS')
        rows=self.rows()*2
        self.assertEqual(financial_summary(rows,'00126380','2026','11012','CFS')['accounts'],[])

    def test_interim_cash_flow_compares_same_half_year_not_previous_year_end(self):
        row=dict(self.rows()[0], sj_div='CF', account_id='ifrs-full_CashFlowsFromUsedInOperatingActivities',
                 account_nm='영업활동현금흐름', thstrm_amount='1400', frmtrm_q_amount='900',
                 frmtrm_amount='2400', frmtrm_nm='제 56 기말')
        account=financial_summary([row],'00126380','2026','11012','CFS')['accounts'][0]
        self.assertEqual(account['comparison_amount'],900)
        self.assertEqual(account['comparison_name'],'제 56 기 반기')
        self.assertEqual(account['period_basis'],'누적')
        self.assertIsNone(account['ytd_amount'])
        row.pop('frmtrm_q_amount')
        self.assertIsNone(financial_summary([row],'00126380','2026','11012','CFS')['accounts'][0]['comparison_amount'])

    def test_annual_cash_flow_keeps_previous_annual_comparison(self):
        row=dict(self.rows()[0], reprt_code='11011', sj_div='CF', account_id='ifrs-full_CashFlowsFromUsedInOperatingActivities',
                 thstrm_amount='1400', frmtrm_amount='900', frmtrm_nm='제 56 기')
        account=financial_summary([row],'00126380','2026','11011','CFS')['accounts'][0]
        self.assertEqual(account['comparison_amount'],900)
        self.assertEqual(account['comparison_name'],'제 56 기')

    def test_research_selects_report_period_not_latest_old_correction(self):
        seen=[]
        def handler(req):
            seen.append(req)
            self.assertEqual(req.url.host,'opendart.fss.or.kr')
            self.assertEqual(req.url.params['crtfc_key'],KEY)
            if req.url.path.endswith('company.json'):
                return httpx.Response(200,json=dict(status='000',stock_code='005930',acc_mt='12',corp_name='삼성전자',corp_name_eng='Samsung Electronics'))
            if req.url.path.endswith('list.json'):
                rows=[dict(corp_code='00126380',stock_code='005930',rcept_no='20260901000001',rcept_dt='20260901',report_nm='[기재정정]사업보고서 (2025.12)'),
                      dict(corp_code='00126380',stock_code='005930',rcept_no='20260814000001',rcept_dt='20260814',report_nm='반기보고서 (2026.06)')]
                return httpx.Response(200,json=dict(status='000',list=rows,total_count=2))
            self.assertEqual(req.url.params['bsns_year'],'2026')
            self.assertEqual(req.url.params['reprt_code'],'11012')
            return httpx.Response(200,json=dict(status='000',list=self.rows()))
        client=self.client(handler)
        result=research([dict(code='005930',name='삼성전자')],KEY,client=client,codes={'005930':'00126380'},today=date(2026,9,15))
        self.assertEqual(result['stocks'][0]['financials']['report_code'],'11012')
        self.assertEqual(result['stocks'][0]['aliases'],['삼성전자','Samsung Electronics'])
        self.assertNotIn(KEY,json.dumps(result))
        self.assertEqual(len(seen),4)

    def test_unmatched_stock_is_missing_not_guessed_from_name(self):
        client=self.client(lambda req: self.fail('No request expected'))
        result=research([dict(code='0011T0',name='채비')],KEY,client=client,codes={},today=date(2026,9,15))
        self.assertEqual(result['stocks'][0]['status'],'missing')
        self.assertIsNone(result['stocks'][0]['financials'])

    def test_missing_consolidated_falls_back_to_separate_only(self):
        from unittest.mock import Mock
        client=Mock()
        client.json.side_effect=[dict(status='000',stock_code='005930',acc_mt='12'),
            dict(status='013',_fetched_at=0),
            dict(status='000',list=[dict(corp_code='00126380',rcept_no='20260814000001',rcept_dt='20260814',report_nm='반기보고서 (2026.06)')]),
            dict(status='013'),dict(status='000',list=self.rows(),_fetched_at=0)]
        result=research([dict(code='005930',name='삼성전자')],KEY,client=client,codes={'005930':'00126380'},today=date(2026,9,15))
        self.assertEqual(result['stocks'][0]['financials']['fs_div'],'OFS')
        self.assertEqual(client.json.call_count,5)
        self.assertEqual(client.json.call_args.kwargs['fs_div'],'OFS')

    def test_non_december_year_end_does_not_guess_financial_period(self):
        from unittest.mock import Mock
        client=Mock()
        client.json.side_effect=[dict(status='000',stock_code='005930',acc_mt='03'),dict(status='013',_fetched_at=0)]
        result=research([dict(code='005930',name='삼성전자')],KEY,client=client,codes={'005930':'00126380'},today=date(2026,9,15))
        self.assertIsNone(result['stocks'][0]['financials'])
        self.assertEqual(client.json.call_count,2)


if __name__ == '__main__': unittest.main()
