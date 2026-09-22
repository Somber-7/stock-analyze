import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createKey, clearKey } from '../frontend/src/lib/paperRequests.mjs'

test('unconfirmed order A retains its key after successful order B', () => {
  const values = new Map()
  const storage = { getItem: k => values.get(k), setItem: (k, v) => values.set(k, v) }
  const a = { code: '005930', quantity: 1 }
  const b = { code: '000660', quantity: 1 }
  const first = createKey(storage, '/orders', a)
  const second = createKey(storage, '/orders', b)
  clearKey(storage, '/orders', b, second)
  assert.equal(createKey(storage, '/orders', a), first)
  clearKey(storage, '/orders', a, first)
  assert.notEqual(createKey(storage, '/orders', a), first)
})
