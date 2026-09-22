import { useCallback, useEffect, useRef, useState } from 'react'
import StockPicker from './StockPicker'
import { createKey, clearKey } from '../lib/paperRequests.mjs'
import { API, tradingRequest, money, timestamp, accountLabel, today } from '../lib/tradingApi'
import { showToast } from '../lib/toast'
import './PaperTrading.css'
import './LiveTrading.css'

const operationState = { sending: '전송 중', accepted: '접수 확인', rejected: '거절·미접수', unknown: '결과 확인 필요' }
const ruleState = { armed: '조건 대기', executing: '주문 처리 중', fired: '주문 접수', rejected: '조건 주문 거절', cancelled: '해제', review: '전송 기록 확인' }

function Resolution({ op, busy, prepare }) {
  const [number, setNumber] = useState('')
  const [ack, setAck] = useState(false)
  return <div className="live-resolution">
    <label className="live-check"><input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)} />나무 주문 내역에서 접수 여부를 확인했습니다.</label>
    <div className="paper-inline"><input aria-label="확인한 증권사 주문번호" placeholder="확인한 주문번호" value={number} onChange={e => setNumber(e.target.value)} />
      <button disabled={busy || !ack || !number} onClick={() => prepare(`/resolve/${op.id}`, { decision: 'linked', broker_id: number, acknowledged: ack }, '확인한 주문번호 연결')}>주문번호 연결</button>
      <button disabled={busy || !ack} onClick={() => prepare(`/resolve/${op.id}`, { decision: 'not_sent', broker_id: null, acknowledged: ack }, '증권사 미접수 확인 처리')}>미접수 확인</button></div>
  </div>
}

