import test from 'node:test'
import assert from 'node:assert/strict'
import { addToast, showToast, subscribeToasts } from '../src/lib/toast.js'

const item = (id, message, tone = 'info') => ({ id, message, tone })

test('a repeated message replaces its earlier copy instead of stacking', () => {
  const list = addToast([item(1, '저장했습니다'), item(2, '실패', 'error')], item(3, '저장했습니다'))
  assert.deepEqual(list.map(t => t.id), [2, 3])
  assert.equal(addToast([item(1, '같은 문구')], item(2, '같은 문구', 'error')).length, 2)
})

test('over the limit the oldest info toast leaves before any error', () => {
  const list = addToast([item(1, 'e1', 'error'), item(2, 'i1'), item(3, 'e2', 'error'), item(4, 'i2')], item(5, 'i3'))
  assert.deepEqual(list.map(t => t.id), [1, 3, 4, 5])
  const errors = addToast([item(1, 'e1', 'error'), item(2, 'e2', 'error')], item(3, 'i1'), 2)
  assert.deepEqual(errors.map(t => t.id), [2, 3])
})

test('showToast ignores empty text, normalizes tone and stops after unsubscribe', () => {
  const seen = []
  const stop = subscribeToasts(toast => seen.push(toast))
  showToast('')
  showToast('  ')
  showToast(' 추가했습니다 ')
  showToast('실패', { tone: 'error' })
  showToast('알 수 없음', { tone: 'warning' })
  stop()
  showToast('구독 해제 후')
  assert.deepEqual(seen.map(t => [t.message, t.tone]), [['추가했습니다', 'info'], ['실패', 'error'], ['알 수 없음', 'info']])
})
