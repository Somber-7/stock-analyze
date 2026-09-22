import { useEffect, useState } from 'react'
import InlineNumber from './InlineNumber'

const API = import.meta.env.DEV ? 'http://127.0.0.1:8000' : ''
const ITEMS = [
  ['DJI', '다우 산업지수', '지수'], ['SPY', 'S&P 500 참고', 'ETF'],
  ['QQQ', '나스닥 100 참고', 'ETF'], ['SOXX', '미국 반도체 참고', 'ETF'],
  ['NVDA', '엔비디아', '주식'], ['AMD', 'AMD', '주식'], ['MU', '마이크론', '주식'],
]

function formatDate(value) {
  return /^\d{8}$/.test(value || '') ? `${value.slice(0, 4)}.${value.slice(4, 6)}.${value.slice(6)}` : '미제공'
}

export default function UsMarket() {
  const [quotes, setQuotes] = useState({})
  useEffect(() => {
    let stopped = false
    let timer
    const controllers = new Set()
    async function refresh() {
      await Promise.all(ITEMS.map(async ([code]) => {
        const controller = new AbortController()
        controllers.add(controller)
        const timeout = setTimeout(() => controller.abort(), 40000)
        try {
          const response = await fetch(`${API}/api/us-market/${code}`, { signal: controller.signal })
          const data = await response.json()
          if (!response.ok) throw new Error(data.detail || '조회 실패')
          if (!stopped) setQuotes(old => ({ ...old, [code]: { data, error: '' } }))
        } catch (error) {
          if (!stopped) setQuotes(old => ({ ...old, [code]: {
            data: old[code]?.data, error: error.name === 'AbortError' ? '조회 시간 초과' : error.message,
          } }))
        } finally {
          clearTimeout(timeout)
          controllers.delete(controller)
        }
      }))
      if (!stopped) timer = setTimeout(refresh, 60000)
    }
    refresh()
    return () => {
      stopped = true
      clearTimeout(timer)
      controllers.forEach(controller => controller.abort())
    }
  }, [])

  return <>
    <p className="us-market-note">
      국내장 참고용 · 나무 제공 시세 · 화면을 보는 동안 1분마다 조회<br />
      SPY·QQQ·SOXX는 ETF 가격이며 지수 수치가 아닙니다. 시세는 지연될 수 있으며 장전·장후 거래가 포함될 수 있습니다.
    </p>
    <div className="us-market-grid">
      {ITEMS.map(([code, name, kind]) => {
        const quote = quotes[code]
        const data = quote?.data
        return <section className="section-card us-market-card" key={code}>
          <div className="section-card-header">{name}</div>
          <div className="us-market-symbol">{code === 'DJI' ? '.DJI' : code} · {kind}</div>
          {data ? <>
            <div className="us-market-price"><InlineNumber value={data.price} unit={` ${data.unit}`} rate={data.change_rate} title="제공 시세의 등락률" /></div>
            <div className="us-market-change">등락 <InlineNumber value={data.change} unit={` ${data.unit}`} signed /></div>
            <div className="us-market-date">시세 기준일 {formatDate(data.data_date)}<br />
              조회 {new Date(data.fetched_at).toLocaleTimeString('ko-KR')}
              {quote.error && ' · 이전 조회 자료'}
            </div>
          </> : <p>{quote?.error ? '시세 미제공' : '조회 중...'}</p>}
          {quote?.error && <div className="error" role="status">{quote.error}</div>}
        </section>
      })}
    </div>
  </>
}
