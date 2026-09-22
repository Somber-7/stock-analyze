"""Market evidence can be informative without authorizing a quantity change."""
import copy
import unittest

from pydantic import ValidationError
from backend.ai.generation import Analysis


class DecisionBriefTests(unittest.TestCase):
    def payload(self):
        return dict(summary='재무와 가격 약세를 우선 점검하세요.', risks=['영업현금흐름이 음수입니다.'],
            decisions=[dict(code='005930',target_quantity=25,assessment='defer',source_ids=[],
                market_view='negative',decision_basis='preferences_missing',
                headline='가격 약세·현금 유출이 확인되나 축소 수량은 보유기간 확인 후 검토',
                rationale='20구간 하락과 영업현금흐름 유출이 함께 관측됩니다.',
                review_conditions='수량을 정하기 위해 보유기간을 확인하세요.')])

    def test_negative_evidence_and_quantity_deferral_are_independent(self):
        result=Analysis.model_validate(self.payload())
        self.assertEqual(result.decisions[0].market_view,'negative')
        self.assertEqual(result.decisions[0].assessment,'defer')

    def test_new_response_requires_explicit_brief_and_deferral_reason(self):
        for field in ('market_view','headline','decision_basis'):
            value=self.payload(); del value['decisions'][0][field]
            with self.assertRaises(ValidationError): Analysis.model_validate(value)

    def test_brief_field_budgets_reject_long_repetitive_output(self):
        value=self.payload()
        for field,limit in (('headline',120),('rationale',600),('review_conditions',240)):
            invalid=copy.deepcopy(value);invalid['decisions'][0][field]='가'*(limit+1)
            with self.assertRaises(ValidationError): Analysis.model_validate(invalid)
        value['summary']='가'*351
        with self.assertRaises(ValidationError): Analysis.model_validate(value)
        value=self.payload();value['risks']=['위험']*5
        with self.assertRaises(ValidationError): Analysis.model_validate(value)

    def test_defer_cannot_claim_sufficient_quantity_basis(self):
        value=self.payload();value['decisions'][0]['decision_basis']='sufficient'
        with self.assertRaises(ValidationError): Analysis.model_validate(value)
        value=self.payload();value['decisions'][0]['assessment']='supported'
        with self.assertRaises(ValidationError): Analysis.model_validate(value)

    def test_unknown_and_positive_are_distinct_from_mixed_evidence(self):
        for view in ('unknown','mixed','positive'):
            value=self.payload();value['decisions'][0]['market_view']=view
            self.assertEqual(Analysis.model_validate(value).decisions[0].market_view,view)


if __name__=='__main__': unittest.main()
