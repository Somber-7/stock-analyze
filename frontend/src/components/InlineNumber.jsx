import { numberDisplay } from '../lib/numberDisplay'
import './InlineNumber.css'

export default function InlineNumber({ value, unit = '', rate, direction, signed = false, digits = 2, title, className = '' }) {
  const display = numberDisplay(value, { unit, rate, direction, signed, digits })
  return <span className={`inline-number ${className}`} title={title} style={{ color: display.tone === 'neutral' ? 'var(--text)' : `var(--${display.tone})` }}>
    <span className="inline-number-value">{display.value}</span>
    {display.rate != null && <span className="inline-number-rate">({display.rate})</span>}
  </span>
}
