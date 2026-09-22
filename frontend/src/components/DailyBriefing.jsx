import { useEffect, useState } from 'react'
import { timestamp } from '../lib/tradingApi'
import InlineNumber from './InlineNumber'
import './DailyBriefing.css'

const API = import.meta.env.DEV ? 'http://127.0.0.1:8000' : ''
const STATUS = { unavailable: '조회 계좌와 실전 주문 설정이 일치할 때 표시합니다.', error: '조회하지 못했습니다. 새로고침해 주세요.', changed: '설정이 변경되었습니다. 새로고침해 주세요.', empty: '같은 계좌·현재 분석 조건의 결과가 없습니다.' }
const finite = value => typeof value === 'number' && Number.isFinite(value) && value >= 0

export default function DailyBriefing({ account, holdings, summary, onSelect, onWatch, onOrders, onAI }) {
  const [result, setResult] = useState(null)
  useEffect(() => {
    const controller = new AbortController()
    let active = true
    const timeout = setTimeout(() => controller.abort(), 45000)
    fetch(`${API}/api/briefing?account=${encodeURIComponent(account)}`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('briefing')
        const data = await response.json()
        if (!controller.signal.aborted) setResult({ account, data })
      })
      .catch(() => { if (active) setResult({ account, error: true }) })
      .finally(() => clearTimeout(timeout))
    return () => { active = false; clearTimeout(timeout); controller.abort() }
  }, [account])
  const data = result?.account === account ? result.data : null
  const error = result?.account === account && result.error
  const positions = holdings.filter(row => !row.code.startsWith('NHKRCMA'))
  const grouped = new Map()
  for (const row of positions) {
    const prior = grouped.get(row.code)
    grouped.set(row.code, { code: row.code, name: row.name, value: finite(row.eval_amount) && (!prior || prior.value != null) ? (prior?.value || 0) + row.eval_amount : null })
  }
  const largest = [...grouped.values()].filter(row => row.value != null).sort((a, b) => b.value - a.value)[0]
  const known = positions.every(row => finite(row.eval_amount))
  const total = finite(summary.total_assets) ? summary.total_assets : known ? positions.reduce((sum, row) => sum + row.eval_amount, 0) : null
  const weight = known && largest && total > 0 ? largest.value / total * 100 : null
  const watch = data?.watch
  const orders = data?.orders
  const analysis = data?.analysis

  return <section className="daily-briefing" aria-label="오늘 확인할 항목">
    <div className="briefing-heading"><h2>오늘 확인할 항목</h2><span>{data ? `${data.day} · 한국 시간` : error ? '요약 조회 실패' : '요약 불러오는 중…'}</span></div>
    {error && <p className="briefing-muted" role="status">요약을 불러오지 못했습니다. 상단 새로고침으로 다시 조회할 수 있습니다.</p>}
    {data && <div className="briefing-grid">
      <article className="briefing-card"><h3>관심 종목 변화</h3><div className="briefing-value">{watch.status === 'ready' ? `${watch.fresh_count} / ${watch.total_count}` : '미확인'}<small>저장 시세 확인</small></div>
        {watch.status === 'ready' ? <>
          <div className="briefing-movers">{watch.movers.slice(0, 3).map(row => <button key={row.code} onClick={() => onSelect?.(row.code, row.name)} title={`시세 조회 ${timestamp(row.retrieved_at)}`}><span>{row.name}</span><InlineNumber value={row.change_rate} unit="%" signed /></button>)}</div>
          <p className="briefing-muted">{watch.fresh_count ? '요약 조회 시점 최근 2분 내 저장 시세 · 전일 대비' : '관심종목 화면에서 시세를 조회해 주세요.'}{watch.stale_count > 0 && ` · 오래되거나 미확인 ${watch.stale_count}종목`}</p>
        </> : <p className="briefing-muted">{STATUS.error}</p>}
        <button className="briefing-link" onClick={onWatch}>관심종목·알림 →</button>
      </article>
      <article className="briefing-card"><h3>실전 주문 확인</h3><div className="briefing-value">{orders.status === 'ready' ? `${orders.pending_count}건` : '미확인'}<small>오늘 주문 중 미체결</small></div>
        {orders.unresolved_count > 0 && <p className="briefing-attention">접수 여부 확인 필요 {orders.unresolved_count}건 · 저장 기록 전체</p>}
        {orders.status === 'ready' ? <>
          {orders.pending_count > 0 && <details className="briefing-details"><summary>미체결 종목 보기</summary><ul>{orders.rows.map((row, index) => <li key={index}>{row.name || row.code} · {row.side === 'buy' ? '매수' : row.side === 'sell' ? '매도' : '기타'} {row.remaining.toLocaleString()}주</li>)}</ul>{orders.pending_count > 5 && <p>나머지는 주문 화면에서 확인하세요.</p>}</details>}
          <p className="briefing-muted">주문 조회 {timestamp(orders.checked_at)}</p>
        </> : <p className="briefing-muted">{STATUS[orders.status]}</p>}
        <button className="briefing-link" onClick={onOrders}>주문 내역 →</button>
      </article>
      <article className="briefing-card"><h3>최근 AI 판단</h3><div className="briefing-value">{analysis.status === 'ready' ? analysis.changed_count == null ? '첫 비교 기준' : `${analysis.changed_count}종목 변경` : '결과 미확인'}<small>같은 조건의 지난 분석 대비</small></div>
        {analysis.status === 'ready' ? <><p className="briefing-muted">판단 유보 {analysis.defer_count}종목</p><p className="briefing-muted">분석 완료 {timestamp(analysis.completed_at)}</p></> : <p className="briefing-muted">{STATUS[analysis.status]}</p>}
        <button className="briefing-link" onClick={() => onAI?.(analysis.run_id)}>분석 결과 →</button>
      </article>
    </div>}
    <div className="briefing-footer">
      {data && <span>요약 조회 {timestamp(data.fetched_at)}</span>}
      <span>{weight != null ? <>보유 비중 최대 <strong>{largest.name} {weight.toFixed(1)}%</strong><small>{finite(summary.total_assets) ? '조회 계좌 총자산 기준' : '확인된 주식 평가액 내'}</small></> : '보유 비중은 자산 평가액이 확인되면 표시합니다.'}</span>
      {watch?.status === 'ready' && <details className="briefing-details"><summary>오늘 발생한 가격 알림 {watch.alert_count}건</summary>{watch.alert_count > 0 ? <ul>{watch.alerts.map((row, index) => <li key={index}>{row.name || row.code} · {timestamp(row.triggered_at)}</li>)}</ul> : <p>발생한 알림이 없습니다.</p>}{watch.alert_count > 5 && <p>최근 5건 표시 · 전체 내역은 관심종목·알림에서 확인하세요.</p>}</details>}
    </div>
  </section>
}
