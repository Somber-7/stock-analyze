import test from 'node:test'
import assert from 'node:assert/strict'
import { selectAnalysisRun } from '../src/lib/analysisSelection.js'

test('a briefing link outside the returned 50 runs never opens another account or paper report', () => {
  const history = Array.from({ length: 50 }, (_, i) => ({ id: `other-${i}`, mode: 'paper' }))
  assert.equal(selectAnalysisRun(history, 'older-matching-live-run'), null)
  assert.equal(selectAnalysisRun([], 'deleted-run'), null)
})

test('explicit selection is retained as new reports arrive; latest is only the default', () => {
  const matching = { id: 'matching', mode: 'live' }
  const history = [{ id: 'latest', mode: 'paper' }, matching]
  assert.equal(selectAnalysisRun(history, 'matching'), matching)
  assert.equal(selectAnalysisRun(history, null), history[0])
  assert.equal(selectAnalysisRun([], null), null)
})
