import { useState, useEffect } from 'react'
import DailyBriefing from './DailyBriefing'
import InlineNumber from './InlineNumber'
import { loadPortfolioQuotes, fetchPortfolioQuote } from '../lib/portfolioQuotes'

const API = import.meta.env.DEV ? 'http://127.0.0.1:8000' : ''

export default function Portfolio({ onSelect, onWatch, onOrders, onAI }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [accounts, setAccounts] = useState([])
  const [account, setAccount] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [accountRefresh, setAccountRefresh] = useState(0)
  const [quoteBatch, setQuoteBatch] = useState(null)

  useEffect(() => {
    if (!data) return
    const controller = new AbortController()
    loadPortfolioQuotes(data.holdings.map(row => row.code), (code, signal) => fetchPortfolioQuote(API, code, signal), (code, quote) => {
      if (!controller.signal.aborted) setQuoteBatch(previous => ({ data, values: { ...(previous?.data === data ? previous.values : {}), [code]: quote } }))
    }, controller.signal)
    return () => controller.abort()
  }, [data])

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${API}/api/accounts`, { signal: controller.signal })
      .then(async r => {
        const result = await r.json()
        if (!r.ok) throw new Error(result.detail || '계좌 조회 실패')
        return result
      })
      .then(result => {
        if (controller.signal.aborted) return
        setAccounts(result)
        if (result.length === 1) setAccount(result[0].id)
        else setLoading(false)
      })
      .catch(e => { if (e.name !== 'AbortError') { setError(e.message); setLoading(false) } })
    return () => controller.abort()
  }, [accountRefresh])

  useEffect(() => {
    if (!account) return
    const controller = new AbortController()
    async function load() {
      setLoading(true)
      setError('')
      setData(null)
      try {
        const r = await fetch(`${API}/api/portfolio?account=${encodeURIComponent(account)}`, { signal: controller.signal })
        const result = await r.json()
        if (!r.ok) throw new Error(result.detail || '잔고 조회 실패')
        if (!controller.signal.aborted) setData(result)
      } catch (e) {
        if (!controller.signal.aborted) setError(e.message)
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    load()
    return () => controller.abort()
  }, [account, refresh])

  const { summary, holdings } = data || { summary: {}, holdings: [] }
  const cmaRows = holdings.filter(row => row.code.startsWith('NHKRCMA'))
  const cmaBalance = cmaRows.every(row => row.eval_amount != null) ? cmaRows.reduce((total, row) => total + row.eval_amount, 0) : null

  return (
    <div className="portfolio">
      <div className="account-toolbar">
        <label htmlFor="account-select">나무증권 계좌</label>
        <select id="account-select" value={account} onChange={e => { setAccount(e.target.value); setData(null) }}>
          <option value="" disabled>계좌 선택</option>
          {accounts.map(a => <option key={a.id} value={a.id}>{a.label}</option>)}
        </select>
        <button className="search-btn" onClick={() => {
          if (account) setRefresh(v => v + 1)
          else { setError(''); setLoading(true); setAccountRefresh(v => v + 1) }
        }} disabled={loading}>새로고침</button>
      </div>
      {loading && <div className="portfolio-loading">잔고 불러오는 중...</div>}
      {error && <div className="error">{error}</div>}
      {!loading && !error && !account && <div className="no-holdings">{accounts.length ? '조회할 계좌를 선택해주세요.' : 'API에 등록된 실계좌가 없습니다.'}</div>}
      {data && <>
      <div className="portfolio-summary">
        <div className="summary-item">
          <span className="summary-label">총 평가금액</span>
          <span className="summary-value">{summary.total_eval.toLocaleString()}원</span>
        </div>
        <div className="summary-item">
          <span className="summary-label">총 매입금액</span>
          <span className="summary-value">{summary.total_purchase.toLocaleString()}원</span>
        </div>
        <div className="summary-item">
          <span className="summary-label">평가손익</span>
          <InlineNumber className="summary-value" value={summary.total_profit_loss} unit="원" rate={summary.total_profit_rate} signed title="매입금액 대비 평가손익·수익률" />
        </div>
        <div className="summary-item">
          <span className="summary-label">API 예수금 (CMA 제외)</span>
          <span className="summary-value">{summary.cash.toLocaleString()}원</span>
        </div>
        <div className="summary-item"><span className="summary-label">CMA 현금성 잔액</span><span className="summary-value">{cmaBalance == null ? '미확인' : `${cmaBalance.toLocaleString()}원`}</span></div>
        <div className="summary-item"><span className="summary-label">100% 주문가능금액</span><span className="summary-value">{summary.cash_orderable_100 == null ? '미확인' : `${summary.cash_orderable_100.toLocaleString()}원`}</span></div>
        <div className="summary-item"><span className="summary-label">조회 계좌 총자산</span><span className="summary-value">{summary.total_assets == null ? '미확인' : `${summary.total_assets.toLocaleString()}원`}</span></div>
      </div>

      <DailyBriefing key={`${account}-${refresh}`} account={account} holdings={holdings} summary={summary} onSelect={onSelect} onWatch={onWatch} onOrders={onOrders} onAI={onAI} />
      {holdings.length === 0 ? (
        <div className="no-holdings"><strong>아직 보유한 종목이 없습니다</strong><p>주식을 보유하면 종목별 평가금액과 손익이 여기에 표시됩니다.</p></div>
      ) : (
        <div className="section-card">
          <div className="section-card-header">보유 자산 {holdings.length}개</div>
          <div className="holdings-scroll"><table className="holdings-table">
            <thead>
              <tr>
                <th>종목명</th>
                <th>수량</th>
                <th>평균단가</th>
                <th title="현재가·등락률은 별도 시세 조회 기준이며 평가금액·손익은 잔고 조회 기준입니다.">현재가 (전일 대비)</th>
                <th>평가금액</th>
                <th>평가손익 (수익률)</th>
              </tr>
            </thead>
            <tbody>
              {holdings.map(h => {
                const isCma = h.code.startsWith('NHKRCMA')
                const isStockQuote = /^[0-9A-Z]{6}$/.test(h.code)
                const quoted = !isCma && quoteBatch?.data === data ? quoteBatch.values[h.code] : null
                const validQuote = quoted?.status === 'ready' || quoted?.status === 'partial'
                return (
                  <tr key={h.id || h.code} onClick={() => { if (!isCma) onSelect?.(h.code, h.name) }} style={{ cursor: isCma ? 'default' : 'pointer' }}>
                    <td>
                      <span className="holding-name">{h.name}</span>
                      <span className="holding-code">{isCma ? '현금성 운용 잔액' : `${h.code} ${h.holding_type || ''}`} </span>
                    </td>
                    <td>{isCma ? '—' : h.quantity.toLocaleString()}</td>
                    <td>{Math.round(h.avg_price).toLocaleString()}</td>
                    <td>{isCma ? '—' : <><InlineNumber value={validQuote ? quoted.price : h.current_price} unit="원" rate={validQuote ? quoted.change_rate : null} title={validQuote ? `별도 시세 조회 ${new Date(quoted.fetched_at).toLocaleTimeString('ko-KR')} · 전일 대비. 평가금액은 잔고 조회 기준입니다.` : isStockQuote ? '잔고 기준 현재가 · 전일 등락률 확인 중 또는 미확인' : '잔고 기준 가격 · 주식 시세 조회 대상 아님'} />{quoted?.status === 'error' || quoted?.status === 'partial' ? <span className="portfolio-quote-state" title="잔고 새로고침 시 다시 조회합니다."> (등락률 미확인)</span> : !quoted && isStockQuote && <span className="portfolio-quote-state"> (조회 중)</span>}</>}</td>
                    <td>{h.eval_amount == null ? '미확인' : h.eval_amount.toLocaleString()}</td>
                    <td><InlineNumber value={h.profit_loss} unit="원" rate={h.profit_rate} signed title="매입금액 대비 평가손익·수익률" /></td>
                  </tr>
                )
              })}
            </tbody>
          </table></div>
        </div>
      )}
      </>}
    </div>
  )
}
