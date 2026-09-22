const finite = value => typeof value === 'number' && Number.isFinite(value)

export async function loadPortfolioQuotes(codes, fetchQuote, onQuote, signal) {
  const queue = [...new Set(codes.filter(code => /^[0-9A-Z]{6}$/.test(code)))]
  let next = 0
  async function worker() {
    while (!signal.aborted && next < queue.length) {
      const code = queue[next++]
      let quote
      try {
        const result = await fetchQuote(code, signal)
        if (result.code !== code || !finite(result.price) || result.price <= 0) throw new Error('Invalid quote')
        quote = { price: result.price, change_rate: finite(result.change_rate) ? result.change_rate : null,
          status: finite(result.change_rate) ? 'ready' : 'partial', fetched_at: new Date().toISOString() }
      } catch { quote = { status: 'error' } }
      if (!signal.aborted) onQuote(code, quote)
    }
  }
  await Promise.all(Array.from({ length: Math.min(3, queue.length) }, worker))
}

export async function fetchPortfolioQuote(api, code, signal) {
  const controller = new AbortController()
  const abort = () => controller.abort()
  signal.addEventListener('abort', abort, { once: true })
  if (signal.aborted) controller.abort()
  const timeout = setTimeout(abort, 20000)
  try {
    const response = await fetch(`${api}/api/stock/${encodeURIComponent(code)}/price`, { signal: controller.signal })
    if (!response.ok) throw new Error('Quote unavailable')
    return await response.json()
  } finally { clearTimeout(timeout); signal.removeEventListener('abort', abort) }
}
