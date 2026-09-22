import json
import unittest

import httpx

from backend.ai.providers import ProviderError


class GenerationTests(unittest.TestCase):
    key = 'test-secret-api-key-123456789'
    context = {'stocks': [{'code': '005930', 'name': '삼성전자', 'price': 70000}],
               'cash': 1000000, 'positions': [{'code': '005930', 'quantity': 2}]}

    def analysis(self):
        return {'summary': '제공 시세 기준 보유 유지', 'risks': ['시세 변동'],
                'decisions': [{'code': '005930', 'target_quantity': 2, 'rationale': '불필요한 매매 방지',
                               'assessment':'supported', 'source_ids':[], 'review_conditions':'추세와 수급 방향이 달라질 때 재검토',
                               'market_view':'mixed','headline':'추세와 수급이 엇갈려 현재 수량 유지','decision_basis':'sufficient'}]}

    def test_web_citations_must_belong_to_the_same_stock(self):
        from backend.ai.generation import generate
        result = self.analysis()
        result['decisions'][0]['source_ids'] = ['005930-news-1']
        context = dict(self.context,web_research=dict(sources=[dict(id='005930-news-1',code='005930')]))
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200,json=self.envelope('openai',result)))) as client:
            self.assertEqual(generate('openai',self.key,'test-model',context,'분석',http=client)['analysis']['decisions'][0]['source_ids'],['005930-news-1'])
            context['web_research']['sources'][0]['code'] = '000660'
            with self.assertRaises(ProviderError): generate('openai',self.key,'test-model',context,'분석',http=client)

    def test_dart_citation_without_web_search_must_match_stock(self):
        from backend.ai.generation import generate
        result=self.analysis()
        source='005930-dart-20260814000001'
        result['decisions'][0]['source_ids']=[source]
        context=dict(self.context,dart_research=dict(sources=[dict(id=source,code='005930')]))
        with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,json=self.envelope('openai',result)))) as client:
            self.assertEqual(generate('openai',self.key,'test-model',context,'분석',http=client)['analysis']['decisions'][0]['source_ids'],[source])
            context['dart_research']['sources'][0]['code']='000660'
            with self.assertRaises(ProviderError): generate('openai',self.key,'test-model',context,'분석',http=client)

    def test_unsupported_cash_flow_improvement_never_returns_an_actionable_report(self):
        from backend.ai.generation import generate
        result=self.analysis()
        result['decisions'][0]['rationale']='영업현금흐름은 전년보다 크게 개선됐다.'
        context=dict(self.context,dart_research=dict(stocks=[dict(code='005930',financials=dict(accounts=[
            dict(name='영업활동 현금흐름',amount=100,comparison_amount=None,period_basis='누적',currency='KRW',period_name='당기',comparison_name='')]))]))
        calls=[]
        def handler(req):
            calls.append(req)
            return httpx.Response(200,json=self.envelope('openai',result))
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaisesRegex(ProviderError,'재무 비교 근거') as error:
                generate('openai',self.key,'test-model',context,'분석',http=client)
        self.assertEqual(len(calls),1)
        self.assertEqual(error.exception.usage,dict(input_tokens=100,output_tokens=30))
        self.assertEqual(error.exception.issue['code'],'005930')
        self.assertEqual(error.exception.issue['text'],result['decisions'][0]['rationale'])
        self.assertIn('005930',str(error.exception))
        self.assertNotIn(self.key,str(error.exception.issue))

    def envelope(self, provider, analysis=None):
        value = json.dumps(self.analysis() if analysis is None else analysis, ensure_ascii=False)
        if provider == 'openai':
            return {'id': 'resp_test', 'status': 'completed', 'error': None, 'incomplete_details': None,
                    'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
                                'content': [{'type': 'output_text', 'text': value, 'annotations': []}]}],
                    'usage': {'input_tokens': 100, 'output_tokens': 30, 'total_tokens': 130}}
        if provider == 'anthropic':
            return {'id': 'msg_test', 'type': 'message', 'role': 'assistant', 'stop_reason': 'end_turn',
                    'content': [{'type': 'text', 'text': value}],
                    'usage': {'input_tokens': 100, 'output_tokens': 30}}
        return {'candidates': [{'index': 0, 'finishReason': 'STOP',
                                'content': {'role': 'model', 'parts': [{'text': value}]}}],
                'usageMetadata': {'promptTokenCount': 100, 'candidatesTokenCount': 25,
                                  'thoughtsTokenCount': 5, 'totalTokenCount': 130}}

    def call(self, provider, handler, **kwargs):
        try:
            from backend.ai.generation import generate
        except ImportError:
            self.fail('Generation adapter has not been implemented')
        with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
            return generate(provider, kwargs.pop('key', self.key), kwargs.pop('model', 'model-test'),
                            kwargs.pop('context', self.context), kwargs.pop('objective', '보유 자산 분석'),
                            http=client, **kwargs)

    def test_all_providers_use_fixed_endpoints_header_credentials_and_structured_output(self):
        endpoints = {'openai': 'https://api.openai.com/v1/responses',
                     'anthropic': 'https://api.anthropic.com/v1/messages',
                     'gemini': 'https://generativelanguage.googleapis.com/v1beta/models/model-test:generateContent'}
        for provider in endpoints:
            with self.subTest(provider=provider):
                def handle(request):
                    self.assertEqual(str(request.url), endpoints[provider])
                    self.assertEqual(request.method, 'POST')
                    self.assertEqual(request.extensions['timeout']['read'], 120)
                    self.assertNotIn(self.key, request.content.decode())
                    body = json.loads(request.content)
                    self.assertNotIn('tools', body)
                    if provider == 'openai':
                        self.assertEqual(request.headers['authorization'], 'Bearer ' + self.key)
                        self.assertFalse(body['store'])
                        self.assertTrue(body['text']['format']['strict'])
                        self.assertEqual(body['text']['format']['type'], 'json_schema')
                        self.assertEqual(body['model'], 'model-test')
                        schema = body['text']['format']['schema']
                    elif provider == 'anthropic':
                        self.assertEqual(request.headers['x-api-key'], self.key)
                        self.assertEqual(request.headers['anthropic-version'], '2023-06-01')
                        self.assertEqual(body['output_config']['format']['type'], 'json_schema')
                        schema = body['output_config']['format']['schema']
                    else:
                        self.assertEqual(request.headers['x-goog-api-key'], self.key)
                        self.assertEqual(body['generationConfig']['responseMimeType'], 'application/json')
                        schema = body['generationConfig']['responseJsonSchema']
                    self.assertFalse(schema['additionalProperties'])
                    self.assertIn('005930', json.dumps(schema))
                    self.assertIn('보유 자산 분석', json.dumps(body, ensure_ascii=False))
                    return httpx.Response(200, json=self.envelope(provider))
                self.assertEqual(self.call(provider, handle),
                                 {'analysis': self.analysis(), 'usage': {'input_tokens': 100, 'output_tokens': 30}})

    def test_strict_validation_rejects_unsafe_quantities_extra_fields_and_universe_escape(self):
        invalid = []
        for qty in [-1, 1.5, 2.0, True, '2', None, 1000000001]:
            value = self.analysis(); value['decisions'][0]['target_quantity'] = qty; invalid.append(value)
        for code in ['000660', '../bad', '5930', 5930]:
            value = self.analysis(); value['decisions'][0]['code'] = code; invalid.append(value)
        for field, replacement in [('summary', ''), ('summary', 'x' * 4001), ('risks', 'risk'),
                                   ('risks', ['x' * 1001]), ('risks', ['x'] * 11), ('decisions', [])]:
            value = self.analysis(); value[field] = replacement; invalid.append(value)
        value = self.analysis(); value['secret'] = 'unexpected'; invalid.append(value)
        value = self.analysis(); value['decisions'][0]['side'] = 'buy'; invalid.append(value)
        value = self.analysis(); value['decisions'][0]['rationale'] = 'x' * 2001; invalid.append(value)
        value = self.analysis(); value['decisions'] *= 2; invalid.append(value)
        value = self.analysis(); value['decisions'] *= 11; invalid.append(value)
        for provider in ['openai', 'anthropic', 'gemini']:
            for value in invalid:
                with self.subTest(provider=provider, value=repr(value)[:100]):
                    with self.assertRaises(ProviderError):
                        self.call(provider, lambda r: httpx.Response(200, json=self.envelope(provider, value)))

    def test_zero_and_maximum_total_quantity_are_valid_without_an_arbitrary_money_cap(self):
        for qty in [0, 1000000000]:
            value = self.analysis(); value['decisions'][0]['target_quantity'] = qty
            result = self.call('openai', lambda r: httpx.Response(200, json=self.envelope('openai', value)))
            self.assertEqual(result['analysis']['decisions'][0]['target_quantity'], qty)

    def test_defer_requires_unchanged_holdings_and_explicit_assessment(self):
        context = {'stocks':[{'code':'005930'}], 'portfolio':{'holdings':[{'code':'005930','quantity':2}]}}
        value = self.analysis(); value['decisions'][0]['assessment'] = 'defer'
        value['decisions'][0]['decision_basis'] = 'mixed_evidence'
        result = self.call('openai',lambda r: httpx.Response(200,json=self.envelope('openai',value)),context=context)
        self.assertEqual(result['analysis']['decisions'][0]['assessment'],'defer')
        value['decisions'][0]['target_quantity'] = 3
        with self.assertRaises(ProviderError):
            self.call('openai',lambda r: httpx.Response(200,json=self.envelope('openai',value)),context=context)
        for field in ('assessment','review_conditions','source_ids'):
            missing = self.analysis(); del missing['decisions'][0][field]
            with self.assertRaises(ProviderError):
                self.call('openai',lambda r: httpx.Response(200,json=self.envelope('openai',missing)))

    def test_refusal_incomplete_and_nontext_actions_never_produce_analysis(self):
        cases = []
        for status in ['incomplete', 'failed', 'queued', None]:
            value = self.envelope('openai'); value['status'] = status; cases.append(('openai', value))
        value = self.envelope('openai'); value['output'][0]['content'].append({'type': 'refusal', 'refusal': self.key}); cases.append(('openai', value))
        value = self.envelope('openai'); value['output'].append({'type': 'function_call', 'name': 'trade'}); cases.append(('openai', value))
        for stop in ['max_tokens', 'refusal', 'tool_use', 'pause_turn', None]:
            value = self.envelope('anthropic'); value['stop_reason'] = stop; cases.append(('anthropic', value))
        for reason in ['MAX_TOKENS', 'SAFETY', 'RECITATION', None]:
            value = self.envelope('gemini'); value['candidates'][0]['finishReason'] = reason; cases.append(('gemini', value))
        value = self.envelope('gemini'); value['promptFeedback'] = {'blockReason': 'SAFETY'}; cases.append(('gemini', value))
        value = self.envelope('gemini'); value['candidates'][0]['content']['parts'].append({'functionCall': {'name': 'trade'}}); cases.append(('gemini', value))
        for provider, payload in cases:
            with self.subTest(provider=provider, payload=payload):
                with self.assertRaises(ProviderError) as caught:
                    self.call(provider, lambda r: httpx.Response(200, json=payload))
                self.assertNotIn(self.key, str(caught.exception))

    def test_http_errors_are_safe_no_retry_or_redirect_even_with_injected_client(self):
        for status in [301, 307, 400, 401, 403, 429, 500]:
            requests = []
            def handle(request):
                requests.append(request)
                return httpx.Response(status, headers={'location': 'https://untrusted.example/leak'},
                                      text=self.key)
            with self.subTest(status=status):
                with self.assertRaises(ProviderError) as caught:
                    self.call('openai', handle)
                self.assertEqual(len(requests), 1)
                self.assertNotIn(self.key, str(caught.exception))

    def test_malformed_oversized_and_secret_echo_response_are_rejected(self):
        echoed = self.analysis(); echoed['summary'] = self.key
        for response in [httpx.Response(200, text='not json'), httpx.Response(200, json=[]),
                         httpx.Response(200, json={'output': None}),
                         httpx.Response(200, content=b' ' * (2 * 1024 * 1024 + 1)),
                         httpx.Response(200, json=self.envelope('openai', echoed))]:
            with self.assertRaises(ProviderError) as caught:
                self.call('openai', lambda r: response)
            self.assertNotIn(self.key, str(caught.exception))

    def test_input_validation_precedes_any_http_call(self):
        def no_request(request):
            self.fail('Invalid input must never reach the network')
        cases = [{'provider': 'unknown'}, {'model': '../escape'}, {'model': 'models/a'},
                 {'model': 'a?key=bad'}, {'model': self.key}, {'key': 'bad\nheader'},
                 {'context': {'stocks': []}}, {'context': {'stocks': [{'code': '../bad'}]}},
                 {'context': dict(self.context, secret=self.key)}, {'objective': self.key}]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ProviderError):
                    self.call(kwargs.pop('provider', 'gemini'), no_request, **kwargs)

    def test_network_timeout_is_generalized(self):
        def handle(request):
            raise httpx.ReadTimeout(self.key, request=request)
        with self.assertRaises(ProviderError) as caught:
            self.call('openai', handle)
        self.assertNotIn(self.key, str(caught.exception))

    def test_usage_missing_or_invalid_is_not_reported_as_real_consumption(self):
        value = self.envelope('openai'); value.pop('usage')
        result = self.call('openai', lambda r: httpx.Response(200, json=value))
        self.assertEqual(result['usage'], {'input_tokens': None, 'output_tokens': None})
        value['usage'] = {'input_tokens': True, 'output_tokens': -1}
        result = self.call('openai', lambda r: httpx.Response(200, json=value))
        self.assertEqual(result['usage'], {'input_tokens': None, 'output_tokens': None})

    def test_missing_selected_symbol_is_rejected(self):
        context = dict(self.context, stocks=[{'code': '005930'}, {'code': '000660'}])
        with self.assertRaises(ProviderError):
            self.call('openai', lambda r: httpx.Response(200, json=self.envelope('openai')), context=context)

    def test_alphanumeric_domestic_stock_code_is_supported_by_every_provider(self):
        value = self.analysis()
        value['decisions'][0]['code'] = '0011T0'
        context = dict(self.context, stocks=[{'code': '0011T0', 'name': '채비'}])
        for provider in ['openai', 'anthropic', 'gemini']:
            with self.subTest(provider=provider):
                result = self.call(provider, lambda r: httpx.Response(200, json=self.envelope(provider, value)), context=context)
                self.assertEqual(result['analysis']['decisions'][0]['code'], '0011T0')

    def test_malformed_nested_envelopes_always_fail_with_safe_provider_error(self):
        cases = [('gemini', {'promptFeedback': None}),
                 ('gemini', {'candidates': [None]}),
                 ('gemini', {'candidates': {'0': 'bad'}}),
                 ('anthropic', {'stop_reason': 'end_turn', 'content': [None]}),
                 ('openai', {'status': 'completed', 'output': [None]})]
        for provider, payload in cases:
            with self.subTest(provider=provider, payload=payload):
                with self.assertRaises(ProviderError):
                    self.call(provider, lambda r: httpx.Response(200, json=payload))

    def test_oversize_stream_stops_reading_and_closes_without_waiting_for_whole_body(self):
        class Oversize(httpx.SyncByteStream):
            closed = False
            def __iter__(self):
                yield b' ' * (2 * 1024 * 1024)
                yield b'x'
                raise AssertionError('Adapter must stop once response exceeds cap')
            def close(self):
                self.closed = True
        stream = Oversize()
        with self.assertRaises(ProviderError):
            self.call('openai', lambda r: httpx.Response(200, stream=stream))
        self.assertTrue(stream.closed)


if __name__ == '__main__':
    unittest.main()
