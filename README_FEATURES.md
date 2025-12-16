# Features — Outlook published calendar timetable viewer

This document lists the current features of the project and short descriptions for each.

## Overview
The app ingests events from Outlook "published calendar" pages (or uploaded .ics feeds),
normalizes subjects and room/location names, persists configured calendars and user-added
events, and exposes a small admin UI and a number of public views (schedule, departures,
events API). It contains tools that use Playwright when client-side rendering is required.

## Features

- Schedule view (`/schedule`)
  - Full timetable view built from imported events and manual/extracurricular events.
  - Filter by subject, professor, and room.
  - Shows a 7-day default range (configurable via query params).

- Departures / Board view (`/departures`)
  - Departure-board style UI showing events for today and tomorrow grouped by building.
  - Includes manual and extracurricular events (persisted in DB).
  - Useful for large display screens (lecture halls/entrances).

- Admin UI (`/admin`)
  - Add / persist Published Calendar URLs.
  - Optional friendly name and color per calendar for UI identification.
  - Trigger an immediate import (extractor runs in background).
  - Add manual events (persisted in DB and appended to `playwright_captures/events.json`).
  - Manage extracurricular events (add/delete) persisted in DB.
  - Delete configured calendars and manual/extracurricular events from the DB.

- Persistence (SQLite DB)
  - `data/app.db` stores configured calendars, manual events and extracurricular events.
  - Migration helpers: legacy JSON config files (from `config/` or `playwright_captures/`) are
    migrated into the DB via `migrate_from_files()`.

- Playwright-backed extractor
  - Uses Playwright to fully render published calendar pages that are client-side rendered
    and extract `.ics` links or network responses.
  - Fallback parsing: if no `.ics` is available, the extractor attempts to parse microformats
    (hCalendar / vevent) and other heuristics.
  - Extracted events are written to `playwright_captures/events.json` and supporting files
    such as `schedule_by_room.json` / `.csv` and `calendar_full.ics`.

- Subject and location normalization
  - A subject parser attempts to normalize event titles into a subject name, display title,
    and professor where possible. This improves UI grouping and filtering.
  - Room/location normalization maps Outlook locations into canonical building/room codes.

- Events API (`/events.json`)
  - Returns a flattened list of events suitable for FullCalendar or other API consumers.
  - Supports `from`, `to`, `subject`, `professor` and `room` query filters.

- Periodic importer / background fetcher
  - Background thread that performs an initial import on startup and repeats every 60
    minutes (configurable by editing `app.py`).
  - Avoids overlapping runs with an internal lock.

- Manual and extracurricular events
  - Manual events (added from Admin) are persisted and appear in `events.json` and UI views.
  - Extracurricular events are stored in DB (or legacy `config/extracurricular_events.json`)
    and are shown in the `Events` UI and departures view.

- UI templates
  - Jinja2 templates for schedule, departures, admin, extracurricular and small JS helpers.
  - Admin UI shows color swatches and uses fetch/XHR endpoints returning JSON for smooth
    button actions (delete/import/etc.).

- Setup automation (`setup.sh`)
  - Script to create `.venv`, install `requirements.txt`, install Playwright browsers, and
    initialize the DB (runs `init_db()` and `migrate_from_files()`).

- Clean workspace & UX helpers
  - `playwright_captures/` contains extractor outputs; noisy temporary capture files are
    ignored via `.gitignore`.
  - `server.log` is used when running the app via `nohup` or background runs.

## Admin / Developer notes

- Playwright: browser downloads are large; `setup.sh` installs them automatically but this
  step can take time and network bandwidth.
- The app is tested with Python 3.10+ (3.14 used during development). Use an isolated venv
  to avoid dependency conflicts.
- Committing a full virtualenv is intentionally avoided — use `setup.sh` to bootstrap the
  environment quickly. If you need a prebuilt environment for offline distribution, consider
  using an archive or release asset.

## Troubleshooting

- If the extractor fails due to Playwright lifecycle or OS dependencies, run the extractor
  manually from `tools/extract_published_events.py` and inspect `playwright_captures/*.stderr.txt`.
- If DB migration fails, check `data/app.db` permissions and any legacy JSON files under `config/`.

---
If you want, I can extend this file with screenshots, example API responses, or a short
architectural diagram showing where Playwright, DB, and templates interact. Tell me which
extras you prefer.

## Planned features / Roadmap

Below are the features you've asked for and suggested approaches to implement them.

- Per-calendar colors (UI)
  - Description: allow each configured calendar to have an independent color swatch that is
    used throughout the UI (schedule, admin lists, compact views) so users can visually
    distinguish events from different sources more easily.
  - Implementation notes: the DB already stores an optional `color` field for calendars —
    ensure the admin UI exposes a color picker when adding/editing a calendar and propagate
    the color into schedule rendering (add CSS variables or inline style attributes).

- Password-protected Admin and Professor access
  - Description: restrict the Admin panel (and optionally special professor-only actions)
    behind an authentication layer (username/password). Professors would have restricted
    capabilities compared to Admin (for example: view-only or event suggestions).
  - Implementation notes: implement a simple authentication system using Flask sessions and
    a secure password hash stored in the DB or environment variable for a single admin user.
    For a multi-user solution, add a `users` table (id, username, password_hash, role,
    created_at) and use Flask-Login (or a lightweight JWT approach) for sessions. Protect
    all `@app.route('/admin')` endpoints with a login_required decorator and add login/logout
    views. Use TLS (HTTPS) in production and rate-limit login attempts.

- Hosted central server + local DB + real-time sync to devices
  - Description: run a central hosted server (cloud or on-prem) that holds the canonical
    data store and serves the web app. Each device running the app keeps a local DB copy
    (SQLite) for offline resilience and receives updates in near-real-time so multiple
    displays/devices stay synchronized.
  - Implementation notes / options:
    - Simple approach: central REST API + WebSocket push
      - Host a central server with the canonical `app.db` and expose REST endpoints for
        calendar management, events, and exports. Devices run the same app but in client
        mode: they fetch data via the API and subscribe to a WebSocket channel for live
        updates (server pushes a small event payload when calendars/events change).
      - Devices maintain a local SQLite cache that is refreshed when updates arrive.
    - Offline-first / syncable DB approach (CouchDB / PouchDB)
      - Use CouchDB on the server and PouchDB in the browser or a lightweight local
        replication client on devices. PouchDB/CouchDB handle replication and conflict
        resolution automatically and are a good fit when full offline writes are required.
    - Two-way sync considerations
      - Implement conflict handling (last-write-wins or explicit merge UI) and provide
        optimistic updates in the UI. Use change feeds (Postgres logical decoding, CouchDB
        _changes, or Redis streams) to broadcast updates.
    - Security & scaling
      - Use HTTPS, authenticate devices (API keys / OAuth2 / JWT), and rate-limit APIs.
      - For many devices, scale the WebSocket layer via a message broker (Redis pub/sub,
        Kafka) and horizontally scaled web nodes.

Each of these features can be staged incrementally (start with per-calendar colors, add
simple password protection, then design the sync topology). Tell me which one you want
me to implement first and I can create a concrete plan and PR for it.
