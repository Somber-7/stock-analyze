import { useCallback, useEffect, useRef, useState } from 'react'
import StockPicker from './StockPicker'
import AIPromptPresets from './AIPromptPresets'
import AIAnalysisReport from './AIAnalysisReport'
import { HORIZONS } from '../lib/investmentHorizons'
import { timestamp } from '../lib/tradingApi'
import { aiOperationRequest } from '../lib/aiOperationApi'
import { selectAnalysisRun } from '../lib/analysisSelection'
import { showToast } from '../lib/toast'
import './PaperTrading.css'
import './AIOperation.css'

const EXECUTIONS = { suggest: '자동 분석·제안만', paper: '자동 모의 주문', live: '자동 실전 주문' }
const STATUSES = { analyzing: '분석 중', ready: '분석 완료', error: '오류', interrupted: '중단됨' }
const count = value => value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toLocaleString('ko-KR')
const optionalNumber = value => value === '' || value == null ? null : Number(value)
const configValue = config => ({ holding_purpose: config?.holding_purpose || '', max_position_pct: optionalNumber(config?.max_position_pct), review_drawdown_pct: optionalNumber(config?.review_drawdown_pct) })
const sameConfig = (a, b) => a && b && a.execution === b.execution && Number(a.interval_minutes) === Number(b.interval_minutes) && a.objective === b.objective && a.include_us === b.include_us && Boolean(a.include_web) === Boolean(b.include_web) && (a.investment_horizon || 'unspecified') === (b.investment_horizon || 'unspecified') && JSON.stringify(a.codes) === JSON.stringify(b.codes) && JSON.stringify(configValue(a)) === JSON.stringify(configValue(b))

