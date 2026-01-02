# AC UTCN — Timetable Viewer

A modern Flask + React application for viewing and managing university timetables. Imports events from Outlook "published calendar" URLs, normalizes subjects/locations, and provides a modern single-page application (SPA) interface with schedule, departures board, and admin functionality.

## 🎯 Table of Contents
- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [Running the App](#running-the-app)
- [Frontend (React SPA)](#frontend-react-spa)
- [Backend API](#backend-api)
- [Admin UI](#admin-ui)
- [Storage](#storage)
- [Periodic Importer](#periodic-importer)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

## Overview

This project is a complete timetable management system for the Technical University of Cluj-Napoca (UTCN), Faculty of Automation and Computer Science. It:

- Extracts events from published Outlook calendar pages (or uploaded `.ics` files)
- Applies subject/location normalization for consistent display
- Persists configured calendar URLs and user-added events in a local SQLite database
- Provides a **modern React SPA frontend** with:
  - 📅 **Schedule View** — full weekly timetable with filtering
  - 🚀 **Departures View** — departure-board style display for today/tomorrow
  - ⚙️ **Admin Panel** — manage calendars, events, and imports
- Includes Playwright-based tools for extracting calendars from client-side rendered pages

## Features

### ✅ Implemented Features

| Feature | Description |
|---------|-------------|
| **React SPA Frontend** | Modern single-page application with tabbed navigation (Schedule, Departures, Admin) |
| **Live Clock Display** | Real-time clock in header showing current date and time |
| **Schedule View** | Full timetable view with day grouping and event cards |
| **Departures Board** | Departure-board style view for today/tomorrow, ideal for large displays |
| **Admin Panel** | Add/manage calendar URLs, trigger imports, manage manual & extracurricular events |
| **SQLite Persistence** | All calendars, manual events, and extracurricular events stored in `data/app.db` |
| **Playwright Extractor** | Render client-side pages and extract `.ics` links automatically |
| **Subject Normalization** | Parse event titles into subject, professor, and room components |
| **Events API** | REST endpoint `/events.json` with filtering support |
| **Periodic Auto-Import** | Background thread imports calendars every 60 minutes |
| **Per-Calendar Colors** | Optional color assignment for each calendar source |
| **Legacy Migration** | Automatic migration from JSON config files to SQLite |

### 🗓️ Planned Features

- Password-protected Admin access
- Professor-specific views with restricted capabilities
- Central hosted server with real-time sync to multiple devices
- Offline-first local DB with WebSocket push updates

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.10+, Flask |
| **Frontend** | React 18, Vite |
| **Database** | SQLite (`data/app.db`) |
| **Calendar Parsing** | `ics` library, custom microformat parser |
| **Web Scraping** | Playwright (for client-side rendered pages) |
| **Styling** | Custom CSS with modern design |

## Project Structure

```
├── app.py                    # Flask backend (API + routes)
├── timetable.py              # Calendar parsing utilities
├── requirements.txt          # Python dependencies
├── run.sh                    # Quick start script
├── setup.sh                  # Full setup script
├── config/
│   └── room_aliases.json     # Room name mappings
├── data/
│   └── app.db                # SQLite database (created on first run)
├── frontend/                 # React SPA
│   ├── src/
│   │   ├── App.jsx           # Main app component with tabs
│   │   ├── Schedule.jsx      # Schedule view
│   │   ├── Departures.jsx    # Departures board view
│   │   ├── Admin.jsx         # Admin panel
│   │   ├── styles.css        # Application styles
│   │   └── main.jsx          # Entry point
│   ├── package.json
│   └── vite.config.js
├── playwright_captures/      # Extractor output files
│   ├── events.json           # Merged events for UI
│   └── schedule_by_room.json # Room-based schedule
├── templates/                # Jinja2 templates (legacy + fallback)
├── tools/                    # CLI utilities
│   ├── extract_published_events.py
│   ├── build_schedule_by_room.py
│   └── subject_parser.py
└── static/                   # Static assets
```

## Requirements

- **Python**: 3.10+ (tested with 3.14)
- **Node.js**: 18+ (for frontend development)
- **System**: macOS / Linux (Playwright requires extra setup on some systems)

## Quick Start

### Option 1: Automated Setup (Recommended)

```bash
# Clone and setup
./setup.sh

# Run the app
./run.sh
```

### Option 2: Manual Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browsers (for calendar extraction)
python -m playwright install chromium

# Run the app
python app.py
```

## Running the App

### Development Mode

```bash
# Using the run script (recommended)
./run.sh

# Or manually
source .venv/bin/activate
python app.py
```

The app starts at **http://127.0.0.1:5000** and automatically redirects to the React SPA.

### Background Mode

```bash
# Start in background
nohup ./.venv/bin/python app.py > server.log 2>&1 &

# View logs
tail -f server.log

# Stop the server
kill $(lsof -ti:5000)
```

## Frontend (React SPA)

The frontend is a modern React single-page application accessible at `/app`:

### Navigation Tabs

| Tab | Route | Description |
|-----|-------|-------------|
| 📅 **Schedule** | `/app` | Weekly timetable with day grouping |
| 🚀 **Departures** | `/app` | Today/tomorrow events for display boards |
| ⚙️ **Admin** | `/app` | Manage calendars and events |

### Features

- **Live Clock**: Real-time display of current date and time
- **Responsive Design**: Works on desktop and tablet displays
- **Event Cards**: Visual cards showing event details (time, title, location, professor)
- **University Branding**: UTCN themed header and styling

## Backend API

### Main Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Redirects to SPA |
| `GET` | `/app` | React SPA frontend |
| `GET` | `/events.json` | Events API with filters |
| `GET` | `/schedule` | Legacy schedule view |
| `GET` | `/departures` | Legacy departures view |
| `GET` | `/admin` | Legacy admin view |
| `POST` | `/admin/calendar` | Add calendar URL |
| `POST` | `/admin/import` | Trigger import |
| `POST` | `/admin/manual-event` | Add manual event |

### Events API Query Parameters

```
GET /events.json?from=2026-01-01&to=2026-01-07&subject=Math&room=A101
```

| Parameter | Description |
|-----------|-------------|
| `from` | Start date (YYYY-MM-DD) |
| `to` | End date (YYYY-MM-DD) |
| `subject` | Filter by subject |
| `professor` | Filter by professor |
| `room` | Filter by room |

## Admin UI

Access the Admin panel via the ⚙️ Admin tab in the SPA (or `/admin` for legacy view).

### Calendar Management

- **Add Calendar URL**: Enter a published Outlook calendar URL with optional name and color
- **Import Now**: Trigger immediate calendar extraction (runs Playwright in background)
- **Delete Calendar**: Remove a configured calendar from the database

### Event Management

- **Manual Events**: Add one-time events directly (persisted in DB)
- **Extracurricular Events**: Add recurring activities (clubs, sports, etc.)
- **Delete Events**: Remove manual or extracurricular events

### Color Coding

Each calendar can have an assigned color displayed as a swatch in the admin list for easy identification.

## Storage

### SQLite Database (`data/app.db`)

| Table | Description |
|-------|-------------|
| `calendars` | Configured calendar URLs with name, color, enabled status |
| `manual_events` | User-added one-time events |
| `extracurricular_events` | Recurring extracurricular activities |

### Playwright Captures (`playwright_captures/`)

| File | Description |
|------|-------------|
| `events.json` | Merged events from all sources (used by UI) |
| `schedule_by_room.json` | Room-based schedule view |
| `schedule_by_room.csv` | CSV export of room schedule |
| `calendar_full.ics` | Raw downloaded ICS file |
| `events_<hash>.json` | Per-calendar extracted events |

## Periodic Importer

The app includes a background thread that automatically imports calendars:

- **Initial Run**: Immediately on app startup
- **Interval**: Every 60 minutes (configurable in `app.py`)
- **Concurrency**: Uses internal lock to prevent overlapping runs

To disable automatic imports, comment out the `periodic_fetcher` thread in `app.py`.

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'flask'` | Activate venv: `source .venv/bin/activate && pip install -r requirements.txt` |
| Port 5000 already in use | Kill existing process: `kill $(lsof -ti:5000)` |
| Playwright fails to launch | Install browsers: `python -m playwright install chromium` |
| DB migration errors | Check `data/app.db` permissions and legacy JSON files in `config/` |

### Logs

- Development: Logs appear on stdout
- Background mode: Check `server.log` with `tail -f server.log`

### Warnings (Harmless)

- `DeprecationWarning: datetime.utcnow()` — Legacy datetime usage, doesn't affect functionality
- `WARNING: This is a development server` — Normal Flask development mode warning

## Recommended .gitignore

```gitignore
# Virtual environment
.venv/
venv/

# Python cache
__pycache__/

# Playwright temporary files
playwright_captures/*.stdout.txt
playwright_captures/*.stderr.txt
playwright_captures/page*.html
playwright_captures/json_capture_*.json

# Runtime files
server.log
data/app.db
```

## Contributing

### Adding New Parsers

1. Edit `tools/subject_parser.py` for subject/location normalization
2. Add building mappings in `config/room_aliases.json`

### Running the Extractor Manually

```bash
python tools/extract_published_events.py <URL>
```

Check output in `playwright_captures/*.stderr.txt` for debugging.

### Frontend Development

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server runs at `http://localhost:5173` with hot reload.

---

## License

MIT

---

**Built for**: Technical University of Cluj-Napoca (UTCN)  
**Faculty**: Automation and Computer Science
