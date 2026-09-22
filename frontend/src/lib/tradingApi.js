export const API = import.meta.env.DEV ? 'http://127.0.0.1:8000' : ''
export const money = value => value == null ? '—' : Math.round(value).toLocaleString('ko-KR')
export const timestamp = value => value ? new Date(value).toLocaleString('ko-KR') : '—'
export const accountLabel = value => value ? '*'.repeat(Math.max(0, value.length - 4)) + value.slice(-4) : '계좌 미선택'
export const today = () => new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Seoul' }).format(new Date()).replaceAll('-', '')

export async function tradingRequest(path = '', body, version, signal) {
  const response = await fetch(`${API}/api/trading${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Trading-Mode': 'live', 'X-Trading-Version': String(version ?? -1) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: signal || AbortSignal.timeout(body === undefined ? 45000 : 120000),
  })
  let result
  try { result = await response.json() } catch { throw new Error('응답을 해석하지 못했습니다. 전송 기록을 확인하세요.') }
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : '입력 형식과 현재 모드를 확인하세요.')
  return result
}
