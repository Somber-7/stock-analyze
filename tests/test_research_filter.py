import unittest
from datetime import date

from backend.ai.research_filter import source_id, validate_source


class ResearchFilterTests(unittest.TestCase):
    def news_reason(self, name, code, title, content='기업 실적과 주가 관련 소식입니다.'):
        return validate_source(name=name,code=code,aliases=(),kind='news',title=title,content=content,
            published='2026-09-11T00:00:00+00:00',today=date(2026,9,15))

    def test_unicode_compatibility_forms_match_the_target_identity(self):
        reason=validate_source(name='ＡＢＣ테크',code='0011T0',aliases=(),kind='news',
            title='ABC테크 신규 수주',content='ABC테크가 신규 수주와 최근 실적을 발표했습니다.',
            published='2026-09-11T00:00:00+00:00',today=date(2026,9,15))
        self.assertIsNone(reason)

    def test_undated_official_report_uses_its_title_period(self):
        reason=validate_source(name='채비',code='0011T0',aliases=(),kind='reports',
            title='채비 반기보고서 (2026.06)',
            content='채비 반기보고서의 재무제표와 매출액 125억원, 영업이익 8억원 및 전기차 충전기 사업 현황입니다.',
            published=None,today=date(2026,9,15))
        self.assertIsNone(reason)

    def test_generic_official_report_shell_is_rejected(self):
        reason=validate_source(name='채비',code='0011T0',aliases=(),kind='reports',
            title='채비 공시',content='기업 공시 페이지입니다.',published=None,today=date(2026,9,15))
        self.assertEqual(reason,'thin_report')

    def test_actual_dart_navigation_shell_is_rejected(self):
        reason=validate_source(name='휴림로봇',code='090710',aliases=(),kind='reports',
            title='[휴림로봇] 분기보고서(일반법인)',
            content='본문선택 첨부파일 선택 PDF 저장 열기 다운로드 최종문서가 아니므로 투자판단에 유의하시기 바랍니다. 문서 목차 회사의 개요 사업의 내용 재무에 관한 사항',
            published='2026-09-11T00:00:00+00:00',today=date(2026,9,15))
        self.assertEqual(reason,'thin_report')

    def test_report_requires_financial_fact_not_just_financial_labels(self):
        reason=validate_source(name='휴림로봇',code='090710',aliases=(),kind='reports',
            title='[휴림로봇] 분기보고서 (2026.06)',
            content='휴림로봇의 매출액은 125억원이고 영업이익은 8억원입니다. 산업용 로봇 사업 현황을 설명합니다.',
            published=None,today=date(2026,9,15))
        self.assertIsNone(reason)

    def test_generic_result_title_accepts_target_at_document_heading(self):
        reason=validate_source(name='휴림로봇',code='090710',aliases=(),kind='reports',
            title='분기보고서 상세보기',
            content='[휴림로봇] 분기보고서\n매출액은 125억원이고 영업이익은 8억원입니다.',
            published='2026-09-11T00:00:00+00:00',today=date(2026,9,15))
        self.assertIsNone(reason)

    def test_short_generic_name_needs_a_company_anchor_in_news(self):
        reason=validate_source(name='채비',code='0011T0',aliases=(),kind='news',
            title='여행 갈 채비, 가을 준비물 안내',content='여행을 떠날 채비를 마친 시민들의 이야기입니다.',
            published='2026-09-11T00:00:00+00:00',today=date(2026,9,15))
        self.assertEqual(reason,'identity_mismatch')

    def test_short_company_name_with_business_anchor_is_allowed(self):
        reason=validate_source(name='채비',code='0011T0',aliases=(),kind='news',
            title='채비, 전기차 충전기 신규 수주',content='코스닥 기업 채비가 충전 인프라 공급 계약을 체결했습니다.',
            published='2026-09-11T00:00:00+00:00',today=date(2026,9,15))
        self.assertIsNone(reason)

    def test_short_ascii_name_does_not_match_affiliated_company_name(self):
        self.assertEqual(self.news_reason('SK','034730','SK하이닉스 반도체 실적 발표'),'identity_mismatch')
        self.assertEqual(self.news_reason('LG','003550','LG전자 신제품과 실적 발표'),'identity_mismatch')

    def test_short_ascii_name_accepts_exact_name_and_korean_particle(self):
        self.assertIsNone(self.news_reason('SK','034730','SK 실적 및 주가 전망'))
        self.assertIsNone(self.news_reason('SK','034730','SK는 신규 사업 투자를 발표'))
        self.assertIsNone(self.news_reason('SK','034730','SK의 실적 및 주가 전망'))

    def test_code_must_be_a_complete_alphanumeric_token(self):
        self.assertEqual(self.news_reason('채비','0011T0','시장 동향',content='기업 코드 A0011T09의 실적 소식입니다.'),'identity_mismatch')
        self.assertIsNone(self.news_reason('채비','0011T0','시장 동향',content='코스닥 종목 0011T0의 실적 소식입니다.'))

    def test_report_heading_short_name_does_not_match_affiliate(self):
        reason=validate_source(name='SK',code='034730',aliases=(),kind='reports',
            title='[SK하이닉스] 분기보고서 (2026.06)',content='매출액은 12조원이고 영업이익은 2조원입니다.',
            published=None,today=date(2026,9,15))
        self.assertEqual(reason,'identity_mismatch')

    def test_source_id_ignores_query_parameter_order(self):
        first=source_id('0011T0','news','https://example.com/a?b=2&a=1')
        second=source_id('0011T0','news','https://example.com/a?a=1&b=2')
        self.assertEqual(first,second)

    def test_related_stock_footer_is_not_company_evidence(self):
        reason=self.news_reason('채비','0011T0','전기차 냉각 기술 전시',
            '이브이엔솔은 냉각 장비를 공급할 계획입니다.\n## 관련종목\n채비 0011T0\n기아 000270')
        self.assertEqual(reason,'identity_mismatch')

    def test_company_title_does_not_rescue_unrelated_link_body(self):
        reason=self.news_reason('삼성전자','005930','삼성전자 AI 기술 개발',
            '* [급등 예상 종목 추천](https://example.com/a)\n* [지금 투자하세요](https://example.com/b)')
        self.assertEqual(reason,'thin_news')


if __name__=='__main__': unittest.main()
