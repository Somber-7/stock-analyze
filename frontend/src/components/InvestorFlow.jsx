import { useEffect, useState } from 'react'
import './InvestorFlow.css'

const API = import.meta.env.DEV ? 'http://127.0.0.1:8000' : ''
const GROUPS = [['personal', '개인'], ['institutional', '기관'], ['foreign', '외국인']]

function formatQuantity(value) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value > 0 ? '+' : ''}${value.toLocaleString('ko-KR', { maximumFractionDigits: 20 })}`
}

function direction(value) {
  return value == null ? 'missing' : value > 0 ? 'positive' : value < 0 ? 'negative' : 'neutral'
}

export default function InvestorFlow({ code }) {
  const [state, setState] = useState({ code, data: null, error: '', loading: true })
  useEffect(() => {
    if (!code) return
    let stopped = false
    let timer
    let controller
    setState({ code, data: null, error: '', loading: true })
    async function refresh() {
      controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 40000)
      try {
        const response = await fetch(`${API}/api/stock/${encodeURIComponent(code)}/investors`, {
          signal: controller.signal,
        })
        const data = await response.json()
        if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '수급 조회 실패')
        if (!Array.isArray(data.rows)) throw new Error('수급 응답 형식이 올바르지 않습니다.')
        if (!stopped) setState({ code, data, error: '', loading: false })
      } catch (error) {
        if (!stopped) setState(old => ({ ...old, loading: false,
          error: error.name === 'AbortError' ? '수급 조회 시간이 초과되었습니다.' : error.message,
        }))
      } finally {
        clearTimeout(timeout)
        if (!stopped) timer = setTimeout(refresh, 60000)
      }
    }
    refresh()
    return () => {
      stopped = true
      clearTimeout(timer)
      controller?.abort()
    }
  }, [code])

  const current = state.code === code ? state : { data: null, loading: true, error: '' }
  const { data, error, loading } = current
  const summary = data?.summary
  return <section className="section-card investor-flow" aria-label="투자자별 수급">
    <div className="investor-flow-header">
      <div>
        <h3>투자자별 수급</h3>
        <p>일별 순매수 · 최근 최대 20거래일</p>
      </div>
      <span className="investor-flow-unit">{data?.unit_label || '제공 수량 · 원본값'}</span>
    </div>
    {!code ? <p className="investor-flow-empty">종목을 선택해주세요.</p> : <>
      {loading && <p className="investor-flow-empty" role="status">수급을 조회하고 있습니다…</p>}
      {error && <p className="investor-flow-error" role="status">{error}{data ? ' · 이전 조회 자료를 표시합니다.' : ''}</p>}
      {data && <>
        <div className="investor-flow-meta">
          <span>{data.source} · 기준일 {data.data_date || '미제공'}</span>
          <span>조회 {new Date(data.fetched_at).toLocaleString('ko-KR')}</span>
        </div>
        <div className="investor-flow-summary">
          {GROUPS.map(([field, label]) => <div className="investor-flow-summary-item" key={field}>
            <span>{label}</span>
            <strong className={direction(summary?.[field])}>{formatQuantity(summary?.[field])}</strong>
            <small>{summary?.[field] == null ? '미제공' : summary[field] > 0 ? '순매수' : summary[field] < 0 ? '순매도' : '순매수량 0'}</small>
          </div>)}
        </div>
        {data.rows.length ? <div className="investor-flow-table-wrap">
          <table className="investor-flow-table">
            <caption>거래일별 투자자 순매수량 · {data.unit_label}</caption>
            <thead><tr><th scope="col">거래일</th>{GROUPS.map(([field, label]) => <th scope="col" key={field}>{label}</th>)}</tr></thead>
            <tbody>{data.rows.slice(0, 20).map(row => <tr key={row.date}>
              <th scope="row">{row.date}</th>
              {GROUPS.map(([field]) => <td key={field} className={direction(row[field])}>{formatQuantity(row[field])}</td>)}
            </tr>)}</tbody>
          </table>
        </div> : <p className="investor-flow-empty">이 종목의 투자자별 수급 자료가 제공되지 않았습니다.</p>}
        <div className="investor-flow-notes">
          <p>+ 순매수 / − 순매도 · — 미제공 · 화면을 보는 동안 1분마다 조회</p>
          {(data.notes || []).map(note => <p key={note}>{note}</p>)}
        </div>
      </>}
    </>}
  </section>
}
