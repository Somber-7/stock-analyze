import { useCallback, useEffect, useState } from 'react'
import { addToast, INFO_TOAST_MS, subscribeToasts } from '../lib/toast'
import './Toaster.css'

export default function Toaster() {
  const [toasts, setToasts] = useState([])
  useEffect(() => subscribeToasts(toast => setToasts(list => addToast(list, toast))), [])
  const close = useCallback(id => setToasts(list => list.filter(toast => toast.id !== id)), [])
  return toasts.map(toast => <ToastItem key={toast.id} toast={toast} onClose={close} />)
}

function ToastItem({ toast, onClose }) {
  // Info closes by itself; an error stays until the user closes it.
  useEffect(() => {
    if (toast.tone === 'error') return
    const timer = setTimeout(() => onClose(toast.id), INFO_TOAST_MS)
    return () => clearTimeout(timer)
  }, [toast, onClose])
  return <div className={`app-toast ${toast.tone}`} role={toast.tone === 'error' ? 'alert' : 'status'}>
    <p>{toast.message}</p>
    <button type="button" aria-label="알림 닫기" onClick={() => onClose(toast.id)}>×</button>
  </div>
}
