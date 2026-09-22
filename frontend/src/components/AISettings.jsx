import { useEffect, useRef, useState } from 'react'
import { API } from '../lib/tradingApi'
import { withConnection } from '../lib/connectionStatus'
import { showToast } from '../lib/toast'
import ConnectionStatus from './ConnectionStatus'
import './PaperTrading.css'
import './AISettings.css'
import DartSettings from './DartSettings'

const PROVIDERS = [
  { id: 'openai', name: 'OpenAI', caption: 'OpenAI API', mark: 'O' },
  { id: 'anthropic', name: 'Claude', caption: 'Anthropic API', mark: 'A' },
  { id: 'gemini', name: 'Gemini', caption: 'Google AI API', mark: 'G' },
]

async function request(path, body, controller) {
  const timeout = setTimeout(() => controller.abort('timeout'), 60000)
  try {
    const response = await fetch(`${API}/api/ai${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      headers: { 'Content-Type': 'application/json', 'X-AI-Action': 'manage' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    })
    const result = await response.json()
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'AI 설정 요청을 처리하지 못했습니다.')
    return result
  } catch (error) {
    if (controller.signal.aborted) throw new Error('요청 시간이 초과되었습니다. 설정을 다시 불러와 상태를 확인하세요.', { cause: error })
    if (error instanceof TypeError || error instanceof SyntaxError) throw new Error('AI 설정 서버에 연결하지 못했습니다. 잠시 후 다시 시도하세요.', { cause: error })
    throw error
  } finally {
    clearTimeout(timeout)
  }
}

export default function AISettings({ activeTab = 'ai', onSettings, onLoadError }) {
  const [settings, setSettings] = useState(null)
  const [provider, setProvider] = useState('openai')
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [tavilyKey, setTavilyKey] = useState('')
  const [dartKey, setDartKey] = useState('')
  const [dartEnabled, setDartEnabled] = useState(false)
  const [busy, setBusy] = useState('load')
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const mounted = useRef(false)
  const pending = useRef(null)

  useEffect(() => { onSettings?.(settings) }, [settings, onSettings])
  useEffect(() => { onLoadError?.(!settings && Boolean(error)) }, [settings, error, onLoadError])

  function hydrate(result, action = 'load') {
    setSettings(result)
    if (!action.startsWith('tavily-') && !action.startsWith('dart-')) {
      setProvider(result.provider)
      setModel(result.profiles[result.provider]?.model || '')
      setApiKey('')
    }
    if (action === 'load' || action.startsWith('tavily-')) setTavilyKey('')
    if (action === 'load' || action.startsWith('dart-')) { setDartKey(''); setDartEnabled(Boolean(result.tools?.dart?.enabled)) }
  }

  useEffect(() => {
    mounted.current = true
    const controller = new AbortController()
    pending.current = controller
    request('/settings', undefined, controller)
      .then(result => { if (!controller.signal.aborted) hydrate(result) })
      .catch(e => { if (mounted.current && (!controller.signal.aborted || controller.signal.reason === 'timeout')) setError(e.message) })
      .finally(() => {
        if (pending.current === controller && mounted.current) { pending.current = null; setBusy('') }
      })
    return () => { mounted.current = false; pending.current?.abort(); pending.current = null }
  }, [revision])

  async function manage(action, path, body, message) {
    if (pending.current || !settings) return
    let controller = new AbortController()
    pending.current = controller
    setBusy(action)
    setError('')
    const checkTarget = action === 'check' ? provider : action === 'tavily-check' ? 'tavily' : action === 'dart-check' ? 'dart' : null
    const scope = checkTarget === 'tavily' ? 'usage' : checkTarget === 'dart' ? 'company' : 'models'
    if (checkTarget) setSettings(current => withConnection(current, checkTarget, { status: 'checking', checked_at: null, scope }))
    else {
      const changedTarget = action.startsWith('tavily-') ? 'tavily' : action.startsWith('dart-') ? 'dart' : action === 'import' ? 'openai' : provider
      setSettings(current => withConnection(current, changedTarget, { status: 'unverified', checked_at: null }))
    }
    try {
      const result = await request(path, { ...body, version: settings.version }, controller)
      if (mounted.current && !controller.signal.aborted) { hydrate(result, action); showToast(message) }
    } catch (e) {
      if (mounted.current) {
        // A lost response does not establish whether the provider accepted the check.
        if (checkTarget) setSettings(current => withConnection(current, checkTarget, { status: 'unverified', checked_at: null, scope }))
        controller = new AbortController()
        pending.current = controller
        try {
          const latest = await request('/settings', undefined, controller)
          if (mounted.current && !controller.signal.aborted) {
            // The server snapshot also accounts for completed checks and concurrent key changes.
            setSettings(latest)
            showToast(e.message, { tone: 'error' })
          }
        } catch {
          // Keep the original error and entered draft; the retry button can reload later.
          if (mounted.current) setError(e.message)
        }
      }
    } finally {
      if (mounted.current && pending.current === controller) { pending.current = null; setBusy('') }
    }
  }

  function reload() {
    if (pending.current) return
    setApiKey('')
    setTavilyKey('')
    setDartKey('')
    setBusy('load')
    setError('')
    setRevision(value => value + 1)
  }

  function selectProvider(id) {
    if (busy || id === provider) return
    setProvider(id)
    setModel(settings.profiles[id]?.model || '')
    setApiKey('')
    setError('')
  }

  const profile = settings?.profiles[provider]
  const selected = PROVIDERS.find(item => item.id === provider)
  const models = profile?.models || []
  const dirty = Boolean(settings && (provider !== settings.provider || model.trim() !== (profile?.model || '') || apiKey.trim()))
  const listedModel = models.some(item => item.id === model)
  const hasTavilyKey = Boolean(settings?.tools?.tavily?.has_key)
  const tavilyDirty = Boolean(tavilyKey.trim())

  return <section className="paper-page ai-settings" aria-label="AI 연결 설정" aria-busy={Boolean(busy)} hidden={activeTab === 'trading'}>


    {error && <div className="ai-feedback ai-feedback-error" role="alert"><span>{error}</span><button type="button" disabled={Boolean(busy)} onClick={reload}>설정 다시 불러오기</button></div>}

    {!settings ? <div className="paper-card ai-loading" role="status">{busy ? 'AI 설정을 불러오는 중…' : '설정을 불러오지 못했습니다. 다시 불러오기를 눌러주세요.'}</div> : <>
      <div role="tabpanel" id="settings-panel-ai" aria-labelledby="settings-tab-ai" hidden={activeTab !== 'ai'}>
      <div className="ai-provider-list" role="group" aria-label="AI 서비스 선택">
        {PROVIDERS.map(item => <button type="button" key={item.id} className={`ai-provider ${provider === item.id ? 'is-selected' : ''}`} aria-pressed={provider === item.id} disabled={Boolean(busy)} onClick={() => selectProvider(item.id)}>
          <span className="ai-provider-mark" aria-hidden="true">{item.mark}</span>
          <span className="ai-provider-copy"><strong>{item.name}</strong></span>
          <ConnectionStatus record={settings.profiles[item.id]} compact />
          {settings.provider === item.id && <span className="ai-active-label">선택됨</span>}
        </button>)}
      </div>

      <form className="paper-card ai-editor" onSubmit={event => {
        event.preventDefault()
        manage('save', '/settings', { provider, model: model.trim(), ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}) }, `${selected.name} 설정을 저장했습니다.`)
      }}>
        <div className="ai-editor-heading"><h3>{selected.name} 연결</h3><span className="ai-selected-status">{profile?.has_key ? '키 저장됨' : '키 미등록'}</span></div>
        <fieldset disabled={Boolean(busy)} className="ai-fields">
          <div className="ai-field"><label htmlFor="ai-api-key">API 키</label><input id="ai-api-key" key={provider} type="password" value={apiKey} onChange={event => setApiKey(event.target.value)} autoComplete="off" spellCheck={false} autoCapitalize="none" placeholder={profile?.has_key ? '새 키를 입력하면 기존 키가 교체됩니다' : 'API 키 입력'} aria-describedby="ai-key-help" /><p id="ai-key-help" className="paper-help">키 변경 시에만 입력하세요.</p></div>

          <div className="ai-model-fields">
            <div className="ai-field"><label htmlFor="ai-model-list">조회된 모델</label><select id="ai-model-list" value={listedModel ? model : ''} onChange={event => { if (event.target.value) setModel(event.target.value) }} disabled={!models.length}>
              <option value="">{models.length ? '모델 선택 또는 ID 직접 입력' : '인증 확인 후 모델 목록을 불러옵니다'}</option>
              {models.map(item => <option key={item.id} value={item.id}>{item.name || item.id}{item.name && item.name !== item.id ? ` · ${item.id}` : ''}</option>)}
            </select></div>
            <div className="ai-field"><label htmlFor="ai-model-id">모델 ID 직접 입력</label><input id="ai-model-id" value={model} onChange={event => setModel(event.target.value)} placeholder="사용할 모델의 정확한 ID" autoComplete="off" spellCheck={false} autoCapitalize="none" /></div>
          </div>
          
        </fieldset>

        <div className="ai-save-row"><span className={dirty ? 'ai-dirty' : 'paper-help'} role="status">{dirty ? '저장하지 않은 변경 사항' : '저장됨'}</span><button className="paper-primary" type="submit" disabled={Boolean(busy) || !dirty}>{busy === 'save' ? '저장 중…' : `${selected.name} 설정 저장`}</button></div>

        <div className="ai-check-panel"><div><h4>모델 연결</h4><ConnectionStatus record={profile} /></div><button type="button" disabled={Boolean(busy) || dirty || !profile?.has_key} onClick={() => manage('check', `/${provider}/check`, {}, '인증을 확인하고 모델 목록을 새로 불러왔습니다.')}>{busy === 'check' ? '확인 중…' : '인증 확인 · 모델 조회'}</button></div>
        {dirty && <p className="paper-help ai-action-help">저장 후 인증을 확인할 수 있습니다.</p>}

        <details className="settings-details"><summary>키 관리</summary><div className="ai-key-management">
          {provider === 'openai' && <details className="ai-import"><summary>파일에서 OpenAI 키 가져오기</summary><p className="paper-help">서버의 Api_Key.txt를 읽어 저장하며 기존 OpenAI 키가 있으면 교체합니다. EXE는 사용자 앱 데이터 폴더(%APPDATA%\stock-analyze), 소스 실행은 프로젝트 폴더를 사용합니다.</p><button type="button" disabled={Boolean(busy) || dirty} onClick={() => manage('import', '/import-openai', {}, 'Api_Key.txt에서 OpenAI 키를 가져와 저장했습니다.')}>{busy === 'import' ? '가져오는 중…' : '서버의 Api_Key.txt에서 OpenAI 키 가져오기'}</button></details>}
          <div className="ai-delete"><p className="paper-help">이 서비스의 저장된 키를 삭제합니다.</p><button className="paper-danger" type="button" disabled={Boolean(busy) || dirty || !profile?.has_key} onClick={() => manage('delete', `/${provider}/delete-key`, {}, `${selected.name} API 키를 삭제했습니다.`)}>{busy === 'delete' ? '삭제 중…' : `${selected.name} 저장된 키 삭제`}</button></div>
        </div></details>
        <details className="settings-details"><summary>연결 도움말</summary><p>모델 목록에서 선택하거나 ID를 직접 입력하세요. 키만 먼저 저장할 수도 있습니다.</p><p>인증 확인은 모델 목록만 조회하며 유료 응답을 생성하지 않습니다. 생성 권한과 잔여 한도는 제공사에서 확인하세요.</p><p>키는 현재 Windows 계정으로 암호화되어 저장됩니다. 빈 입력란은 기존 키를 유지합니다. AI 서비스 전환 시 입력 중인 키와 모델은 초기화됩니다.</p></details>
      </form>
      </div>
      <div role="tabpanel" id="settings-panel-search" aria-labelledby="settings-tab-search" hidden={activeTab !== 'search'}>
      <form className="paper-card ai-editor ai-search-editor" aria-labelledby="tavily-settings-title" onSubmit={event => {
        event.preventDefault()
        if (!tavilyDirty) return
        manage('tavily-save', '/tools/tavily/settings', { api_key: tavilyKey.trim() }, 'Tavily API 키를 저장했습니다. AI 분석에서 뉴스·공시 웹 검색 포함을 선택하고 설정을 저장하세요.')
      }}>
        <div className="ai-editor-heading"><div><h3 id="tavily-settings-title">Tavily 웹 검색</h3></div><span className={`ai-key-status ${hasTavilyKey ? 'is-stored' : ''}`}>{hasTavilyKey ? '키 저장됨' : '키 미등록'}</span></div>
        <fieldset disabled={Boolean(busy)} className="ai-fields">
          <div className="ai-field"><label htmlFor="tavily-api-key">Tavily API 키</label><input id="tavily-api-key" type="password" value={tavilyKey} onChange={event => setTavilyKey(event.target.value)} autoComplete="off" spellCheck={false} autoCapitalize="none" maxLength={512} placeholder={hasTavilyKey ? '새 키를 입력하면 기존 키가 교체됩니다' : 'tvly-로 시작하는 API 키 입력'} aria-describedby="tavily-key-help" /><p id="tavily-key-help" className="paper-help">키 변경 시에만 입력하세요.</p></div>
        </fieldset>
        <div className="ai-save-row"><span className={tavilyDirty ? 'ai-dirty' : 'paper-help'} role="status">{tavilyDirty ? '저장하지 않은 변경 사항' : hasTavilyKey ? '저장됨' : '키 미등록'}</span><button className="paper-primary" type="submit" disabled={Boolean(busy) || !tavilyDirty}>{busy === 'tavily-save' ? '저장 중…' : 'Tavily 키 저장'}</button></div>
        <p className="paper-help">AI 분석에서 ‘뉴스·공시 웹 검색 포함’을 켜면 사용합니다.</p>
        <div className="ai-check-panel"><div><h4>검색 API 연결</h4><ConnectionStatus record={settings.tools?.tavily} /></div><button type="button" disabled={Boolean(busy) || tavilyDirty || !hasTavilyKey} onClick={() => manage('tavily-check', '/tools/tavily/check', {}, 'Tavily 사용량 조회로 인증을 확인했습니다. 검색은 실행하지 않았습니다.')}>{busy === 'tavily-check' ? '확인 중…' : '인증 확인 · 사용량 조회'}</button></div>
        {tavilyDirty && <p className="paper-help ai-action-help">저장 후 인증을 확인할 수 있습니다.</p>}
        <details className="settings-details"><summary>검색 범위·요금 안내</summary><p>종목별 뉴스와 DART·KIND 공시 검색 발췌를 AI에 전달합니다. 계좌정보는 검색 서비스에 전달하지 않습니다.</p><p>키 저장만으로는 검색하지 않습니다. 검색 시 Tavily 크레딧이 사용되며, 출처·게시일·사용량은 분석 결과에서 확인할 수 있습니다.</p><p>키는 현재 Windows 계정으로 암호화되어 저장됩니다. 입력란을 비우면 기존 키를 유지합니다.</p></details>
        <details className="settings-details"><summary>키 관리</summary><div className="ai-key-management"><div className="ai-delete"><p className="paper-help">저장된 Tavily 키만 삭제합니다.</p><button className="paper-danger" type="button" disabled={Boolean(busy) || tavilyDirty || !hasTavilyKey} onClick={() => manage('tavily-delete', '/tools/tavily/delete-key', {}, 'Tavily API 키를 삭제했습니다.')}>{busy === 'tavily-delete' ? '삭제 중…' : 'Tavily 저장된 키 삭제'}</button></div></div></details>
      </form>
      </div>

      <div role="tabpanel" id="settings-panel-dart" aria-labelledby="settings-tab-dart" hidden={activeTab !== 'dart'}><DartSettings settings={settings} apiKey={dartKey} setApiKey={setDartKey} enabled={dartEnabled} setEnabled={setDartEnabled} busy={busy} manage={manage} /></div>
    </>}
  </section>
}
