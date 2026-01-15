import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './styles.css'

// Development-only client-side error reporter: sends JS errors to the server
try {
  window.addEventListener('error', function (evt) {
    try {
      const payload = {
        message: evt.message,
        filename: evt.filename,
        lineno: evt.lineno,
        colno: evt.colno,
        error: evt.error ? (evt.error.stack || String(evt.error)) : null,
        userAgent: navigator.userAgent,
        href: window.location.href,
        ts: new Date().toISOString()
      }
      try {
        // Prefer sendBeacon for reliability on unload; ensure we send a proper
        // application/json body by using a Blob so the server can parse it.
        if (navigator.sendBeacon) {
          const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' })
          navigator.sendBeacon('/log_js_error', blob)
        } else {
          fetch('/log_js_error', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
        }
      } catch (e) {
        // fallback: attempt fetch if sendBeacon throws
        try { fetch('/log_js_error', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }) } catch (e) {}
      }
    } catch (e) {
      // swallow
    }
  })

  window.addEventListener('unhandledrejection', function (evt) {
    try {
      const payload = {
        message: (evt.reason && evt.reason.message) || String(evt.reason),
        error: evt.reason && (evt.reason.stack || String(evt.reason)),
        userAgent: navigator.userAgent,
        href: window.location.href,
        ts: new Date().toISOString()
      }
      try {
        if (navigator.sendBeacon) {
          const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' })
          navigator.sendBeacon('/log_js_error', blob)
        } else {
          fetch('/log_js_error', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
        }
      } catch (e) { try { fetch('/log_js_error', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }) } catch (e) {} }
    } catch (e) {}
  })
} catch (e) {}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
