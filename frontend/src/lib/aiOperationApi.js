import { API } from './tradingApi'

export async function aiOperationRequest(path = '', body, signal) {
  try {
    const response = await fetch(`${API}/api/ai/operation${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      headers: { 'Content-Type': 'application/json', 'X-AI-Action': 'manage' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(120000)]) : AbortSignal.timeout(120000),
    })
    const result = await response.json()
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'AI 운용 요청을 처리하지 못했습니다. 현재 설정과 입력을 확인하세요.')
    return result
  } catch (error) {
    if (signal?.aborted) throw error
    if (error.name === 'TimeoutError') throw new Error('응답 시간이 초과되었습니다. 실행 기록을 확인하세요. 주문 요청은 자동 재전송하지 않습니다.', { cause: error })
    if (error instanceof TypeError || error instanceof SyntaxError) throw new Error('AI 운용 서버의 응답을 확인하지 못했습니다. 실행 기록을 확인한 후 다시 시도하세요.', { cause: error })
    throw error
  }
}
