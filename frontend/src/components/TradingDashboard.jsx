import { useEffect, useState } from 'react'
import { tradingRequest } from '../lib/tradingApi'
import PaperTrading from './PaperTrading'
import LiveTrading from './LiveTrading'

export default function TradingDashboard({ initialCode }) {
  const [state, setState] = useState(null)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let stopped = false
    let timer
    let controller
    async function load() {
      controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 8000)
      try {
        const next = await tradingRequest('', undefined, undefined, controller.signal)
        if (!stopped) { setState(next); setError('') }
      } catch {
        if (!stopped) setError('매매 상태 연결이 끊겼습니다. 전송 기록과 서버 상태를 확인하세요.')
      } finally {
        clearTimeout(timeout)
        if (!stopped) timer = setTimeout(load, 2000)
      }
    }
    load()
    return () => { stopped = true; clearTimeout(timer); controller?.abort() }
  }, [revision])
  return <>
    {error && <p className="error" role="alert">{error}</p>}
    {state?.mode === 'paper' && <PaperTrading initialCode={initialCode} />}
    {state?.mode === 'live' && <LiveTrading initialCode={initialCode} state={state} disconnected={!!error} onRefresh={() => setRevision(v => v + 1)} />}
  </>
}
