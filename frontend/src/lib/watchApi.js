import { API } from './tradingApi'

export async function watchRequest(path = '', body, signal) {
  const response = await fetch(`${API}/api/watch${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Watch-Action': 'manage' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(10000)]) : AbortSignal.timeout(10000),
  })
  const data = await response.json()
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '입력 내용을 확인하세요.')
  return data
}