export default function LiveTrading({ initialCode = '', state, disconnected, onRefresh }) {
  const [stock, setStock] = useState(null)
  const code = stock?.code || ''
  const [side, setSide] = useState('buy')
  const [quantity, setQuantity] = useState('1')
  const [price, setPrice] = useState('')
  const [kind, setKind] = useState('order')
  const [comparison, setComparison] = useState('lte')
  const [threshold, setThreshold] = useState('')
  const [capacity, setCapacity] = useState(null)
  const [day, setDay] = useState(today())
  const [history, setHistory] = useState(null)
  const [historyError, setHistoryError] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [preview, setPreview] = useState(null)
  const [amend, setAmend] = useState({})
  const [revision, setRevision] = useState(0)
  const actionLock = useRef(false)
  const capacitySequence = useRef(0)
  const selectStock = useCallback(next => {
    setStock(next); setPrice(''); setCapacity(null); setNotice(''); capacitySequence.current++
  }, [])
  // A lookup answered after leaving this screen must not raise a toast elsewhere.
  useEffect(() => () => { capacitySequence.current += 1 }, [])

  useEffect(() => {
    let stopped = false
    let timer
    let controller
    async function load() {
      controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 45000)
      try {
        const next = await tradingRequest(`/live?day=${day}`, undefined, undefined, controller.signal)
        if (!stopped) { setHistory(next); setHistoryError('') }
      } catch (e) { if (!stopped) setHistoryError(e.name === 'AbortError' ? '계좌·주문 조회가 지연되고 있습니다.' : e.message) }
      finally { clearTimeout(timeout); if (!stopped) timer = setTimeout(load, 15000) }
    }
    load()
    return () => { stopped = true; clearTimeout(timer); controller?.abort() }
  }, [day, state.account, revision])

  function prepare(path, payload, title, detail = '', keyed = false) {
    if (actionLock.current) return
    setError(''); setNotice('')
    const signaturePath = `${state.account}:${path}`
    const id = keyed ? createKey(sessionStorage, signaturePath, payload) : null
    setPreview({ path, payload: keyed ? { ...payload, client_id: id } : payload,
      signature: payload, signaturePath, id, version: state.version, title, detail, account: state.account, day: today() })
  }

  async function execute(item, emergency = false) {
    if (actionLock.current && !emergency) return
    if (!emergency) { actionLock.current = true; setBusy(true) }
    setError(''); setNotice('')
    try {
      const result = await tradingRequest(item.path, item.payload, item.version)
      if (item.id) clearKey(sessionStorage, item.signaturePath, item.signature, item.id)
      if (result.status === 'unknown') setError(result.message)
      else if (result.status === 'rejected') setError(result.message)
      else setNotice(result.message || (emergency ? result.error || '실전 실행을 정지했습니다.' : '처리했습니다. 증권사 내역을 새로 조회합니다.'))
      setPreview(null)
    } catch (e) {
      setError(e.name === 'TimeoutError' || e.name === 'TypeError'
        ? '응답 확인 실패. 전송 기록을 먼저 확인하세요. 동일 입력의 재시도는 같은 요청으로 처리합니다.' : e.message)
    } finally {
      if (!emergency) { actionLock.current = false; setBusy(false) }
      onRefresh(); setRevision(v => v + 1)
    }
  }

  async function checkCapacity() {
    const seq = ++capacitySequence.current
    setError(''); setCapacity(null)
    try {
      const result = await tradingRequest(`/capacity?code=${code}&side=${side}&price=${Number(price)}`)
      if (capacitySequence.current === seq) setCapacity({ ...result, at: new Date().toISOString(), signature: `${code}:${side}:${price}` })
    } catch (e) { if (capacitySequence.current === seq) setError(e.message) }
  }

  async function usePrice() {
    const seq = ++capacitySequence.current
    try {
      const response = await fetch(`${API}/api/stock/${code}/price`, { signal: AbortSignal.timeout(35000) })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || '시세 조회 실패')
      if (capacitySequence.current === seq) { setPrice(String(data.price)); showToast(`${data.name || code} 조회 가격을 입력했습니다.`) }
    } catch (e) { if (capacitySequence.current === seq) showToast(e.message, { tone: 'error' }) }
  }

  function submit(event) {
    event.preventDefault()
    if (!stock) { setError('주문할 종목을 검색하고 선택하세요.'); return }
    const payload = { code, side, quantity: Number(quantity), price: Number(price) }
    if (kind === 'rule') Object.assign(payload, { comparison, threshold: Number(threshold) })
    prepare(kind === 'rule' ? '/rules' : '/orders', payload,
      kind === 'rule' ? '실전 가격 조건 등록' : `실전 ${side === 'buy' ? '매수' : '매도'} 주문 전송`,
      `${stock.name} (${code}) · ${side === 'buy' ? '매수' : '매도'} ${quantity}주 × ${money(Number(price))}원 = ${money(Number(price) * Number(quantity))}원${kind === 'rule' ? ` · ${money(Number(threshold))}원 ${comparison === 'lte' ? '이하' : '이상'}일 때 한 번 주문` : ''}`, true)
  }

  const validHistory = history?.account === state.account && history?.day === day
  const blocked = busy || disconnected || state.emergency_active
  return <div className="paper-page live-page">
    <div className="paper-banner live-banner"><strong>실전매매 · 실제 계좌 주문</strong><span>계좌 {accountLabel(state.account)} · 국내 현금 / KRX / 지정가</span></div>
    <div className="paper-controls"><span className="paper-state">{state.running ? '실전 주문 가능 · 가격 조건 실행 중' : '신규 주문 잠금 · 조건 정지'}</span>
      <button disabled={blocked || state.running} onClick={() => prepare('/control', { action: 'start' }, '실전 실행 시작', '신규 실전 주문을 허용하고 대기 중인 가격 조건을 실행합니다.')}>실전 실행 시작</button>
      <button disabled={!state.running || busy} onClick={() => execute({ path: '/control', payload: { action: 'pause' }, version: state.version })}>실전 실행 중단</button>
      <button className="paper-danger" onClick={() => execute({ path: '/control', payload: { action: 'emergency' }, version: state.version }, true)}>긴급정지 · 앱 주문 취소</button></div>
    <p className="paper-help">중단해도 증권사 미체결 주문은 남습니다. 긴급정지는 이 앱이 접수한 당일 KRX 주문의 잔량 취소를 요청합니다. 이미 체결된 주문은 되돌리지 않습니다.</p>
    {(error || state.error) && <p className="error" role="alert">{error || state.error}</p>}
    {notice && <p className="paper-notice" role="status">{notice}</p>}
    <p className="paper-help">앱 주문 금액 제한 없음 · 전송 전 나무 계좌의 실제 주문 가능 수량을 확인합니다.</p>
    <div className="paper-columns">
      <section className="paper-card"><h2>실전 주문 / 가격 조건</h2><form className="paper-form" onSubmit={submit}>
        <label>등록 방식<select value={kind} onChange={e => setKind(e.target.value)}><option value="order">지정가 실전 주문</option><option value="rule">가격 조건 충족 시 한 번 주문</option></select></label>
        <StockPicker initialCode={initialCode} onChange={selectStock} />
        <div className="paper-form-row"><label>매매 구분<select value={side} onChange={e => { setSide(e.target.value); capacitySequence.current++ }}><option value="buy">현금 매수</option><option value="sell">현금 매도</option></select></label><label>수량 (주)<input type="number" min="1" step="1" required value={quantity} onChange={e => setQuantity(e.target.value)} /></label></div>
        <label>지정가 (원)<div className="paper-inline"><input type="number" min="1" step="1" required value={price} onChange={e => { setPrice(e.target.value); capacitySequence.current++ }} /><button type="button" disabled={!/^[0-9A-Z]{6}$/.test(code)} onClick={usePrice}>현재가 입력</button></div></label>
        <button type="button" disabled={!/^[0-9A-Z]{6}$/.test(code) || Number(price) <= 0} onClick={checkCapacity}>현금 주문 가능 수량 확인</button>
        {capacity?.signature === `${code}:${side}:${price}` && <p className="paper-notice">가능 {money(capacity.quantity)}주{capacity.amount != null && ` · ${money(capacity.amount)}원`}<br />{timestamp(capacity.at)} 조회 · 전송 전에 다시 검사합니다.</p>}
        {kind === 'rule' && <div className="paper-form-row"><label>기준 가격 (원)<input required type="number" min="1" step="1" value={threshold} onChange={e => setThreshold(e.target.value)} /></label><label>발동 조건<select value={comparison} onChange={e => setComparison(e.target.value)}><option value="lte">이하</option><option value="gte">이상</option></select></label></div>}
        <p className="paper-help">주문 금액 {money(Number(price) * Number(quantity))}원</p>
        <button className="paper-danger" disabled={blocked || !stock || (kind === 'order' && !state.running)}>{kind === 'rule' ? '실전 조건 내용 확인' : '실전 주문 내용 확인'}</button>
        <p className="paper-help">실전 가격 조건: 평일 09:00~15:20, 약 10초마다 확인합니다. 휴장일은 별도 판단하지 않습니다. 조건 충족 후 접수 또는 오류 결과를 남기고 반복하지 않습니다. 현재 {state.session_open ? '조건 확인 시간' : '조건 확인 시간 외'}입니다.</p>
      </form></section>
      <section className="paper-card"><h2>실계좌 잔고</h2>{historyError && <p className="error">{historyError} · 이전 조회값이 표시될 수 있습니다.</p>}
        <p className="paper-help">계좌 {accountLabel(state.account)} · {validHistory ? timestamp(history.checked_at) : '조회 중'}</p>
        {validHistory && <><p className="live-cash">예수금 {money(history.balance.summary.cash)}원</p><div className="paper-table-wrap"><table><thead><tr><th>종목</th><th>구분</th><th>보유 수량</th></tr></thead><tbody>{history.balance.holdings.map(p => <tr key={p.id}><td>{p.name}<small>{p.code}</small></td><td>{p.holding_type}</td><td>{money(p.quantity)}주</td></tr>)}{!history.balance.holdings.length && <tr><td colSpan={3}>보유 종목 없음</td></tr>}</tbody></table></div></>}
        <p className="paper-help">예수금과 주문 가능 금액은 다를 수 있습니다. 현금 주문 가능 수량 조회 결과를 사용하며 신용 보유분의 매도는 지원하지 않습니다.</p>
      </section>
    </div>
    <section className="paper-card"><h2>증권사 주문·체결 내역</h2><div className="paper-controls"><label>조회일 <input type="date" value={`${day.slice(0,4)}-${day.slice(4,6)}-${day.slice(6,8)}`} onChange={e => { if (e.target.value) setDay(e.target.value.replaceAll('-', '')) }} /></label><button onClick={() => setRevision(v => v + 1)}>계좌·주문 새로고침</button></div>
      <p className="paper-help">15초마다 조회합니다. 부분 체결·잔량·취소 수량은 증권사 응답 기준입니다. 당일 정상 KRX 현금 지정가 주문만 정정·취소할 수 있습니다.</p>
      <div className="paper-table-wrap"><table><thead><tr><th>주문번호 / 원주문</th><th>종목 / 구분</th><th>주문 수량 / 가격</th><th>체결 / 잔량 / 취소</th><th>증권사 상태</th><th>미체결 관리</th></tr></thead><tbody>
        {(validHistory ? history.rows : []).map(r => <tr key={r.broker_id}><td>{r.broker_id}<small>원주문 {r.original_id}</small></td><td>{r.name}<small>{r.code} · {r.side_name} · {r.market}</small></td><td>{r.quantity}주<small>{money(r.price)}원</small></td><td>{r.filled} / {r.remaining} / {r.cancelled}<small>평균 {money(r.average_price)}원</small></td><td>{r.reason}</td><td>{day === today() && r.remaining > 0 && r.reason === '정상' && r.market === 'KRX' && r.split === 'N' && ['buy','sell'].includes(r.side) && ['보통','보통가','지정가'].includes(r.order_type) ? <div className="paper-inline"><input aria-label={`${r.broker_id} 정정 지정가`} type="number" min="1" placeholder="정정 가격" value={amend[r.broker_id] || ''} onChange={e => setAmend({ ...amend, [r.broker_id]: e.target.value })} /><button disabled={blocked || !state.running || !amend[r.broker_id] || !!historyError} onClick={() => prepare(`/orders/${r.broker_id}`, { action: 'modify', price: Number(amend[r.broker_id]), order_day: day }, '실전 잔량 가격 정정', `${r.name} (${r.code}) · 주문 ${r.broker_id} · 새 지정가 ${money(Number(amend[r.broker_id]))}원`, true)}>정정</button><button disabled={blocked || !!historyError} onClick={() => prepare(`/orders/${r.broker_id}`, { action: 'cancel', price: 0, order_day: day }, '실전 미체결 잔량 취소', `${r.name} (${r.code}) · 주문 ${r.broker_id} · 현재 잔량 ${r.remaining}주`, true)}>취소</button></div> : '—'}</td></tr>)}
        {validHistory && !history.rows.length && <tr><td colSpan={6} className="paper-empty">해당 날짜의 주문 내역이 없습니다.</td></tr>}
      </tbody></table></div>
    </section>
    <section className="paper-card"><h2>실전 가격 조건</h2><div className="paper-table-wrap"><table><thead><tr><th>계좌 / 종목</th><th>조건 / 주문</th><th>상태</th><th>관리</th></tr></thead><tbody>{state.rules.map(r => <tr key={r.id}><td>{r.name || "종목명 확인 불가"}<small>{r.code} · {accountLabel(r.account)}</small></td><td>{money(r.threshold)}원 {r.comparison === 'lte' ? '이하' : '이상'}<small>{r.side === 'buy' ? '매수' : '매도'} {r.quantity}주 · {money(r.price)}원</small></td><td>{ruleState[r.status]}<small>{r.message}</small></td><td>{r.status === 'armed' && <button disabled={blocked} onClick={() => execute({ path: `/rules/${r.id}/cancel`, payload: {}, version: state.version })}>조건 해제</button>}</td></tr>)}{!state.rules.length && <tr><td colSpan={4} className="paper-empty">등록된 조건이 없습니다.</td></tr>}</tbody></table></div></section>
    <section className="paper-card"><h2>앱 주문 전송 기록 <small>확인 대기 전체 + 최근 200건</small></h2><p className="paper-help">접수 성공은 체결 완료와 다릅니다. 결과 확인 필요 항목은 자동 재전송하지 않으며, 확인 처리 전 신규 주문을 잠급니다.</p>
      <div className="paper-table-wrap"><table><thead><tr><th>시각 / 계좌</th><th>종목 / 작업</th><th>수량 / 가격</th><th>접수 결과</th></tr></thead><tbody>{state.operations.map(op => <tr key={op.id}><td>{timestamp(op.created_at)}<small>{accountLabel(op.account)}</small></td><td>{op.name || "종목명 확인 불가"}<small>{op.code}</small><small>{{buy:'매수',sell:'매도',modify:'정정',cancel:'취소'}[op.kind]}</small></td><td>{op.quantity}주<small>{money(op.price)}원</small></td><td>{operationState[op.status]} · 주문번호 {op.broker_id || '미확인'}<small>{op.message}</small>{op.status === 'unknown' && <Resolution op={op} busy={blocked} prepare={prepare} />}</td></tr>)}{!state.operations.length && <tr><td colSpan={4} className="paper-empty">아직 전송한 실전 주문이 없습니다.</td></tr>}</tbody></table></div>
    </section>
    {preview && <div className="live-modal-shade"><section className="paper-card live-modal" role="dialog" aria-modal="true" aria-label="실전 작업 최종 확인"><h2>{preview.title}</h2><p>실제 계좌 {accountLabel(preview.account)}</p><p>{preview.detail}</p><p className="paper-help">현재 화면의 작업을 확인한 뒤 전송하세요. 실전 주문은 실제 계좌에 반영됩니다.</p><div className="paper-controls"><button disabled={busy} onClick={() => setPreview(null)}>돌아가기</button><button className="paper-danger" disabled={busy || disconnected || preview.version !== state.version || preview.day !== today() || state.emergency_active || (preview.payload.order_day && preview.payload.order_day !== today())} onClick={() => execute(preview)}>{busy ? '증권사 응답 확인 중…' : '확인 · 실행'}</button></div>{(preview.version !== state.version || preview.day !== today()) && <p className="error">상태가 바뀌었습니다. 돌아가서 다시 확인하세요.</p>}{error && <p className="error" role="alert">{error}</p>}<button className="paper-danger" onClick={() => execute({ path: '/control', payload: { action: 'emergency' }, version: state.version }, true)}>긴급정지 · 앱 주문 취소</button></section></div>}
  </div>
}
