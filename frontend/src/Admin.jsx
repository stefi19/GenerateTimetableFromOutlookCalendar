import React, { useState, useEffect, useCallback, useRef } from 'react'

const COLORS = ['#003366', '#0066cc', '#28a745', '#dc3545', '#fd7e14', '#6f42c1', '#20c997', '#e83e8c']

export default function Admin() {
  const [calendars, setCalendars] = useState([])
  // manual events feature removed: manual events are no longer supported
  const [loading, setLoading] = useState(true)
  const [importing, setImporting] = useState(false)
  const [message, setMessage] = useState(null)
  const [newCalendar, setNewCalendar] = useState({ url: '', name: '', color: '#003366' })
  // removed newEvent state (manual add event removed)
  const [stats, setStats] = useState({ events_count: 0, last_import: null, extractor_running: false })
  const pollingRef = useRef(null)

  const fetchData = useCallback(async (showLoading = true) => {
    try {
      if (showLoading) setLoading(true)
      const res = await fetch('/admin/api/status')
      if (res.ok) {
        const data = await res.json()
  setCalendars(data.calendars || [])
        setStats({ 
          events_count: data.events_count || 0, 
          last_import: data.last_import,
          extractor_running: data.extractor_running || false,
          periodic_fetcher: data.periodic_fetcher
        })
      }
    } catch (e) {
      console.error(e)
    } finally {
      if (showLoading) setLoading(false)
    }
  }, [])

  // Initial fetch
  useEffect(() => { fetchData() }, [fetchData])
  
  // Polling: refresh every 3 seconds for real-time updates
  useEffect(() => {
    pollingRef.current = setInterval(() => {
      fetchData(false) // Don't show loading spinner on polling
    }, 3000)
    
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current)
      }
    }
  }, [fetchData])

  const showMessage = (text, type) => {
    setMessage({ text, type })
    setTimeout(() => setMessage(null), 4000)
  }

  const addCalendar = async (e) => {
    e.preventDefault()
    if (!newCalendar.url) return showMessage('URL is required', 'error')
    
    try {
      const form = new FormData()
      form.append('calendar_url', newCalendar.url)
      form.append('calendar_name', newCalendar.name)
      form.append('calendar_color', newCalendar.color)
      
      const res = await fetch('/admin/set_calendar_url', { method: 'POST', body: form })
      if (res.ok) {
        showMessage('Calendar added successfully', 'success')
        setNewCalendar({ url: '', name: '', color: '#003366' })
        fetchData()
      }
    } catch (e) {
      showMessage('Error adding calendar', 'error')
    }
  }

  const importCalendar = async () => {
    setImporting(true)
    try {
      const res = await fetch('/admin/import_calendar', { method: 'POST' })
      const data = await res.json()
      showMessage(data.message || 'Import started', 'success')
    } catch (e) {
      showMessage('Import error', 'error')
    } finally {
      setImporting(false)
    }
  }

  const deleteCalendar = async (id) => {
    if (!confirm('Are you sure you want to delete this calendar?')) return
    try {
      const form = new FormData()
      form.append('id', id)
      const res = await fetch('/admin/delete_calendar', { method: 'POST', body: form })
      if (res.ok) {
        showMessage('Calendar deleted', 'success')
        fetchData()
      }
    } catch (e) {
      showMessage('Error deleting', 'error')
    }
  }

  // manual event add/delete removed

  const updateCalendarColor = async (id, color) => {
    try {
      const form = new FormData()
      form.append('id', id)
      form.append('color', color)
      const res = await fetch('/admin/update_calendar_color', { method: 'POST', body: form })
      if (res.ok) {
        showMessage('Color updated', 'success')
        fetchData()
      }
    } catch (e) {
      showMessage('Error updating color', 'error')
    }
  }

  const updateCalendarEnabled = async (id, enabled) => {
    try {
      const form = new FormData()
      form.append('id', id)
      form.append('enabled', enabled ? '1' : '0')
      const res = await fetch('/admin/update_calendar', { method: 'POST', body: form })
      if (res.ok) {
        showMessage(enabled ? 'Calendar enabled' : 'Calendar disabled', 'success')
        // update local state
        setCalendars(cals => cals.map(c => c.id === id ? { ...c, enabled: enabled ? 1 : 0 } : c))
      } else {
        showMessage('Error updating calendar', 'error')
      }
    } catch (e) {
      showMessage('Error updating calendar', 'error')
    }
  }

  return (
    <div className="admin-container">
      {message && (
        <div className={'alert alert-' + message.type}>{message.text}</div>
      )}

      <div className="admin-grid">
        <div className="admin-section">
          <div className="section-header">
            <h3>Statistics</h3>
            {stats.extractor_running && (
              <span className="status-badge importing">Importing...</span>
            )}
          </div>
          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-value">{stats.events_count}</div>
              <div className="stat-label">Events</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{calendars.length}</div>
              <div className="stat-label">Calendars</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{manualEvents.length}</div>
              <div className="stat-label">Manual</div>
            </div>
          </div>
          {stats.periodic_fetcher && (
            <div className="periodic-status">
              <small>
                Auto-refresh: every {stats.periodic_fetcher.interval_minutes} min
                {stats.periodic_fetcher.last_success && (
                  <> | Last: {new Date(stats.periodic_fetcher.last_success).toLocaleTimeString()}</>
                )}
              </small>
            </div>
          )}
          <button onClick={importCalendar} className="btn-primary btn-full" disabled={importing || stats.extractor_running}>
            {importing || stats.extractor_running ? 'Importing...' : 'Re-import all calendars'}
          </button>
        </div>

        <div className="admin-section">
          <div className="section-header">
            <h3>Configured Calendars</h3>
          </div>
          {calendars.length === 0 ? (
            <p className="text-muted">No calendars configured.</p>
          ) : (
            <div className="calendar-list">
              {calendars.map((cal, idx) => (
                <div key={cal.id || idx} className="calendar-item">
                  <div className="calendar-color-picker">
                    {COLORS.map(c => (
                      <button 
                        key={c} 
                        type="button" 
                        className={'color-btn-sm ' + ((cal.color || COLORS[idx % COLORS.length]) === c ? 'active' : '')}
                        style={{ backgroundColor: c }} 
                        onClick={() => updateCalendarColor(cal.id, c)} 
                        title="Change color"
                      />
                    ))}
                  </div>
                  <div className="calendar-info">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <strong>{cal.name || 'Calendar ' + (idx + 1)}</strong>
                      {cal.enabled ? <span className="badge badge-success">Imported</span> : <span className="badge badge-muted">Imported (disabled)</span>}
                    </div>
                    <div className="calendar-meta">
                      <span className="calendar-upn">{(function(u){ try{ const m = (u||'').match(/([\w.+-]+@[\w.-]+\.[A-Za-z]{2,})/); return m ? m[1] : '' }catch(e){return ''}})(cal.url)}</span>
                      <span className="calendar-link">{cal.url ? (<a href={cal.url} target="_blank" rel="noreferrer">Open calendar</a>) : null}</span>
                    </div>
                  </div>
                  <div className="calendar-actions">
                    <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <input type="checkbox" checked={!!cal.enabled} onChange={(e) => updateCalendarEnabled(cal.id, e.target.checked)} />
                      <small>Enabled</small>
                    </label>
                  </div>
                  <button onClick={() => deleteCalendar(cal.id)} className="btn-danger-sm">Delete</button>
                </div>
              ))}
            </div>
          )}

          <form onSubmit={addCalendar} className="form-add">
            <h4>Add New Calendar</h4>
            <input type="url" placeholder="Outlook Calendar URL" value={newCalendar.url}
              onChange={(e) => setNewCalendar(c => ({ ...c, url: e.target.value }))} required />
            <input type="text" placeholder="Calendar Name (e.g. Year 3 CTI)" value={newCalendar.name}
              onChange={(e) => setNewCalendar(c => ({ ...c, name: e.target.value }))} />
            <div className="color-picker">
              <label>Color:</label>
              <div className="color-options">
                {COLORS.map(c => (
                  <button key={c} type="button" className={'color-btn ' + (newCalendar.color === c ? 'active' : '')}
                    style={{ backgroundColor: c }} onClick={() => setNewCalendar(nc => ({ ...nc, color: c }))} />
                ))}
              </div>
            </div>
            <button type="submit" className="btn-primary">+ Add Calendar</button>
          </form>
        </div>

          {/* Manual events feature removed */}
      </div>
    </div>
  )
}
