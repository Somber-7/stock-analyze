import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.ai.api import router, get_ai_settings
from backend.ai.providers import ProviderError
from backend.ai.settings import AISettings, SettingsError, protect


class ConnectionStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'ai.enc'
        self.store = AISettings(self.path, fetch_models=lambda *_: [])
        self.key = 'sk-test-' + 'x' * 35

    def version(self): return self.store.snapshot()['version']

    def test_saved_key_is_unverified_and_failure_survives_restart(self):
        self.store.save('openai', '', self.key, 0)
        self.assertEqual(self.store.snapshot()['profiles']['openai']['connection']['status'], 'unverified')
        self.store.check('openai', self.version())
        def fail(*_):
            current = self.store.snapshot()['profiles']['openai']
            self.assertEqual(current['connection']['status'], 'checking')
            self.assertIsNone(current['checked_at'])
            raise ProviderError('API 인증 실패')
        self.store.fetch_models = fail
        with self.assertRaises(ProviderError): self.store.check('openai', self.version())
        result = AISettings(self.path).snapshot()['profiles']['openai']
        self.assertEqual(result['connection']['status'], 'error')
        self.assertEqual(result['connection']['scope'], 'models')
        self.assertEqual(result['connection']['message'], 'API 인증 실패')
        self.assertTrue(result['connection']['checked_at'])
        self.assertIsNone(result['checked_at'])
        self.assertTrue(result['has_key'])

    def test_key_replacement_and_deletion_reset_status_but_model_edit_preserves(self):
        self.store.save('openai', '', self.key, 0)
        self.store.check('openai', self.version())
        self.store.save('openai', 'gpt-test', None, self.version())
        self.assertEqual(self.store.snapshot()['profiles']['openai']['connection']['status'], 'success')
        self.store.save('openai', 'gpt-test', 'sk-other-'+'y'*35, self.version())
        result = self.store.snapshot()['profiles']['openai']['connection']
        self.assertEqual(result['status'], 'unverified')
        self.assertIsNone(result['checked_at'])
        self.store.check('openai', self.version())
        self.store.delete('openai', self.version())
        self.assertEqual(self.store.snapshot()['profiles']['openai']['connection']['status'], 'unverified')

    def test_stale_success_and_failure_cannot_mark_replaced_key(self):
        for failure in (False, True):
            with self.subTest(failure=failure):
                self.store.save('openai', '', self.key, self.version())
                def fetch(*_):
                    self.store.save('openai', '', 'sk-other-'+'y'*35, self.version())
                    if failure: raise ProviderError('old key failure')
                    return []
                self.store.fetch_models = fetch
                with self.assertRaises((SettingsError, ProviderError)):
                    self.store.check('openai', self.version())
                result = self.store.snapshot()['profiles']['openai']['connection']
                self.assertEqual(result['status'], 'unverified')
                self.assertIsNone(result['checked_at'])

    def test_unrelated_save_during_check_does_not_leave_checking_forever(self):
        self.store.save('openai', '', self.key, 0)
        def fetch(*_):
            self.store.save_tavily('tvly-test-'+'t'*30, self.version())
            return []
        self.store.fetch_models = fetch
        with self.assertRaises(SettingsError): self.store.check('openai', self.version())
        self.assertEqual(self.store.snapshot()['profiles']['openai']['connection']['status'], 'unverified')

    def test_legacy_success_migrates_read_only_and_interrupted_check_is_unverified(self):
        state = dict(version=8, provider='openai', profiles={
            name: dict(key=self.key if name == 'openai' else '', model='', models=[],
                       checked_at='2026-01-01T00:00:00+00:00' if name == 'openai' else None)
            for name in ('openai', 'anthropic', 'gemini')})
        self.path.write_bytes(b'DPAPI1:' + base64.b64encode(protect(json.dumps(state).encode())))
        before = self.path.read_bytes()
        result = self.store.snapshot()
        self.assertEqual(result['profiles']['openai']['connection']['status'], 'success')
        self.assertEqual(result['tools']['tavily']['connection']['status'], 'unverified')
        self.assertEqual(before, self.path.read_bytes())
        state['profiles']['openai'].update(checked_at=None, connection=dict(
            status='checking', checked_at='2026-01-01T00:00:00+00:00', message='', scope='models'))
        self.path.write_bytes(b'DPAPI1:' + base64.b64encode(protect(json.dumps(state).encode())))
        self.assertEqual(AISettings(self.path).snapshot()['profiles']['openai']['connection']['status'], 'unverified')

    def test_domain_error_cannot_echo_credential(self):
        self.store.save('openai', '', self.key, 0)
        def fail(*_): raise SettingsError('upstream echoed ' + self.key)
        self.store.fetch_models = fail
        with self.assertRaises(SettingsError) as error: self.store.check('openai', self.version())
        self.assertNotIn(self.key, str(error.exception))
        self.assertNotIn(self.key, json.dumps(AISettings(self.path).snapshot()))

    def test_dart_failure_records_attempt_and_changed_key_resets(self):
        from backend.ai.dart_client import DartError
        self.store.save_dart('a'*40, False, 0)
        with patch('backend.ai.dart_client.check_key', side_effect=DartError('DART 인증 실패')):
            with self.assertRaises(SettingsError): self.store.check_dart(self.version())
        result = AISettings(self.path).snapshot()['tools']['dart']
        self.assertEqual(result['connection']['status'], 'error')
        self.assertEqual(result['connection']['scope'], 'company')
        self.assertTrue(result['connection']['checked_at'])
        self.store.save_dart('b'*40, False, self.version())
        self.assertEqual(self.store.snapshot()['tools']['dart']['connection']['status'], 'unverified')

    def test_tavily_check_route_guard_version_failure_and_success(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_ai_settings] = lambda: self.store
        with TestClient(app) as client:
            self.store.save_tavily('tvly-test-'+'t'*30, 0)
            path = '/api/ai/tools/tavily/check'
            self.assertEqual(client.post(path, json={'version':self.version()}).status_code, 422)
            self.assertEqual(client.post(path, json={'version':0}, headers={'X-AI-Action':'manage'}).status_code, 400)
            from backend.ai.connection_check import ConnectionCheckError
            with patch('backend.ai.connection_check.check_tavily', side_effect=ConnectionCheckError('Tavily 인증 실패')):
                response = client.post(path, json={'version':self.version()}, headers={'X-AI-Action':'manage'})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(AISettings(self.path).snapshot()['tools']['tavily']['connection']['status'], 'error')
            with patch('backend.ai.connection_check.check_tavily'):
                response = client.post(path, json={'version':self.version()}, headers={'X-AI-Action':'manage'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['tools']['tavily']['connection']['scope'], 'usage')
            self.assertEqual(response.json()['tools']['tavily']['connection']['status'], 'success')
            self.store.save_tavily('tvly-changed-'+'u'*30, self.version())
            self.assertEqual(self.store.snapshot()['tools']['tavily']['connection']['status'], 'unverified')

    def test_each_provider_success_exposes_only_metadata_scope(self):
        for name in ('openai', 'anthropic', 'gemini'):
            with self.subTest(provider=name):
                self.store.save(name, '', self.key, self.version())
                result = self.store.check(name, self.version())['profiles'][name]
                self.assertEqual(result['connection']['status'], 'success')
                self.assertEqual(result['connection']['scope'], 'models')
                self.assertEqual(result['connection']['checked_at'], result['checked_at'])
                self.assertNotIn(self.key, json.dumps(result))

    def test_tool_blank_preserves_verification_delete_and_stale_result_reset(self):
        for tool in ('tavily', 'dart'):
            target = 'backend.ai.connection_check.check_tavily' if tool == 'tavily' else 'backend.ai.dart_client.check_key'
            save = (lambda key: self.store.save_tavily(key, self.version())) if tool == 'tavily' else (
                lambda key: self.store.save_dart(key, False, self.version()))
            check = getattr(self.store, 'check_'+tool)
            delete = getattr(self.store, 'delete_'+tool)
            with self.subTest(tool=tool):
                key = 'tvly-test-'+'t'*30 if tool == 'tavily' else 'a'*40
                replacement = 'tvly-other-'+'u'*30 if tool == 'tavily' else 'b'*40
                save(key)
                with patch(target): check(self.version())
                save('')
                self.assertEqual(self.store.snapshot()['tools'][tool]['connection']['status'], 'success')
                def replace(*_):
                    self.assertEqual(self.store.snapshot()['tools'][tool]['connection']['status'], 'checking')
                    with self.assertRaises(SettingsError): check(self.version())
                    save(replacement)
                with patch(target, side_effect=replace):
                    with self.assertRaises(SettingsError): check(self.version())
                self.assertEqual(self.store.snapshot()['tools'][tool]['connection']['status'], 'unverified')
                with patch(target): check(self.version())
                delete(self.version())
                result = self.store.snapshot()['tools'][tool]
                self.assertFalse(result['has_key'])
                self.assertEqual(result['connection']['status'], 'unverified')
                self.assertIsNone(result['connection']['checked_at'])

    def test_get_settings_never_checks_network_or_modifies_saved_file(self):
        self.store.save('openai', '', self.key, 0)
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_ai_settings] = lambda: self.store
        before = self.path.read_bytes()
        def forbidden(*_): self.fail('GET /settings must not access network')
        self.store.fetch_models = forbidden
        with patch('backend.ai.connection_check.check_tavily', side_effect=forbidden), patch('backend.ai.dart_client.check_key', side_effect=forbidden):
            with TestClient(app) as client:
                self.assertEqual(client.get('/api/ai/settings').status_code, 200)
        self.assertEqual(self.path.read_bytes(), before)


