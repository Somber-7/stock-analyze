import unittest
import httpx


class ProviderTests(unittest.TestCase):
    key = 'test-secret-api-key-123456789'

    def call(self, provider, handler, key=None):
        from backend.ai.providers import list_models
        with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as http:
            return list_models(provider, key or self.key, http=http)

    def test_openai_lists_only_text_candidates_with_header_auth(self):
        def handle(request):
            self.assertEqual(str(request.url), 'https://api.openai.com/v1/models')
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.content, b'')
            self.assertEqual(request.headers['authorization'], 'Bearer ' + self.key)
            self.assertEqual(request.extensions['timeout']['read'], 15)
            return httpx.Response(200, json={'object': 'list', 'data': [
                {'id': name, 'object': 'model', 'created': 1, 'owned_by': 'openai'}
                for name in ['gpt-4.1', 'o3', 'gpt-4o-audio-preview', 'gpt-realtime',
                             'gpt-image-1', 'text-embedding-3-small', 'tts-1',
                             'gpt-4o-transcribe', 'o4-mini', 'gpt-4.1']
            ]})
        self.assertEqual(self.call('openai', handle), [
            {'id': 'gpt-4.1', 'name': 'gpt-4.1'}, {'id': 'o3', 'name': 'o3'},
            {'id': 'o4-mini', 'name': 'o4-mini'}])

    def test_anthropic_paginates_with_fixed_host_and_required_headers(self):
        seen = []
        def handle(request):
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.url.host, 'api.anthropic.com')
            self.assertEqual(request.url.path, '/v1/models')
            self.assertEqual(request.headers['x-api-key'], self.key)
            self.assertEqual(request.headers['anthropic-version'], '2023-06-01')
            self.assertEqual(request.url.params['limit'], '1000')
            cursor = request.url.params.get('after_id')
            seen.append(cursor)
            model = 'claude-sonnet-test' if cursor is None else 'claude-opus-test'
            return httpx.Response(200, json={'data': [
                {'id': model, 'display_name': 'Claude Test', 'type': 'model', 'created_at': '2026-01-01T00:00:00Z'}
            ], 'first_id': model, 'last_id': model, 'has_more': cursor is None})
        self.assertEqual(self.call('anthropic', handle), [
            {'id': 'claude-sonnet-test', 'name': 'Claude Test'},
            {'id': 'claude-opus-test', 'name': 'Claude Test'}])
        self.assertEqual(seen, [None, 'claude-sonnet-test'])

    def test_gemini_paginates_and_filters_capabilities_without_query_key(self):
        seen = []
        def handle(request):
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.url.host, 'generativelanguage.googleapis.com')
            self.assertEqual(request.url.path, '/v1beta/models')
            self.assertEqual(request.headers['x-goog-api-key'], self.key)
            self.assertNotIn(self.key, str(request.url))
            self.assertNotIn('key', request.url.params)
            self.assertEqual(request.url.params['pageSize'], '1000')
            cursor = request.url.params.get('pageToken')
            seen.append(cursor)
            if cursor is None:
                return httpx.Response(200, json={'models': [
                    {'name': 'models/gemini-test', 'displayName': 'Gemini Test', 'supportedGenerationMethods': ['generateContent']},
                    {'name': 'models/embedding-test', 'supportedGenerationMethods': ['embedContent']}
                ], 'nextPageToken': 'next+/='})
            return httpx.Response(200, json={'models': [
                {'name': 'models/gemma-test', 'supportedGenerationMethods': ['generateContent']}
            ]})
        self.assertEqual(self.call('gemini', handle), [
            {'id': 'gemini-test', 'name': 'Gemini Test'}, {'id': 'gemma-test', 'name': 'gemma-test'}])
        self.assertEqual(seen, [None, 'next+/='])

    def test_errors_and_redirects_never_expose_response_or_follow_redirects(self):
        from backend.ai.providers import ProviderError
        for status in [301, 400, 401, 403, 429, 500]:
            with self.subTest(status=status):
                seen = []
                def handle(request):
                    seen.append(request)
                    return httpx.Response(status, headers={'location': 'https://evil.example/leak'},
                                          text=self.key + ' upstream debug details')
                with self.assertRaises(ProviderError) as error:
                    self.call('openai', handle)
                self.assertNotIn(self.key, str(error.exception))
                self.assertNotIn('upstream debug details', str(error.exception))
                self.assertEqual(len(seen), 1)

    def test_transport_and_json_failures_are_safe(self):
        from backend.ai.providers import ProviderError
        def timeout(request):
            raise httpx.ReadTimeout(self.key, request=request)
        for handler in [timeout, lambda _: httpx.Response(200, text=self.key)]:
            with self.assertRaises(ProviderError) as error:
                self.call('openai', handler)
            self.assertNotIn(self.key, str(error.exception))
            self.assertIsNone(error.exception.__cause__)
            self.assertTrue(error.exception.__suppress_context__)

    def test_malformed_payloads_are_rejected(self):
        from backend.ai.providers import ProviderError
        cases = [('openai', []), ('openai', {}), ('openai', {'data': {}}),
                 ('openai', {'data': [None]}), ('openai', {'data': [{'id': 123}]}),
                 ('openai', {'data': [{'id': 'gpt-bad\nvalue'}]}),
                 ('openai', {'data': [{'id': 'gpt-' + 'x' * 160}]}),
                 ('openai', {'data': [{'id': 'gpt-test'}] * 1001}),
                 ('anthropic', {'data': [], 'has_more': 'false'}),
                 ('anthropic', {'data': [], 'has_more': True, 'last_id': None}),
                 ('gemini', {'models': [], 'nextPageToken': 42}),
                 ('gemini', {'models': [{'name': 'models/gemini-test', 'supportedGenerationMethods': 'generateContent'}]})]
        for provider, payload in cases:
            with self.subTest(provider=provider, payload=repr(payload)[:100]):
                with self.assertRaises(ProviderError):
                    self.call(provider, lambda _: httpx.Response(200, json=payload))

    def test_upstream_key_echo_never_reaches_output_or_url(self):
        from backend.ai.providers import ProviderError
        cases = [('openai', {'data': [{'id': 'gpt-' + self.key}]}),
                 ('anthropic', {'data': [{'id': 'claude-test', 'display_name': self.key}], 'has_more': False}),
                 ('gemini', {'models': [], 'nextPageToken': self.key})]
        for provider, payload in cases:
            with self.subTest(provider=provider):
                with self.assertRaises(ProviderError) as error:
                    self.call(provider, lambda _: httpx.Response(200, json=payload))
                self.assertNotIn(self.key, str(error.exception))

    def test_pagination_is_bounded_and_repeated_cursors_rejected(self):
        from backend.ai.providers import ProviderError
        for repeat in [False, True]:
            seen = []
            def handle(request):
                seen.append(request)
                return httpx.Response(200, json={'models': [], 'nextPageToken': 'same' if repeat else str(len(seen))})
            with self.assertRaises(ProviderError):
                self.call('gemini', handle)
            self.assertEqual(len(seen), 2 if repeat else 10)

    def test_invalid_provider_or_key_never_sends_request(self):
        from backend.ai.providers import ProviderError, list_models
        with httpx.Client(transport=httpx.MockTransport(lambda _: self.fail('unexpected request'))) as http:
            for provider, key in [('other', self.key), ('openai', ''), ('openai', 'key\r\nheader'), ('openai', '한글')]:
                with self.subTest(provider=provider, key=key):
                    with self.assertRaises(ProviderError):
                        list_models(provider, key, http=http)

    def test_valid_empty_response_returns_empty_list(self):
        for provider, payload in [('openai', {'data': []}), ('anthropic', {'data': [], 'has_more': False}), ('gemini', {'models': []})]:
            with self.subTest(provider=provider):
                self.assertEqual(self.call(provider, lambda _: httpx.Response(200, json=payload)), [])
