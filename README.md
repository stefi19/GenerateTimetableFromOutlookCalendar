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

- [Project Structure](#project-structure)- [Frontend (React SPA)](#frontend-react-spa)

- [Quick Start](#quick-start)- [Backend API](#backend-api)

  - [Docker (Production)](#docker-production)- [Admin UI](#admin-ui)

  - [VM Deployment](#vm-deployment)- [Storage](#storage)

  - [Local Development](#local-development)- [Periodic Importer](#periodic-importer)

- [Configuration](#configuration)- [Troubleshooting](#troubleshooting)

  - [Environment Variables](#environment-variables)- [Contributing](#contributing)

  - [CSV Calendar Source](#csv-calendar-source)

  - [Room & Building Aliases](#room--building-aliases)## Overview

- [Extraction Pipeline](#extraction-pipeline)

- [API Reference](#api-reference)This project is a complete timetable management system for the Technical University of Cluj-Napoca (UTCN), Faculty of Automation and Computer Science. It:

  - [Public Endpoints](#public-endpoints)

  - [Admin Endpoints](#admin-endpoints)- Extracts events from published Outlook calendar pages (or uploaded `.ics` files)

- [Admin Panel](#admin-panel)- Applies subject/location normalization for consistent display

- [Frontend Development](#frontend-development)- Persists configured calendar URLs and user-added events in a local SQLite database

- [Data Storage](#data-storage)- Provides a **modern React SPA frontend** with:

- [Deployment Operations](#deployment-operations)  - 📅 **Schedule View** — full weekly timetable with filtering

- [Troubleshooting](#troubleshooting)  - 🚀 **Departures View** — departure-board style display for today/tomorrow

- [License](#license)  - ⚙️ **Admin Panel** — manage calendars, events, and imports

- Includes Playwright-based tools for extracting calendars from client-side rendered pages

---

## Features

## Overview

### ✅ Implemented Features

The system ingests room calendars published by Outlook/Exchange (≈200 rooms), parses ICS feeds or scrapes HTML calendar pages with Playwright, and exposes the merged timetable through a React SPA with three views:

| Feature | Description |

| View | Description ||---------|-------------|

|------|-------------|| **React SPA Frontend** | Modern single-page application with tabbed navigation (Schedule, Departures, Admin) |

| **Schedule** | Weekly timetable grid grouped by day, filterable by room/subject/professor || **Live Clock Display** | Real-time clock in header showing current date and time |

| **Departures** | Airport-style departure board for lobby displays — shows today + tomorrow || **Schedule View** | Full timetable view with day grouping and event cards |

| **Admin** | Password-protected panel to upload CSVs, manage calendars, trigger imports || **Departures Board** | Departure-board style view for today/tomorrow, ideal for large displays |

| **Admin Panel** | Add/manage calendar URLs, trigger imports, manage manual & extracurricular events |

---| **SQLite Persistence** | All calendars, manual events, and extracurricular events stored in `data/app.db` |

| **Playwright Extractor** | Render client-side pages and extract `.ics` links automatically |

## Features| **Subject Normalization** | Parse event titles into subject, professor, and room components |

| **Events API** | REST endpoint `/events.json` with filtering support |

| Category | Feature || **Periodic Auto-Import** | Background thread imports calendars every 60 minutes |

|----------|---------|| **Per-Calendar Colors** | Optional color assignment for each calendar source |

| **Calendar Import** | Dual-URL pipeline — ICS feed (fast, concurrent) with HTML/Playwright fallback || **Legacy Migration** | Automatic migration from JSON config files to SQLite |

| **Bulk CSV Upload** | Upload `Rooms_PUBLISHER_HTML-ICS(in).csv` to populate all room calendars at once |

| **React SPA** | Schedule, Departures board, and Admin views with live clock and UTCN branding |### 🗓️ Planned Features

| **Admin Auth** | Password-protected admin with session management, CSRF protection, rate limiting |

| **Per-Calendar Colors** | Optional hex color per calendar source for visual differentiation |- Password-protected Admin access

| **Periodic Auto-Import** | Background thread re-fetches all calendars every 60 minutes |- Professor-specific views with restricted capabilities

| **Daily Cleanup** | Automatic pruning of events older than 60 days |- Central hosted server with real-time sync to multiple devices

| **Subject Normalisation** | Parses titles into subject + professor + room components |- Offline-first local DB with WebSocket push updates

| **Room/Building Aliases** | JSON-based mappings for consistent room and building names |

| **ICS Export** | Export per-room schedules as `.ics` files |## Tech Stack

| **Health Check** | `GET /health` endpoint for Docker/load-balancer probes |

| **Debug Pipeline** | `GET /debug/pipeline` diagnostic endpoint (no auth) || Layer | Technology |

| **SQLite + WAL** | WAL-mode SQLite with file-locking for concurrent Gunicorn workers ||-------|------------|

| **Performance Tuned** | Optimised for 32 GB RAM / 16 vCPU — 8 Gunicorn workers × 4 threads || **Backend** | Python 3.10+, Flask, Gunicorn |

| **Manual Events** | Admin can add one-off events directly || **Frontend** | React 18, Vite |

| **Extracurricular Events** | Manage recurring activities (clubs, sports) shown alongside timetable || **Database** | SQLite (`data/app.db`) |

| **Calendar Parsing** | `ics` library, custom microformat parser |

---| **Web Scraping** | Playwright (for client-side rendered pages) |

| **Styling** | Custom CSS with modern design |

## Architecture| **Containerization** | Docker, Docker Compose |



```## Project Structure

┌─────────────────────────────────────────────────────────────────┐

│                      React SPA (Vite)                           │```

│   ┌───────────┐   ┌──────────────┐   ┌──────────┐              │├── app.py                    # Flask backend (API + routes)

│   │ Schedule  │   │  Departures  │   │  Admin   │              │├── timetable.py              # Calendar parsing utilities

│   └───────────┘   └──────────────┘   └──────────┘              │├── requirements.txt          # Python dependencies

└───────────────────────────┬─────────────────────────────────────┘├── Dockerfile                # Docker image build

                            │ /events.json, /calendars.json, ...├── docker-compose.yml        # Docker Compose config

┌───────────────────────────▼─────────────────────────────────────┐├── run.sh                    # Quick start script

│                    Flask + Gunicorn                              │├── setup.sh                  # Full setup script

│   ┌────────────┐  ┌───────────────┐  ┌──────────────────────┐  │├── config/

│   │ Events API │  │ Admin Routes  │  │ Background Tasks     │  ││   └── room_aliases.json     # Room name mappings

│   │            │  │ (auth-gated)  │  │ • periodic_fetcher   │  │├── data/

│   │            │  │               │  │ • daily_cleanup       │  ││   └── app.db                # SQLite database (created on first run)

│   └────────────┘  └───────────────┘  └──────────────────────┘  │├── frontend/                 # React SPA

└───────────────────────────┬─────────────────────────────────────┘│   ├── src/

                            ││   │   ├── App.jsx           # Main app component with tabs

┌───────────────────────────▼─────────────────────────────────────┐│   │   ├── Schedule.jsx      # Schedule view

│                     Data Layer                                   ││   │   ├── Departures.jsx    # Departures board view

│   ┌────────────────┐  ┌─────────────────────────────────────┐   ││   │   ├── Admin.jsx         # Admin panel

│   │ SQLite (WAL)   │  │ playwright_captures/                │   ││   │   ├── styles.css        # Application styles

│   │ data/app.db    │  │   events_<hash>.json  (per-room)    │   ││   │   └── main.jsx          # Entry point

│   │                │  │   schedule_by_room.json (merged)    │   ││   ├── package.json

│   │                │  │   calendar_map.json                 │   ││   └── vite.config.js

│   └────────────────┘  └─────────────────────────────────────┘   │├── playwright_captures/      # Extractor output files

└───────────────────────────┬─────────────────────────────────────┘│   ├── events.json           # Merged events for UI

                            ││   └── schedule_by_room.json # Room-based schedule

┌───────────────────────────▼─────────────────────────────────────┐├── templates/                # Jinja2 templates (legacy + fallback)

│                  Extraction Pipeline                             │├── tools/                    # CLI utilities

│                                                                  ││   ├── extract_published_events.py

│   Phase 1: ICS-direct (ThreadPoolExecutor, 8 workers)           ││   ├── build_schedule_by_room.py

│   ┌──────────────────────────────────────────────────────┐      ││   └── subject_parser.py

│   │  parse_ics_from_url() → events_<sha1[:8]>.json      │      │└── static/                   # Static assets

│   │  Empty VCALENDAR = success (room has no bookings)    │      │```

│   └──────────────────────────────────────────────────────┘      │

│                         │ failures only                          │## Requirements

│   Phase 2: Playwright fallback (4 workers)                      │

│   ┌──────────────────────────────────────────────────────┐      │- **Python**: 3.10+ (tested with 3.14)

│   │  extract_published_events.py → headless Chromium     │      │- **Node.js**: 18+ (for frontend development)

│   │  Uses html_url from CSV (not the ICS URL)            │      │- **Docker**: 20+ (for containerized deployment)

│   └──────────────────────────────────────────────────────┘      │- **System**: macOS / Linux (Playwright requires extra setup on some systems)

│                         │                                        │

│   Phase 3: build_schedule_by_room.py                            │## Quick Start

│   ┌──────────────────────────────────────────────────────┐      │

│   │  Merge all events_*.json → schedule_by_room.json     │      │### Option 1: Docker (Recommended for Production)

│   └──────────────────────────────────────────────────────┘      │

└──────────────────────────────────────────────────────────────────┘```bash

```# Build and run with Docker Compose

docker compose up -d

---

# View logs

## Tech Stackdocker compose logs -f



| Layer | Technology |# Stop

|-------|------------|docker compose down

| **Runtime** | Python 3.12, Flask, Gunicorn (gthread) |```

| **Frontend** | React 18, Vite, custom CSS |

| **Database** | SQLite 3 (WAL mode) |The app will be available at **http://localhost:5000**

| **Calendar Parsing** | `ics` library + custom microformat parser |

| **Web Scraping** | Playwright (headless Chromium) |### Option 2: VM Deployment (Production Server)

| **Container** | Docker multi-stage build (Node 20 + Python 3.12-slim-bookworm) |

| **Orchestration** | Docker Compose with health checks |For deploying on a VM with persistent data that survives code updates:



---```bash

# First time setup on VM

## Project Structuregit clone https://github.com/stefi19/GenerateTimetableFromOutlookCalendar.git

cd GenerateTimetableFromOutlookCalendar

```

├── app.py                          # Flask backend — routes, API, background tasks# Set admin password (optional)

├── timetable.py                    # ICS parsing, event model, fetch utilitiesecho "ADMIN_PASSWORD=your-secure-password" > .env

├── requirements.txt                # Python dependencies

├── Dockerfile                      # Multi-stage build (frontend + backend)# Start the app

├── docker-compose.yml              # Production compose with perf tuningdocker compose up -d --build

├── docker-compose.local.yml        # Local development overrides```

├── entrypoint.sh                   # Container entrypoint (DB setup, extraction, Gunicorn)

├── deploy.sh                       # One-command VM deployment script**Updating the app without losing data:**

├── run.sh                          # Local development start script

├── setup.sh                        # First-time local setup (venv, deps, Playwright)```bash

│# Pull latest code and rebuild

├── config/./deploy.sh

│   ├── Rooms_PUBLISHER_HTML-ICS(in).csv   # Authoritative room calendar list

│   ├── room_aliases.json                  # Room name normalisations# Or manually:

│   └── building_aliases.json              # Building name mappingsgit pull origin main

│docker compose down

├── data/docker compose build --no-cache

│   └── app.db                      # SQLite database (created at runtime)docker compose up -d

│```

├── frontend/                       # React SPA (Vite)

│   ├── package.json**Data persistence:** User data (calendars, events) is stored in Docker volumes:

│   ├── vite.config.js- `timetable_data` — SQLite database with calendars and manual events

│   └── src/- `timetable_captures` — Extracted calendar events

│       ├── main.jsx                # Entry point

│       ├── App.jsx                 # Root component with tab navigationThese volumes persist across container rebuilds. To backup:

│       ├── Schedule.jsx            # Weekly timetable view

│       ├── Departures.jsx          # Departure board view```bash

│       ├── Admin.jsx               # Admin panel# Backup data

│       ├── RouteMap.jsx            # Route / campus mapdocker run --rm -v timetable_data:/data -v $(pwd):/backup alpine tar czf /backup/data-backup.tar.gz -C /data .

│       └── styles.css              # Application styles

│# Restore data

├── tools/                          # CLI utilities & pipeline scriptsdocker run --rm -v timetable_data:/data -v $(pwd):/backup alpine tar xzf /backup/data-backup.tar.gz -C /data

│   ├── run_full_extraction.py      # Orchestrates full ICS + Playwright extraction```

│   ├── build_schedule_by_room.py   # Merges per-room files → schedule_by_room.json

│   ├── extract_published_events.py # Playwright-based HTML calendar scraper### Option 3: Automated Setup (Development)

│   ├── populate_calendars_from_csv.py  # CSV → DB population

│   ├── enforce_csv_full_update.py  # Sync DB metadata from CSV```bash

│   ├── subject_parser.py           # Title → subject + professor parsing# Clone and setup

│   ├── event_parser.py             # Event normalisation utilities./setup.sh

│   ├── init_db.py                  # Standalone DB initialisation

│   ├── worker_update_future.py     # Background worker for incremental updates# Run the app

│   └── ...                         # Additional maintenance/diagnostic tools./run.sh

│```

├── playwright_captures/            # Extraction output (runtime, git-ignored)

│   ├── events_<hash>.json          # Per-calendar events (sha1(url)[:8])### Option 3: Manual Setup

│   ├── schedule_by_room.json       # Merged room schedule (served by API)

│   ├── calendar_map.json           # Hash → URL/name/building mapping```bash

│   ├── import_progress.json        # Live extraction progress# Create virtual environment

│   └── import_complete.txt         # Marker written when extraction finishespython3 -m venv .venv

│source .venv/bin/activate

├── templates/                      # Jinja2 templates (admin login, React shell)

└── static/                         # Static assets# Install Python dependencies

```pip install -r requirements.txt



---# Install Playwright browsers (for calendar extraction)

python -m playwright install chromium

## Quick Start

# Run the app

### Docker (Production)python app.py

```

```bash

# Clone the repository## Running the App

git clone https://github.com/stefi19/GenerateTimetableFromOutlookCalendar.git

cd GenerateTimetableFromOutlookCalendar### Development Mode



# (Optional) Create a .env file with your settings```bash

cat > .env <<EOF# Using the run script (recommended)

ADMIN_PASSWORD=your-secure-password./run.sh

FLASK_SECRET=$(openssl rand -hex 32)

HOST_PORT=5000# Or manually

EOFsource .venv/bin/activate

python app.py

# Build and run```

docker compose up -d --build

The app starts at **http://127.0.0.1:5000** and automatically redirects to the React SPA.

# Check status

docker compose ps### Background Mode

docker compose logs -f timetable

``````bash

# Start in background

The app will be available at **http://localhost:5000**.nohup ./.venv/bin/python app.py > server.log 2>&1 &



### VM Deployment# View logs

tail -f server.log

For a production VM with persistent data:

# Stop the server

```bashkill $(lsof -ti:5000)

# First time```

git clone https://github.com/stefi19/GenerateTimetableFromOutlookCalendar.git

cd GenerateTimetableFromOutlookCalendar## Frontend (React SPA)

echo "ADMIN_PASSWORD=your-secure-password" > .env

docker compose up -d --buildThe frontend is a modern React single-page application accessible at `/app`:



# Subsequent updates (preserves all data)### Navigation Tabs

./deploy.sh

```| Tab | Route | Description |

|-----|-------|-------------|

`deploy.sh` pulls the latest code, rebuilds the image, restarts the container, and waits for health. Docker volumes persist data across rebuilds:| 📅 **Schedule** | `/app` | Weekly timetable with day grouping |

| 🚀 **Departures** | `/app` | Today/tomorrow events for display boards |

| Volume | Contents || ⚙️ **Admin** | `/app` | Manage calendars and events |

|--------|----------|

| `timetable_data` | SQLite database (`data/app.db`) |### Features

| `timetable_captures` | Extracted events, schedules |

| `timetable_config` | CSV and alias configuration |- **Live Clock**: Real-time display of current date and time

| `playwright_user_data` | Playwright browser profile |- **Responsive Design**: Works on desktop and tablet displays

- **Event Cards**: Visual cards showing event details (time, title, location, professor)

**Backup & restore:**- **University Branding**: UTCN themed header and styling



```bash## Backend API

# Backup

docker run --rm -v timetable_data:/data -v $(pwd):/backup alpine \### Main Endpoints

  tar czf /backup/data-backup.tar.gz -C /data .

| Method | Endpoint | Description |

# Restore|--------|----------|-------------|

docker run --rm -v timetable_data:/data -v $(pwd):/backup alpine \| `GET` | `/` | Redirects to SPA |

  tar xzf /backup/data-backup.tar.gz -C /data| `GET` | `/app` | React SPA frontend |

```| `GET` | `/events.json` | Events API with filters |

| `GET` | `/schedule` | Legacy schedule view |

### Local Development| `GET` | `/departures` | Legacy departures view |

| `GET` | `/admin` | Legacy admin view |

```bash| `POST` | `/admin/calendar` | Add calendar URL |

# First-time setup| `POST` | `/admin/import` | Trigger import |

python3 -m venv .venv| `POST` | `/admin/manual-event` | Add manual event |

source .venv/bin/activate

pip install -r requirements.txt### Events API Query Parameters

python -m playwright install chromium

```

# Run the backendGET /events.json?from=2026-01-01&to=2026-01-07&subject=Math&room=A101

python app.py```

# → http://localhost:5000

| Parameter | Description |

# In a separate terminal — frontend dev server with hot reload|-----------|-------------|

cd frontend| `from` | Start date (YYYY-MM-DD) |

npm install| `to` | End date (YYYY-MM-DD) |

npm run dev| `subject` | Filter by subject |

# → http://localhost:5173 (proxies API to Flask)| `professor` | Filter by professor |

```| `room` | Filter by room |



Or use the convenience scripts:## Admin UI



```bashAccess the Admin panel via the ⚙️ Admin tab in the SPA (or `/admin` for legacy view).

./setup.sh   # Full first-time setup

./run.sh     # Start the app### Calendar Management

```

- **Add Calendar URL**: Enter a published Outlook calendar URL with optional name and color

---- **Import Now**: Trigger immediate calendar extraction (runs Playwright in background)

- **Delete Calendar**: Remove a configured calendar from the database

## Configuration

### Event Management

### Environment Variables

- **Manual Events**: Add one-time events directly (persisted in DB)

| Variable | Default | Description |- **Extracurricular Events**: Add recurring activities (clubs, sports, etc.)

|----------|---------|-------------|- **Delete Events**: Remove manual or extracurricular events

| `ADMIN_USERNAME` | `admin` | Admin login username |

| `ADMIN_PASSWORD` | `admin123` | Admin login password (**change in production**) |### Color Coding

| `ADMIN_SESSION_TIMEOUT` | `3600` | Admin session duration (seconds) |

| `FLASK_SECRET` | `dev-secret` | Flask session secret key |Each calendar can have an assigned color displayed as a swatch in the admin list for easy identification.

| `PORT` | `5000` | HTTP listen port |

| `GUNICORN_WORKERS` | `8` | Number of Gunicorn worker processes |## Storage

| `GUNICORN_THREADS` | `4` | Threads per worker |

| `GUNICORN_WORKER_CLASS` | `gthread` | Worker class |### SQLite Database (`data/app.db`)

| `GUNICORN_TIMEOUT` | `180` | Request timeout (seconds) |

| `GUNICORN_MAX_REQUESTS` | `2000` | Max requests before worker restart || Table | Description |

| `SQLITE_WAL_MODE` | `1` | Enable WAL mode for concurrent reads ||-------|-------------|

| `PLAYWRIGHT_CONCURRENCY` | `6` | Max simultaneous Playwright browsers || `calendars` | Configured calendar URLs with name, color, enabled status |

| `ICS_CONCURRENCY` | `8` | Max simultaneous ICS HTTP fetches || `manual_events` | User-added one-time events |

| `DISABLE_BACKGROUND_TASKS` | `0` | Set to `1` to skip periodic fetcher/cleanup || `extracurricular_events` | Recurring extracurricular activities |

| `PLAYWRIGHT_USER_DATA_DIR` | — | Path to persistent Playwright browser profile |

| `APP_PYTHON` | — | Override Python executable path |### Playwright Captures (`playwright_captures/`)



### CSV Calendar Source| File | Description |

|------|-------------|

The authoritative list of room calendars is a CSV file: `config/Rooms_PUBLISHER_HTML-ICS(in).csv`| `events.json` | Merged events from all sources (used by UI) |

| `schedule_by_room.json` | Room-based schedule view |

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
