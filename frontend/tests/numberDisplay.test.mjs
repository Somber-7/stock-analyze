import test from 'node:test'
import assert from 'node:assert/strict'
import { numberDisplay, percentChange } from '../src/lib/numberDisplay.js'

test('inline amounts retain the direction, comma grouping and percentage sign', () => {
  assert.deepEqual(numberDisplay(10000, { unit: '원', rate: -0.2 }), { value: '10,000원', rate: '-0.20%', tone: 'down' })
  assert.deepEqual(numberDisplay(1200, { unit: '원', rate: 1.5, signed: true }), { value: '+1,200원', rate: '+1.50%', tone: 'up' })
  assert.equal(numberDisplay(10000, { rate: 0 }).tone, 'neutral')
  assert.equal(numberDisplay(-0, { rate: -0, signed: true }).value, '0')
  assert.equal(numberDisplay(-100, { rate: 0, signed: true }).tone, 'down')
  assert.equal(numberDisplay(100, { rate: 0, signed: true }).tone, 'up')
})

test('missing amounts and rates never create a direction or percentage', () => {
  for (const value of [null, undefined, NaN, Infinity, '10000', true]) {
    assert.deepEqual(numberDisplay(value, { rate: -10 }), { value: '미확인', rate: null, tone: 'neutral' })
  }
  assert.equal(numberDisplay(10000, { rate: null }).rate, null)
  assert.equal(numberDisplay(-100, { signed: true }).tone, 'down')
})

test('calculated percentages need a positive known reference, and may cross below zero', () => {
  assert.equal(percentChange(800, 1000), -20)
  assert.ok(Math.abs(percentChange(-100, 1000) + 110) < 1e-9)
  for (const before of [0, -100, null, NaN, Infinity]) assert.equal(percentChange(100, before), null)
  assert.equal(percentChange(null, 100), null)
})
