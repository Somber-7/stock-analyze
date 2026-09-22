import { useEffect, useRef, useState } from 'react'
import { API, tradingRequest, accountLabel } from '../lib/tradingApi'
import ConnectionStatus from './ConnectionStatus'
import './PaperTrading.css'
import './LiveTrading.css'

export default function TradingSettings({ onSaved, onConnection }) {
  const [settings, setSettings] = useState(null)
  const [accounts, setAccounts] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [ack, setAck] = useState(false)
  const [revision, setRevision] = useState(0)
  const [accountRevision, setAccountRevision] = useState(0)
  const [connection, setConnection] = useState({ has_key: true, connection: { status: 'checking', checked_at: null, scope: 'accounts' } })
  const [saved, setSaved] = useState(null)
  const accountPending = useRef(null)
  const dirty = Boolean(settings && saved && (settings.mode !== saved.mode || settings.account !== saved.account))
  useEffect(() => { onConnection?.(connection) }, [connection, onConnection])
  useEffect(() => {
    const controller = new AbortController()
    tradingRequest('', undefined, undefined, controller.signal).then(result => { if (!controller.signal.aborted) { setSettings(result); setSaved(result) } })
      .catch(e => { if (!controller.signal.aborted) setError(e.message) })
    return () => controller.abort()
  }, [revision])

  useEffect(() => {
    const controller = new AbortController()
    accountPending.current = controller
    const timeout = setTimeout(() => controller.abort('timeout'), 45000)
    fetch(`${API}/api/accounts`, { signal: controller.signal }).then(async r => {
      const data = await r.json()
      if (!r.ok) throw new Error(data.detail || '계좌 조회 실패')
      if (!Array.isArray(data)) throw new Error('계좌 응답을 확인하지 못했습니다.')
      if (controller.signal.aborted || accountPending.current !== controller) return
      setAccounts(data)
      setConnection({ has_key: true, accountCount: data.length, connection: { status: 'success', checked_at: new Date().toISOString(), scope: 'accounts' } })
    }).catch(() => {
      if (accountPending.current !== controller || (controller.signal.aborted && controller.signal.reason !== 'timeout')) return
      setAccounts([])
      setConnection({ has_key: true, connection: { status: 'error', checked_at: new Date().toISOString(), scope: 'accounts', message: controller.signal.reason === 'timeout' ? '계좌 조회 시간 초과 · 다시 확인해 주세요' : '나무 계좌를 조회하지 못했습니다' } })
    }).finally(() => { clearTimeout(timeout); if (accountPending.current === controller) accountPending.current = null })
    return () => { clearTimeout(timeout); controller.abort(); if (accountPending.current === controller) accountPending.current = null }
  }, [accountRevision])

  async function save(event) {
    event.preventDefault()
    setBusy(true); setError('')
    try {
      const result = await tradingRequest('/settings', { mode: settings.mode, account: settings.account,
        live_acknowledged: ack }, settings.version)
      setSaved(result)
      setSettings(result)
      onSaved?.(result)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return <div className="paper-page">
    <div className="paper-card ai-check-panel"><div><h4>나무 API 연결</h4><ConnectionStatus record={connection} /><p className="paper-help ai-action-help">{connection?.accountCount === 0 ? '조회된 계좌가 없습니다. 주문 가능 여부는 확인하지 않았습니다.' : '계좌 정보만 조회합니다. 주문 가능 여부는 확인하지 않습니다.'}</p></div><button type="button" disabled={busy || dirty || connection?.connection.status === 'checking'} onClick={() => { setConnection({ has_key: true, connection: { status: 'checking', checked_at: null, scope: 'accounts' } }); setAccountRevision(v => v + 1) }}>{connection?.connection.status === 'checking' ? '계좌 조회 중…' : '계좌 연결 다시 확인'}</button></div>
    {dirty && <p className="paper-help">설정 저장 후 계좌 연결을 다시 확인할 수 있습니다.</p>}
    {error && <div className="error" role="alert">{error} <button onClick={() => { setError(''); setRevision(v => v + 1) }}>설정 다시 불러오기</button></div>}
    {!settings ? <p>설정을 불러오는 중…</p> : <form className="paper-card paper-form live-settings" onSubmit={save}>
      <h2>매매·계좌</h2>
      <label>사용할 모드<select value={settings.mode} onChange={e => { setSettings({ ...settings, mode: e.target.value }); setAck(false) }}>
        <option value="paper">모의매매 · 가상 잔고로 동작 시험</option><option value="live">실전매매 · 나무 실계좌 주문</option>
      </select></label>
      <div className={`paper-banner ${settings.mode === 'live' ? 'live-banner' : ''}`}>
        {settings.mode === 'live' ? '실제 계좌로 주문하는 모드입니다. 저장 후 주문 화면에서 실행을 시작하세요.' : '가상 잔고로 거래합니다. 실제 주문은 전송하지 않습니다.'}
      </div>
      <label>실전 주문 계좌<select value={settings.account} onChange={e => setSettings({ ...settings, account: e.target.value })}>
        <option value="">계좌 선택</option>{accounts.map(a => <option key={a.id} value={a.id}>{a.label || accountLabel(a.id)}</option>)}
      </select></label>
      {settings.mode === 'live' && <label className="live-check"><input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)} />실전 모드에서는 실제 계좌로 주문된다는 점을 확인했습니다.</label>}
      <div className="settings-save-bar"><p className="paper-help">저장하면 자동 실행이 정지됩니다.</p><button className="paper-primary" disabled={busy || (settings.mode === 'live' && !ack)}>{busy ? '저장 중…' : '설정 저장'}</button></div>
      <details className="settings-details"><summary>주문 지원 범위</summary><p>앱 자체의 주문 금액 제한은 없습니다. 나무에서 조회한 현금 주문가능금액·수량과 매도 가능 수량을 확인합니다.</p><p>국내 현금·KRX 지정가 주문을 지원합니다. 가격 조건은 평일 09:00~15:20에 확인하며 휴장일 여부는 별도로 판단하지 않습니다. 신용·공매도·해외 주문은 지원하지 않습니다.</p></details>
    </form>}
  </div>
}
