# AC UTCN — Room Timetable Viewer# AC UTCN — Timetable Viewer



A production-grade Flask + React application that imports events from **Outlook published calendar** feeds (ICS + HTML), normalises room/subject data, and serves a modern timetable UI. Built for the Technical University of Cluj-Napoca (UTCN), Faculty of Automation and Computer Science.A modern Flask + React application for viewing and managing university timetables. Imports events from Outlook "published calendar" URLs, normalizes subjects/locations, and provides a modern single-page application (SPA) interface with schedule, departures board, and admin functionality.



---## 🎯 Table of Contents

- [Overview](#overview)

## Table of Contents- [Features](#features)

- [Tech Stack](#tech-stack)

- [Overview](#overview)- [Project Structure](#project-structure)

- [Features](#features)- [Requirements](#requirements)

- [Architecture](#architecture)- [Quick Start](#quick-start)

- [Tech Stack](#tech-stack)- [Running the App](#running-the-app)


├── app.py                          # Flask backend — routes, API, background tasks# Set admin password (optional)


├── deploy.sh                       # One-command VM deployment script**Updating the app without losing data:**
├── data/docker compose build --no-cache


### Event Management
| `GUNICORN_MAX_REQUESTS` | `2000` | Max requests before worker restart || Table | Description |

<!--
  Clean, condensed README for the AC UTCN Timetable Viewer.
  Replaces older/duplicated READMEs with a single authoritative document.
-->

# AC UTCN — Room Timetable Viewer

A production-grade Flask + React application that imports events from
Outlook "published calendar" feeds (ICS + HTML), normalizes room/subject
data, and serves a modern timetable UI. Built for the Technical
University of Cluj-Napoca (UTCN), Faculty of Automation and Computer
Science.

---

## Table of contents

- Overview
- Features
- Architecture
- Tech stack
- Project structure
- Quick start
  - Docker (production)
  - VM deployment
  - Local development
- Configuration
  - Environment variables
  - CSV calendar source
  - Room & building aliases
- Extraction pipeline
- API reference
  - Public endpoints
  - Admin endpoints
- Admin panel
- Frontend development
- Data storage
- Deployment operations
- Troubleshooting
- License

---

## Overview

The system ingests room calendars published by Outlook/Exchange (≈200
rooms), parses ICS feeds or scrapes HTML calendar pages with Playwright,
and exposes the merged timetable through a React SPA with three views:

| View | Purpose |
|------|---------|
| Schedule | Weekly timetable grid (filterable by room/subject/professor) |
| Departures | Departure-board style view for today/tomorrow (lobby displays) |
| Admin | Manage calendars, run imports, add manual/extracurricular events |

---

## Features

- Dual-URL pipeline: ICS feed (fast, concurrent) with HTML/Playwright fallback
- Bulk CSV upload (`Rooms_PUBLISHER_HTML-ICS(in).csv`) to populate calendars
- React SPA frontend (Vite) with Schedule, Departures and Admin
- Admin authentication, CSRF protection and per-IP rate limiting
- Per-calendar color assignment
- Periodic background importer (default: every 60 minutes)
- Daily cleanup and retention (default: 60 days)
- Title parsing & subject normalization (subject/professor/room)
- Room and building aliasing via JSON config files
- Playwright extractor for client-side rendered calendar pages
- WAL-mode SQLite for robust concurrent access

---

## Architecture (high level)

The core components:

- Flask backend (REST API, admin routes, background threads)
- React frontend (Vite) — SPA used by end users and admins
- Extraction pipeline (`tools/*`) that writes per-calendar JSON files
- `playwright_captures/` directory that stores per-calendar outputs and
  the merged schedule

Extraction flow summary:

1. CSV → DB: populate calendars and store both ICS (primary) and HTML
   fallback URLs
2. Phase 1 — ICS direct: parse ICS feeds concurrently (fast)
   - Empty VCALENDAR (no events) is considered success and does not fall
     back to Playwright
3. Phase 2 — Playwright fallback: render the HTML URL when ICS fails
4. Phase 3 — Merge: `build_schedule_by_room.py` builds `schedule_by_room.json`

---

## Tech stack

- Backend: Python 3.12, Flask, Gunicorn (gthread)
- Frontend: React 18, Vite
- Database: SQLite (WAL)
- Scraping: Playwright (headless Chromium)
- Calendar parsing: `ics` library + custom parsers
- Container: Docker (multi-stage build: Node + Python)

---

## Project structure (important files)

```
app.py                      # Flask backend (API + routes)
timetable.py                # Calendar parsing utilities
requirements.txt            # Python dependencies
Dockerfile
docker-compose.yml
entrypoint.sh
deploy.sh
frontend/                   # React SPA
tools/                      # Extraction and utility scripts
config/                     # CSV + alias mappings
data/                       # data/app.db (SQLite)
playwright_captures/        # Extractor outputs (git-ignored)
```

---

## Quick start

### Docker (recommended)

```bash
git clone https://github.com/stefi19/GenerateTimetableFromOutlookCalendar.git
cd GenerateTimetableFromOutlookCalendar
# (optional) create .env with ADMIN_PASSWORD and FLASK_SECRET
docker compose up -d --build
docker compose logs -f timetable
```

App is available at `http://localhost:5000`.

### VM deployment

Use `deploy.sh` for a one-command deploy and safe rolling updates.

### Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
python app.py  # backend
cd frontend
npm install
npm run dev    # frontend HMR
```

---

## Configuration

Key environment variables (set in `.env` or Docker compose):

- `ADMIN_PASSWORD` — admin password (change in production)
- `FLASK_SECRET` — Flask session secret
- `GUNICORN_WORKERS`, `GUNICORN_THREADS`, `GUNICORN_WORKER_CLASS` — Gunicorn tuning
- `SQLITE_WAL_MODE` — enable WAL mode for SQLite
- `PLAYWRIGHT_CONCURRENCY` / `ICS_CONCURRENCY` — extraction concurrency
- `DISABLE_BACKGROUND_TASKS` — set `1` to disable periodic importer

CSV format: `config/Rooms_PUBLISHER_HTML-ICS(in).csv` — columns include
`Nume_Sala`, `Email_Sala`, `Cladire`, `PublishedCalendarUrl` (HTML),
`PublishedICalUrl` (ICS). The CSV is authoritative and is used to populate
the calendars table.

---

## Extraction pipeline (details)

- Phase 1: Try `parse_ics_from_url()` concurrently (fast path). Events are
  filtered to ±60 days and written to `playwright_captures/events_<hash>.json`.
- If the feed is an empty VCALENDAR (0 events), the run is considered
  successful and no Playwright fallback is queued.
- Phase 2: Playwright fallback renders the HTML URL (from CSV) and
  captures XHR responses to extract calendar items.
- Phase 3: `build_schedule_by_room.py` merges per-calendar files into
  `schedule_by_room.json` which the frontend consumes.

---

## API reference (high level)

- `GET /` → SPA
- `GET /health` → health check
- `GET /events.json` → merged events (supports `from`, `to`, `room`, `subject` filters)
- `GET /calendars.json` → configured calendars
- Admin endpoints require authentication and are exposed under `/admin`.

Refer to the in-repo admin UI for exact operations (upload CSV, import,
add manual events, delete calendars).

---

## Admin panel

Accessible at `/admin`. Features include bulk CSV upload, manual event
creation, import controls, and calendar metadata editing (name, color,
enabled toggles).

Security: session-based auth, CSRF protection, per-IP authentication
rate limiting.

---

## Troubleshooting (quick)

- If the UI shows 0 events: visit `/debug/pipeline` to inspect per-calendar
  file counts and schedule state.
- If Playwright crashes (SIGSEGV) on your host, either use the provided
  Docker image (includes system deps) or install platform-specific
  libraries (`libnss3`, `libatk1.0-0`, etc.).
- If you see `too many open files`, increase `ulimit -n` or run inside
  container which sets a higher limit in `entrypoint.sh`.

---

## Data & backups

- Database: `data/app.db` (SQLite). Persisted in Docker volume `timetable_data`.
- Extracted files: `playwright_captures/` (persisted in `timetable_captures`).

Backup example:

```bash
docker run --rm -v timetable_data:/data -v $(pwd):/backup alpine \
  tar czf /backup/data-backup.tar.gz -C /data .
```

---

## License

MIT

---

If you'd like, I can also: add a concise `CONTRIBUTING.md`, generate a
clean `.gitignore`, or create a short `README_ADMIN.md` for the admin
user workflows. Which would you prefer next?
| Column | Index | Description || `schedule_by_room.csv` | CSV export of room schedule |

|--------|-------|-------------|| `calendar_full.ics` | Raw downloaded ICS file |

| Nume_Sala | 0 | Room name || `events_<hash>.json` | Per-calendar extracted events |

| Email_Sala | 1 | Room publisher email (used to generate display name) |

| Cladire | 2 | Building name |## Periodic Importer

| Optiune_Delegat | 3 | Delegation option |

| PublishedCalendarUrl | 4 | HTML calendar URL (Playwright fallback) |The app includes a background thread that automatically imports calendars:

| PublishedICalUrl | 5 | ICS feed URL (primary, fast-path) |

- **Initial Run**: Immediately on app startup

Upload via the Admin panel or place in `config/` before starting the container.- **Interval**: Every 60 minutes (configurable in `app.py`)

- **Concurrency**: Uses internal lock to prevent overlapping runs

### Room & Building Aliases

To disable automatic imports, comment out the `periodic_fetcher` thread in `app.py`.

- **`config/room_aliases.json`** — Maps raw room strings to normalised names

- **`config/building_aliases.json`** — Maps raw building names to canonical forms## Troubleshooting



---### Common Issues



## Extraction Pipeline| Issue | Solution |

|-------|----------|

The pipeline runs on container start (detached) and repeats via `periodic_fetcher` every 60 minutes:| `ModuleNotFoundError: No module named 'flask'` | Activate venv: `source .venv/bin/activate && pip install -r requirements.txt` |

| Port 5000 already in use | Kill existing process: `kill $(lsof -ti:5000)` |

1. **CSV → DB** — `populate_calendars_from_csv.py` inserts all URLs from the CSV into SQLite, storing both the ICS URL (primary) and HTML URL (Playwright fallback)| Playwright fails to launch | Install browsers: `python -m playwright install chromium` |

| DB migration errors | Check `data/app.db` permissions and legacy JSON files in `config/` |

2. **Phase 1 — ICS Direct** (concurrent, 8 workers)

   - Fetches each ICS URL via HTTP, parses with the `ics` library### Logs

   - Filters events to a ±60-day window

   - Writes `events_<sha1(url)[:8]>.json` per calendar- Development: Logs appear on stdout

   - Empty VCALENDAR (no bookings) = success — writes `[]`, does **not** fall through to Playwright- Background mode: Check `server.log` with `tail -f server.log`



3. **Phase 2 — Playwright Fallback** (concurrent, 4 workers)### Warnings (Harmless)

   - Only for calendars where ICS parsing failed (network error, not an ICS URL)

   - Launches headless Chromium against the **HTML URL** (not the ICS URL)- `DeprecationWarning: datetime.utcnow()` — Legacy datetime usage, doesn't affect functionality

   - Intercepts XHR responses containing `CalendarItem` JSON- `WARNING: This is a development server` — Normal Flask development mode warning

   - Writes `events_<hash>.json`

## Recommended .gitignore

4. **Phase 3 — Schedule Build**

   - `build_schedule_by_room.py` reads all `events_*.json` files```gitignore

   - Produces `schedule_by_room.json` (served by the API) and `.csv` export# Virtual environment

.venv/

5. **Fingerprint-based Cache**venv/

   - `ensure_schedule()` tracks the max mtime + count of `events_*.json` files

   - Skips rebuild when data hasn't changed# Python cache

   - Cross-process file lock prevents concurrent rebuilds across Gunicorn workers__pycache__/



---# Playwright temporary files

playwright_captures/*.stdout.txt

## API Referenceplaywright_captures/*.stderr.txt

playwright_captures/page*.html

### Public Endpointsplaywright_captures/json_capture_*.json



| Method | Endpoint | Description |# Runtime files

|--------|----------|-------------|server.log

| `GET` | `/` | React SPA frontend |data/app.db

| `GET` | `/health` | Health check (`200 OK`) |```

| `GET` | `/events.json` | Events API (main data endpoint) |

| `GET` | `/calendars.json` | List of configured calendars |## Contributing

| `GET` | `/departures.json` | Departures board data |

| `GET` | `/departures` | Legacy departures HTML view |### Adding New Parsers

| `GET` | `/export_room` | Export room schedule as ICS |

| `GET` | `/debug/pipeline` | Pipeline diagnostic (no auth) |1. Edit `tools/subject_parser.py` for subject/location normalization

| `GET` | `/download/<filename>` | Download generated files |2. Add building mappings in `config/room_aliases.json`



#### `GET /events.json`### Running the Extractor Manually



Returns a JSON array of events for the schedule view.```bash

python tools/extract_published_events.py <URL>

| Parameter | Type | Default | Description |```

|-----------|------|---------|-------------|

| `from` | `YYYY-MM-DD` | today − 7d | Start of date range |Check output in `playwright_captures/*.stderr.txt` for debugging.

| `to` | `YYYY-MM-DD` | today + 7d | End of date range |

| `subject` | string | — | Filter by subject |### Frontend Development

| `professor` | string | — | Filter by professor |

| `room` | string | — | Filter by room |```bash

| `building` | string | — | Filter by building |cd frontend

npm install

### Admin Endpointsnpm run dev

```

All admin endpoints require authentication (session or Basic auth).

The Vite dev server runs at `http://localhost:5173` with hot reload.

| Method | Endpoint | Description |

|--------|----------|-------------|---

| `GET` | `/admin` | Admin panel (React UI) |

| `GET/POST` | `/admin/login` | Login form / authenticate |## Docker Deployment

| `POST` | `/admin/logout` | End admin session |

| `GET` | `/admin/api/status` | Full system status JSON |### Quick Deploy

| `GET` | `/admin/session_status` | Session time remaining |

| `POST` | `/admin/extend_session` | Reset session timeout |```bash

| `POST` | `/admin/upload_rooms_publisher` | Upload CSV calendar list |# Build and start

| `POST` | `/admin/import_calendar` | Trigger extraction |docker compose up -d

| `POST` | `/admin/set_calendar_url` | Add a single calendar |

| `POST` | `/admin/update_calendar` | Update calendar metadata |# Check status

| `POST` | `/admin/update_calendar_color` | Set calendar color |docker compose ps

| `POST` | `/admin/delete_calendar` | Remove a calendar |

| `POST` | `/admin/add_event` | Add manual event |# View logs

| `POST` | `/admin/delete_event` | Delete an event |docker compose logs -f timetable

| `POST` | `/admin/delete_manual` | Delete manual event |

| `POST` | `/admin/cleanup_old_events` | Prune events older than 60 days |# Stop

docker compose down

---```



## Admin Panel### Production Deployment



Access at **http://localhost:5000/admin** (login required).1. **Set environment variables:**



| Feature | Description |```bash

|---------|-------------|# Create .env file

| **Upload CSV** | Bulk-import all room calendars from the publisher CSV |echo "FLASK_SECRET=$(openssl rand -hex 32)" > .env

| **Import Now** | Trigger immediate full extraction for all calendars |```

| **Add Calendar** | Add a single calendar URL with optional name + color |

| **Manage Calendars** | View all calendars with status, toggle enabled, set color, delete |2. **Deploy with Docker Compose:**

| **Manual Events** | Create one-off events with title, time, location |

| **Extracurricular Events** | Add recurring activities (clubs, sports, etc.) |```bash

| **System Status** | View extraction progress, event counts, last import time |docker compose up -d --build

```

Authentication features:

- Session-based with configurable timeout (default 1 hour)3. **With reverse proxy (nginx):**

- CSRF token protection on forms

- Per-IP rate limiting (10 failed attempts / 5 minutes = temporary block)```nginx

- Session extension via "Keep me logged in" actionserver {

    listen 80;

---    server_name timetable.example.com;



## Frontend Development    location / {

        proxy_pass http://localhost:5000;

The React SPA lives in `frontend/` and uses Vite for builds.        proxy_set_header Host $host;

        proxy_set_header X-Real-IP $remote_addr;

```bash        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

cd frontend        proxy_set_header X-Forwarded-Proto $scheme;

npm install    }

npm run dev      # Dev server with HMR at http://localhost:5173}

npm run build    # Production build → frontend/dist/```

```

### Docker Commands Reference

The Vite config proxies API calls (`/events.json`, `/admin/*`, etc.) to `http://localhost:5000` during development.

| Command | Description |

Components:|---------|-------------|

| `docker compose up -d` | Start in background |

| Component | File | Description || `docker compose down` | Stop and remove containers |

|-----------|------|-------------|| `docker compose logs -f` | Follow logs |

| `App` | `App.jsx` | Root — tab navigation, live clock, UTCN header || `docker compose restart` | Restart service |

| `Schedule` | `Schedule.jsx` | Weekly timetable with day grouping + event cards || `docker compose build --no-cache` | Rebuild from scratch |

| `Departures` | `Departures.jsx` | Departure board for lobby screens || `docker compose exec timetable bash` | Shell into container |

| `Admin` | `Admin.jsx` | Calendar management, import controls, event CRUD |

| `RouteMap` | `RouteMap.jsx` | Campus route / map view |### Volumes



---Data is persisted in Docker volumes:

- `timetable_data` — SQLite database

## Data Storage- `timetable_captures` — Playwright captures/events



### SQLite Database — `data/app.db````bash

# Backup data

| Table | Key Columns |docker compose exec timetable cat /app/data/app.db > backup.db

|-------|-------------|

| `calendars` | `id`, `url` (unique), `name`, `color`, `enabled`, `building`, `room`, `email_address`, `html_url`, `created_at`, `last_fetched` |# View volume location

| `manual_events` | `id`, `start`, `end`, `title`, `location`, `raw`, `created_at` |docker volume inspect utcn-timetable_timetable_data

| `extracurricular_events` | `id`, `title`, `organizer`, `date`, `time`, `location`, `category`, `description`, `created_at` |```



The schema auto-migrates on startup — new columns are added via `ALTER TABLE` with try/except so old databases are upgraded seamlessly.### Resource Requirements



### File-Based Event Storage — `playwright_captures/`| Resource | Minimum | Recommended |

|----------|---------|-------------|

| File | Description || CPU | 1 core | 2 cores |

|------|-------------|| RAM | 512MB | 2GB |

| `events_<hash>.json` | Per-calendar events (hash = `sha1(url)[:8]`) || Disk | 1GB | 5GB |

| `schedule_by_room.json` | Merged schedule served by `/events.json` |

| `schedule_by_room.csv` | CSV export of room schedule |*Note: Playwright/Chromium requires ~500MB RAM when running extractions.*

| `calendar_map.json` | Hash → URL/name/color/building mapping |

| `import_progress.json` | Live extraction progress counters |---

| `import_complete.txt` | Written atomically when extraction finishes |

## License

---

MIT

## Deployment Operations

---

### Docker Commands

**Built for**: Technical University of Cluj-Napoca (UTCN)  

| Command | Description |**Faculty**: Automation and Computer Science

|---------|-------------|
| `docker compose up -d --build` | Build and start |
| `docker compose down` | Stop (preserves volumes) |
| `docker compose logs -f timetable` | Follow logs |
| `docker compose restart` | Restart service |
| `docker compose build --no-cache` | Full rebuild |
| `docker compose exec timetable bash` | Shell into container |

### One-Command Redeploy

```bash
./deploy.sh
```

Flags (export before running):

| Flag | Default | Description |
|------|---------|-------------|
| `RUN_FULL_EXTRACTION` | `false` | Run Playwright extraction during deploy |
| `DO_PRUNE` | `false` | Prune unused Docker images |
| `INSTALL_SYSTEMD_TIMER` | `false` | Install hourly import systemd timer |
| `WAIT_FOR_HEALTH` | `true` | Wait for `/health` to return 200 |

### Manual Extraction

```bash
# Inside the container
docker compose exec timetable python3 tools/run_full_extraction.py

# Or a single calendar
docker compose exec timetable python3 tools/extract_published_events.py <URL>
```

### Resource Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 cores | 16 cores |
| RAM | 2 GB | 32 GB |
| Disk | 2 GB | 10 GB |

> Playwright/Chromium uses ~300–500 MB RAM per browser instance. With `PLAYWRIGHT_CONCURRENCY=6`, peak extraction memory is ~3 GB.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **0 events in UI** | Check `/debug/pipeline` — verify `events_files_non_empty > 0` and `schedule_rooms > 0` |
| **All `events_*.json` are 2 bytes** | ICS feeds may be returning empty VCALENDARs — normal for rooms with no bookings |
| **Playwright SIGSEGV** | Install system deps (`libnss3`, `libatk1.0-0`, etc.) or use the Docker image which includes them |
| **Port 5000 in use** | `lsof -i:5000` and kill the process, or set `HOST_PORT=8080` in `.env` |
| **`ModuleNotFoundError`** | Activate the venv: `source .venv/bin/activate && pip install -r requirements.txt` |
| **EMFILE (too many open files)** | Container sets `ulimit -n 65536`; if running locally, increase with `ulimit -n 65536` |
| **DB locked errors** | Enable WAL mode: `export SQLITE_WAL_MODE=1` |
| **Stale schedule** | `rm playwright_captures/schedule_by_room.json` and hit `/events.json` to trigger rebuild |
| **Import stuck** | Check `playwright_captures/extract_stderr.txt` for errors |

### Logs

```bash
# Docker
docker compose logs -f timetable

# Local development — stdout
python app.py

# Background mode
nohup python app.py > server.log 2>&1 &
tail -f server.log
```

### Diagnostic Endpoints

- **`GET /health`** — Returns `200 OK` if the app is running
- **`GET /debug/pipeline`** — Shows event file counts, schedule state, fingerprint info, and extraction status (no auth required)

---

## License

MIT

---

**Built for**: Technical University of Cluj-Napoca (UTCN), Faculty of Automation and Computer Science
