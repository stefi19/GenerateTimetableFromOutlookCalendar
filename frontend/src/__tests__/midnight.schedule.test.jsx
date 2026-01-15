import React from 'react'
import { render, waitFor } from '@testing-library/react'
import Schedule from '../Schedule'
import { vi, beforeEach, afterEach, describe, it, expect } from 'vitest'

// Mock fetch responses
const okJson = (data) => Promise.resolve({ ok: true, json: () => Promise.resolve(data) })

beforeEach(() => {
  global.fetch = vi.fn((url) => {
    // calendars.json
    if (url.includes('/calendars.json')) return okJson({})
    // events.json
    if (url.includes('/events.json')) return okJson([])
    return okJson({})
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Schedule midnight behavior', () => {
  it('calls fetch again when midnight event is dispatched', async () => {
    const { container } = render(<Schedule />)

    // Wait for initial fetches to be called
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled()
    })

    const initialCalls = global.fetch.mock.calls.length

    // Dispatch midnight
    window.dispatchEvent(new Event('midnight'))

    // Wait for a subsequent fetch call
    await waitFor(() => {
      expect(global.fetch.mock.calls.length).toBeGreaterThan(initialCalls)
    })
  })
})
