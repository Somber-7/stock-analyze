import copy
import unittest

from backend.ai import generation


class ReportEvidenceTests(unittest.TestCase):
    def financials(self, previous=None):
        return dict(accounts=[dict(name='영업활동 현금흐름',amount=1400,comparison_amount=previous,
            ytd_amount=None,comparison_ytd_amount=None,currency='KRW',period_basis='누적',
            period_name='제 58 기 반기',comparison_name='제 57 기 반기')])

    def guard(self, text, previous=None):
        from backend.ai.evidence import validate_financial_claims
        context=dict(stocks=[dict(code='005930',name='삼성전자')],
            dart_research=dict(stocks=[dict(code='005930',financials=self.financials(previous))]))
        validate_financial_claims(dict(summary='',risks=[],decisions=[dict(code='005930',rationale=text)]),context)

    def test_missing_cashflow_comparison_cannot_support_report_claim(self):
        self.assertTrue(hasattr(generation,'validate_financial_claims'),'Generation must validate financial comparisons')
        with self.assertRaisesRegex(ValueError,'비교'):
            self.guard('반기 연결 매출·영업이익 및 누적 영업현금흐름은 비교기간보다 크게 개선됐다.')

    def test_present_comparison_must_support_the_claimed_direction(self):
        from backend.ai.evidence import validate_financial_claims
        self.assertTrue(callable(validate_financial_claims))
        self.guard('영업현금흐름은 전년보다 개선됐다.',900)
        with self.assertRaisesRegex(ValueError,'비교'):
            self.guard('영업현금흐름은 전년보다 개선됐다.',1900)

    def test_unknown_future_condition_and_positive_level_are_not_comparisons(self):
        for text in ('영업현금흐름은 양수다.', '영업현금흐름 개선 여부는 비교값이 없어 미확인이다.',
                     '영업현금흐름 개선 근거가 부족하다.', '영업현금흐름 개선은 확인이 필요하다.',
                     '다음 보고서에서 영업현금흐름이 개선되면 재검토한다.',
                     '영업현금흐름이 양수인 반면 가격은 하락했다.'):
            self.guard(text)

    def test_summary_is_also_checked_for_named_company(self):
        from backend.ai.evidence import validate_financial_claims
        context=dict(stocks=[dict(code='005930',name='삼성전자')],dart_research=dict(stocks=[dict(code='005930',financials=self.financials())]))
        with self.assertRaises(ValueError):
            validate_financial_claims(dict(summary='삼성전자 영업현금흐름 개선이 확인됐다.',risks=[],decisions=[]),context)

    def test_unrelated_subject_and_negated_comparison_are_not_rejected(self):
        for text in ('영업현금흐름은 1400억원이며 차입금은 증가했다.',
                     '영업현금흐름 개선을 단정할 수 없다.',
                     '영업현금흐름은 개선되지 않았다.'):
            self.guard(text,1900)

    def test_mixed_periods_and_profit_transitions(self):
        from backend.ai.evidence import validate_financial_claims
        accounts=[dict(name=name,amount=current,comparison_amount=previous,ytd_amount=ytd,
            comparison_ytd_amount=prior_ytd,period_basis='3개월',currency='KRW',period_name='당기',comparison_name='전기')
            for name,current,previous,ytd,prior_ytd in [('매출액',100,120,190,220),('영업이익',20,10,30,40)]]
        context=dict(stocks=[dict(code='005930',name='삼성전자')],dart_research=dict(stocks=[dict(code='005930',financials=dict(accounts=accounts))]))
        def check(text): validate_financial_claims(dict(decisions=[dict(code='005930',rationale=text)]),context)
        check('누적 매출액은 감소했고 3개월 영업이익은 증가했다.')
        with self.assertRaises(ValueError): check('3개월 영업이익은 흑자 전환했다.')
        accounts[1]['comparison_amount']=-10
        check('3개월 영업이익은 흑자 전환했다.')
        with self.assertRaises(ValueError): check('3개월 영업이익은 적자로 전환했다.')

    def test_cash_outflow_growth_means_a_more_negative_balance(self):
        from backend.ai.evidence import validate_financial_claims
        financials=self.financials(-8391349895)
        financials['accounts'][0]['amount']=-14171742806
        context=dict(stocks=[dict(code='0011T0',name='채비')],dart_research=dict(stocks=[dict(code='0011T0',financials=financials)]))
        def check(text): validate_financial_claims(dict(decisions=[dict(code='0011T0',rationale=text)]),context)
        check('영업현금흐름의 유출이 증가했다.')
        check('영업현금흐름은 전년보다 악화됐다.')
        with self.assertRaises(ValueError): check('영업현금흐름의 유출이 감소했다.')

    def test_ambiguous_prose_is_not_treated_as_a_direct_account_comparison(self):
        for text in ('영업현금흐름은 음수로, 매수 위험이 증가했다.',
                     '영업현금흐름과 별개로 외국인 순매수가 증가했다.',
                     '영업현금흐름 개선 없이 매수하기 어렵다.',
                     '영업현금흐름은 개선됐는지 확인해야 한다.',
                     '영업현금흐름 개선이 필요하다.', '영업현금흐름 개선 시 재검토한다.',
                     '영업현금흐름 개선 가능성이 있다.'):
            self.guard(text)

    def test_rejection_identifies_account_and_exact_field_without_guessing(self):
        from backend.ai.evidence import validate_financial_claims
        context=dict(stocks=[dict(code='005930',name='삼성전자')],dart_research=dict(stocks=[dict(code='005930',financials=self.financials())]))
        with self.assertRaises(ValueError) as error:
            validate_financial_claims(dict(decisions=[dict(code='005930',headline='영업현금흐름은 개선됐다.')]),context)
        self.assertEqual(error.exception.issue['code'],'005930')
        self.assertEqual(error.exception.issue['field'],'headline')
        self.assertEqual(error.exception.issue['account'],'영업활동 현금흐름')
        self.assertEqual(error.exception.issue['text'],'영업현금흐름은 개선됐다.')

    def test_evidence_has_distinct_periods_and_missing_does_not_become_zero(self):
        from backend.ai.evidence import financial_evidence
        values=financial_evidence(dict(accounts=[dict(name='매출액',currency='KRW',period_basis='3개월',
            amount=120,ytd_amount=210,comparison_amount=100,comparison_ytd_amount=None,
            period_name='이번 반기',comparison_name='전년 반기')]))
        self.assertEqual(values[0]['period_basis'],'3개월')
        self.assertEqual(values[0]['change_pct'],20)
        self.assertEqual(values[1]['period_basis'],'누적')
        self.assertEqual(values[1]['status'],'comparison_missing')
        self.assertIsNone(values[1]['change_pct'])

    def test_account_weights_and_review_levels_use_only_verified_inputs(self):
        from backend.ai.evidence import enrich_context
        context=dict(portfolio=dict(total_assets=2000,cash_balance=900,available_cash=850,
            holdings=[dict(code='005930',eval_amount=700),dict(code='000660',eval_amount=400)]),
            stocks=[dict(code='005930',holding_eval_amount=700,account_weight_pct=35,
                data_quality=dict(requires_defer=False),metrics=dict(sma_20=110,sma_60=120),
                price_basis=dict(daily_close=100,daily_date='2026-09-15'))])
        enrich_context(context)
        self.assertEqual(context['portfolio']['allocation']['cash_weight_pct'],45)
        self.assertEqual(context['portfolio']['allocation']['unselected_stock_weight_pct'],20)
        point=context['stocks'][0]['review_points'][0]
        self.assertEqual(point['level'],110)
        self.assertEqual(point['direction'],'above')
        self.assertIn('20봉',point['text'])
        self.assertIn('110',point['text'])
        missing=copy.deepcopy(context);missing['portfolio']['total_assets']=None
        missing['stocks'][0]['data_quality']['requires_defer']=True
        enrich_context(missing)
        self.assertIsNone(missing['portfolio']['allocation']['cash_weight_pct'])
        self.assertEqual(missing['stocks'][0]['review_points'],[])


if __name__=='__main__': unittest.main()
