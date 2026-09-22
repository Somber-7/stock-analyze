import test from 'node:test'
import assert from 'node:assert/strict'
import { excerpt, marketAssessment, quantityDecision } from '../src/lib/analysisReport.js'

test('excerpts preserve source text and visibly mark truncation without splitting Unicode', () => {
  assert.deepEqual(excerpt('짧은 원문', 10), { text: '짧은 원문', truncated: false })
  assert.deepEqual(excerpt('하락📉 가능성', 3), { text: '하락📉…', truncated: true })
  assert.deepEqual(excerpt(null), { text: '', truncated: false })
})

test('unknown and legacy assessments never imply neutral or positive views', () => {
  assert.deepEqual(marketAssessment({ market_view: 'unknown' }), { key: 'unknown', label: '평가 미확인' })
  assert.deepEqual(marketAssessment({ side: 'hold', assessment: 'defer' }), { key: 'legacy', label: '미분류' })
  assert.deepEqual(marketAssessment({ market_view: 'positive', quality_override: true }), { key: 'unknown', label: '평가 미확인' })
})

test('negative market opinions remain distinct from deferred quantity decisions', () => {
  const decision = { market_view: 'negative', assessment: 'defer', side: 'hold', decision_basis: 'preferences_missing' }
  assert.deepEqual(marketAssessment(decision), { key: 'negative', label: '부정적' })
  assert.deepEqual(quantityDecision(decision), { label: '수량 결정 보류', reason: '투자조건 미지정', tone: 'defer' })
  assert.equal(quantityDecision({ ...decision, side: 'sell' }).label, '수량 결정 보류')
  assert.equal(quantityDecision({ assessment: 'supported', side: 'hold' }).label, '수량 유지')
})

test('old records and missing bases do not acquire invented reasons', () => {
  assert.deepEqual(quantityDecision({ side: 'hold' }), { label: '유지 · 이전 기록', reason: '', tone: 'legacy' })
  assert.equal(quantityDecision({ assessment: 'defer', side: 'hold' }).reason, '')
  assert.equal(quantityDecision({ assessment: 'defer', decision_basis: 'data_missing' }).reason, '분석 자료 부족')
  assert.equal(quantityDecision({ assessment: 'defer', decision_basis: 'execution_unverified' }).reason, '주문 조건 미확인')
})
