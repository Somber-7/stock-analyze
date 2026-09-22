import base64
import json
import tempfile
import unittest
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.ai.api import router, get_ai_settings
from backend.ai.settings import AISettings, protect, unprotect
from backend.ai.providers import ProviderError


class AIApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = AISettings(Path(self.tmp.name)/'ai.enc', fetch_models=lambda *_: [{'id':'gpt-test','name':'gpt-test'}])
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_ai_settings] = lambda: self.store
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.key = 'sk-only-test-'+'x'*35

    def post(self, path, body):
        return self.client.post('/api/ai'+path, json=body, headers={'X-AI-Action':'manage'})

    def body(self): return dict(provider='openai', model='', api_key=self.key, version=self.store.snapshot()['version'])

    def test_no_echo_in_success_validation_or_unknown_fields(self):
        for change in ({'version':'invalid'}, {'provider':'invalid'}, {'model':self.key}, {'unexpected':self.key}):
            response = self.post('/settings', {**self.body(), **change})
            self.assertGreaterEqual(response.status_code, 400)
            self.assertNotIn(self.key, response.text)
        response = self.post('/settings', self.body())
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.key, response.text)
        self.assertNotIn(self.key, self.client.get('/api/ai/settings').text)

    def test_guard_and_connection_then_delete(self):
        self.assertEqual(self.client.post('/api/ai/settings', json=self.body()).status_code, 422)
        self.post('/settings', self.body())
        response = self.post('/openai/check', {'version':self.store.snapshot()['version']})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['profiles']['openai']['models'][0]['id'], 'gpt-test')
        response = self.post('/openai/delete-key', {'version':response.json()['version']})
        self.assertFalse(response.json()['profiles']['openai']['has_key'])

    def test_dart_routes_do_not_echo_key_and_bad_inputs(self):
        from unittest.mock import patch
        key='a'*40
        for body in (dict(api_key=key,enabled='yes',version=0),dict(api_key=key,enabled=True,version='bad')):
            response=self.post('/tools/dart/settings',body)
            self.assertEqual(response.status_code,422)
            self.assertNotIn(key,response.text)
        result=self.post('/tools/dart/settings',dict(api_key=key,enabled=True,version=0))
        self.assertEqual(result.status_code,200)
        self.assertNotIn(key,result.text)
        with patch('backend.ai.dart_client.check_key'):
            result=self.post('/tools/dart/check',dict(version=result.json()['version']))
        self.assertEqual(result.status_code,200)
        self.assertTrue(result.json()['tools']['dart']['checked_at'])
        result=self.post('/tools/dart/delete-key',dict(version=result.json()['version']))
        self.assertFalse(result.json()['tools']['dart']['has_key'])

    def test_error_response_is_safe_and_failed_check_clears_badge(self):
        self.post('/settings', self.body())
        def fail(*_): raise ProviderError('API 인증 실패')
        self.store.fetch_models = fail
        response = self.post('/openai/check', {'version':self.store.snapshot()['version']})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn(self.key, response.text)
        state = self.client.get('/api/ai/settings').json()
        self.assertTrue(state['profiles']['openai']['has_key'])
        self.assertIsNone(state['profiles']['openai']['checked_at'])

    def test_tavily_save_encrypted_restart_replace_and_delete_preserves_ai(self):
        ai = self.post('/settings', {**self.body(), 'model': 'gpt-test'}).json()
        key = 'tvly-test-only-' + 't'*35
        response = self.post('/tools/tavily/settings', dict(api_key=key, version=ai['version']))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn(key, response.text)
        self.assertNotIn(key.encode(), self.store.path.read_bytes())
        fresh = AISettings(self.store.path).snapshot()
        self.assertTrue(fresh['tools']['tavily']['has_key'])
        self.assertEqual(fresh['profiles'], ai['profiles'])
        self.assertEqual(fresh['provider'], ai['provider'])
        replacement = 'tvly-test-replacement-' + 'r'*30
        response = self.post('/tools/tavily/settings', dict(api_key=replacement, version=fresh['version']))
        self.assertEqual(response.status_code, 200)
        # A real encrypted-file roundtrip verifies replacement, without a public secret getter.
        stored = json.loads(unprotect(base64.b64decode(self.store.path.read_bytes()[7:])))
        self.assertEqual(stored['tools']['tavily']['key'], replacement)
        self.assertNotIn(key, json.dumps(stored))
        response = self.post('/tools/tavily/delete-key', dict(version=response.json()['version']))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['tools']['tavily']['has_key'])
        self.assertEqual(self.store.credentials()['key'], self.key)
        self.assertEqual(response.json()['profiles'], ai['profiles'])

    def test_tavily_blank_preserves_key_and_stale_or_invalid_requests_do_not_mutate(self):
        key = 'tvly-test-only-' + 't'*35
        saved = self.post('/tools/tavily/settings', dict(api_key=key, version=0))
        self.assertEqual(saved.status_code, 200, saved.text)
        saved = self.post('/tools/tavily/settings', dict(api_key='  ', version=saved.json()['version']))
        self.assertEqual(saved.status_code, 200)
        self.assertTrue(saved.json()['tools']['tavily']['has_key'])
        version = saved.json()['version']
        for change in ({'version':0}, {'version':True}, {'api_key':'short'},
                       {'api_key':self.key}, {'api_key':key+'\nextra'},
                       {'api_key':123}, {'unexpected':key}):
            response = self.post('/tools/tavily/settings', dict(api_key=key, version=version) | change)
            self.assertGreaterEqual(response.status_code, 400)
            self.assertNotIn(key, response.text)
            self.assertEqual(self.store.snapshot()['version'], version)
        denied = self.client.post('/api/ai/tools/tavily/settings', json=dict(api_key=key, version=version))
        self.assertEqual(denied.status_code, 422)
        self.assertNotIn(key, denied.text)
        self.assertGreaterEqual(self.post('/tools/tavily/delete-key', {'version':0}).status_code, 400)
        self.assertTrue(self.store.snapshot()['tools']['tavily']['has_key'])
        self.assertNotIn(key, self.client.get('/api/ai/settings').text)

    def test_legacy_settings_load_without_tools_and_ai_saves_preserve_tavily(self):
        legacy = dict(version=8, provider='openai', profiles={
            name: dict(key=self.key if name == 'openai' else '', model='gpt-test' if name == 'openai' else '',
                       models=[], checked_at=None) for name in ('openai','anthropic','gemini')})
        self.store.path.write_bytes(b'DPAPI1:' + base64.b64encode(protect(json.dumps(legacy).encode())))
        response = self.client.get('/api/ai/settings')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['tools']['tavily']['has_key'])
        self.assertEqual(response.json()['tools']['tavily']['connection']['status'], 'unverified')
        self.assertFalse(response.json()['tools']['dart']['has_key'])
        self.assertFalse(response.json()['tools']['dart']['enabled'])
        self.assertIsNone(response.json()['tools']['dart']['checked_at'])
        self.assertEqual(response.json()['tools']['dart']['connection']['status'], 'unverified')
        self.assertEqual(self.store.credentials()['key'], self.key)
        saved = self.post('/tools/tavily/settings', dict(api_key='tvly-test-only-'+'t'*35, version=8))
        self.assertEqual(saved.status_code, 200)
        self.post('/settings', self.body())
        self.assertTrue(self.store.snapshot()['tools']['tavily']['has_key'])

    def test_tavily_key_pasted_into_model_is_not_echoed(self):
        key = 'tvly-test-only-'+'t'*35
        response = self.post('/settings', {**self.body(), 'model':key})
        self.assertGreaterEqual(response.status_code, 400)
        self.assertNotIn(key, response.text)
        self.assertNotIn(key, self.client.get('/api/ai/settings').text)


if __name__ == '__main__': unittest.main()
