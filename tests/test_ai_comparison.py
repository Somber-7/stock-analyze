import unittest
from backend.ai.comparison import compare_decision, previous_analysis


class OpinionComparisonTests(unittest.TestCase):
    def row(self, **changes):
        return dict(code='005930',assessment='defer',target_quantity=25,current_quantity=25,
            reference_price=100,review_conditions='보유기간 확인',market_view='negative',
            decision_basis='preferences_missing',**changes)

    def test_changed_market_view_is_counted_even_when_quantity_stays(self):
        before=self.row();after=dict(before,market_view='positive')
        result=compare_decision(after,dict(decisions=[before]))
        self.assertTrue(result['changed'])
        self.assertTrue(result['market_view_changed'])
        self.assertEqual(result['previous_market_view'],'negative')

    def test_changed_deferral_reason_is_not_reported_as_identical(self):
        before=self.row();after=dict(before,decision_basis='data_missing')
        self.assertTrue(compare_decision(after,dict(decisions=[before]))['changed'])

    def test_legacy_missing_opinion_is_not_fabricated_or_counted_as_flip(self):
        before=self.row();del before['market_view'];del before['decision_basis']
        result=compare_decision(self.row(),dict(decisions=[before]))
        self.assertFalse(result['changed'])
        self.assertIsNone(result['previous_market_view'])

    def test_original_market_opinion_reaches_next_analysis_context(self):
        run=dict(id='previous',status='ready',comparison_scope='scope',completed_at='2026-09-15',
                 provider='openai',model='test',decisions=[self.row()])
        result=previous_analysis([run],'scope','current')
        self.assertEqual(result['decisions'][0]['market_view'],'negative')
        self.assertEqual(result['decisions'][0]['decision_basis'],'preferences_missing')
