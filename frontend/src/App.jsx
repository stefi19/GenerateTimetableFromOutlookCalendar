import React, { useState, useEffect } from 'react'
import Schedule from './Schedule'
import Departures from './Departures'

export default function App() {
  const [tab, setTab] = useState('schedule')
  const [currentTime, setCurrentTime] = useState(new Date())

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000)
    return () => clearInterval(timer)
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
              <span className="logo-icon">🎓</span>
              <div className="logo-text">
                <h1>AC UTCN</h1>
                <span className="subtitle">Automation & Computer Science • Schedule</span>
              </div>
            </div>
          </div>
          <nav className="nav">
            <button 
              onClick={() => setTab('schedule')} 
              className={"nav-btn " + (tab === 'schedule' ? 'active' : '')}
            >
              📅 Schedule
            </button>
            <button 
              onClick={() => setTab('departures')} 
              className={"nav-btn " + (tab === 'departures' ? 'active' : '')}
            >
              🚀 Departures
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
          <p>© 2025 Faculty of Automation and Computer Science, UTCN</p>
          <p className="footer-note">Schedule Management System • Auto-refresh every hour</p>
        </div>
      </footer>
    </div>
  )
}
