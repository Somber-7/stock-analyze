function pending(storage) {
  try { return JSON.parse(storage.getItem('paper-requests') || '{}') } catch { return {} }
}

export function createKey(storage, path, payload) {
  const signature = JSON.stringify({ path, payload })
  const requests = pending(storage)
  if (requests[signature]) return requests[signature]
  const id = crypto.randomUUID()
  requests[signature] = id
  storage.setItem('paper-requests', JSON.stringify(requests))
  return id
}

export function clearKey(storage, path, payload, id) {
  const signature = JSON.stringify({ path, payload })
  const requests = pending(storage)
  if (requests[signature] === id) delete requests[signature]
  storage.setItem('paper-requests', JSON.stringify(requests))
}
