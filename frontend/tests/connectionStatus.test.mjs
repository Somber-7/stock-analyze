import test from 'node:test'
import assert from 'node:assert/strict'
import { connectionStatus, withConnection } from '../src/lib/connectionStatus.js'

const now = Date.parse('2026-09-15T12:00:00Z')
test('saved keys and legacy checked_at never imply a verified connection', () => {
  assert.equal(connectionStatus({ has_key: true, checked_at: new Date(now).toISOString() }, now).label, '미확인')
  assert.equal(connectionStatus({ has_key: false }, now).label, '키 미등록')
  assert.equal(connectionStatus({ has_key: true, connection: { status: 'success' } }, now).label, '미확인')
})
test('confirmation describes only its scope and expires after 24 hours', () => {
  const record = { has_key: true, connection: { status: 'success', checked_at: new Date(now).toISOString(), scope: 'models' } }
  assert.equal(connectionStatus(record, now).detail, '인증·모델 목록 확인')
  assert.equal(connectionStatus(record, now + 86400001).label, '재확인 필요')
  assert.equal(connectionStatus(record, now + 86400001).tone, 'stale')
})
test('new checking or failed results replace old success without changing other services', () => {
  const settings = { profiles: { openai: { has_key: true, model: 'model' } }, tools: { tavily: { has_key: true }, dart: { enabled: false } } }
  const checking = withConnection(settings, 'tavily', { status: 'checking', scope: 'usage' })
  assert.equal(connectionStatus(checking.tools.tavily, now).label, '확인 중')
  const failed = withConnection(checking, 'tavily', { status: 'error', scope: 'usage', checked_at: new Date(now).toISOString() })
  assert.equal(connectionStatus(failed.tools.tavily, now).tone, 'error')
  assert.equal(failed.profiles, settings.profiles)
  assert.equal(failed.tools.dart, settings.tools.dart)
  assert.equal(settings.tools.tavily.connection, undefined)
})
