import { useEffect, useState } from 'react'
import { connectionStatus } from '../lib/connectionStatus'
import './ConnectionStatus.css'

export default function ConnectionStatus({ record, compact = false }) {
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 60000)
    return () => clearInterval(timer)
  }, [])
  const state = connectionStatus(record, now)
  return <span className={`connection-status is-${state.tone}`}>
    <span className="connection-status-label"><i aria-hidden="true" />{state.label}</span>
    {!compact && <><span className="connection-status-detail">{state.detail}</span><span className="connection-status-time">{state.checkedAt ? <>최근 확인 <time dateTime={state.checkedAt}>{new Date(state.checkedAt).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })}</time></> : '확인 기록 없음'}</span></>}
  </span>
}
