import json
import unittest
import httpx


class WebSearchTests(unittest.TestCase):
    key='tvly-only-test-'+'x'*30
    stocks=[{'code':'005930','name':'삼성전자'}]

    def research(self, handler, **kwargs):
        from backend.ai.web_search import research
        with httpx.Client(transport=httpx.MockTransport(handler)) as http:
            return research(self.stocks,self.key,http=http,**kwargs)

    def test_search_uses_public_identifiers_and_returns_bounded_citable_sources(self):
        def handler(request):
            self.assertEqual(str(request.url),'https://api.tavily.com/search')
            self.assertEqual(request.headers['authorization'],'Bearer '+self.key)
            body=json.loads(request.content)
            self.assertIn('삼성전자',body['query'])
            self.assertNotIn(self.key,request.content.decode())
            self.assertFalse(body['include_raw_content'])
            self.assertFalse(body['include_answer'])
            self.assertEqual(body['search_depth'],'basic')
            self.assertEqual(body['language'],'ko')
            self.assertTrue(body['filter_by_language'])
            if body['topic']=='general': self.assertEqual(body['country'],'south korea')
            url='https://dart.fss.or.kr/dsaf001/main.do?rcpNo=202609110001' if body['topic']=='general' else 'https://news.example.com/article'
            content='삼성전자 반기보고서 매출액 12조원 영업이익 2조원 재무제표 사업 현황 '+'자료 '*1000
            return httpx.Response(200,json={'results':[{'title':'삼성전자 반기보고서 (2026.06)','url':url,'content':content,'published_date':'Fri, 11 Sep 2026 01:00:00 GMT'}], 'usage':{'credits':1}})
        result=self.research(handler)
        self.assertEqual(result['status'],'ready')
        self.assertEqual(len(result['searches']),2)
        self.assertEqual(result['usage_credits'],2)
        self.assertEqual(len(result['sources']),2)
        self.assertTrue(all(len(s['content'])<=900 for s in result['sources']))
        self.assertTrue(all(s['code']=='005930' and s['id'] for s in result['sources']))
        self.assertNotIn(self.key,json.dumps(result))

    def test_unsafe_urls_secret_echoes_and_non_official_reports_are_filtered(self):
        def handler(request):
            return httpx.Response(200,json={'results':[
                {'url':'javascript:alert(1)','title':'bad','content':'x'},
                {'url':'https://127.0.0.1/private','title':'bad','content':'x'},
                {'url':'https://user:pass@example.com','title':'bad','content':'x'},
                {'url':'https://safe.example.com','title':self.key,'content':'x'},
                {'url':'https://blog.example.com','title':'삼성전자 최근 뉴스','content':'삼성전자 반도체 사업의 최근 실적과 주요 소식입니다.','published_date':'2026-09-11'}]})
        result=self.research(handler)
        self.assertEqual(len(result['sources']),1)
        self.assertEqual(result['sources'][0]['kind'],'news')
        self.assertNotIn(self.key,json.dumps(result))

    def test_auth_failure_is_safe_and_does_not_retry(self):
        from backend.ai.web_search import SearchError
        calls=[]
        def handler(request):
            calls.append(1)
            return httpx.Response(401,json={'detail':self.key})
        with self.assertRaises(SearchError) as caught: self.research(handler)
        self.assertNotIn(self.key,str(caught.exception))
        self.assertLessEqual(len(calls),2)

    def test_partial_failure_and_empty_results_are_distinct(self):
        def handler(request):
            if json.loads(request.content)['topic']=='news': return httpx.Response(503,text=self.key)
            return httpx.Response(200,json={'results':[],'usage':{'credits':1}})
        result=self.research(handler)
        self.assertEqual(result['status'],'partial')
        self.assertFalse(result['sources'])
        self.assertTrue(result['diagnostics']['missing'])
        self.assertNotIn(self.key,str(result))

    def test_wrong_company_results_are_rejected_even_on_official_report_domain(self):
        def handler(request):
            body=json.loads(request.content)
            url='https://dart.fss.or.kr/dsaf001/main.do?rcpNo=202609110001' if body['topic']=='general' else 'https://news.example.com/wrong'
            return httpx.Response(200,json={'results':[{
                'url':url,'title':'하이브 주성엔지니어링 심팩 주요 소식',
                'content':'하이브와 주성엔지니어링, 심팩의 사업보고서와 매출액 영업이익 소식입니다.',
                'published_date':'2026-09-11T01:00:00Z'}], 'usage':{'credits':1}})
        result=self.research(handler)
        self.assertEqual(result['status'],'empty')
        self.assertEqual(result['sources'],[])
        self.assertGreaterEqual(result['diagnostics']['rejected']['identity_mismatch'],2)
        self.assertNotIn('하이브',json.dumps(result,ensure_ascii=False))

    def test_report_rejects_target_only_mentioned_after_another_issuer_heading(self):
        def handler(request):
            body=json.loads(request.content)
            if body['topic']=='news': return httpx.Response(200,json={'results':[],'usage':{'credits':1}})
            return httpx.Response(200,json={'results':[{
                'url':'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=202609110002',
                'title':'하이브 분기보고서 (2026.06)',
                'content':'하이브의 매출액은 1,200억원이며 협력사 삼성전자 관련 거래는 50억원입니다.',
                'published_date':'2026-09-11'}], 'usage':{'credits':1}})
        result=self.research(handler)
        self.assertFalse([s for s in result['sources'] if s['kind']=='reports'])
        self.assertGreaterEqual(result['diagnostics']['rejected']['identity_mismatch'],2)

    def test_validation_uses_only_the_content_that_can_be_stored(self):
        def handler(request):
            body=json.loads(request.content)
            if body['topic']=='general': return httpx.Response(200,json={'results':[],'usage':{'credits':1}})
            content='시장 일반 소식입니다. '*100+'삼성전자 매출액은 1조원입니다.'
            return httpx.Response(200,json={'results':[{'url':'https://news.example.com/late-target',
                'title':'시장 동향','content':content,'published_date':'2026-09-11'}], 'usage':{'credits':1}})
        result=self.research(handler)
        self.assertFalse([s for s in result['sources'] if s['kind']=='news'])

    def test_stale_future_and_undated_news_are_rejected_with_safe_diagnostics(self):
        def handler(request):
            if json.loads(request.content)['topic']=='general': return httpx.Response(200,json={'results':[],'usage':{'credits':1}})
            return httpx.Response(200,json={'results':[
                {'url':'https://news.example.com/old','title':'삼성전자 실적','content':'삼성전자 최근 실적과 사업 소식입니다.','published_date':'2025-01-01'},
                {'url':'https://news.example.com/future','title':'삼성전자 전망','content':'삼성전자 최근 실적과 사업 소식입니다.','published_date':'2027-01-01'},
                {'url':'https://news.example.com/undated','title':'삼성전자 뉴스','content':'삼성전자 최근 실적과 사업 소식입니다.'}], 'usage':{'credits':1}})
        result=self.research(handler)
        self.assertEqual(result['sources'],[])
        rejected=result['diagnostics']['rejected']
        self.assertGreaterEqual(rejected['stale'],1)
        self.assertGreaterEqual(rejected['future'],1)
        self.assertGreaterEqual(rejected['undated'],1)

    def test_empty_target_kind_gets_only_one_alternate_query(self):
        calls=[]
        def handler(request):
            calls.append(json.loads(request.content)['query'])
            return httpx.Response(200,json={'results':[],'usage':{'credits':1}})
        result=self.research(handler)
        self.assertEqual(len(calls),4)
        self.assertEqual(result['requested_queries'],4)
        self.assertEqual(len(set(calls)),4)

    def test_duplicate_urls_are_kept_once_with_deterministic_ids(self):
        def handler(request):
            body=json.loads(request.content)
            if body['topic']=='general': return httpx.Response(200,json={'results':[],'usage':{'credits':1}})
            row={'url':'https://news.example.com/samsung?b=2&a=1','title':'삼성전자 3분기 실적 발표',
                 'content':'삼성전자 매출액과 영업이익이 발표되었습니다. 반도체 사업 소식입니다.',
                 'published_date':'2026-09-11'}
            return httpx.Response(200,json={'results':[row,row],'usage':{'credits':1}})
        first=self.research(handler)
        second=self.research(handler)
        news=[s for s in first['sources'] if s['kind']=='news']
        self.assertEqual(len(news),1)
        self.assertEqual(news[0]['id'],[s for s in second['sources'] if s['kind']=='news'][0]['id'])

    def test_cache_reuses_public_results_and_key_rotation_requires_new_request(self):
        from backend.ai.web_search import SearchCache, research
        cache=SearchCache(ttl=900)
        calls=[]
        def handler(request):
            calls.append(1)
            return httpx.Response(200,json={'results':[],'usage':{'credits':1}})
        with httpx.Client(transport=httpx.MockTransport(handler)) as http:
            research(self.stocks,self.key,http=http,cache=cache)
            again=research(self.stocks,self.key,http=http,cache=cache)
            self.assertEqual(len(calls),4)
            self.assertEqual(again['usage_credits'],0)
            self.assertTrue(all(q['cached'] for q in again['searches']))
            research(self.stocks,'tvly-different-'+'y'*30,http=http,cache=cache)
            self.assertEqual(len(calls),8)

    def test_cancelled_research_never_calls_network(self):
        from backend.ai.web_search import SearchError
        def handler(request): self.fail('cancelled retrieval must not make a request')
        with self.assertRaises(SearchError): self.research(handler,cancelled=lambda:True)

    def test_syndicated_news_kept_once_after_boilerplate_cleanup(self):
        def handler(request):
            if json.loads(request.content)['topic']=='general': return httpx.Response(200,json={'results':[],'usage':{'credits':1}})
            body='삼성전자는 새로운 반도체 공급 계약을 발표했습니다. 매출 확대와 공장 투자 계획을 설명했습니다.'
            return httpx.Response(200,json={'results':[
                dict(url='https://news.example.com/a',title='삼성전자, 반도체 공급 계약 | 경제신문',content=body+'\n'+body+'\n관련종목 삼성전자 005930',published_date='2026-09-11'),
                dict(url='https://portal.example.com/b',title='삼성전자, 반도체 공급 계약',content=body,published_date='2026-09-11')], 'usage':{'credits':1}})
        result=self.research(handler)
        self.assertEqual(len(result['sources']),1)
        self.assertNotIn('관련종목',result['sources'][0]['content'])
        self.assertEqual(result['sources'][0]['content'].count('새로운 반도체'),1)
        self.assertEqual(result['diagnostics']['rejected']['duplicate'],1)

    def test_dart_financials_avoid_redundant_paid_report_search(self):
        from backend.ai.web_search import research
        calls=[]
        def handler(request):
            body=json.loads(request.content);calls.append(body)
            return httpx.Response(200,json={'results':[], 'usage':{'credits':1}})
        with httpx.Client(transport=httpx.MockTransport(handler)) as http:
            result=research([dict(code='005930',name='삼성전자',has_dart_financials=True)],self.key,http=http)
        self.assertEqual(len(calls),2)
        self.assertTrue(all(c['topic']=='news' for c in calls))
        self.assertFalse(any(m['kind']=='reports' for m in result['diagnostics']['missing']))


if __name__=='__main__': unittest.main()
