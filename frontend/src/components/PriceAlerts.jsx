import { useEffect, useRef, useState } from 'react'
import { watchRequest } from '../lib/watchApi'
import { money, timestamp } from '../lib/tradingApi'
import './Watchlist.css'

export default function PriceAlerts({ onOpen }) {
  const [rows, setRows] = useState([])
  const seen = useRef(new Set())
  useEffect(() => window.electronAPI?.onWatchOpen?.(onOpen), [onOpen])
  useEffect(() => {
    let stopped = false, timer
    const controller = new AbortController()
    async function poll() {
      try {
        const pending = await watchRequest('/notifications', undefined, controller.signal)
        if (stopped) return
        const fresh = pending.filter(row => !seen.current.has(row.id))
        if (fresh.length) {
          fresh.forEach(row => seen.current.add(row.id))
          setRows(old => [...fresh, ...old].slice(0, 1000))
          // In-app notice remains available if Windows notification delivery is disabled.
          try { await window.electronAPI?.notifyPriceAlerts?.(fresh.map(row => ({ id: row.id, name: row.name, code: row.code, price: row.observed_price }))) } catch { /* in-app fallback */ }
        }
        if (pending.length && !stopped) await watchRequest('/notifications/ack', { ids: pending.map(row => row.id) }, controller.signal)
      } catch { /* Retry after connection recovery; durable notifications stay pending. */ }
      finally { if (!stopped) timer = setTimeout(poll, 3000) }
    }
    poll()
    return () => { stopped = true; clearTimeout(timer); controller.abort() }
  }, [])
  if (!rows.length) return null
  return <aside className="price-alert-toast" role="status" aria-live="polite">
    <h3>가격 알림 · {rows.length}건</h3>
    {rows.slice(0, 3).map(row => <div key={row.id}><p><strong>{row.name}</strong> · {money(row.observed_price)}원<br />{money(row.threshold)}원 {row.comparison === 'gte' ? '이상' : '이하'} 조건 도달</p><small>{row.code} · {timestamp(row.triggered_at)}</small></div>)}
    {rows.length > 3 && <p>외 {rows.length - 3}건 · 알림 기록에서 확인하세요.</p>}
    <footer><button onClick={() => { setRows([]); onOpen() }}>알림 기록</button><button onClick={() => setRows([])}>닫기</button></footer>
  </aside>
}
