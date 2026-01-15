import React, { useState, useEffect } from 'react'
import Schedule from './Schedule'
import Departures from './Departures'

export default function App() {
  const [tab, setTab] = useState('schedule')
  const [currentTime, setCurrentTime] = useState(new Date())

  useEffect(() => {
    // Regular clock tick (updates every second)
    const tick = () => setCurrentTime(new Date())
    const timer = setInterval(tick, 1000)

    // Schedule a precise update at the next local midnight (00:00)
    // and dispatch a `midnight` event so child components can refresh if needed.
    function scheduleMidnight() {
      const now = new Date()
      // Set to next midnight: move to next day at 00:00:00.000
      const nextMidnight = new Date(now)
      nextMidnight.setHours(24, 0, 0, 0)
      const msUntilMidnight = nextMidnight - now

      // Fallback: if computed time is negative or too large, default to 60s
      const safeMs = msUntilMidnight > 0 && msUntilMidnight < 8.64e7 ? msUntilMidnight : 60000

      const t = setTimeout(() => {
        // Update the clock state so the UI shows the new day
        tick()
        // Notify any listeners (children/components) that midnight occurred
        try {
          window.dispatchEvent(new Event('midnight'))
        } catch (e) {
          // older browsers may throw; ignore safely
        }
        // Schedule the following midnight
        scheduleMidnight()
      }, safeMs)

      return t
    }

    const midnightTimer = scheduleMidnight()

    return () => {
      clearInterval(timer)
      clearTimeout(midnightTimer)
    }
  }, [])

  const formatDate = (date) => {
    return date.toLocaleDateString('en-US', { 
      weekday: 'long', 
      year: 'numeric', 
      month: 'long', 
      day: 'numeric' 
    })
  }

  const formatTime = (date) => {
    return date.toLocaleTimeString('en-US', { 
      hour: '2-digit', 
      minute: '2-digit',
      second: '2-digit'
    })
  }

  return (
    <div className="app">
      <div className="top-bar">
        <div className="top-bar-content">
          <span>Technical University of Cluj-Napoca</span>
          <span className="clock">{formatTime(currentTime)}</span>
        </div>
      </div>

      <header className="header">
        <div className="header-content">
          <div className="header-brand">
            <div className="logo">
              <div className="logo-text">
                <h1>UTCN Timetable</h1>
                <span className="subtitle">Technical University of Cluj-Napoca</span>
              </div>
            </div>
          </div>
          <nav className="nav">
            <button 
              onClick={() => setTab('schedule')} 
              className={"nav-btn " + (tab === 'schedule' ? 'active' : '')}
            >
              Schedule
            </button>
            <button 
              onClick={() => setTab('departures')} 
              className={"nav-btn " + (tab === 'departures' ? 'active' : '')}
            >
              Live
            </button>
          </nav>
        </div>
      </header>

      <div className="date-bar">
        <span>{formatDate(currentTime)}</span>
      </div>

      <main className="main">
        {tab === 'schedule' && <Schedule />}
        {tab === 'departures' && <Departures />}
      </main>

      <footer className="footer">
        <div className="footer-content">
          <p>© 2026 Technical University of Cluj-Napoca</p>
          <p className="footer-note">Schedule Management System • Auto-refresh every hour</p>
        </div>
      </footer>
    </div>
  )
}
