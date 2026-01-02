# Features — AC UTCN Timetable Viewer

This document provides a detailed breakdown of all implemented features and the technical architecture.

## Overview

The app is a complete timetable management system with:
- **React SPA Frontend** — Modern single-page application with Schedule, Departures, and Admin views
- **Flask Backend** — REST API and calendar extraction pipeline
- **SQLite Persistence** — Reliable data storage for calendars and events
- **Playwright Extraction** — Automated scraping of client-side rendered calendar pages

## Implemented Features

### 🎨 React SPA Frontend (`/app`)

The main user interface is a React single-page application built with Vite.

| Component | File | Description |
|-----------|------|-------------|
| **App** | `App.jsx` | Main container with tabbed navigation and live clock |
| **Schedule** | `Schedule.jsx` | Weekly timetable with day grouping and event cards |
| **Departures** | `Departures.jsx` | Departure-board style view for displays |
| **Admin** | `Admin.jsx` | Calendar and event management panel |

**UI Features:**
- Live clock with real-time updates (second precision)
- UTCN branding with university header
- Responsive tabbed navigation
- Event cards with visual styling
- Date-based grouping for schedule view

### 📅 Schedule View

- Full timetable built from imported + manual + extracurricular events
- Events grouped by day with clear date headers
- Event cards showing:
  - Time range (start - end)
  - Event title/subject
  - Location/room
  - Professor (when parsed)
- Supports query parameter filtering (subject, professor, room, date range)
- 7-day default range (configurable)

### 🚀 Departures / Board View

- Departure-board style UI optimized for large displays
- Shows events for today and tomorrow
- Grouped by building/location
- Includes all event types (imported, manual, extracurricular)
- Auto-refreshing display suitable for lobby screens

### ⚙️ Admin Panel

| Feature | Description |
|---------|-------------|
| Add Calendar URL | Save published Outlook calendar with optional name and color |
| Import Now | Trigger immediate calendar extraction (background Playwright) |
| Delete Calendar | Remove calendar configuration from database |
| Add Manual Event | Create one-time event with custom details |
| Add Extracurricular | Add recurring activities (clubs, sports) |
| Delete Events | Remove manual or extracurricular events |
| Color Swatches | Visual color indicators for each calendar source |

### 💾 Persistence (SQLite)

Database location: `data/app.db`

**Tables:**
```sql
calendars (id, url, name, color, enabled, created_at, last_fetched)
manual_events (id, start, end, title, location, raw, created_at)
extracurricular_events (id, title, organizer, date, time, location, category, description, created_at)
```

**Features:**
- Automatic migration from legacy JSON config files
- Transaction-safe operations
- Concurrent access handling

### 🎭 Playwright-Backed Extractor

- Renders client-side JavaScript pages in headless Chromium
- Captures network responses for calendar data
- Extracts `.ics` links from DOM
- Fallback parsing for microformats (hCalendar/vevent)
- Outputs to `playwright_captures/events.json`

### 📝 Subject & Location Normalization

- Parses event titles into structured components:
  - Subject name
  - Display title
  - Professor name
- Room/location mapping via `config/room_aliases.json`
- Improves filtering and UI grouping

### 🔌 Events API

**Endpoint:** `GET /events.json`

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `from` | date | Start date filter (YYYY-MM-DD) |
| `to` | date | End date filter (YYYY-MM-DD) |
| `subject` | string | Filter by subject |
| `professor` | string | Filter by professor |
| `room` | string | Filter by room |

**Response:** JSON array of event objects suitable for FullCalendar or custom UIs.

### ⏰ Periodic Background Importer

- Background thread started on app launch
- Initial import runs immediately (no delay)
- Subsequent runs every 60 minutes
- Internal lock prevents overlapping runs
- Configurable interval in `app.py`

### 🎨 Per-Calendar Colors

- Optional hex color assignment for each calendar source
- Color displayed as swatch in Admin UI
- Can be used for visual differentiation in schedule view

### 🔧 Setup Automation

**`setup.sh`** performs full bootstrap:
1. Creates `.venv` virtual environment
2. Installs Python dependencies from `requirements.txt`
3. Installs Playwright browsers (Chromium)
4. Initializes SQLite database
5. Migrates legacy JSON configs to database

**`run.sh`** quick start script:
1. Activates virtual environment
2. Ensures dependencies are installed
3. Starts Flask development server

### 📁 Clean Workspace

- `playwright_captures/` contains extractor outputs
- Temporary/noisy files excluded via `.gitignore`
- `server.log` for background execution logging

## Technical Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     React SPA Frontend                       │
│  ┌──────────┐  ┌──────────────┐  ┌─────────┐               │
│  │ Schedule │  │  Departures  │  │  Admin  │               │
│  └──────────┘  └──────────────┘  └─────────┘               │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTP/JSON
┌─────────────────────────▼───────────────────────────────────┐
│                     Flask Backend                            │
│  ┌──────────────┐  ┌───────────────┐  ┌─────────────────┐  │
│  │  Events API  │  │  Admin Routes │  │ Periodic Import │  │
│  └──────────────┘  └───────────────┘  └─────────────────┘  │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                   Data Layer                                 │
│  ┌────────────────┐  ┌──────────────────────────────────┐  │
│  │ SQLite (app.db)│  │ playwright_captures/events.json  │  │
│  └────────────────┘  └──────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│               Playwright Extractor                           │
│  ┌──────────────────┐  ┌────────────────────────────────┐  │
│  │ Headless Browser │  │ .ics Parser / Microformat      │  │
│  └──────────────────┘  └────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Playwright lifecycle errors | Run extractor manually: `python tools/extract_published_events.py` and check `*.stderr.txt` |
| DB migration fails | Check `data/app.db` permissions and legacy JSON in `config/` |
| Import hangs | Check network connectivity to calendar URLs |
| Events not appearing | Verify `playwright_captures/events.json` contains data |

---

## Planned Features / Roadmap

### 🔐 Password-Protected Admin Access

- Restrict Admin panel behind authentication
- Flask sessions with secure password hash
- Optional multi-user with roles (admin, professor)
- Implementation: `users` table + Flask-Login + login_required decorator

### ☁️ Hosted Central Server + Sync

- Central hosted server with canonical database
- Local DB copies on devices for offline resilience
- Real-time sync via WebSocket push
- Options:
  - REST API + WebSocket channel
  - CouchDB/PouchDB for offline-first sync
  - Redis pub/sub for scaling

### 👨‍🏫 Professor-Specific Views

- Restricted capabilities compared to Admin
- View-only or event suggestion features
- Personal schedule filtering

---

**Last Updated**: January 2026
