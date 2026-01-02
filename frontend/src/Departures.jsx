import React, { useState, useEffect, useCallback } from 'react'

export default function Departures() {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedBuilding, setSelectedBuilding] = useState('')
  const [buildings, setBuildings] = useState([])
  const [lastUpdate, setLastUpdate] = useState(null)

  const fetchDepartures = useCallback(async () => {
    try {
      setLoading(true)
      let data
      try {
        const res = await fetch('/departures.json')
        if (res.ok) data = await res.json()
      } catch (e) {}

      if (!data) {
        const today = new Date().toISOString().split('T')[0]
        const tomorrow = new Date(Date.now() + 86400000).toISOString().split('T')[0]
        const res = await fetch('/events.json?from=' + today + '&to=' + tomorrow)
        if (!res.ok) throw new Error('HTTP ' + res.status)
        const evts = await res.json()
        data = { events: Array.isArray(evts) ? evts : [], buildings: {} }
      }

      const evts = data.events || data || []
      setEvents(Array.isArray(evts) ? evts : [])
      
      const buildingSet = new Set()
      evts.forEach(ev => {
        const loc = ev.room || ev.location || ''
        const match = loc.match(/^([A-Z]{1,3})/i)
        if (match) buildingSet.add(match[1].toUpperCase())
      })
      setBuildings(Array.from(buildingSet).sort())
      setLastUpdate(new Date())
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchDepartures()
    const interval = setInterval(fetchDepartures, 3600000)
    return () => clearInterval(interval)
  }, [fetchDepartures])

  const now = new Date()
  const today = now.toISOString().split('T')[0]
  const tomorrow = new Date(Date.now() + 86400000).toISOString().split('T')[0]

  const filteredEvents = events.filter(ev => {
    if (selectedBuilding) {
      const loc = (ev.room || ev.location || '').toUpperCase()
      if (!loc.startsWith(selectedBuilding)) return false
    }
    return true
  })

  const todayEvents = filteredEvents.filter(ev => ev.start && ev.start.startsWith(today))
  const tomorrowEvents = filteredEvents.filter(ev => ev.start && ev.start.startsWith(tomorrow))

  const formatTime = (isoString) => {
    if (!isoString) return '--:--'
    try {
      return new Date(isoString).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
    } catch (e) {
      return '--:--'
    }
  }

  const getTimeStatus = (isoString) => {
    if (!isoString) return { text: '', className: '' }
    try {
      const eventTime = new Date(isoString)
      const diff = eventTime - now
      if (diff < 0) return { text: 'In progress', className: 'status-active' }
      const mins = Math.floor(diff / 60000)
      if (mins < 15) return { text: 'in ' + mins + ' min', className: 'status-soon' }
      if (mins < 60) return { text: 'in ' + mins + ' min', className: 'status-upcoming' }
      const hours = Math.floor(mins / 60)
      return { text: 'in ' + hours + 'h ' + (mins % 60) + 'm', className: '' }
    } catch (e) {
      return { text: '', className: '' }
    }
  }

  const DepartureBoard = ({ events: evts, title, isToday }) => (
    <div className="departure-section">
      <div className="section-header">
        <h3>{title}</h3>
        <span className="event-count">{evts.length} events</span>
      </div>
      {evts.length === 0 ? (
        <div className="no-events"><span>📭</span> No scheduled events</div>
      ) : (
        <div className="departure-board">
          <div className="board-header">
            <span className="col-time">Time</span>
            <span className="col-event">Event</span>
            <span className="col-room">Room</span>
            <span className="col-status">Status</span>
          </div>
          {evts.sort((a, b) => (a.start || '').localeCompare(b.start || '')).slice(0, 20).map((ev, idx) => {
            const status = isToday ? getTimeStatus(ev.start) : { text: '', className: '' }
            return (
              <div key={idx} className={'board-row ' + status.className} style={{ borderLeftColor: ev.color || '#003366' }}>
                <span className="col-time">{formatTime(ev.start)}</span>
                <span className="col-event">
                  <span className="event-title">{ev.display_title || ev.title}</span>
                  {ev.professor && <span className="event-professor">{ev.professor}</span>}
                </span>
                <span className="col-room">{ev.room || ev.location || '-'}</span>
                <span className={'col-status ' + status.className}>{status.text}</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )

  return (
    <div className="departures-container">
      <div className="toolbar">
        <div className="toolbar-left"><h2>Departures Board</h2></div>
        <div className="toolbar-right">
          <div className="filter-group">
            <label>Building:</label>
            <select value={selectedBuilding} onChange={(e) => setSelectedBuilding(e.target.value)}>
              <option value="">All</option>
              {buildings.map(b => <option key={b} value={b}>{b}</option>)}
            </select>
          </div>
          <button onClick={fetchDepartures} className="btn-refresh" disabled={loading}>
            {loading ? '⏳' : '🔄'} Refresh
          </button>
        </div>
      </div>

      {error && <div className="alert alert-error"><strong>Error:</strong> {error}</div>}
      {loading && <div className="loading-state"><div className="spinner"></div><p>Loading...</p></div>}

      {!loading && !error && (
        <div className="departures-grid">
          <DepartureBoard events={todayEvents} title={'📅 Today (' + today + ')'} isToday={true} />
          <DepartureBoard events={tomorrowEvents} title={'📅 Tomorrow (' + tomorrow + ')'} isToday={false} />
        </div>
      )}

      {lastUpdate && (
        <div className="status-bar">
          <span>Last update: {lastUpdate.toLocaleTimeString('en-US')}</span>
        </div>
      )}
    </div>
  )
}
