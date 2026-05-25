import { useEffect, useState, useCallback } from "react"

type ToastType = "success" | "error" | "info"

interface ToastMessage {
  id: number
  message: string
  type: ToastType
}

let toastId = 0
const listeners: ((toast: ToastMessage) => void)[] = []

export function showToast(message: string, type: ToastType = "info") {
  const toast = { id: ++toastId, message, type }
  listeners.forEach((fn) => fn(toast))
}

export function ToastContainer() {
  const [toasts, setToasts] = useState<ToastMessage[]>([])

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  useEffect(() => {
    const handler = (toast: ToastMessage) => {
      setToasts((prev) => [...prev, toast])
      setTimeout(() => removeToast(toast.id), 4000)
    }
    listeners.push(handler)
    return () => {
      const idx = listeners.indexOf(handler)
      if (idx !== -1) listeners.splice(idx, 1)
    }
  }, [removeToast])

  const icons: Record<ToastType, string> = {
    success: "✓",
    error: "✕",
    info: "ℹ",
  }

  if (toasts.length === 0) return null

  return (
    <div className="toast-container">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast toast-${toast.type}`} role="status">
          <span className="toast-icon">{icons[toast.type]}</span>
          <span className="toast-message">{toast.message}</span>
          <button
            type="button"
            className="toast-close"
            onClick={() => removeToast(toast.id)}
            aria-label="Bildirimi kapat"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  )
}
