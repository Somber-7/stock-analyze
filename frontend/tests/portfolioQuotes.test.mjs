import test from 'node:test'
import assert from 'node:assert/strict'
import { loadPortfolioQuotes } from '../src/lib/portfolioQuotes.js'
import { formatKoreanClock } from '../src/lib/koreanClock.js'

test('deduplicates domestic codes, excludes CMA and bounds simultaneous requests', async () => {
  let active = 0, maximum = 0
  const calls = [], results = []
  await loadPortfolioQuotes(['005930', '005930', 'NHKRCMA030', '000660', '0011T0', '005380', '035420'], async code => {
    calls.push(code); active++; maximum = Math.max(maximum, active)
    await new Promise(resolve => setTimeout(resolve, 5)); active--
    return { code, price: 10000, change_rate: -.2 }
  }, (code, quote) => results.push({ code, quote }), new AbortController().signal)
  assert.equal(calls.length, 5)
  assert.ok(maximum <= 3)
  assert.equal(results.length, 5)
  assert.equal(results[0].quote.change_rate, -.2)
  assert.equal(results[0].quote.price, 10000)
})

test('partial failures never replace a missing percentage with zero or mix mismatched symbols', async () => {
  const results = {}
  await loadPortfolioQuotes(['005930', '000660', '0011T0'], async code => {
    if (code === '005930') return { code, price: 9000, change_rate: null }
    if (code === '000660') throw new Error('private upstream text')
    return { code: '999999', price: 3, change_rate: 4 }
  }, (code, quote) => { results[code] = quote }, new AbortController().signal)
  assert.equal(results['005930'].status, 'partial')
  assert.equal(results['005930'].change_rate, null)
  assert.equal(results['000660'].status, 'error')
  assert.equal(results['0011T0'].status, 'error')
  assert.equal(JSON.stringify(results).includes('private'), false)
})

test('aborted view cannot publish late responses or start remaining requests', async () => {
  const controller = new AbortController(), results = [], calls = []
  await loadPortfolioQuotes(['005930', '000660', '0011T0', '005380'], async code => {
    calls.push(code); controller.abort()
    return { code, price: 100, change_rate: 2 }
  }, (...args) => results.push(args), controller.signal)
  assert.equal(results.length, 0)
  assert.equal(calls.length, 1)
})

test('clock uses Korean time through midnight and year rollover', () => {
  const before = formatKoreanClock(new Date('2026-12-31T14:59:59Z'))
  const after = formatKoreanClock(new Date('2026-12-31T15:00:00Z'))
  assert.equal(before.date, '2026.12.31 (목)')
  assert.equal(before.time, '23:59:59')
  assert.equal(after.date, '2027.01.01 (금)')
  assert.equal(after.time, '00:00:00')
})
