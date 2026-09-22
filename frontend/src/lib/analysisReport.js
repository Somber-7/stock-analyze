const MARKET_LABELS = { positive: '긍정적', mixed: '엇갈림', negative: '부정적', unknown: '평가 미확인' }
const BASIS_LABELS = { sufficient: '', data_missing: '분석 자료 부족', preferences_missing: '투자조건 미지정', mixed_evidence: '근거 엇갈림', execution_unverified: '주문 조건 미확인' }
const SIDE_LABELS = { buy: '매수', sell: '매도', hold: '유지' }

export function excerpt(value, limit = 240) {
  const source = typeof value === 'string' ? value.trim() : ''
  const characters = Array.from(source)
  const truncated = characters.length > limit
  return { text: truncated ? `${characters.slice(0, limit).join('').trimEnd()}…` : source, truncated }
}

export function marketAssessment(decision) {
  const key = decision.quality_override ? 'unknown' : Object.hasOwn(MARKET_LABELS, decision.market_view) ? decision.market_view : 'legacy'
  return { key, label: MARKET_LABELS[key] || '미분류' }
}

export function quantityDecision(decision) {
  if (decision.assessment === 'defer') return { label: '수량 결정 보류', reason: BASIS_LABELS[decision.decision_basis] || '', tone: 'defer' }
  if (!decision.assessment) return { label: `${SIDE_LABELS[decision.side] || '판단 미확인'} · 이전 기록`, reason: '', tone: 'legacy' }
  return { label: decision.side === 'hold' ? '수량 유지' : `${SIDE_LABELS[decision.side] || '판단 미확인'} 제안`, reason: BASIS_LABELS[decision.decision_basis] || '', tone: decision.side }
}
