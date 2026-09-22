import { useEffect, useState } from 'react'
import InlineNumber from './InlineNumber'

const API = import.meta.env.DEV ? 'http://127.0.0.1:8000' : ''
const formatTime = value => value ? new Date(value).toLocaleString('ko-KR') : '—'
const number = value => value == null ? '—' : value.toLocaleString('ko-KR')

export default function Top100({ onSelect }) {
  const [data, setData] = useState({ rows: [], loading: true })
  const [error, setError] = useState('')
  useEffect(() => {
    let stopped = false
    let timer
    let controller
    async function refresh() {
      controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 8000)
      try {
        const response = await fetch(`${API}/api/market/top100`, { signal: controller.signal })
        if (!response.ok) throw new Error('조회 실패')
        const next = await response.json()
        if (!stopped) { setData(next); setError('') }
      } catch {
        if (!stopped) setError('서버에 연결하지 못했습니다. 자동으로 다시 시도합니다.')
      } finally {
        clearTimeout(timeout)
        if (!stopped) timer = setTimeout(refresh, 2000)
      }
    }
    refresh()
    return () => { stopped = true; clearTimeout(timer); controller?.abort() }
  }, [])

  return <>
    <p className="top100-note">
      나무 종목파일의 전일 시가총액 순위 · 코스피·코스닥 주식(우선주 포함), ETF·ETN 제외<br />
      순위는 현재가에 따라 바뀌지 않습니다. 현재가는 순차 조회하므로 종목별 시차가 있습니다.
    </p>
    <div className="top100-status" role="status">
      <span>종목파일 수신 {formatTime(data.downloaded_at)}</span>
      {data.master_stale && <span>저장된 파일 기준 · 최신 파일 확인 중</span>}
      <span>{data.refreshing ? `현재가 갱신 ${data.completed}/${data.rows.length}`
        : data.rows.length ? `다음 갱신 약 ${data.next_refresh_seconds}초 후` : ''}</span>
    </div>
    {(error || data.error) && <div className="error" role="alert">{error || data.error}</div>}
    <div className="section-card top100-scroll">
      <table className="holdings-table">
        <thead><tr><th>순위</th><th>종목</th><th>전일 시총(억)</th><th>전일종가</th>
          <th>현재가 (전일 대비)</th><th>조회 시각</th></tr></thead>
        <tbody>{data.rows.map(row => {
          const quote = row.quote
          const hasPrice = quote?.price != null
          return <tr key={row.code}>
            <td>{row.rank}</td>
            <td><button className="top100-stock" onClick={() => onSelect(row.code, row.name)}>
              {row.name}<span>{row.code} · {row.market}</span>
            </button></td>
            <td>{number(row.previous_market_cap)}</td><td>{number(row.previous_close)}</td>
            <td><InlineNumber value={quote?.price} unit="원" rate={quote?.change_rate} title="시세의 전일 대비 등락률" /></td>
            <td className="top100-time">{quote?.retrieved_at ? new Date(quote.retrieved_at).toLocaleTimeString('ko-KR') : '대기'}
              {quote?.error && <span className="top100-warning">{quote.error}{hasPrice ? ' · 이전 시세' : ''}</span>}
            </td>
          </tr>
        })}
        {!data.rows.length && <tr><td colSpan={6} className="top100-empty">
          {error || data.error ? '위 오류 안내를 확인해 주세요.' : data.loading ? '나무 종목파일을 받는 중...' : '표시할 종목이 없습니다.'}
        </td></tr>}
        </tbody>
      </table>
    </div>
  </>
}
