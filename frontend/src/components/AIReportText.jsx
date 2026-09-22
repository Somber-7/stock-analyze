import { excerpt } from '../lib/analysisReport'

export default function AIReportText({ text, limit = 240, label = '근거 전체 읽기', className = '' }) {
  const preview = excerpt(text, limit)
  if (!preview.text) return null
  if (!preview.truncated) return <p className={`aio-prose ${className}`}>{preview.text}</p>
  return <details className={`aio-text-disclosure ${className}`}>
    <summary><span className="aio-text-preview">{preview.text}</span><span className="aio-text-open">{label}</span><span className="aio-text-close">접기</span></summary>
    <p className="aio-prose">{text}</p>
  </details>
}
