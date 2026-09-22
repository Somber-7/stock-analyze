import json
import tempfile
import unittest
from pathlib import Path

from backend.ai.settings import AISettings, SettingsError, protect, unprotect


class AISettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'ai.enc'
        self.key = 'sk-test-only-' + 'x'*35
        self.calls = []
        def models(provider, key):
            self.calls.append((provider, key))
            return [{'id': 'gpt-test', 'name': 'gpt-test'}]
        self.models = models
        self.store = AISettings(self.path, fetch_models=models)

    def save(self, provider='openai', key=None, model=''):
        return self.store.save(provider, model, key, self.store.snapshot()['version'])

    def test_encrypted_save_restart_and_public_state_never_returns_key(self):
        self.save(key=self.key, model='gpt-test')
        self.assertNotIn(self.key.encode(), self.path.read_bytes())
        fresh = AISettings(self.path, fetch_models=self.models)
        state = fresh.snapshot()
        self.assertTrue(state['profiles']['openai']['has_key'])
        self.assertEqual(state['profiles']['openai']['model'], 'gpt-test')
        self.assertNotIn(self.key, json.dumps(state))
        fresh.check('openai', state['version'])
        self.assertEqual(self.calls, [('openai', self.key)])

    def test_dart_key_encryption_toggle_blank_preserve_delete(self):
        key='a'*40
        self.save(key=self.key)
        self.store.save_dart(key,True,self.store.snapshot()['version'])
        self.assertNotIn(key.encode(),self.path.read_bytes())
        self.assertNotIn(key,json.dumps(self.store.snapshot()))
        self.store.save_dart('',False,self.store.snapshot()['version'])
        self.assertTrue(self.store.snapshot()['tools']['dart']['has_key'])
        self.assertIsNone(self.store.dart_credentials())
        self.store.save_dart(None,True,self.store.snapshot()['version'])
        self.assertEqual(self.store.dart_credentials()['key'],key)
        self.store.delete_dart(self.store.snapshot()['version'])
        self.assertFalse(self.store.snapshot()['tools']['dart']['enabled'])
        self.assertTrue(self.store.snapshot()['profiles']['openai']['has_key'])

    def test_dart_check_failure_clears_previous_success(self):
        from unittest.mock import patch
        from backend.ai.dart_client import DartError
        self.store.save_dart('a'*40,True,0)
        with patch('backend.ai.dart_client.check_key'):
            self.store.check_dart(self.store.snapshot()['version'])
        self.assertIsNotNone(self.store.snapshot()['tools']['dart']['checked_at'])
        with patch('backend.ai.dart_client.check_key',side_effect=DartError('DART 인증 실패')):
            with self.assertRaises(SettingsError): self.store.check_dart(self.store.snapshot()['version'])
        self.assertIsNone(self.store.snapshot()['tools']['dart']['checked_at'])

    def test_blank_preserves_key_switch_keeps_profiles_delete_removes(self):
        self.save(key=self.key)
        self.save(key='')
        self.save('anthropic', 'sk-ant-test-'+'y'*30, 'claude-test')
        self.save(model='gpt-test')
        state = self.store.snapshot()
        self.assertTrue(state['profiles']['anthropic']['has_key'])
        self.store.delete('openai', state['version'])
        state = AISettings(self.path).snapshot()
        self.assertFalse(state['profiles']['openai']['has_key'])
        self.assertTrue(state['profiles']['anthropic']['has_key'])

    def test_stale_save_and_changed_key_inflight_check_do_not_overwrite(self):
        self.save(key=self.key)
        with self.assertRaises(SettingsError): self.store.save('openai', '', None, 0)
        old = self.store.snapshot()['version']
        def fetch(provider, key):
            self.save(key='sk-changed-'+'y'*35)
            return self.models(provider, key)
        self.store.fetch_models = fetch
        with self.assertRaises(SettingsError): self.store.check('openai', old)
        self.assertIsNone(self.store.snapshot()['profiles']['openai']['checked_at'])

    def test_failure_does_not_erase_saved_keys_or_claim_verified(self):
        self.save(key=self.key)
        self.store.check('openai', self.store.snapshot()['version'])
        def fail(*_): raise SettingsError('연결 실패')
        self.store.fetch_models = fail
        with self.assertRaises(SettingsError): self.store.check('openai', self.store.snapshot()['version'])
        state = self.store.snapshot()
        self.assertTrue(state['profiles']['openai']['has_key'])
        self.assertIsNone(state['profiles']['openai']['checked_at'])

    def test_corrupt_storage_fails_closed_and_is_not_overwritten(self):
        self.path.write_bytes(b'corrupted')
        with self.assertRaises(SettingsError): self.store.snapshot()
        with self.assertRaises(SettingsError): self.save(key=self.key)
        self.assertEqual(self.path.read_bytes(), b'corrupted')

    def test_file_import_only_openai_unambiguous_and_does_not_expose_key(self):
        source = Path(self.tmp.name)/'Api_Key.txt'
        source.write_text('App Secret: namuh-secret\nOpen AI Secret: '+self.key, encoding='utf-8')
        state = self.store.import_openai(source, 0)
        self.assertTrue(state['profiles']['openai']['has_key'])
        self.assertNotIn(self.key, json.dumps(state))
        source.write_text(self.key+'\nsk-different-'+'z'*30, encoding='utf-8')
        with self.assertRaises(SettingsError): self.store.import_openai(source, state['version'])

    def test_windows_cipher_roundtrip_and_invalid_key(self):
        encrypted = protect(b'private-test')
        self.assertNotIn(b'private-test', encrypted)
        self.assertEqual(unprotect(encrypted), b'private-test')
        for key in ('short', 'sk-hello\n'+'x'*25, '가'*30):
            with self.assertRaises(SettingsError): self.save(key=key)


if __name__ == '__main__': unittest.main()