export default function AIOperation({ initialCode = '', initialRunId = null, onSettings, onOrders }) {
  const [view, setView] = useState(initialCode ? 'setup' : 'results')
  const viewButtons = useRef([])
  const [state, setState] = useState(null)
  const [form, setForm] = useState(null)
  const [formVersion, setFormVersion] = useState(null)
  const [names, setNames] = useState({})
  const [candidate, setCandidate] = useState(null)
  const [holdings, setHoldings] = useState(null)
  const [focusedId, setFocusedId] = useState(initialRunId)
  const [liveAck, setLiveAck] = useState(false)
  const [action, setAction] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [now, setNow] = useState(() => Date.now())
  const alive = useRef(false)
  const pending = useRef(null)
  const reading = useRef(null)
  const initialized = useRef(false)
  const observed = useRef(null)
  const baseline = useRef(null)

  const accept = useCallback((result, replaceForm = false) => {
    if (!alive.current) return
    const signature = JSON.stringify([result.version, result.mode, result.connection])
    if (observed.current !== signature) { setLiveAck(false); observed.current = signature }
    setState(result)
    setNames(previous => ({ ...previous, ...Object.fromEntries((result.symbols || []).map(row => [row.code, row.name])) }))
    if (!initialized.current || replaceForm) {
      const config = { ...result.config, ...configValue(result.config), codes: [...result.config.codes] }
      if (!initialized.current && initialCode && !config.codes.includes(initialCode) && config.codes.length < 10) config.codes.push(initialCode)
      setForm(config)
      setFormVersion(result.version)
      baseline.current = result.config
      initialized.current = true
    } else if (sameConfig(baseline.current, result.config)) {
      setFormVersion(result.version)
    }
  }, [initialCode])

  const refresh = useCallback(async () => {
    if (pending.current || reading.current) return
    const controller = new AbortController()
    reading.current = controller
    try {
      const result = await aiOperationRequest('', undefined, controller.signal)
      if (!controller.signal.aborted) accept(result)
    } catch (e) {
      if (alive.current && !controller.signal.aborted) setError(e.message)
    } finally {
      if (reading.current === controller) reading.current = null
    }
  }, [accept])

  useEffect(() => {
    alive.current = true
    refresh()
    const timer = setInterval(() => { setNow(Date.now()); refresh() }, 3000)
    return () => { alive.current = false; clearInterval(timer); reading.current?.abort(); reading.current = null; pending.current?.abort(); pending.current = null }
  }, [refresh])

  async function manage(label, path, body, message) {
    if (pending.current || !state) return
    reading.current?.abort()
    reading.current = null
    const controller = new AbortController()
    pending.current = controller
    setAction(label); setError(''); setNotice('')
    try {
      const result = await aiOperationRequest(path, { ...body, version: path === '/settings' ? formVersion : state.version }, controller.signal)
      if (alive.current && !controller.signal.aborted) {
        accept(result, path === '/settings')
        if (path === '/settings' || path === '/analyze') showToast(message); else setNotice(message)
        if (path === '/analyze') { setFocusedId(null); setView('results') }
      }
    } catch (e) {
      if (alive.current && !controller.signal.aborted) {
        if (path === '/settings' || path === '/analyze') showToast(e.message, { tone: 'error' }); else setError(e.message)
        try {
          const latest = await aiOperationRequest('', undefined, controller.signal)
          if (!controller.signal.aborted) accept(latest)
        } catch { /* Preserve the original error and the draft. Polling will refresh state. */ }
      }
    } finally {
      if (alive.current && pending.current === controller) { pending.current = null; setAction(''); setLiveAck(false) }
    }
  }

  async function loadHoldings() {
    if (pending.current) return
    const controller = new AbortController()
    pending.current = controller
    setAction('holdings'); setError('')
    try {
      const rows = await aiOperationRequest('/holdings', undefined, controller.signal)
      if (alive.current && !controller.signal.aborted) {
        setHoldings(rows)
        setNames(previous => ({ ...previous, ...Object.fromEntries(rows.map(row => [row.code, row.name])) }))
        showToast('보유 종목을 조회했습니다. 분석할 종목을 직접 추가하세요.')
      }
    } catch (e) { if (alive.current && !controller.signal.aborted) showToast(e.message, { tone: 'error' }) }
    finally { if (alive.current && pending.current === controller) { pending.current = null; setAction('') } }
  }

  const chooseCandidate = useCallback(row => {
    setCandidate(row)
    if (row) setNames(previous => ({ ...previous, [row.code]: row.name }))
  }, [])

  function edit(key, value) {
    setForm(previous => ({ ...previous, [key]: value }))
    setNotice(''); setLiveAck(false)
  }
  function addCode(code) {
    if (!code || form.codes.includes(code) || form.codes.length >= 10) return
    if (!/^[0-9A-Z]{6}$/.test(code) || !state.symbols.some(row => row.code === code)) {
      showToast('국내 종목 목록에서 확인되는 주식만 추가할 수 있습니다. CMA 등은 분석 대상에서 제외됩니다.', { tone: 'error' })
      return
    }
    edit('codes', [...form.codes, code])
  }

  const dirty = Boolean(form && state && !sameConfig(form, state.config))
  const changedVersion = Boolean(state && formVersion !== state.version)
  const locked = Boolean(action)
  const ready = Boolean(state?.connection?.has_key && state?.connection?.model)
  const execution = state?.config.execution
  const live = execution === 'live'
  const manualLive = state?.mode === 'live'
  const engineReady = execution === 'suggest' || (state?.engine_running && state?.mode === execution)
  const availableCodes = new Set((state?.symbols || []).map(row => row.code))
  const invalidCodes = (form?.codes || []).filter(code => !/^[0-9A-Z]{6}$/.test(code) || !availableCodes.has(code))
  const invalidInterval = !Number.isInteger(Number(form?.interval_minutes)) || Number(form?.interval_minutes) < 5 || Number(form?.interval_minutes) > 1440
  const invalidHoldingPurpose = (form?.holding_purpose?.length || 0) > 500
  const invalidOptionalPct = value => value !== '' && value != null && (!Number.isFinite(Number(value)) || Number(value) <= 0 || Number(value) > 100)
  const invalidRiskInputs = invalidOptionalPct(form?.max_position_pct) || invalidOptionalPct(form?.review_drawdown_pct)
  const invalid = invalidCodes.length > 0 || !form?.codes.length || invalidInterval || !form?.objective.trim() || (form?.objective.length || 0) > 2000 || invalidHoldingPurpose || invalidRiskInputs
  const webReady = !form?.include_web || state?.web_search?.has_key
  const canAnalyze = Boolean(state && ready && webReady && !locked && !state.busy && !dirty && !invalid && !changedVersion && state.config.codes.length)
  const analysisHint = locked ? '요청을 처리하고 있습니다.'
    : state?.busy ? '진행 중인 분석이 끝나면 다시 분석할 수 있습니다.'
    : state?.running ? '1회만 분석하려면 먼저 자동 운용을 정지하세요.'
    : !ready ? 'AI 연결 설정에서 API 키와 모델을 저장하세요.'
    : !webReady ? '설정의 웹 검색 탭에서 Tavily API 키를 저장하세요.'
    : invalidCodes.length ? `${invalidCodes.map(code => names[code] || code).join(', ')}: 국내 주식 분석 대상이 아닙니다. 선택 목록에서 제외하세요.`
    : !form?.codes.length ? '분석할 종목을 추가한 뒤 설정을 저장하세요.'
    : invalidInterval ? '자동 운용의 반복 주기를 5~1440분으로 입력하세요.'
    : invalidHoldingPurpose ? '보유 목적은 500자 이내로 입력하세요.'
    : invalidRiskInputs ? '비중과 낙폭 기준은 0보다 크고 100 이하인 숫자로 입력하세요.'
    : invalid ? '분석 지침을 1~2,000자로 입력하세요.'
    : changedVersion ? '서버 설정이 변경되었습니다. 최신 설정을 불러온 뒤 저장하세요.'
    : dirty ? '변경한 분석 조건을 먼저 저장하세요.'
    : '1회 분석 준비가 완료되었습니다.'

  function saveSettings() {
    if (!state || invalid || locked || state.busy || state.running || changedVersion) return
    manage('save', '/settings', { ...form, interval_minutes: Number(form.interval_minutes), max_position_pct: optionalNumber(form.max_position_pct), review_drawdown_pct: optionalNumber(form.review_drawdown_pct) }, '분석 설정을 저장했습니다. 1회 분석 버튼을 눌러 시작하세요.')
  }
  const canStart = canAnalyze && engineReady && (!live || liveAck)
  const runs = state?.runs || []
  const run = selectAnalysisRun(runs, focusedId)
  const missingRun = Boolean(focusedId && !run)
  const hasOrderProposals = Boolean(run?.decisions?.some(row => row.side !== 'hold' && row.assessment !== 'defer'))
  const expiryTime = Date.parse(run?.created_at || '')
  const expired = Boolean(run && Number.isFinite(expiryTime) && now - expiryTime > 300000)
  const canExecute = Boolean(run?.status === 'ready' && !expired && state?.engine_running && !locked && !state?.busy && !state?.running && !dirty && (!manualLive || liveAck) && run.mode === state?.mode)

  const views = [{ id: 'results', label: '분석 결과' }, { id: 'setup', label: '분석 설정' }, { id: 'automation', label: '자동 운용' }]
  function selectView(value) { setView(value); setLiveAck(false) }
  function navigateView(event, index) {
    const next = event.key === 'ArrowRight' ? (index + 1) % 3 : event.key === 'ArrowLeft' ? (index + 2) % 3 : event.key === 'Home' ? 0 : event.key === 'End' ? 2 : null
    if (next == null) return
    event.preventDefault(); selectView(views[next].id); viewButtons.current[next]?.focus()
  }
  const saveBar = <div className="aio-save">
    <span>{state?.running ? '자동 운용을 정지하면 수정할 수 있습니다.' : dirty ? '저장하지 않은 변경 사항' : '설정 저장됨'}</span>
    <div>{(dirty || changedVersion) && <button type="button" disabled={locked || state?.busy || state?.running} onClick={() => accept(state, true)}>저장된 설정 복원</button>}
    <button type="button" className="paper-primary" disabled={locked || state?.busy || state?.running || invalid || !dirty || changedVersion} onClick={saveSettings}>{action === 'save' ? '저장 중…' : '조건 저장'}</button></div>
  </div>

  return <section className="paper-page ai-operation" aria-label="AI 분석 및 운용">
    {error && <div className="aio-feedback aio-error" role="alert"><span>{error}</span><button disabled={locked} onClick={() => { setError(''); refresh() }}>새로고침</button></div>}
    {notice && <div className="paper-notice" role="status">{notice}</div>}
    {!state || !form ? <div className="paper-card aio-empty" role="status">{error ? 'AI 운용 상태를 불러오지 못했습니다.' : 'AI 운용 상태를 불러오는 중…'}</div> : <>
      <header className="aio-toolbar">
        <div className="aio-connection"><span className={`aio-state-dot ${state.busy || state.running ? 'active' : ''}`} /><div><strong>{state.connection?.model || 'AI 모델을 연결하세요'}</strong><span>{state.connection?.provider || '연결 미설정'} · {state.mode === 'live' ? '실전 계좌' : '모의 계좌'} · {state.running ? '자동 운용 중' : state.busy ? '분석 중' : '대기 중'}</span></div></div>
        <div className="aio-toolbar-actions"><button onClick={onSettings}>연결 설정</button>{(state.running || state.busy) && <button className="paper-danger" disabled={locked} onClick={() => manage('stop', '/control', {action:'stop'}, 'AI 운용을 정지했습니다. 접수된 주문은 주문 화면에서 확인하세요.')}>AI 정지</button>}<button className="paper-primary" disabled={!canAnalyze || state.running} onClick={() => manage('analyze', '/analyze', {}, '1회 분석을 요청했습니다. 주문은 실행하지 않습니다.')}>{state.busy ? '분석 중…' : '1회 분석'}</button></div>
      </header>
      <div className="aio-context-line"><span>{state.config.codes.length}개 종목 · {HORIZONS[state.config.investment_horizon] || '기간 미지정'} · 웹 검색 {state.config.include_web ? '포함' : '꺼짐'} · DART {state.dart?.enabled ? '포함' : '꺼짐'}</span><span>1회 분석은 주문 없이 결과만 생성합니다.</span></div>
      {(!canAnalyze || state.running) && <div className="aio-readiness" role="status"><span>{analysisHint}</span>{!ready || !webReady ? <button onClick={onSettings}>연결 설정</button> : !state.running && !state.busy && view !== (invalidInterval ? 'automation' : 'setup') && <button onClick={() => selectView(invalidInterval ? 'automation' : 'setup')}>{invalidInterval ? '반복 주기 확인' : '분석 조건 확인'}</button>}</div>}
      {changedVersion && <div className="aio-feedback" role="alert">서버 설정이 변경되었습니다. 입력 내용을 확인한 뒤 저장된 설정을 복원하세요.</div>}
      {state.error && state.error !== error && <div className="aio-feedback aio-error" role="alert">{state.error}</div>}
      <nav className="aio-tabs" role="tablist" aria-label="AI 작업 화면">{views.map((item,index) => <button key={item.id} role="tab" id={`aio-tab-${item.id}`} aria-controls={`aio-panel-${item.id}`} aria-selected={view === item.id} tabIndex={view === item.id ? 0 : -1} ref={node=>{viewButtons.current[index]=node}} onClick={()=>selectView(item.id)} onKeyDown={event=>navigateView(event,index)}>{item.label}{item.id === 'setup' && dirty && <span className="aio-unsaved" aria-label="저장하지 않은 변경 사항" />}{item.id === 'automation' && state.running && <span className="aio-unsaved" />}</button>)}</nav>

      <div role="tabpanel" id="aio-panel-results" aria-labelledby="aio-tab-results" hidden={view !== 'results'}>
        <div className="aio-report-heading"><div><h2>{run || missingRun ? '분석 리포트' : '첫 분석을 시작하세요'}</h2><p>{run || missingRun ? '종목별 판단을 비교하고 필요한 근거를 펼쳐보세요.' : '종목과 분석 관점을 저장하면 리포트가 여기에 쌓입니다.'}</p></div>{runs.length > 0 && <label className="aio-history-select">분석 이력<select value={run?.id || ''} onChange={event=>{setFocusedId(event.target.value);setLiveAck(false)}}>{missingRun && <option value="" disabled>선택한 이력 조회 불가</option>}{runs.map(row=><option key={row.id} value={row.id}>{timestamp(row.created_at)} · {STATUSES[row.status] || row.status}{row.source === 'auto' ? ' · 자동' : ''}</option>)}</select></label>}</div>
        {missingRun ? <div className="paper-card aio-empty" role="status"><h3>선택한 분석을 불러올 수 없습니다</h3><p>최근 50개 표시 범위를 벗어났거나 이력이 삭제되었습니다. 위 목록에서 확인할 분석을 직접 선택하세요.</p></div> : !run ? <div className="paper-card aio-empty"><div className="aio-empty-symbol" aria-hidden="true">↗</div><h3>어떤 종목을 살펴볼까요?</h3><p>국내 종목 선택 → 분석 조건 저장 → 1회 분석</p><button onClick={()=>selectView('setup')}>분석 설정으로 이동</button></div> : <AIAnalysisReport key={run.id} run={run} names={names} state={state} expired={expired} hasOrderProposals={hasOrderProposals} canExecute={canExecute} manualLive={manualLive} liveAck={liveAck} setLiveAck={setLiveAck} locked={locked} action={action} onOrders={onOrders} onExecute={decision=>manage(`execute-${decision.code}`, `/runs/${encodeURIComponent(run.id)}/execute`, {code:decision.code,live_acknowledged:liveAck}, '제안 실행 결과를 확인하세요.')} />}
      </div>

      <div role="tabpanel" id="aio-panel-setup" aria-labelledby="aio-tab-setup" hidden={view !== 'setup'}>
        <div className="aio-report-heading"><div><h2>분석 설정</h2><p>분석할 종목과 판단에 사용할 조건을 정하세요.</p></div></div>
        <fieldset className="aio-setup-grid" disabled={locked || state.busy || state.running}>
          <section className="paper-card aio-universe-card"><div className="aio-section-heading"><h3><span className="aio-step">01</span>분석 종목</h3><span>{form.codes.length} / 10</span></div>
            <StockPicker initialCode={initialCode} onChange={chooseCandidate} label="종목 이름 또는 코드" />
            <div className="aio-picker-actions"><button type="button" disabled={!candidate || form.codes.includes(candidate.code) || form.codes.length >= 10} onClick={()=>addCode(candidate.code)}>선택 종목 추가</button><button type="button" onClick={loadHoldings}>{action === 'holdings' ? '조회 중…' : '보유 종목 불러오기'}</button></div>
            <div className="aio-universe" aria-label="선택한 분석 종목">{form.codes.map(code=><div className="aio-selected-stock" key={code}><div><strong>{names[code] || code}</strong><small>{code}</small></div><button type="button" aria-label={`${names[code] || code} 분석 범위에서 제거`} onClick={()=>edit('codes',form.codes.filter(item=>item!==code))}>×</button></div>)}{!form.codes.length && <p className="aio-selection-empty">위에서 검색한 종목을 추가하세요.</p>}</div>
            {holdings && <details className="aio-fold" open><summary>보유 종목 {holdings.length}개</summary><div className="aio-holdings">{holdings.map(row=><button type="button" key={row.code} disabled={form.codes.includes(row.code) || form.codes.length >= 10 || !availableCodes.has(row.code)} onClick={()=>addCode(row.code)}><span>{row.name} <small>{row.code}</small></span><span>{count(row.quantity)}주 · {form.codes.includes(row.code) ? '추가됨' : '+ 추가'}</span></button>)}</div><p>CMA는 현금성 잔액으로 반영됩니다.</p></details>}
          </section>
          <section className="paper-card aio-condition-card"><div className="aio-section-heading"><h3><span className="aio-step">02</span>분석 관점</h3></div>
            <AIPromptPresets value={form.objective} onChange={value=>edit('objective',value)} includeUs={form.include_us} compact />
            <label className="aio-field">투자기간<select value={form.investment_horizon || 'unspecified'} onChange={event=>edit('investment_horizon',event.target.value)}>{Object.entries(HORIZONS).map(([key,name])=><option key={key} value={key}>{name}</option>)}</select></label>
            <details className="aio-fold"><summary>보유 목적·위험 기준 <small>선택 입력</small></summary><div className="aio-optional-criteria">
              <label className="aio-objective">보유 목적<textarea maxLength={500} rows={3} value={form.holding_purpose || ''} onChange={event=>edit('holding_purpose',event.target.value)} placeholder="예: 장기 성장, 배당, 단기 이벤트 관찰" /><small>{(form.holding_purpose?.length || 0).toLocaleString()} / 500자</small></label>
              <div className="aio-criteria-numbers"><label className="aio-field">종목 최대 비중 (%)<input type="number" min="0.01" max="100" step="0.01" value={form.max_position_pct ?? ''} onChange={event=>edit('max_position_pct',event.target.value)} placeholder="미지정" /></label><label className="aio-field">재검토 낙폭 (%)<input type="number" min="0.01" max="100" step="0.01" value={form.review_drawdown_pct ?? ''} onChange={event=>edit('review_drawdown_pct',event.target.value)} placeholder="미지정" /></label></div>
              <p className="paper-help">분석 판단에 참고하는 기준이며 주문 수량·가격을 직접 제한하지 않습니다.</p>
            </div></details>
            <div className="aio-data-options"><label className="aio-check"><input type="checkbox" checked={form.include_us} onChange={event=>edit('include_us',event.target.checked)} /><span>미국 시장 참고<small>주요 지수·반도체 시세</small></span></label><label className="aio-check"><input type="checkbox" checked={Boolean(form.include_web)} onChange={event=>edit('include_web',event.target.checked)} /><span>뉴스·공시 검색<small>{state.web_search?.has_key ? 'Tavily 키 등록됨 · 검색 크레딧 사용' : 'Tavily 키 등록 필요'}</small></span></label></div>
            <details className="aio-fold"><summary>분석 지침 직접 편집 <small>{form.objective.length.toLocaleString()} / 2,000자</small></summary><label className="aio-objective">분석 목표와 고려할 조건<textarea maxLength={2000} rows={8} value={form.objective} onChange={event=>edit('objective',event.target.value)} /></label></details>
          </section>
        </fieldset>
        {saveBar}
        <details className="aio-fold aio-footnote"><summary>분석 데이터·사용 요금 안내</summary><p>선택 종목의 시세·일봉·수급·정량 지표, 보유 수량, 계좌 자산·주문가능금액과 투자기간을 AI에 전달합니다. 계좌번호와 API 키는 입력 자료에서 제외합니다. 분석마다 AI API 사용 요금이 발생할 수 있습니다.</p><p>웹 검색은 종목명·코드로 종목당 최대 4회 검색합니다. 관련성이 낮은 결과를 제거한 뒤 필요한 검색만 제한적으로 다시 시도하며, 검색 발췌와 크레딧이 사용될 수 있습니다.</p></details>
      </div>

      <div role="tabpanel" id="aio-panel-automation" aria-labelledby="aio-tab-automation" hidden={view !== 'automation'}>
        <div className="aio-report-heading"><div><h2>자동 운용</h2><p>저장된 분석 조건으로 반복 실행합니다.</p></div><span className={`aio-badge ${state.running ? 'active' : ''}`}>{state.running ? '실행 중' : '정지됨'}</span></div>
        <div className="aio-auto-grid"><section className="paper-card"><h3>실행 설정</h3><fieldset className="aio-auto-fields" disabled={locked || state.busy || state.running}><label className="aio-field">자동 운용 방식<select value={form.execution} onChange={event=>edit('execution',event.target.value)}>{Object.entries(EXECUTIONS).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label><label className="aio-field">반복 주기 (분)<input type="number" min="5" max="1440" step="1" value={form.interval_minutes} onChange={event=>edit('interval_minutes',event.target.value)} /></label></fieldset>{saveBar}</section>
        <section className="paper-card aio-auto-control"><h3>운용 상태</h3><dl className="aio-auto-status"><div><dt>저장된 방식</dt><dd>{EXECUTIONS[execution]}</dd></div><div><dt>다음 실행</dt><dd>{timestamp(state.next_run_at)}</dd></div><div><dt>주문 엔진</dt><dd>{state.engine_running ? '실행 중' : '정지'}</dd></div></dl>
          {live && <label className="aio-check aio-live-ack"><input type="checkbox" checked={liveAck} disabled={locked || state.running} onChange={event=>setLiveAck(event.target.checked)} /><span>자동 실전 운용은 매 주기 실제 계좌로 주문할 수 있음을 확인했습니다.</span></label>}
          {!engineReady && <p className="aio-warning">{execution === state.mode ? '주문 화면에서 주문 엔진을 먼저 시작하세요.' : '저장된 운용 방식과 계좌 모드가 다릅니다.'}</p>}
          <div className="aio-auto-actions"><button className={live ? 'paper-danger' : 'paper-primary'} disabled={state.running || !canStart} onClick={()=>manage('start','/control',{action:'start',live_acknowledged:liveAck},'자동 운용을 시작했습니다.')}>자동 운용 시작</button><button disabled={locked || (!state.running && !state.busy)} onClick={()=>manage('stop','/control',{action:'stop'},'AI 운용을 정지했습니다.')}>운용 정지</button></div><p className="paper-help">정지는 이미 접수된 주문을 취소하지 않습니다.</p><button onClick={onOrders}>주문·긴급정지 화면 열기 →</button>
        </section></div>
        <details className="aio-fold aio-footnote"><summary>자동 실행·주문 조건</summary><p>자동 운용은 앱이 실행 중일 때 동작합니다. 자동 주문은 평일 09:00~15:20(한국)에 확인하며 휴장일 달력은 지원하지 않습니다. 당일 거래 일봉과 양수 거래량이 확인되지 않으면 주문을 보류합니다.</p><p>앱 재시작, 설정 변경, 주문 엔진 정지 또는 오류가 발생하면 자동 운용을 정지합니다. 1회 분석은 위 설정과 관계없이 주문을 실행하지 않습니다.</p></details>
      </div>
    </>}
  </section>
}

