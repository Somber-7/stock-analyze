import { useState, useEffect, useRef, useCallback } from 'react'
import CandleChart from './components/CandleChart'
import Portfolio from './components/Portfolio'
import InlineNumber from './components/InlineNumber'
import WorkspaceClock from './components/WorkspaceClock'
import UsMarket from './components/UsMarket'
import Top100 from './components/Top100'
import TradingDashboard from './components/TradingDashboard'
import SettingsPage from './components/SettingsPage'
import AIOperation from './components/AIOperation'
import Icon from './components/Icon'
import Watchlist from './components/Watchlist'
import PriceAlerts from './components/PriceAlerts'
import Toaster from './components/Toaster'
import InvestorFlow from './components/InvestorFlow'
import { watchRequest } from './lib/watchApi'
import { tradingRequest } from './lib/tradingApi'
import { showToast } from './lib/toast'
import './App.css'

const API = import.meta.env.DEV ? 'http://127.0.0.1:8000' : ''
const isElectron = !!window.electronAPI
const PERIODS = [
  { key: '1m', label: '1분' },
  { key: '5m', label: '5분' },
  { key: 'D',  label: '일' },
  { key: 'W',  label: '주' },
  { key: 'M',  label: '월' },
]
const PAGES = {
  watch: ['관심종목·알림', '자주 보는 종목과 기다리는 가격을 한곳에서 관리하세요.'],
  portfolio: ['내 포트폴리오', '보유 자산과 손익을 한눈에 확인하세요.'],
  top100: ['시가총액 TOP 100', '국내 시장의 주요 종목을 살펴보세요.'],
  search: ['종목 조회', '현재가부터 차트까지, 한 종목에 집중하세요.'],
  us: ['미국 시장 참고', '다음 국내장을 준비하는 지수·반도체 시세입니다.'],
  paper: ['주문·자동매매', '주문을 관리하고 나만의 가격 조건을 설정하세요.'],
  ai: ['AI 분석·운용', '선택한 종목을 분석하고, 제안을 검토해 운용하세요.'],
  settings: ['설정', 'AI 연결, 매매 모드와 주문 계좌를 관리하세요.'],
}

