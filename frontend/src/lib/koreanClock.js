const dateFormat = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit', weekday: 'short' })
const timeFormat = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' })

export function formatKoreanClock(date) {
  const parts = Object.fromEntries(dateFormat.formatToParts(date).map(part => [part.type, part.value]))
  return { date: `${parts.year}.${parts.month}.${parts.day} (${parts.weekday})`, time: timeFormat.format(date) }
}
