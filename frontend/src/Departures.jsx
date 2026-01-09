import React, { useState, useEffect, useCallback } from 'react'

export default function Departures() {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedBuilding, setSelectedBuilding] = useState('')
  const [selectedYear, setSelectedYear] = useState('')
  const [selectedGroup, setSelectedGroup] = useState('')
  const [buildings, setBuildings] = useState([])
  const [calendarsMap, setCalendarsMap] = useState({})
  const [lastUpdate, setLastUpdate] = useState(null)

  // UTCN Buildings
  const BUILDING_NAMES = {
    'Baritiu': 'Bariţiu',
    'DAIC': 'DAIC',
    'Dorobantilor': 'Dorobanţilor', 
    'Observatorului': 'Observatorului',
    'Memorandumului': 'Memorandumului',
  }

  // Helpers to extract room/building from free-form location strings when parser
  // didn't provide structured values from the backend.
  const parseRoomFromLocation = (loc) => {
    if (!loc) return ''
    try {
      // common Romanian form: "Sala 40" or "Sala 40 (Cluj...)"
      const sala = /Sala\s*([A-Za-z0-9\-]+)/i.exec(loc)
      if (sala && sala[1]) return sala[1]
      // fallback: last numeric token in the string
      const nums = loc.match(/(\d+)/g)
      if (nums && nums.length) return nums[nums.length - 1]
    } catch (e) {}
    return ''
  }

  const parseGroupFromString = (s) => {
    if (!s) return ''
    try {
      const txt = s.toString()
      const l = txt.toLowerCase()
      // common patterns: 'Year 3', 'year 3', 'Grupa A', 'Group A', '3A', '3 A', 'Engl 3'
      // Year
      let m = l.match(/\byear\s*(\d)\b/) || l.match(/\b(1|2|3|4)\s*year\b/)
      if (m) return 'Year ' + (m[1] || m[0])
      // Group (Grupa/Group)
      m = l.match(/\bgrup[ai]\s*([A-Za-z0-9]+)\b/) || l.match(/\bgroup\s*([A-Za-z0-9]+)\b/)
      if (m) return 'Group ' + m[1].toUpperCase()
      // Patterns like '3A' or '3 A'
      m = l.match(/\b([1-4])\s*([A-Za-z])\b/) || l.match(/\b([1-4][A-Za-z])\b/)
      if (m) {
        const year = m[1]
        const grp = m[2] ? m[2].toUpperCase() : (m[1].slice ? m[1].slice(1).toUpperCase() : '')
        return 'Year ' + year + ' • Group ' + grp
      }
      // trailing year token e.g. 'Engl 3' or ends with digit
      m = l.match(/(\b[1-4]\b)(?!.*\d)/)
      if (m) return 'Year ' + m[1]
    } catch (e) {}
    return ''
  }

  const inferBuildingFromLocation = (loc) => {
    if (!loc) return ''
    const l = loc.toLowerCase()
    // Simple keyword mapping - extend as needed
    const mapping = [
      { keys: ['ac bar', 'acbar', 'baritiu', 'bar -', 'baritiu', 'bar'], val: 'Baritiu' },
      { keys: ['daic'], val: 'DAIC' },
      { keys: ['doroban', 'dorobantilor'], val: 'Dorobantilor' },
      { keys: ['observator'], val: 'Observatorului' },
      { keys: ['memorandum'], val: 'Memorandumului' },
    ]
    for (const m of mapping) {
      for (const k of m.keys) {
        if (k && l.indexOf(k) !== -1) return m.val
      }
    }
    return ''
  }

  const fetchDepartures = useCallback(async () => {
    try {
      setLoading(true)
      let data
      try {
        const res = await fetch('/departures.json')
        if (res.ok) data = await res.json()
      } catch (e) {}

      if (!data || !data.events || data.events.length === 0) {
        const today = new Date().toISOString().split('T')[0]
        const tomorrow = new Date(Date.now() + 86400000).toISOString().split('T')[0]
        const res = await fetch('/events.json?from=' + today + '&to=' + tomorrow)
        if (!res.ok) throw new Error('HTTP ' + res.status)
        const evts = await res.json()
        data = { events: Array.isArray(evts) ? evts : [], buildings: {} }
      }

      const evts = data.events || data || []
      setEvents(Array.isArray(evts) ? evts : [])
      // also fetch calendar map to resolve calendar names by source
      try {
        const cres = await fetch('/calendars.json')
        if (cres.ok) {
          const cmap = await cres.json()
          setCalendarsMap(cmap || {})
        }
      } catch (e) {}
      
      // Extract unique buildings from API data (use inferred building if backend
      // didn't provide one). This powers the Building select dropdown.
      const buildingSet = new Set()
      evts.forEach(ev => {
        const b = (ev.building && ev.building.trim()) || inferBuildingFromLocation(ev.location || ev.room || '')
        if (b) buildingSet.add(b)
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
      const evBuilding = (ev.building && ev.building.trim()) || inferBuildingFromLocation(ev.location || ev.room || '')
      if (evBuilding !== selectedBuilding) return false
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
        <div className="no-events">No scheduled events</div>
      ) : (
        <div className="departure-board">
          <div className="board-header">
            <span className="col-time">Time</span>
            <span className="col-event">Event</span>
            <span className="col-prof">Professor</span>
            <span className="col-room">Room</span>
            <span className="col-group">Group/Year</span>
            <span className="col-status">Status</span>
          </div>
          {evts.sort((a, b) => (a.start || '').localeCompare(b.start || '')).slice(0, 20).map((ev, idx) => {
            const status = isToday ? getTimeStatus(ev.start) : { text: '', className: '' }
            return (
              <div key={idx} className={'board-row ' + status.className} style={{ borderLeftColor: ev.color || '#003366' }}>
                <span className="col-time">{formatTime(ev.start)}</span>
                <span className="col-event">
                  <span className="event-title">{ev.display_title || ev.title}</span>
                  <span className="event-meta">{ev.calendar_name || ev.subject || ''}</span>
                </span>
                <span className="col-prof">{ev.professor || '-'}</span>
                <span className="col-room">{ev.room || parseRoomFromLocation(ev.location) || '-'}</span>
                <span className="col-group">{ev.group_display || parseGroupFromString((calendarsMap[ev.source] && (calendarsMap[ev.source].name)) || ev.calendar_name || ev.subject || ev.title) || '-'}</span>
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
        <div className="toolbar-left"><h2>Live Board</h2></div>
        <div className="toolbar-right">
          <div className="filter-group">
            <label>Year:</label>
            <select value={selectedYear} onChange={(e) => setSelectedYear(e.target.value)}>
              <option value="">All</option>
              <option value="1">Year 1</option>
              <option value="2">Year 2</option>
              <option value="3">Year 3</option>
              <option value="4">Year 4</option>
            </select>
          </div>
          <div className="filter-group">
            <label>Group:</label>
            <select value={selectedGroup} onChange={(e) => setSelectedGroup(e.target.value)}>
              <option value="">All</option>
              <option value="A">Group A</option>
              <option value="B">Group B</option>
              <option value="C">Group C</option>
              <option value="Eng">English</option>
            </select>
          </div>
          <div className="filter-group">
            <label>Building:</label>
            <select value={selectedBuilding} onChange={(e) => setSelectedBuilding(e.target.value)}>
              <option value="">All Buildings</option>
              {buildings.map(b => <option key={b} value={b}>{BUILDING_NAMES[b] || b}</option>)}
            </select>
          </div>
          <button onClick={fetchDepartures} className="btn-refresh" disabled={loading}>
            {loading ? 'Loading...' : 'Refresh'}
          </button>
        </div>
      </div>

      {error && <div className="alert alert-error"><strong>Error:</strong> {error}</div>}
      {loading && <div className="loading-state"><div className="spinner"></div><p>Loading...</p></div>}

      {!loading && !error && (
        <div className="departures-grid">
          <DepartureBoard events={todayEvents} title={'Today (' + today + ')'} isToday={true} />
          <DepartureBoard events={tomorrowEvents} title={'Tomorrow (' + tomorrow + ')'} isToday={false} />
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
