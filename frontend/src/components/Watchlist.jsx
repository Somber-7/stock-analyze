import { useEffect, useRef, useState } from 'react'
import StockPicker from './StockPicker'
import InlineNumber from './InlineNumber'
import { watchRequest } from '../lib/watchApi'
import { money, timestamp } from '../lib/tradingApi'
import { createKey, clearKey } from '../lib/paperRequests.mjs'
import { showToast } from '../lib/toast'
import './Watchlist.css'

const STATUS = { armed: '감시 대기', triggered: '조건 도달', cancelled: '취소됨' }
export default function Watchlist({ onSelect, onOrder }) {
  const [state, setState] = useState(null)
  const [selected, setSelected] = useState(null)
  const [code, setCode] = useState('')
  const [comparison, setComparison] = useState('gte')
  const [threshold, setThreshold] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const formRef = useRef(null)
  const actionLock = useRef(false)
  useEffect(() => {
    let stopped = false, timer
    const controller = new AbortController()
    async function refresh() {
      try {
        const data = await watchRequest('', undefined, controller.signal)
        if (!stopped) { setState(data); setError('') }
      } catch { if (!stopped) setError('관심종목을 불러오지 못했습니다. 서버 연결을 확인하세요.') }
      finally { if (!stopped) timer = setTimeout(refresh, 2000) }
    }
    refresh()
    return () => { stopped = true; clearTimeout(timer); controller.abort() }
  }, [])

  async function action(fn, message) {
    if (actionLock.current) return
    actionLock.current = true; setBusy(true)
    try {
      await fn()
      showToast(message)
      setState(await watchRequest())
    } catch (e) { showToast(e.message || '처리하지 못했습니다. 목록을 확인하고 다시 시도하세요.', { tone: 'error' }) }
    finally { actionLock.current = false; setBusy(false) }
  }
  function chooseAlert(item) {
    setCode(item.code); setThreshold(item.quote?.price ? String(item.quote.price) : '')
    formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
  const items = state?.items || []
  const alerts = state?.alerts || []
  const alertCode = items.some(item => item.code === code) ? code : (items[0]?.code || '')
  const armed = alerts.filter(a => a.status === 'armed')

  return <div className="watch-page">
    <div className="watch-stats">
      <div><span>관심종목</span><strong>{items.length}<small>종목</small></strong></div>
      <div><span>대기 중인 알림</span><strong>{armed.length}<small>건</small></strong></div>
      <div><span>가격 감시</span><strong className="watch-status">{state ? state.session_open ? '감시 시간' : '장외 대기' : '연결 중'}</strong><small>한국 시간 평일 09:00–15:30</small></div>
    </div>
    {error && <p className="watch-error" role="alert">{error}</p>}
    <section className="section-card watch-add">
      <StockPicker onChange={setSelected} label="관심종목 추가 · 이름 또는 코드" />
      <button className="watch-primary" disabled={!selected || busy} onClick={() => action(() => watchRequest('/items', { code: selected.code }), '관심종목에 추가했습니다.')}>관심종목 추가</button>
    </section>
    <section className="section-card">
      <div className="watch-section-title"><h3>나의 관심종목</h3><span>{state?.refreshing ? '시세 조회 중…' : `조회 완료 후 30초 간격 · ${state?.next_refresh_seconds ?? '—'}초`}</span></div>
      <div className="watch-table-wrap"><table className="watch-table"><thead><tr><th>종목</th><th>현재가 (전일 대비)</th><th>조회 시각</th><th>바로가기</th></tr></thead><tbody>
        {items.map(item => <tr key={item.id}>
          <td><button className="watch-stock" onClick={() => onSelect(item.code, item.name)}>{item.name}</button><small>{item.code}</small></td>
          <td><InlineNumber value={item.quote?.price} unit="원" rate={item.quote?.change_rate} title="시세의 전일 대비 등락률" /></td>
          <td><span className="watch-time">{timestamp(item.quote?.retrieved_at)}</span>{item.quote?.error && <small className="watch-error">{item.quote.error} {item.quote.price ? '이전 조회 가격입니다.' : ''}</small>}</td>
          <td><div className="watch-actions"><button onClick={() => onSelect(item.code, item.name)}>차트·수급</button><button onClick={() => onOrder(item.code, item.name)}>주문</button><button onClick={() => chooseAlert(item)}>알림</button><button disabled={busy} aria-label={`${item.name} 관심종목 삭제`} onClick={() => action(() => watchRequest(`/items/${item.code}/remove`, {}), `${item.name}을 삭제하고 해당 종목의 대기 알림을 취소했습니다.`)}>삭제</button></div></td>
        </tr>)}
      </tbody></table></div>
      {!items.length && <div className="watch-empty">자주 확인하는 종목을 추가해보세요.<small>이름과 코드를 함께 표시하고 시세를 자동으로 불러옵니다.</small></div>}
      <p className="watch-help">관심종목 삭제 시 해당 종목의 대기 알림도 취소됩니다. 조회 시각은 서버가 시세를 받은 시간이며, 체결 시각은 아닙니다.</p>
    </section>
    <section className="section-card" ref={formRef}>
      <div className="watch-section-title"><h3>가격 알림 만들기</h3><span>조건당 한 번 알림</span></div>
      <form className="watch-alert-form" onSubmit={e => {
        e.preventDefault()
        const payload = { code: alertCode, comparison, threshold: Number(threshold) }
        action(async () => {
          const id = createKey(sessionStorage, '/watch/alerts', payload)
          const result = await watchRequest('/alerts', { ...payload, client_id: id })
          clearKey(sessionStorage, '/watch/alerts', payload, id)
          if (result.status !== 'armed') throw new Error(result.status === 'triggered'
            ? '이전 등록 요청은 이미 조건에 도달했습니다. 기록을 확인하세요. 새 알림은 등록 버튼을 다시 눌러 만드세요.'
            : '이전 등록 요청은 취소된 상태입니다. 새 알림은 등록 버튼을 다시 눌러 만드세요.')
        }, '가격 알림을 등록했습니다.')
      }}>
        <label>관심종목<select value={alertCode} onChange={e => setCode(e.target.value)} required><option value="" disabled>관심종목을 먼저 추가하세요</option>{items.map(s => <option value={s.code} key={s.id}>{s.name} · {s.code}</option>)}</select></label>
        <label>목표 가격 (원)<input type="number" min="1" max="1000000000" step="1" required value={threshold} onChange={e => setThreshold(e.target.value)} placeholder="예: 75000" /></label>
        <label>알림 조건<select value={comparison} onChange={e => setComparison(e.target.value)}><option value="gte">목표 가격 이상</option><option value="lte">목표 가격 이하</option></select></label>
        <button className="watch-primary" disabled={!alertCode || busy}>알림 등록</button>
      </form>
      <p className="watch-help">앱과 서버가 켜져 있을 때 평일 09:00–15:30에 감시합니다. 휴장일은 별도 구분하지 않으며 나무 API가 반환한 가격으로 판단합니다. 등록 후 첫 조회가 이미 조건을 충족하면 바로 알립니다. 자동 주문은 실행하지 않습니다.</p>
    </section>
    <section className="section-card">
      <div className="watch-section-title"><h3>알림 기록</h3><span>대기 알림 전체 · 최근 완료 기록 100건</span></div>
      <div className="watch-alerts">{alerts.map(a => <div className="watch-alert-row" key={a.id}>
        <div><strong>{a.name} <small>{a.code}</small></strong><p>{money(a.threshold)}원 {a.comparison === 'gte' ? '이상' : '이하'}</p></div>
        <div><span className={`watch-pill ${a.status}`}>{STATUS[a.status]}</span><small>{a.status === 'triggered' ? `${timestamp(a.triggered_at)} · 확인 가격 ${money(a.observed_price)}원` : timestamp(a.cancelled_at || a.created_at)}</small></div>
        {a.status === 'armed' && <button disabled={busy} onClick={() => action(() => watchRequest(`/alerts/${a.id}/cancel`, {}), '알림을 취소했습니다.')}>취소</button>}
      </div>)}</div>
      {!alerts.length && <div className="watch-empty">등록된 가격 알림이 없습니다.</div>}
    </section>
  </div>
}
