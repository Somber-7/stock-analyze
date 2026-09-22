import { useCallback, useEffect, useRef, useState } from 'react'
import StockPicker from './StockPicker'
import './PaperTrading.css'
import { createKey, clearKey } from '../lib/paperRequests.mjs'
import { showToast } from '../lib/toast'

const API = import.meta.env.DEV ? 'http://127.0.0.1:8000' : ''
const fmt = value => value == null ? '—' : Math.round(value).toLocaleString('ko-KR')
const stamp = value => value ? new Date(value).toLocaleString('ko-KR') : '—'
const states = { pending: '미체결', partial: '부분 체결', filled: '체결 완료', cancelled: '취소', armed: '조건 대기', fired: '주문 접수', rejected: '주문 거절' }
const active = o => ['pending', 'partial'].includes(o.status)

async function request(path, body, signal, version = -1) {
  const response = await fetch(`${API}/api/paper${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Paper-Mode': 'paper', 'X-Paper-Version': String(version) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: signal || AbortSignal.timeout(10000),
  })
  const data = await response.json()
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '입력한 종목코드·수량·가격을 확인하세요.')
  return data
}

export default function PaperTrading({ initialCode = '' }) {
  const [data, setData] = useState(null)
  const [connectionError, setConnectionError] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [revision, setRevision] = useState(0)
  const [stock, setStock] = useState(null)
  const code = stock?.code || ''
  const [side, setSide] = useState('buy')
  const [quantity, setQuantity] = useState('1')
  const [limitPrice, setLimitPrice] = useState('')
  const [kind, setKind] = useState('order')
  const [comparison, setComparison] = useState('lte')
  const [threshold, setThreshold] = useState('')
  const [quote, setQuote] = useState(null)
  const [amend, setAmend] = useState({})
  const actionLock = useRef(false)
  const quoteSequence = useRef(0)
  const selectStock = useCallback(next => {
    setStock(next); setQuote(null); setLimitPrice(''); quoteSequence.current++
  }, [])
  // A lookup answered after leaving this screen must not raise a toast elsewhere.
  useEffect(() => () => { quoteSequence.current += 1 }, [])

  useEffect(() => {
    let stopped = false
    let timer
    let controller
    async function poll() {
      controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 8000)
      try {
        const next = await request('', undefined, controller.signal)
        if (!stopped) { setData(next); setConnectionError('') }
      } catch {
        if (!stopped) setConnectionError('서버 상태를 확인할 수 없습니다. 아래 값은 마지막 수신 기록입니다.')
      } finally {
        clearTimeout(timeout)
        if (!stopped) timer = setTimeout(poll, 2000)
      }
    }
    poll()
    return () => { stopped = true; clearTimeout(timer); controller?.abort() }
  }, [revision])

  async function action(path, body = {}, success = '처리했습니다.', emergency = false) {
    if (actionLock.current && !emergency) return false
    if (!emergency) { actionLock.current = true; setBusy(true) }
    setError('')
    try {
      await request(path, body, undefined, data?.version ?? -1)
      showToast(success)
      setRevision(v => v + 1)
      return true
    } catch (e) {
      setError(e.name === 'TimeoutError' || e.name === 'TypeError'
        ? '응답을 확인하지 못했습니다. 주문·조건 기록을 확인하세요. 같은 입력으로 재시도하면 중복 접수를 방지합니다.' : e.message)
      setRevision(v => v + 1)
      return false
    } finally {
      if (!emergency) { actionLock.current = false; setBusy(false) }
    }
  }

  async function submit(event) {
    event.preventDefault()
    if (!stock) { setError('주문할 종목을 검색하고 선택하세요.'); return }
    const payload = { code, side, quantity: Number(quantity), limit_price: Number(limitPrice) }
    if (kind === 'rule') Object.assign(payload, { comparison, threshold: Number(threshold) })
    const path = kind === 'rule' ? '/rules' : '/orders'
    const id = createKey(sessionStorage, path, payload)
    if (await action(path, { ...payload, client_id: id }, kind === 'rule' ? '일회성 조건을 등록했습니다.' : '모의 주문을 접수했습니다. 실행 중일 때 시세를 확인해 체결합니다.')) {
      clearKey(sessionStorage, path, payload, id)
    }
  }

  async function checkQuote() {
    const seq = ++quoteSequence.current
    setError(''); setQuote(null)
    try {
      const response = await fetch(`${API}/api/stock/${code}/price`, { signal: AbortSignal.timeout(35000) })
      const next = await response.json()
      if (!response.ok) throw new Error(next.detail || '시세 조회 실패')
      if (quoteSequence.current === seq) setQuote({ ...next, fetched: new Date().toISOString() })
    } catch {
      if (quoteSequence.current === seq) showToast('종목 시세를 확인하지 못했습니다. 종목코드와 API 연결을 확인하세요.', { tone: 'error' })
    }
  }

  const working = data?.running
  return <div className="paper-page">
    <div className="paper-banner"><strong>모의매매 · 실제 주문 전송 없음</strong>
      <span>나무 시세로 주문 흐름을 시험합니다. 실제 계좌 잔고와 별도로 기록됩니다.</span></div>
    <div className="paper-controls">
      <span className={`paper-state ${working ? 'running' : ''}`}>{connectionError ? '연결 확인 필요' : working ? '모의 실행 중' : '모의 실행 정지'}</span>
      <button disabled={busy || !data || !!connectionError || working} onClick={() => action('/control', { action: 'start' }, '모의 실행을 시작했습니다.')}>모의 실행 시작</button>
      <button disabled={busy || !data || !working} onClick={() => action('/control', { action: 'pause' }, '일시정지했습니다. 미체결 주문과 조건은 유지됩니다.')}>일시정지</button>
      <button className="paper-danger" onClick={() => action('/control', { action: 'emergency' }, '긴급정지했습니다. 미체결 잔량과 대기 조건을 취소했습니다.', true)}>긴급정지·잔량 취소</button>
    </div>
    <p className="paper-help">실행 중에는 다른 화면으로 이동해도 계속 동작합니다. 앱·서버 재실행 후에는 정지 상태로 시작합니다.</p>
    {(error || connectionError || data?.error) && <p className="error" role="alert">{error || connectionError || data.error}</p>}
    {!data && <p className="paper-help">모의 기록을 불러오는 중…</p>}
    {data && <>
      <div className="paper-metrics">
        {[['가상 현금', data.cash], ['주문 가능 현금', data.available_cash], ['매수 예약금', data.reserved_cash], ['실현 손익 · 비용 제외', data.realized_pnl]].map(([label, value]) =>
          <div key={label}><span>{label}</span><strong>{fmt(value)}<small> 원</small></strong></div>)}
      </div>
      <div className="paper-columns">
        <section className="paper-card">
          <h2>모의 주문 / 가격 조건</h2>
          <form onSubmit={submit} className="paper-form">
            <label>등록 방식<select value={kind} onChange={e => setKind(e.target.value)}><option value="order">지정가 모의 주문</option><option value="rule">가격 조건 충족 시 한 번 주문</option></select></label>
            <StockPicker initialCode={initialCode} onChange={selectStock} />
            <button type="button" disabled={!stock} onClick={checkQuote}>선택 종목 현재가 조회</button>
            {quote && <div className="paper-quote"><strong>{quote.name || code} · {fmt(quote.price)}원</strong><span>{stamp(quote.fetched)} 조회</span><button type="button" onClick={() => setLimitPrice(String(quote.price))}>이 가격을 지정가에 입력</button></div>}
            <div className="paper-form-row"><label>매매 구분<select value={side} onChange={e => setSide(e.target.value)}><option value="buy">모의 매수</option><option value="sell">모의 매도</option></select></label><label>수량 (주)<input type="number" min="1" step="1" required value={quantity} onChange={e => setQuantity(e.target.value)} /></label></div>
            <label>주문 지정가 (원)<input type="number" min="1" step="1" required value={limitPrice} onChange={e => setLimitPrice(e.target.value)} /></label>
            {kind === 'rule' && <div className="paper-form-row"><label>기준 가격 (원)<input type="number" min="1" step="1" required value={threshold} onChange={e => setThreshold(e.target.value)} /></label><label>발동 조건<select value={comparison} onChange={e => setComparison(e.target.value)}><option value="lte">기준 가격 이하</option><option value="gte">기준 가격 이상</option></select></label></div>}
            <p className="paper-help">주문 금액 {fmt(Number(quantity) * Number(limitPrice))}원</p>
            <button className="paper-primary" disabled={busy || !!connectionError || !stock} type="submit">{busy ? '처리 중…' : kind === 'rule' ? '일회성 모의 조건 등록' : `지정가 모의 ${side === 'buy' ? '매수' : '매도'} 접수`}</button>
            {kind === 'rule' && <p className="paper-help">조건 등록 시에는 잔고를 예약하지 않습니다. 조건 충족 시 주문 가능 잔고를 검사하며, 거절된 조건도 자동 재시도하지 않습니다.</p>}
          </form>
        </section>
        <section className="paper-card"><h2>가상 보유 종목</h2>
          <div className="paper-table-wrap"><table><thead><tr><th>종목</th><th>보유 / 매도 가능</th><th>평균 원가</th></tr></thead><tbody>
            {data.positions.map(p => <tr key={p.code}><td>{p.name}<small>{p.code}</small></td><td>{fmt(p.quantity)} / {fmt(p.available)}주</td><td>{fmt(p.average_price)}원</td></tr>)}
            {!data.positions.length && <tr><td colSpan={3} className="paper-empty">모의 매수가 체결되면 표시됩니다.</td></tr>}
          </tbody></table></div>
          <details className="paper-model"><summary>모의매매 체결 기준</summary>
            <p>초기 가상 현금 1,000만 원 · 금액 제한 없이 가상 주문 가능 현금·보유 수량 내에서 주문 · 최대 10개 종목 감시</p>
            <p>약 10초마다 시세를 새로 조회하고, 지정가에 맞으면 종목당 한 주기에 최대 10주를 가상 체결합니다. 시세 조회가 밀리면 주기도 길어집니다.</p>
            <p>장외에는 API의 마지막 가격으로 시험합니다. 호가 잔량·수수료·세금·슬리피지는 반영하지 않습니다. 이 손익은 실제 수익성 검증 결과가 아닙니다.</p>
          </details>
        </section>
      </div>
      <section className="paper-card"><h2>주문·체결 기록 <small>미체결 전체 + 종료 기록 최근 200건</small></h2>
        <div className="paper-table-wrap"><table><thead><tr><th>접수 시각 / 종목</th><th>구분</th><th>상태</th><th>체결 / 주문</th><th>지정가 / 평균 체결가</th><th>미체결 관리</th></tr></thead><tbody>
          {data.orders.map(o => <tr key={o.id}><td>{o.name || "종목명 확인 불가"}<small>{o.code}</small><small>{stamp(o.created_at)}</small></td><td className={o.side === 'buy' ? 'paper-buy' : 'paper-sell'}>{o.side === 'buy' ? '매수' : '매도'}<small>{o.source === 'rule' ? '조건 주문' : '수동 주문'}</small></td><td>{states[o.status] || o.status}</td><td>{o.filled} / {o.quantity}주</td><td>{fmt(o.limit_price)}원<small>평균 {o.filled ? fmt(o.fill_value / o.filled) + '원' : '—'}</small></td><td>{active(o) ? <div className="paper-inline"><input aria-label={`${o.code} 정정 가격`} type="number" min="1" step="1" placeholder="새 지정가" value={amend[o.id] || ''} onChange={e => setAmend({ ...amend, [o.id]: e.target.value })} /><button disabled={busy || !amend[o.id]} onClick={() => action(`/orders/${o.id}/modify`, { limit_price: Number(amend[o.id]) }, '미체결 잔량의 가격을 정정했습니다.')}>정정</button><button disabled={busy} onClick={() => action(`/orders/${o.id}/cancel`, {}, '미체결 잔량을 취소했습니다.')}>취소</button></div> : '—'}</td></tr>)}
          {!data.orders.length && <tr><td colSpan={6} className="paper-empty">등록된 모의 주문이 없습니다.</td></tr>}
        </tbody></table></div>
      </section>
      <section className="paper-card"><h2>일회성 가격 조건 <small>대기 전체 + 종료 기록 최근 200건</small></h2>
        <div className="paper-table-wrap"><table><thead><tr><th>종목</th><th>발동 조건</th><th>예정 주문</th><th>상태 / 결과</th><th>관리</th></tr></thead><tbody>
          {data.rules.map(r => <tr key={r.id}><td>{r.name || "종목명 확인 불가"}<small>{r.code}</small></td><td>{fmt(r.threshold)}원 {r.comparison === 'lte' ? '이하' : '이상'}</td><td>{r.side === 'buy' ? '매수' : '매도'} {r.quantity}주 · {fmt(r.limit_price)}원</td><td>{states[r.status]}<small>{r.message}</small></td><td>{r.status === 'armed' && <button disabled={busy} onClick={() => action(`/rules/${r.id}/cancel`, {}, '가격 조건을 해제했습니다.')}>해제</button>}</td></tr>)}
          {!data.rules.length && <tr><td colSpan={5} className="paper-empty">등록된 가격 조건이 없습니다.</td></tr>}
        </tbody></table></div>
      </section>
      <details className="paper-card"><summary>시세 확인·실행 기록 · 마지막 주기 {stamp(data.last_cycle)}</summary>
        {Object.entries(data.quotes).map(([symbol, q]) => <p className="paper-help" key={symbol}>{symbol} · {q.error || `${fmt(q.price)}원`} · {stamp(q.checked_at)}</p>)}
        <ol className="paper-log">{data.events.map((entry, i) => <li key={`${entry.at}-${i}`}><time>{stamp(entry.at)}</time> {entry.message}</li>)}</ol>
      </details>
    </>}
  </div>
}