class TavilyUsageTests(unittest.TestCase):
    key = 'tvly-test-' + 't'*30

    def call(self, handler):
        from backend.ai.connection_check import check_tavily
        with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as http:
            return check_tavily(self.key, http=http)

    def test_check_only_gets_fixed_usage_endpoint_with_header_credentials(self):
        def handle(request):
            self.assertEqual(str(request.url), 'https://api.tavily.com/usage')
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.content, b'')
            self.assertEqual(request.headers['authorization'], 'Bearer '+self.key)
            self.assertLessEqual(request.extensions['timeout']['read'], 15)
            return httpx.Response(200, json={'key':{'usage':150,'limit':1000},'account':{'current_plan':'Bootstrap'}})
        self.call(handle)

    def test_null_usage_limit_is_valid_without_fabricating_available_quota(self):
        result = self.call(lambda _: httpx.Response(200, json={
            'key': {'usage': 150, 'limit': None, 'search_usage': 100},
            'account': {'current_plan': 'Bootstrap', 'plan_usage': 500,
                        'plan_limit': 15000, 'paygo_limit': None}}))
        self.assertIsNone(result)

    def test_usage_remains_required_and_finite_when_limit_is_null(self):
        from backend.ai.connection_check import ConnectionCheckError
        invalid_keys = [
            {'usage': 150}, {'usage': 150, 'limit': 'unlimited'},
            {'usage': None, 'limit': None}, {'usage': True, 'limit': None},
            {'usage': -1, 'limit': None}, {'usage': float('inf'), 'limit': None},
            {'usage': float('nan'), 'limit': None}, {'limit': None}]
        for key in invalid_keys:
            with self.subTest(key=key):
                with self.assertRaises(ConnectionCheckError):
                    self.call(lambda _: httpx.Response(200, text=json.dumps({'key': key, 'account': {}})))

    def test_errors_redirects_malformed_and_oversized_responses_are_safe(self):
        from backend.ai.connection_check import ConnectionCheckError
        for status, body in [(401, self.key), (403, self.key), (429, self.key), (500, self.key),
                             (302, self.key), (200, 'not json'), (200, '{}'), (200, '['),
                             (200, 'x'*70000), (200, '{"key":{"usage":true,"limit":3},"account":{}}')]:
            with self.subTest(status=status, length=len(body)):
                seen = []
                def handle(request):
                    seen.append(request)
                    return httpx.Response(status, text=body, headers={'location':'https://evil.example/leak'})
                with self.assertRaises(ConnectionCheckError) as error: self.call(handle)
                self.assertNotIn(self.key, str(error.exception))
                self.assertEqual(len(seen), 1)

    def test_transport_failure_never_echoes_request(self):
        from backend.ai.connection_check import ConnectionCheckError
        def handle(request): raise httpx.ReadTimeout(self.key, request=request)
        with self.assertRaises(ConnectionCheckError) as error: self.call(handle)
        self.assertNotIn(self.key, str(error.exception))

    def test_created_client_disables_environment_proxies(self):
        from backend.ai.connection_check import check_tavily
        original_client = httpx.Client
        def client(**options):
            self.assertFalse(options['trust_env'])
            self.assertFalse(options['follow_redirects'])
            return original_client(**options, transport=httpx.MockTransport(lambda _: httpx.Response(
                200, json={'key':{'usage':0,'limit':1000},'account':{}})))
        with patch('backend.ai.connection_check.httpx.Client', side_effect=client):
            check_tavily(self.key)
