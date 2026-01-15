import React from 'react'
import { render, waitFor } from '@testing-library/react'
import Departures from '../Departures'
import { vi, beforeEach, afterEach, describe, it, expect } from 'vitest'

const okJson = (data) => Promise.resolve({ ok: true, json: () => Promise.resolve(data) })

beforeEach(() => {
  global.fetch = vi.fn((url) => {
    if (url.includes('/departures.json')) return okJson({ events: [] })
    if (url.includes('/events.json')) return okJson([])
    if (url.includes('/calendars.json')) return okJson({})
    return okJson({})
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Departures midnight behavior', () => {
  it('calls fetch again when midnight event is dispatched', async () => {
    render(<Departures />)

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled()
    })

    const initial = global.fetch.mock.calls.length

    window.dispatchEvent(new Event('midnight'))

    await waitFor(() => {
      expect(global.fetch.mock.calls.length).toBeGreaterThan(initial)
    })
  })
})
