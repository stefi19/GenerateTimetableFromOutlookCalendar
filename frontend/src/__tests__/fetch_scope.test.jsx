import React from 'react'
import { render, waitFor } from '@testing-library/react'
import Schedule from '../Schedule'
import { vi, beforeEach, afterEach, describe, it, expect } from 'vitest'

// Helper to find events.json calls and parse query params
const findEventsCall = (calls) => {
  for (const call of calls) {
    const url = call[0]
    if (typeof url === 'string' && url.includes('/events.json?')) return url
  }
  return null
}

beforeEach(() => {
  // Freeze time to 2026-01-15 10:00 local
  vi.setSystemTime(new Date(2026, 0, 15, 10, 0, 0))
  global.fetch = vi.fn((url) => {
    if (typeof url === 'string' && url.includes('/calendars.json')) return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    if (typeof url === 'string' && url.includes('/events.json')) return Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
  })
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('Scoped fetch behavior', () => {
  it('fetches current week on mount (currentWeek scope)', async () => {
    render(<Schedule />)

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled()
    })

    // Compute expected week start/end using the same logic as the app (Monday start)
    const computeWeekStart = (date, offset = 0) => {
      const d = new Date(date)
      const day = d.getDay()
      const diff = d.getDate() - day + (day === 0 ? -6 : 1)
      d.setDate(diff + (offset * 7))
      d.setHours(0, 0, 0, 0)
      return d.toISOString().split('T')[0]
    }
    const expectedFrom = computeWeekStart(new Date(2026, 0, 15), 0)
    const expectedTo = (function(fromStr) {
      const d = new Date(fromStr)
      d.setDate(d.getDate() + 6)
      return d.toISOString().split('T')[0]
    })(expectedFrom)
    let matched = false
    for (const call of global.fetch.mock.calls) {
      const url = call[0]
      if (typeof url === 'string' && url.includes('/events.json?')) {
        const params = new URL('http://localhost' + url.split('/events.json')[1])
        const from = params.searchParams.get('from')
        const to = params.searchParams.get('to')
        if (from === expectedFrom && to === expectedTo) {
          matched = true
          break
        }
      }
    }
    expect(matched).toBe(true)
  })

  it('on midnight dispatch fetches twoMonthsAll', async () => {
    render(<Schedule />)

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled()
    })

    const initialCount = global.fetch.mock.calls.length

    // Dispatch midnight event
    window.dispatchEvent(new Event('midnight'))

    await waitFor(() => {
      expect(global.fetch.mock.calls.length).toBeGreaterThan(initialCount)
    })

    // find the most recent events.json call
    const calls = global.fetch.mock.calls.slice()
    let found = null
    for (let i = calls.length - 1; i >= 0; i--) {
      const u = calls[i][0]
      if (typeof u === 'string' && u.includes('/events.json?')) { found = u; break }
    }
    expect(found).toBeTruthy()
    const params = new URL('http://localhost' + found.split('/events.json')[1])
    const from = params.searchParams.get('from')
    const to = params.searchParams.get('to')

    // twoMonthsAll starts from today 2026-01-15 to +60 days = 2026-03-16
    expect(from).toBe('2026-01-15')
    expect(to).toBe('2026-03-16')
  })
})
