const finite = value => typeof value === 'number' && Number.isFinite(value)

export function percentChange(current, previous) {
  if (!finite(current) || !finite(previous) || previous <= 0) return null
  const rate = (current - previous) / previous * 100
  return finite(rate) ? rate : null
}

export function numberDisplay(value, { unit = '', rate, direction, signed = false, digits = 2 } = {}) {
  if (!finite(value)) return { value: '미확인', rate: null, tone: 'neutral' }
  const trend = signed && value !== 0 ? value : finite(rate) ? rate : finite(direction) ? direction : 0
  return {
    value: `${signed && value > 0 ? '+' : ''}${(value || 0).toLocaleString('ko-KR', { maximumFractionDigits: digits })}${unit}`,
    rate: finite(rate) ? `${rate > 0 ? '+' : ''}${(rate || 0).toFixed(2)}%` : null,
    tone: trend > 0 ? 'up' : trend < 0 ? 'down' : 'neutral',
  }
}
