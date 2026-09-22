// Transient notices and one-off action failures. Page state, data caveats and order results stay inline.
const listeners = new Set()
let nextId = 1

export const TOAST_LIMIT = 4
export const INFO_TOAST_MS = 4500

export function showToast(message, { tone = 'info' } = {}) {
  const text = String(message ?? '').trim()
  if (!text) return
  const toast = { id: nextId++, message: text, tone: tone === 'error' ? 'error' : 'info' }
  listeners.forEach(listener => listener(toast))
}

export function subscribeToasts(listener) {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

// A repeated message replaces its earlier copy. Over the limit, the oldest info toast leaves first.
export function addToast(list, toast, limit = TOAST_LIMIT) {
  const next = [...list.filter(item => item.message !== toast.message || item.tone !== toast.tone), toast]
  while (next.length > limit) {
    const index = next.findIndex(item => item.tone === 'info')
    next.splice(index >= 0 && index < next.length - 1 ? index : 0, 1)
  }
  return next
}
