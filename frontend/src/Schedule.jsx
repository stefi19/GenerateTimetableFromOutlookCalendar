import React, { useState, useEffect, useCallback } from 'react'

const CALENDAR_COLORS = [
  '#003366', '#0066cc', '#28a745', '#dc3545',
  '#fd7e14', '#6f42c1', '#20c997', '#e83e8c'
]

export default function Schedule() {
  const [events, setEvents] = useState([])
  const [allEvents, setAllEvents] = useState([]) // All events for 2 months
  const [calendars, setCalendars] = useState({})
  const [enabledCalendars, setEnabledCalendars] = useState({}) // Which calendars are checked
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [filters, setFilters] = useState({ subject: '', professor: '', room: '' })
  const [searchQuery, setSearchQuery] = useState('') // Search input
  const [searchSuggestions, setSearchSuggestions] = useState([]) // Autocomplete suggestions
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [calendarSearch, setCalendarSearch] = useState('') // Search calendars
  const [lastUpdate, setLastUpdate] = useState(null)
  const [viewMode, setViewMode] = useState('week')
  const [nearestDay, setNearestDay] = useState(null) // For showing nearest events message
  const [weekOffset, setWeekOffset] = useState(0) // For calendar navigation (0 = current week)

  // Get start of week (Monday) for a given date
  const getWeekStart = useCallback((date, offset = 0) => {
    const d = new Date(date)
    const day = d.getDay()
    const diff = d.getDate() - day + (day === 0 ? -6 : 1) // Adjust for Monday start
    d.setDate(diff + (offset * 7))
    d.setHours(0, 0, 0, 0)
    return d
  }, [])

  // Get week range label
  const getWeekLabel = useCallback((offset) => {
    const weekStart = getWeekStart(new Date(), offset)
    const weekEnd = new Date(weekStart)
    weekEnd.setDate(weekEnd.getDate() + 6)
    
    const startStr = weekStart.toLocaleDateString('en-US', { day: 'numeric', month: 'short' })
    const endStr = weekEnd.toLocaleDateString('en-US', { day: 'numeric', month: 'short', year: 'numeric' })
    
    if (offset === 0) return `This Week (${startStr} - ${endStr})`
    if (offset === 1) return `Next Week (${startStr} - ${endStr})`
    if (offset === -1) return `Last Week (${startStr} - ${endStr})`
    return `${startStr} - ${endStr}`
  }, [getWeekStart])

  // Fetch list of all calendars from calendar_map.json (includes all calendars with their hashes)
  const fetchCalendarList = useCallback(async () => {
    try {
      const res = await fetch('/calendars.json')
      if (res.ok) {
        const data = await res.json()
        // data is { hash: { name, color, url }, ... }
        const calMap = {}
        const enabled = {}
        Object.entries(data).forEach(([hash, info]) => {
          calMap[hash] = {
            color: info.color || CALENDAR_COLORS[Object.keys(calMap).length % CALENDAR_COLORS.length],
            name: info.name || hash
          }
          enabled[hash] = true // All enabled by default
        })
        setCalendars(calMap)
        setEnabledCalendars(prev => {
          // Keep existing preferences, add new calendars as enabled
          const merged = { ...enabled }
          Object.keys(prev).forEach(k => {
            if (k in merged) merged[k] = prev[k]
          })
          return merged
        })
      }
    } catch (e) {
      console.error('Failed to fetch calendar list:', e)
    }
  }, [])

  // Fetch calendars on mount
  useEffect(() => {
    fetchCalendarList()
  }, [fetchCalendarList])

  // When calendars (from /calendars.json) change, ensure events already loaded pick up their calendar colors
  useEffect(() => {
    if (!calendars || Object.keys(calendars).length === 0) return
    setEvents(prev => prev.map(ev => ({
      ...ev,
      color: ev.color || (calendars[ev.source] && calendars[ev.source].color) || ev.color
    })))
    setAllEvents(prev => prev.map(ev => ({
      ...ev,
      color: ev.color || (calendars[ev.source] && calendars[ev.source].color) || ev.color
    })))
  }, [calendars])

  // Find the nearest day with events from today onwards
  const findNearestDayWithEvents = useCallback((allEvts) => {
    if (!allEvts || allEvts.length === 0) return null
    
    const today = new Date().toISOString().split('T')[0]
    
    // Get all unique dates that have events, sorted
    const datesWithEvents = [...new Set(
      allEvts
        .filter(ev => ev.start && ev.start.split('T')[0] >= today)
        .map(ev => ev.start.split('T')[0])
    )].sort()
    
    return datesWithEvents.length > 0 ? datesWithEvents[0] : null
  }, [])

  const fetchEvents = useCallback(async () => {
    try {
      setLoading(true)
      const today = new Date()
      const todayStr = today.toISOString().split('T')[0]
      
      let fromDate, toDate
      
      if (viewMode === 'calendar') {
        // Calendar mode: use weekOffset to determine which week to show
        const weekStart = getWeekStart(today, weekOffset)
        const weekEnd = new Date(weekStart)
        weekEnd.setDate(weekEnd.getDate() + 6)
        fromDate = weekStart.toISOString().split('T')[0]
        toDate = weekEnd.toISOString().split('T')[0]
      } else {
        // Day/Week mode: start from today
        const days = viewMode === 'week' ? 7 : 1
        fromDate = todayStr
        toDate = new Date(Date.now() + days * 24 * 60 * 60 * 1000).toISOString().split('T')[0]
      }
      
      // Also fetch all events for 2 months to find nearest day and build calendar list
      const twoMonthsEnd = new Date(Date.now() + 60 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]
      
      const params = new URLSearchParams({ from: fromDate, to: toDate })
      if (filters.subject) params.set('subject', filters.subject)
      if (filters.professor) params.set('professor', filters.professor)
      if (filters.room) params.set('room', filters.room)

      // Fetch current view events
      const res = await fetch('/events.json?' + params.toString())
      if (!res.ok) throw new Error('HTTP ' + res.status)
      
      let data = await res.json()
      let evts = Array.isArray(data) ? data : []
      
      // Also fetch all events for 2 months (without view filters)
      const allParams = new URLSearchParams({ from: todayStr, to: twoMonthsEnd })
      const allRes = await fetch('/events.json?' + allParams.toString())
      let allEvts = []
      if (allRes.ok) {
        const allData = await allRes.json()
        allEvts = Array.isArray(allData) ? allData : []
      }
      setAllEvents(allEvts)
      
      // If no events in current view (and not in calendar mode), find nearest day and fetch those events
      if (evts.length === 0 && allEvts.length > 0 && viewMode !== 'calendar') {
        const nearest = findNearestDayWithEvents(allEvts)
        if (nearest) {
          setNearestDay(nearest)
          // Fetch events for that day (and a week from it if in week mode)
          const nearestEnd = viewMode === 'week' 
            ? new Date(new Date(nearest).getTime() + 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]
            : nearest
          const nearestParams = new URLSearchParams({ from: nearest, to: nearestEnd })
          if (filters.subject) nearestParams.set('subject', filters.subject)
          if (filters.professor) nearestParams.set('professor', filters.professor)
          if (filters.room) nearestParams.set('room', filters.room)
          
          const nearestRes = await fetch('/events.json?' + nearestParams.toString())
          if (nearestRes.ok) {
            const nearestData = await nearestRes.json()
            evts = Array.isArray(nearestData) ? nearestData : []
          }
        }
      } else {
        setNearestDay(null)
      }
      
      // Build calendar map preferring DB-provided calendars (from /calendars.json); fall back to event-derived colors
      const calendarMap = { ...calendars }
      let colorIndex = Object.keys(calendarMap).length || 0
      allEvts.forEach(ev => {
        const source = ev.source || 'default'
        if (!calendarMap[source]) {
          calendarMap[source] = {
            color: ev.color || CALENDAR_COLORS[colorIndex % CALENDAR_COLORS.length],
            name: ev.calendar_name || source
          }
          colorIndex++
        } else {
          // fill missing metadata from events when possible
          if (!calendarMap[source].name) calendarMap[source].name = ev.calendar_name || source
          if (!calendarMap[source].color && ev.color) calendarMap[source].color = ev.color
        }
      })

      // Ensure events in the current view get a color (prefer event.color, then calendarMap color)
      evts.forEach(ev => {
        if (!ev.color) {
          const src = ev.source || 'default'
          if (calendarMap[src] && calendarMap[src].color) ev.color = calendarMap[src].color
        }
      })
      
      // Don't overwrite calendars - fetchCalendarList gets the complete list from DB
      setEvents(evts)
      setLastUpdate(new Date())
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [filters, viewMode, weekOffset, getWeekStart, findNearestDayWithEvents])

  useEffect(() => {
    fetchEvents()
    const interval = setInterval(fetchEvents, 3600000)
    return () => clearInterval(interval)
  }, [fetchEvents])

  // Reset weekOffset when switching away from calendar mode
  useEffect(() => {
    if (viewMode !== 'calendar') {
      setWeekOffset(0)
    }
  }, [viewMode])

  // Generate search suggestions from event titles
  const updateSearchSuggestions = useCallback((query) => {
    const lowerQuery = (query || '').toLowerCase()
    const titleSet = new Set()
    allEvents.forEach(ev => {
      const title = ev.display_title || ev.title || ''
      // If no query, show all unique titles; otherwise filter
      if (!lowerQuery || title.toLowerCase().includes(lowerQuery)) {
        titleSet.add(title)
      }
      // Also check calendar names
      const calName = ev.calendar_name || calendars[ev.source]?.name || ''
      if (!lowerQuery || calName.toLowerCase().includes(lowerQuery)) {
        if (calName) titleSet.add(calName)
      }
    })
    // Sort and limit to 10 suggestions
    const suggestions = [...titleSet].sort().slice(0, 10)
    setSearchSuggestions(suggestions)
  }, [allEvents, calendars])

  // Handle search input change
  const handleSearchChange = (e) => {
    const value = e.target.value
    setSearchQuery(value)
    updateSearchSuggestions(value)
    setShowSuggestions(true)
  }

  // Handle search focus - show all suggestions
  const handleSearchFocus = () => {
    updateSearchSuggestions(searchQuery)
    setShowSuggestions(true)
  }

  // Select a suggestion
  const selectSuggestion = (suggestion) => {
    setSearchQuery(suggestion)
    setShowSuggestions(false)
    setSearchSuggestions([])
  }

  // Toggle calendar visibility
  const toggleCalendar = (source) => {
    setEnabledCalendars(prev => ({
      ...prev,
      [source]: !prev[source]
    }))
  }

  // Toggle all calendars
  const toggleAllCalendars = (enabled) => {
    const newState = {}
    Object.keys(calendars).forEach(k => { newState[k] = enabled })
    setEnabledCalendars(newState)
  }

  // Filter events by enabled calendars and search query
  const filteredEvents = events.filter(ev => {
    const source = ev.source || 'default'
    // Check if calendar is enabled
    if (enabledCalendars[source] === false) return false
    // Check search query
    if (searchQuery) {
      const lowerQuery = searchQuery.toLowerCase()
      const title = (ev.display_title || ev.title || '').toLowerCase()
      const location = (ev.room || ev.location || '').toLowerCase()
      const professor = (ev.professor || '').toLowerCase()
      const calName = (ev.calendar_name || calendars[source]?.name || '').toLowerCase()
      if (!title.includes(lowerQuery) && !location.includes(lowerQuery) && 
          !professor.includes(lowerQuery) && !calName.includes(lowerQuery)) {
        return false
      }
    }
    return true
  })

  const groupedByDate = filteredEvents.reduce((acc, ev) => {
    const date = ev.start ? ev.start.split('T')[0] : 'Unknown'
    if (!acc[date]) acc[date] = []
    acc[date].push(ev)
    return acc
  }, {})

  const sortedDates = Object.keys(groupedByDate).sort()

  const formatTime = (isoString) => {
    if (!isoString) return '--:--'
    try {
      return new Date(isoString).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
    } catch (e) {
      return '--:--'
    }
  }

  // Helpers copied from Departures.jsx to keep parsing consistent in calendar view
  const parseRoomFromLocation = (loc) => {
    if (!loc) return ''
    try {
      const sala = /Sala\s*([A-Za-z0-9\-]+)/i.exec(loc)
      if (sala && sala[1]) return sala[1]
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
      let m = l.match(/\byear\s*(\d)\b/) || l.match(/\b(1|2|3|4)\s*year\b/)
      if (m) return 'Year ' + (m[1] || m[0])
      m = l.match(/\bgrup[ai]\s*([A-Za-z0-9]+)\b/) || l.match(/\bgroup\s*([A-Za-z0-9]+)\b/)
      if (m) return 'Group ' + m[1].toUpperCase()
      m = l.match(/\b([1-4])\s*([A-Za-z])\b/) || l.match(/\b([1-4][A-Za-z])\b/)
      if (m) {
        const year = m[1]
        const grp = m[2] ? m[2].toUpperCase() : (m[1].slice ? m[1].slice(1).toUpperCase() : '')
        return 'Year ' + year + ' • Group ' + grp
      }
      m = l.match(/(\b[1-4]\b)(?!.*\d)/)
      if (m) return 'Year ' + m[1]
    } catch (e) {}
    return ''
  }

  const formatDateHeader = (dateStr) => {
    try {
      const d = new Date(dateStr)
      const today = new Date().toISOString().split('T')[0]
      const tomorrow = new Date(Date.now() + 86400000).toISOString().split('T')[0]
      let prefix = ''
      if (dateStr === today) prefix = 'Today • '
      else if (dateStr === tomorrow) prefix = 'Tomorrow • '
      return prefix + d.toLocaleDateString('en-US', { weekday: 'long', day: 'numeric', month: 'long' })
    } catch (e) {
      return dateStr
    }
  }

  const clearFilters = () => {
    setFilters({ subject: '', professor: '', room: '' })
    setSearchQuery('')
    setSearchSuggestions([])
    toggleAllCalendars(true)
  }

  const someCalendarsDisabled = Object.values(enabledCalendars).some(v => v === false)
  const hasActiveFilters = filters.subject || filters.professor || filters.room || searchQuery || someCalendarsDisabled

  return (
    <div className="schedule-container">
      <div className="toolbar">
        <div className="toolbar-left">
          <h2>{viewMode === 'calendar' ? 'Calendar View' : 'Weekly Schedule'}</h2>
          <div className="view-toggle">
            <button className={viewMode === 'day' ? 'active' : ''} onClick={() => setViewMode('day')}>Day</button>
            <button className={viewMode === 'week' ? 'active' : ''} onClick={() => setViewMode('week')}>Week</button>
            <button className={viewMode === 'calendar' ? 'active' : ''} onClick={() => setViewMode('calendar')}>Calendar</button>
          </div>
        </div>
        <div className="toolbar-right">
          <button onClick={fetchEvents} className="btn-refresh" disabled={loading}>
            {loading ? 'Loading...' : 'Refresh'}
          </button>
        </div>
      </div>

      {viewMode === 'calendar' && (
        <div className="week-navigation">
          <button onClick={() => setWeekOffset(o => o - 1)} className="btn-nav">
            ← Previous Week
          </button>
          <span className="week-label">{getWeekLabel(weekOffset)}</span>
          <button onClick={() => setWeekOffset(o => o + 1)} className="btn-nav">
            Next Week →
          </button>
          {weekOffset !== 0 && (
            <button onClick={() => setWeekOffset(0)} className="btn-today">
              Today
            </button>
          )}
        </div>
      )}

      <div className="filters-bar">
        <div className="filter-group search-group">
          <label>Search:</label>
          <div className="search-wrapper">
            <input 
              type="text" 
              placeholder="Search events..." 
              value={searchQuery}
              onChange={handleSearchChange}
              onFocus={handleSearchFocus}
              onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
              className="search-input"
            />
            {showSuggestions && searchSuggestions.length > 0 && (
              <div className="search-suggestions">
                {searchSuggestions.map((suggestion, idx) => (
                  <div 
                    key={idx} 
                    className="suggestion-item"
                    onClick={() => selectSuggestion(suggestion)}
                  >
                    {suggestion}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
        <div className="filter-group">
          <label>Subject:</label>
          <input type="text" placeholder="e.g. Algorithms" value={filters.subject}
            onChange={(e) => setFilters(f => ({ ...f, subject: e.target.value }))} />
        </div>
        <div className="filter-group">
          <label>Professor:</label>
          <input type="text" placeholder="e.g. Smith" value={filters.professor}
            onChange={(e) => setFilters(f => ({ ...f, professor: e.target.value }))} />
        </div>
        <div className="filter-group">
          <label>Room:</label>
          <input type="text" placeholder="e.g. A101" value={filters.room}
            onChange={(e) => setFilters(f => ({ ...f, room: e.target.value }))} />
        </div>
        {hasActiveFilters && (
          <button onClick={clearFilters} className="btn-clear">Clear filters</button>
        )}
      </div>

      {Object.keys(calendars).length > 0 && (
        <div className="calendar-legend-container">
          <span className="legend-title">Calendars:</span>
          <input 
            type="text"
            placeholder="Search calendars..."
            value={calendarSearch}
            onChange={(e) => setCalendarSearch(e.target.value)}
            className="calendar-search-input"
          />
          <div className="calendar-legend">
            {Object.entries(calendars)
              .filter(([source, cal]) => {
                if (!calendarSearch) return true
                return cal.name.toLowerCase().includes(calendarSearch.toLowerCase())
              })
              .map(([source, cal]) => (
              <label key={source} className="legend-item" title={cal.name}>
                <input 
                  type="checkbox" 
                  checked={enabledCalendars[source] !== false}
                  onChange={() => toggleCalendar(source)}
                />
                <span className="legend-dot" style={{ backgroundColor: cal.color }}></span>
                <span className="legend-name">{cal.name}</span>
              </label>
            ))}
          </div>
          <div className="legend-actions">
            <button onClick={() => toggleAllCalendars(true)} className="btn-legend">All</button>
            <button onClick={() => toggleAllCalendars(false)} className="btn-legend">None</button>
          </div>
        </div>
      )}

      {error && <div className="alert alert-error"><strong>Error:</strong> {error}</div>}

      {nearestDay && (
        <div className="alert alert-info">
          <strong>No events today/this week.</strong> Showing events starting from{' '}
          <strong>{new Date(nearestDay).toLocaleDateString('en-US', { weekday: 'long', day: 'numeric', month: 'long' })}</strong>
          {' '}— the nearest day with scheduled events.
        </div>
      )}

      {!loading && !error && events.length === 0 && !nearestDay && (
        <div className="empty-state">
          <div className="empty-icon"></div>
          <h3>No events found</h3>
          <p>Go to <strong>Admin</strong> to import a calendar.</p>
        </div>
      )}

      {loading && (
        <div className="loading-state"><div className="spinner"></div><p>Loading...</p></div>
      )}

      <div className="schedule-grid">
        {sortedDates.map(date => (
          <div key={date} className="day-section">
            <div className="day-header">
              <h3>{formatDateHeader(date)}</h3>
              <span className="event-count">{groupedByDate[date].length} events</span>
            </div>
            <div className="events-table">
              <div className="events-table-inner">
                <div className="table-header">
                  <span className="col-time">Time</span>
                  <span className="col-title">Event</span>
                  <span className="col-professor">Professor</span>
                  <span className="col-location">Room</span>
                  <span className="col-group">Group/Year</span>
                  <span className="col-status">Status</span>
                </div>
                {groupedByDate[date].sort((a, b) => (a.start || '').localeCompare(b.start || '')).map((ev, idx) => (
                  <div key={idx} className="table-row" style={{ borderLeftColor: ev.color || '#003366' }}>
                    <span className="col-time">{formatTime(ev.start)}<small>{formatTime(ev.end)}</small></span>
                    <span className="col-title"><strong>{ev.display_title || ev.title}</strong>
                      {ev.subject && ev.subject !== ev.display_title && <small className="event-meta">{ev.subject}</small>}
                    </span>
                    <span className="col-professor">{ev.professor || '-'}</span>
                    <span className="col-location">{ev.room || parseRoomFromLocation(ev.location) || '-'}</span>
                    <span className="col-group">{ev.group_display || parseGroupFromString((calendars[ev.source] && calendars[ev.source].name) || ev.calendar_name || ev.subject || ev.title) || '-'}</span>
                    <span className="col-status">{''}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>

      {lastUpdate && (
        <div className="status-bar">
          <span>Last update: {lastUpdate.toLocaleTimeString('en-US')}</span>
          <span>•</span>
          <span>{events.length} events</span>
        </div>
      )}
    </div>
  )
}