export default function App() {
  const [tab, setTab] = useState('portfolio')
  const [aiInitialCode, setAiInitialCode] = useState('')
  const [aiInitialRunId, setAiInitialRunId] = useState(null)
  const openWatch = useCallback(() => setTab('watch'), [])
  const [watchBusy, setWatchBusy] = useState(false)
  const [tradingMode, setTradingMode] = useState(null)
  const [code, setCode] = useState('')
  const [stockName, setStockName] = useState('')
  const [input, setInput] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [period, setPeriod] = useState('D')
  const [price, setPrice] = useState(null)
  const [chartData, setChartData] = useState([])
  const [loading, setLoading] = useState(false)
  const [chartLoading, setChartLoading] = useState(false)
  const [error, setError] = useState('')
  const [cooldown, setCooldown] = useState(0)
  const [serverOn, setServerOn] = useState(true)
  const [serverBusy, setServerBusy] = useState(false)
  const debounceRef = useRef(null)
  const cooldownRef = useRef(null)
  const searchWrapRef = useRef(null)
  const mainRef = useRef(null)
  useEffect(() => { mainRef.current?.scrollTo({ top: 0 }) }, [tab])

  useEffect(() => {
    let stopped = false
    async function refreshMode() {
      try { const state = await tradingRequest(); if (!stopped) setTradingMode(state.mode) }
      catch { if (!stopped) setTradingMode(null) }
    }
    refreshMode()
    const timer = setInterval(refreshMode, 5000)
    return () => { stopped = true; clearInterval(timer) }
  }, [])

  useEffect(() => {
    if (!isElectron) return
    const check = async () => {
      const on = await window.electronAPI.getStatus()
      setServerOn(on)
    }
    check()
    const id = setInterval(check, 5000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const handler = (e) => {
      if (searchWrapRef.current && !searchWrapRef.current.contains(e.target))
        setShowSuggestions(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  async function toggleServer() {
    if (!isElectron) return
    setServerBusy(true)
    try {
      if (serverOn) { await window.electronAPI.stopBackend(); setServerOn(false) }
      else { await window.electronAPI.startBackend(); setServerOn(true) }
    } finally { setServerBusy(false) }
  }

  function handleInputChange(e) {
    const val = e.target.value
    setInput(val)
    clearTimeout(debounceRef.current)
    if (!val.trim()) { setSuggestions([]); setShowSuggestions(false); return }
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await fetch(`${API}/api/stocks/search?q=${encodeURIComponent(val)}`)
        const data = await res.json()
        setSuggestions(data)
        setShowSuggestions(data.length > 0)
      } catch { /* ignore */ }
    }, 200)
  }

  function startCooldown() {
    setCooldown(5)
    clearInterval(cooldownRef.current)
    cooldownRef.current = setInterval(() => {
      setCooldown(prev => {
        if (prev <= 1) { clearInterval(cooldownRef.current); return 0 }
        return prev - 1
      })
    }, 1000)
  }

  const chartAbortRef = useRef(null)
  const priceAbortRef = useRef(null)

  async function fetchChart(targetCode, p) {
    // 이전 요청 취소
    if (chartAbortRef.current) chartAbortRef.current.abort()
    const controller = new AbortController()
    chartAbortRef.current = controller
    setChartLoading(true)
    try {
      const res = await fetch(`${API}/api/stock/${targetCode}/chart?period=${p}`, { signal: controller.signal })
      const data = await res.json()
      if (controller.signal.aborted) return
      if (!res.ok) throw new Error(data.detail || '차트 조회에 실패했습니다.')
      setChartData(data)
    } catch (e) {
      if (e.name !== 'AbortError') { setChartData([]); setError(e.message) }
    } finally {
      if (chartAbortRef.current === controller) setChartLoading(false)
    }
  }

  async function fetchStock(targetCode, name = '') {
    priceAbortRef.current?.abort()
    chartAbortRef.current?.abort()
    const controller = new AbortController()
    priceAbortRef.current = controller
    setLoading(true)
    setError('')
    setPrice(null)
    setChartData([])
    setCode(targetCode)
    setStockName(name)
    try {
      const response = await fetch(`${API}/api/stock/${targetCode}/price`, { signal: controller.signal })
      const priceRes = await response.json()
      if (controller.signal.aborted) return
      if (!response.ok) throw new Error(priceRes.detail || '현재가 조회에 실패했습니다.')
      setPrice(priceRes)
      if (!name && priceRes.name) setStockName(priceRes.name)
    } catch (e) {
      if (controller.signal.aborted) return
      setError(e.message || '조회 실패. 종목코드를 확인해주세요.')
      setLoading(false)
      return
    }
    await fetchChart(targetCode, period)
    if (controller.signal.aborted) return
    setLoading(false)
    startCooldown()
  }

  function selectSuggestion(stock) {
    setInput(stock.name)
    setShowSuggestions(false)
    fetchStock(stock.code, stock.name)
  }

  // 포트폴리오 또는 Top50 종목 클릭 → 종목 조회 탭
  function handleStockSelect(code, name) {
    setTab('search')
    setInput(name)
    fetchStock(code, name)
  }

  async function search(e) {
    e.preventDefault()
    const trimmed = input.trim()
    if (!trimmed) return
    setShowSuggestions(false)
    if (/^\d+$/.test(trimmed)) {
      fetchStock(trimmed)
    } else if (suggestions.length > 0) {
      selectSuggestion(suggestions[0])
    } else {
      try {
        const res = await fetch(`${API}/api/stocks/search?q=${encodeURIComponent(trimmed)}`)
        const data = await res.json()
        if (data.length > 0) selectSuggestion(data[0])
        else setError('종목을 찾을 수 없습니다.')
      } catch { setError('검색 중 오류가 발생했습니다.') }
    }
  }

  const isIntraday = period === '1m' || period === '5m'

  return (
    <div className={`app-layout${isElectron ? ' desktop-frame' : ''}`}>
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="brand-mark"><Icon name="mark" size={26} /></div>
          <div><strong>Stock Analyze</strong><p>나의 투자 워크스페이스</p></div>
        </div>
        <nav className="sidebar-nav">
          <span className="nav-group">시장과 자산</span>
          <button className={`nav-item ${tab === 'top100' ? 'active' : ''}`} onClick={() => setTab('top100')}>
            <Icon name="top100" />시가총액 TOP 100
          </button>
          <button className={`nav-item ${tab === 'portfolio' ? 'active' : ''}`} onClick={() => setTab('portfolio')}>
            <Icon name="portfolio" />내 포트폴리오
          </button>
          <button className={`nav-item ${tab === 'search' ? 'active' : ''}`} onClick={() => setTab('search')}>
            <Icon name="search" />종목 조회
          </button>
          <button className={`nav-item ${tab === 'watch' ? 'active' : ''}`} onClick={openWatch}><Icon name="watch" />관심종목·알림</button>
          <button className={`nav-item ${tab === 'us' ? 'active' : ''}`} onClick={() => setTab('us')}>
            <Icon name="us" />미국 시장 참고
          </button>
          <span className="nav-group">거래 관리</span>
          <button className={`nav-item ${tab === 'ai' ? 'active' : ''}`} onClick={() => { setAiInitialCode(''); setAiInitialRunId(null); setTab('ai') }}><Icon name="mark" />AI 분석·운용</button>
          <button className={`nav-item ${tab === 'paper' ? 'active' : ''}`} onClick={() => setTab('paper')}>
            <Icon name="paper" />주문·자동매매
          </button>
          <button className={`nav-item ${tab === 'settings' ? 'active' : ''}`} onClick={() => setTab('settings')}><Icon name="settings" />설정</button>
        </nav>
        <div className="sidebar-provider"><span className="provider-mark">N</span><div><strong>나무증권</strong><small>NH PLUG API</small></div></div>
        <div className={`sidebar-mode ${tradingMode === 'live' ? 'live' : ''}`}>{tradingMode === 'live' ? '실전 모드 · 실제 계좌' : tradingMode === 'paper' ? '모의 모드 · 가상 계좌' : '매매 모드 확인 중'}</div>
        {isElectron && (
          <div className="sidebar-footer">
            <div className="server-status">
              <span className={`server-dot ${serverOn ? 'on' : 'off'}`} />
              <span className="server-label">{serverOn ? '서버 실행 중' : '서버 중지됨'}</span>
            </div>
            <button className={`server-btn ${serverOn ? 'stop' : 'start'}`} onClick={toggleServer} disabled={serverBusy}>
              {serverBusy ? '...' : serverOn ? '서버 중지' : '서버 시작'}
            </button>
          </div>
        )}
      </aside>

      <main className="main-content" ref={mainRef}>
        <div className="workspace-bar"><span>투자 워크스페이스 <span className="breadcrumb-divider">/</span> {tab === 'us' ? '미국 시장 참고' : '국내 주식'}</span><div className="workspace-status"><WorkspaceClock /><span className={`workspace-mode ${tradingMode === 'live' ? 'live' : ''}`}>{tradingMode === 'live' ? '실전 모드 · 실제 계좌' : tradingMode === 'paper' ? '모의 모드 · 가상 계좌' : '모드 확인 중'}</span></div></div>
        <div className="page-heading"><div><h1>{PAGES[tab][0]}</h1><p>{PAGES[tab][1]}</p></div>{tab === 'paper' ? <button className="heading-action" onClick={() => setTab('settings')}><Icon name="settings" size={16} />매매 설정</button> : <span className="market-tag">{tab === 'us' ? '미국 시장' : '국내 주식'}</span>}</div>
        {tab === 'paper' && <TradingDashboard initialCode={code} />}
        {tab === 'ai' && <AIOperation initialCode={aiInitialCode} initialRunId={aiInitialRunId} onSettings={() => setTab('settings')} onOrders={() => setTab('paper')} />}
        {tab === 'watch' && <Watchlist onSelect={handleStockSelect} onOrder={(nextCode, name) => { setInput(name); fetchStock(nextCode, name); setTab('paper') }} />}
        {tab === 'settings' && <SettingsPage onTradingSaved={state => { setTradingMode(state.mode); setTab('paper') }} />}
        {tab === 'top100' && <><Top100 onSelect={handleStockSelect} /></>}
        {tab === 'us' && <><UsMarket /></>}
        {tab === 'portfolio' && (
          <>
            
            <Portfolio onSelect={handleStockSelect} onWatch={() => setTab('watch')} onOrders={() => setTab('paper')} onAI={runId => { setAiInitialCode(''); setAiInitialRunId(runId || null); setTab('ai') }} />
          </>
        )}

        {tab === 'search' && (
          <>
            
            <form className="search-form" onSubmit={search}>
              <div className="search-wrap" ref={searchWrapRef}>
                <input
                  className="search-input"
                  value={input}
                  onChange={handleInputChange}
                  onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
                  placeholder="종목명 또는 코드 (예: 삼성전자, 005930)"
                  autoComplete="off"
                />
                {showSuggestions && (
                  <ul className="suggestions">
                    {suggestions.map(s => (
                      <li key={s.code} onMouseDown={() => selectSuggestion(s)}>
                        <span className="sug-name">{s.name}</span>
                        <span className="sug-code">{s.code}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <button className="search-btn" type="submit" disabled={loading || cooldown > 0}>
                {loading ? '조회 중...' : cooldown > 0 ? `${cooldown}초` : '조회'}
              </button>
            </form>

            {error && <p className="error">{error}</p>}
            {!price && !loading && !error && <div className="search-empty"><div className="empty-icon"><Icon name="search" size={28} /></div><h2>어떤 종목이 궁금하신가요?</h2><p>종목명이나 코드를 검색해 현재가와 차트를 확인하세요.</p><span>예: 삼성전자 · SK하이닉스 · 채비</span></div>}

            {price && (
              <div className="price-card">
                <div className="price-main">
                  <span className="stock-code">{stockName || code}<small>{code}</small></span>
                  <InlineNumber className="price-value" value={price.price} unit="원" rate={price.change_rate} title="전일 대비 등락률" />
                  <button className="search-btn" onClick={() => setTab('paper')}>주문 화면</button>
                  <button className="heading-action" onClick={() => { setAiInitialCode(code); setAiInitialRunId(null); setTab('ai') }}>AI 분석</button>
                  <button className="heading-action" disabled={watchBusy} onClick={async () => {
                    setWatchBusy(true)
                    try { await watchRequest('/items', { code }); showToast('관심종목에 추가했습니다. 관심종목·알림 메뉴에서 가격 알림을 설정하세요.') }
                    catch (e) { showToast(e.message, { tone: 'error' }) }
                    finally { setWatchBusy(false) }
                  }}>관심종목 추가</button>
                </div>
                <div className="price-detail">
                  <span>전일 대비 <InlineNumber value={price.change} unit="원" signed /></span>
                  <span className="meta">거래량 {price.volume.toLocaleString()}</span>
                  <span className="meta">시가 {price.open.toLocaleString()} · 고 {price.high.toLocaleString()} · 저 {price.low.toLocaleString()}</span>
                </div>
                <div className="price-meta-grid">
                  {price.w52_high > 0 && <div className="meta-item"><span className="meta-label">52주 최고</span><span className="meta-val">{price.w52_high.toLocaleString()}</span></div>}
                  {price.w52_low  > 0 && <div className="meta-item"><span className="meta-label">52주 최저</span><span className="meta-val">{price.w52_low.toLocaleString()}</span></div>}
                  {price.market_cap > 0 && <div className="meta-item"><span className="meta-label">시가총액</span><span className="meta-val">{price.market_cap.toLocaleString()}억</span></div>}
                  {price.per && price.per !== '0.00' && <div className="meta-item"><span className="meta-label">PER</span><span className="meta-val">{price.per}배</span></div>}
                  {price.pbr && price.pbr !== '0.00' && <div className="meta-item"><span className="meta-label">PBR</span><span className="meta-val">{price.pbr}배</span></div>}
                  {price.eps && price.eps !== '0' && <div className="meta-item"><span className="meta-label">EPS</span><span className="meta-val">{parseInt(price.eps).toLocaleString()}원</span></div>}
                </div>
              </div>
            )}

            {price && (
              <div className="chart-wrap">
                <div className="period-tabs">
                  {PERIODS.map(p => (
                    <button
                      key={p.key}
                      className={`period-btn ${period === p.key ? 'active' : ''}`}
                      onClick={() => { setPeriod(p.key); if (code) fetchChart(code, p.key) }}
                      disabled={chartLoading}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
                <div className="chart-inner">
                  {chartLoading
                    ? <div className="chart-empty">로딩 중...</div>
                    : chartData.length > 0
                      ? <CandleChart data={chartData} isIntraday={isIntraday} />
                      : <div className="chart-empty">데이터 없음</div>
                  }
                </div>
              </div>
            )}
            {price && <InvestorFlow code={code} />}
          </>
        )}
      </main>
      <div className="toast-stack"><Toaster /><PriceAlerts onOpen={openWatch} /></div>
    </div>
  )
}
