import { useEffect, useState } from 'react'
import { formatKoreanClock } from '../lib/koreanClock'
import './WorkspaceClock.css'

export default function WorkspaceClock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const update = () => setNow(new Date())
    const timer = setInterval(update, 1000)
    document.addEventListener('visibilitychange', update)
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange', update) }
  }, [])
  const clock = formatKoreanClock(now)
  return <time className="workspace-clock" dateTime={now.toISOString()} aria-live="off" aria-label={`한국 현재 시각 ${clock.date} ${clock.time}`} title="이 PC의 시계를 기준으로 표시하는 한국 표준시">
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 6v6l4 2" /></svg>
    <span className="workspace-clock-content"><span className="workspace-clock-date">{clock.date}</span><span className="workspace-clock-time">{clock.time}<span className="workspace-clock-zone">KST</span></span></span>
  </time>
}
