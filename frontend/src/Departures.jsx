import React, { useState, useEffect, useCallback } from 'react'

export default function Departures() {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedBuilding, setSelectedBuilding] = useState('')
  // Year/Group filtering removed for Live board per request
  const [buildings, setBuildings] = useState([])
  const [calendarsMap, setCalendarsMap] = useState({})
  const [lastUpdate, setLastUpdate] = useState(null)

  // UTCN Buildings
  const BUILDING_NAMES = {
    'Rectorat': 'Rectorat',
    'HUB Cluj': 'HUB Cluj',
    'BT Electro Cluj': 'BT Electro Cluj',
    'Daicoviciu Cluj': 'Daicoviciu Cluj',
    'Baritiu Electro Cluj': 'Baritiu Electro Cluj',
    'Baritiu Constructii Cluj': 'Baritiu Constructii Cluj',
    'Dorobantilor DECIDFR CLUJ': 'Dorobantilor DECIDFR CLUJ',
    'OBSERVATOR CONSTRUCTII CLUJ': 'OBSERVATOR CONSTRUCTII CLUJ',
    'OBSERVATOR ELECTRO CLUJ': 'OBSERVATOR ELECTRO CLUJ',
    '21 DECEMBRIE INSTALATII CLUJ': '21 DECEMBRIE INSTALATII CLUJ',
    'MUNCII CLUJ': 'MUNCII CLUJ',
    'CUNBM VICTORIEI': 'CUNBM VICTORIEI',
    'CUNBM BABES': 'CUNBM BABES',
    'UTCN AIRI': 'UTCN AIRI',
  }

  const CANONICAL_BUILDINGS = [
    'Rectorat', 'HUB Cluj', 'BT Electro Cluj', 'Daicoviciu Cluj',
    'Baritiu Electro Cluj', 'Baritiu Constructii Cluj', 'Dorobantilor DECIDFR CLUJ',
    'OBSERVATOR CONSTRUCTII CLUJ', 'OBSERVATOR ELECTRO CLUJ', '21 DECEMBRIE INSTALATII CLUJ',
    'MUNCII CLUJ', 'CUNBM VICTORIEI', 'CUNBM BABES', 'UTCN AIRI'
  ]

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
      // Look for Romanian keywords as well: 'seria', 'serie', 'an', 'anul'
      let year = null
      let grp = null

      // year patterns: 'an 3', 'anul 3', 'year 3', or trailing digit
      let m = l.match(/\ban(?:ul)?\s*(?:[:\-]?\s*)?(\d)\b/) || l.match(/\byear\s*(\d)\b/)
      if (m) year = m[1]
      if (!year) {
        m = l.match(/(\b[1-4]\b)(?!.*\d)/)
        if (m) year = m[1]
      }

      // group/series patterns: 'seria B', 'serie B', 'grupa A', 'group A'
      m = l.match(/\bseri[ae]\s*([A-Za-z0-9]+)\b/) || l.match(/\bgrup[ai]\s*([A-Za-z0-9]+)\b/) || l.match(/\bgroup\s*([A-Za-z0-9]+)\b/)
      if (m) grp = m[1].toUpperCase()

      // Patterns like '3A' or '3 A' where first token is year and letter is group
      if (!year || !grp) {
        m = l.match(/\b([1-4])\s*([A-Za-z])\b/) || l.match(/\b([1-4])([A-Za-z])\b/)
        if (m) {
          if (!year) year = m[1]
          if (!grp) grp = (m[2] || '').toUpperCase()
        }
      }

      if (year && grp) return 'Year ' + year + ' • Group ' + grp
      if (year) return 'Year ' + year
      if (grp) return 'Group ' + grp
    } catch (e) {}
    return ''
  }

  const inferBuildingFromLocation = (loc) => {
    if (!loc) return ''
    const l = loc.toLowerCase()

  // Priority-based Baritiu parsing using token/word matches
  // Match BT as a standalone token or as a prefix like 'BT123', 'BT-101', 'BT_101',
  // or dotted forms like 'B.T.'. Allow non-letter separators between B and T.
  // This catches variants like 'BT101', 'BT-101', 'B.T.101', 'b_t101', 'Sala B.T. 12'.
  if (/(^|[^a-z0-9])b[\W_]*t(?=[^a-z]|$)/.test(l)) return 'BT Electro Cluj'
  // Match variations that should map to Baritiu Electro: AC Bar, ACBar, IE Bar, IEBar, ETTI Bar, etc.
  // Examples: 'UTCN - AC Bar - Sala S42', 'IE BAr', 'ETTI Bar'
  if (/\bac\s*bar\b/.test(l) || /acbar/.test(l) || /\bie\s*bar\b/.test(l) || /iebar/.test(l) || /\bett?ti\s*bar\b/.test(l) || /etti?bar/.test(l)) return 'Baritiu Electro Cluj'
  // Match variations for construction building -> detect explicit 'construct' or 'constructii',
  // or patterns like 'cons' together with 'bar'/'baritiu' (e.g. 'Cons Bar', 'ConsBar', 'Cons Baritiu')
  if (/\bconstruct/i.test(l) || /\bconstructii\b/.test(l) || (/\bcons\b/.test(l) && (/\bbar\b/.test(l) || /\bbaritiu\b/.test(l)))) return 'Baritiu Constructii Cluj'

    // If string mentions plain 'baritiu' but no qualifier, treat as unknown (avoid general 'Baritiu')
    if (l.indexOf('baritiu') !== -1 && !l.match(/electro|construct/i) && !l.match(/bt|ac|cons/i)) {
      return ''
    }

    // Comprehensive building mapping
    const mapping = [
      { keys: ['rectorat'], val: 'Rectorat' },
      { keys: ['hub cluj', 'hub'], val: 'HUB Cluj' },
      { keys: ['bt electro cluj', 'bt electro'], val: 'BT Electro Cluj' },
      { keys: ['daicoviciu cluj', 'daicoviciu'], val: 'Daicoviciu Cluj' },
      { keys: ['baritiu electro cluj', 'baritiu electro'], val: 'Baritiu Electro Cluj' },
      { keys: ['baritiu constructii cluj', 'baritiu constructii'], val: 'Baritiu Constructii Cluj' },
      { keys: ['dorobantilor decidfr cluj', 'decidfr', 'dorobantilor decidfr'], val: 'Dorobantilor DECIDFR CLUJ' },
      { keys: ['observator constructii cluj', 'observator constructii'], val: 'OBSERVATOR CONSTRUCTII CLUJ' },
      { keys: ['observator electro cluj', 'observator electro'], val: 'OBSERVATOR ELECTRO CLUJ' },
      { keys: ['21 decembrie instalatii cluj', '21 decembrie', 'decembrie instalatii'], val: '21 DECEMBRIE INSTALATII CLUJ' },
      { keys: ['muncII cluj', 'muncII'], val: 'MUNCII CLUJ' },
      { keys: ['cunbm victoriei', 'victoriei'], val: 'CUNBM VICTORIEI' },
      { keys: ['cunbm babes', 'babes'], val: 'CUNBM BABES' },
      { keys: ['utcn airi', 'airi'], val: 'UTCN AIRI' },
      // Fallbacks for existing mappings
      { keys: ['daic'], val: 'DAIC' },
      { keys: ['doroban', 'dorobantilor'], val: 'Dorobantilor' },
      { keys: ['memorandum'], val: 'Memorandumului' },
    ]
    for (const m of mapping) {
      for (const k of m.keys) {
        if (k && l.indexOf(k) !== -1) return m.val
      }
    }
    return ''
  }

  // Normalize a raw building string (from backend) into one of the canonical building names
  // We try (in order): direct canonical substring match, disambiguation for ambiguous
  // 'Baritiu' values by inspecting location/room, then falling back to inference.
  const normalizeBuilding = (raw, loc) => {
    if (!raw && !loc) return ''
    const r = (raw || '').toString().trim()
    const rl = r.toLowerCase()
    const ll = (loc || '').toString().toLowerCase()

    // 1) Direct canonical substring match
    for (const c of CANONICAL_BUILDINGS) {
      if (r && rl.indexOf(c.toLowerCase()) !== -1) return c
    }

    // 2) If raw mentions 'baritiu' but lacks qualifier, attempt to disambiguate
    if (rl.indexOf('baritiu') !== -1) {
      // If location/room hints at Electro (AC/IE/ETTI/IE/AC/ELECTRO/BT)
      if (/\bac\b/.test(ll) || /\bie\b/.test(ll) || /\bett?ti\b/.test(ll) || ll.indexOf('electro') !== -1 || /(^|[^a-z0-9])b[\W_]*t(?=[^a-z]|$)/.test(ll)) {
        return 'Baritiu Electro Cluj'
      }
      // If location/room hints at Constructii
      if (ll.indexOf('construct') !== -1 || ll.indexOf('constructii') !== -1 || (ll.indexOf('cons') !== -1 && (ll.indexOf('bar') !== -1 || ll.indexOf('baritiu') !== -1))) {
        return 'Baritiu Constructii Cluj'
      }
      // Default pragmatic mapping for bare 'Baritiu' -> Baritiu Electro
      return 'Baritiu Electro Cluj'
    }

    // 3) Fallback to infer from location/room
    const inferred = inferBuildingFromLocation(loc || '')
    if (CANONICAL_BUILDINGS.includes(inferred)) return inferred
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
        // Combine location and room so clues in either field are considered
        const combinedLoc = ((ev.location || '') + ' ' + (ev.room || '')).trim()
        const b = normalizeBuilding(ev.building, combinedLoc)
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
      // Use normalized building for comparison so raw DB values and inferred
      // values match the canonical list used in the dropdown. Consider both
      // location and room fields when normalizing so 'BT' in room names is
      // detected.
      const combinedLoc = ((ev.location || '') + ' ' + (ev.room || '')).trim()
      const evBuilding = normalizeBuilding(ev.building, combinedLoc)
      if (evBuilding !== selectedBuilding) return false
    }
    return true
  })

  const todayEvents = filteredEvents.filter(ev => {
    if (!ev.start || !ev.start.startsWith(today)) return false
    // For live board, exclude events that have already ended
    if (ev.end) {
      const endTime = new Date(ev.end)
      if (endTime < new Date()) return false
    }
    return true
  })
  const tomorrowEvents = filteredEvents.filter(ev => ev.start && ev.start.startsWith(tomorrow))

  const formatTime = (isoString) => {
    if (!isoString) return '--:--'
    try {
      return new Date(isoString).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
    } catch (e) {
      return '--:--'
    }
  }

  const getTimeStatus = (ev) => {
    if (!ev.start) return { text: '', className: '' }
    try {
      const now = new Date()
      const startTime = new Date(ev.start)
      const endTime = ev.end ? new Date(ev.end) : null
      
      // If we have end time and current time is past end time, shouldn't happen due to filtering
      if (endTime && now > endTime) {
        return { text: 'Finished', className: 'status-finished' }
      }
      
      // If current time is past start time, it's in progress
      if (now >= startTime) {
        return { text: 'In progress', className: 'status-active' }
      }
      
      // Calculate time until start
      const diff = startTime - now
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
            const status = isToday ? getTimeStatus(ev) : { text: '', className: '' }
            return (
              <div key={idx} className={'board-row ' + status.className} style={{ borderLeftColor: ev.color || '#003366' }}>
                <span className="col-time">{formatTime(ev.start)}<small>{formatTime(ev.end)}</small></span>
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
            {/* Year/Group filters removed from Live board */}
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
