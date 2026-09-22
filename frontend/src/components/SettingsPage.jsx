import { useRef, useState } from 'react'
import AISettings from './AISettings'
import TradingSettings from './TradingSettings'
import ConnectionStatus from './ConnectionStatus'
import './SettingsPage.css'

const TABS = [{ id: 'ai', name: 'AI 모델' }, { id: 'search', name: '웹 검색' }, { id: 'dart', name: 'DART 재무·공시' }, { id: 'trading', name: '매매·계좌' }]

export default function SettingsPage({ onTradingSaved }) {
  const [tab, setTab] = useState('ai')
  const [settings, setSettings] = useState(null)
  const [namuh, setNamuh] = useState(null)
  const [loadError, setLoadError] = useState(false)
  const buttons = useRef([])
  const unavailable = loadError ? { has_key: true, connection: { status: 'error', message: '설정을 불러오지 못했습니다' } } : null
  const provider = { openai: 'OpenAI', anthropic: 'Claude', gemini: 'Gemini' }[settings?.provider] || 'AI 모델'
  const services = [
    { id: 'trading', name: '나무', record: namuh, usage: namuh?.accountCount === 0 ? '조회된 계좌 없음' : '계좌 조회 · 주문 미검증' },
    { id: 'ai', name: provider, record: settings?.profiles?.[settings.provider] || unavailable, usage: settings ? settings.profiles?.[settings.provider]?.model || '모델 미선택' : '선택 정보 미확인' },
    { id: 'search', name: 'Tavily', record: settings?.tools?.tavily || unavailable, usage: '분석 설정에서 사용' },
    { id: 'dart', name: 'DART', record: settings?.tools?.dart || unavailable, usage: settings ? settings.tools?.dart?.enabled ? '분석 포함 켜짐' : '분석 포함 꺼짐' : '사용 설정 미확인' },
  ]
  function navigate(event, index) {
    let next
    if (event.key === 'ArrowRight') next = (index + 1) % TABS.length
    else if (event.key === 'ArrowLeft') next = (index + TABS.length - 1) % TABS.length
    else if (event.key === 'Home') next = 0
    else if (event.key === 'End') next = TABS.length - 1
    else return
    event.preventDefault()
    setTab(TABS[next].id)
    buttons.current[next]?.focus()
  }
  return <div className="settings-page">
    <section className="connection-overview" aria-label="API 연결 상태">
      <div className="connection-overview-heading"><h2>API 연결</h2><span>최근 확인 결과</span></div>
      <div className="connection-overview-grid">{services.map(service => <button type="button" className="connection-overview-item" key={service.id} onClick={() => { setTab(service.id); buttons.current[TABS.findIndex(item => item.id === service.id)]?.focus() }} aria-label={`${service.name} 연결 설정 열기`}>
        <span className="connection-overview-name">{service.name}<span aria-hidden="true">↗</span></span>
        <ConnectionStatus record={service.record} />
        <span className="connection-overview-usage" title={service.usage}>{service.usage}</span>
      </button>)}</div>
    </section>
    <div className="settings-tabs" role="tablist" aria-label="설정 분류">
      {TABS.map((item, index) => <button key={item.id} type="button" role="tab" id={`settings-tab-${item.id}`} aria-controls={`settings-panel-${item.id}`} aria-selected={tab === item.id} tabIndex={tab === item.id ? 0 : -1} ref={node => { buttons.current[index] = node }} onClick={() => setTab(item.id)} onKeyDown={event => navigate(event, index)}>{item.name}</button>)}
    </div>
    <AISettings activeTab={tab} onSettings={setSettings} onLoadError={setLoadError} />
    <div role="tabpanel" id="settings-panel-trading" aria-labelledby="settings-tab-trading" hidden={tab !== 'trading'}><TradingSettings onSaved={onTradingSaved} onConnection={setNamuh} /></div>
  </div>
}
