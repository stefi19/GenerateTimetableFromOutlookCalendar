# Outlook published calendar — Timetable viewer

Small Flask-based timetable viewer that imports events from Outlook "published calendar" URLs, normalizes subjects/locations, and exposes a simple admin UI to manage calendar sources and manual/extracurricular events.

## Table of contents
- Overview
- Requirements
- Setup (recommended)
- Running the app
- Admin UI (how to add/manage calendars & events)
- Storage and important files
- Periodic importer behavior
- Playwright / rendering notes
- Troubleshooting
- Cleanup & .gitignore

## Overview
This project extracts events from published Outlook calendar pages (or uploaded .ics files), applies subject/location normalization, persists configured calendar URLs and user-added events in a local SQLite DB, and exposes several views:

- `/schedule` — full timetable view
- `/departures` — departure-board style view for today/tomorrow by building
- `/admin` — administration UI to add calendar URLs, import now, add manual events, and manage extracurricular events

The project also contains tools in `tools/` for building room schedules and extracting events using Playwright when pages are client-side rendered.

## Requirements
- Python 3.10+ (tested with 3.14)
- System: macOS / Linux (Playwright binaries require extra install step)

Install Python dependencies in an isolated virtualenv (recommended):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Quick setup (automated):

```bash
./setup.sh
```

The `setup.sh` script now performs the full bootstrap:

- creates and activates `.venv`
- installs Python dependencies from `requirements.txt`
- installs Playwright browsers (required for the extractor UI rendering)
- initializes the local SQLite DB and migrates any legacy configs into `data/app.db`

You can then run the app with:

```bash
source .venv/bin/activate
python app.py
```

If you don't want to activate the virtualenv, use the interpreter directly:

```bash
./.venv/bin/python app.py
```

## Setup (one-time)
- (Optional) Install Playwright browsers only if you will use the UI's "Render page" feature that executes JS:

```bash
python -m playwright install
# or install only chromium
python -m playwright install chromium
```

## Running the app (development)

- Start the app (development server):

```bash
source .venv/bin/activate
python app.py
```

- The app listens on http://127.0.0.1:5000. The root redirects to `/schedule`.

To run in background (example):

```bash
nohup ./.venv/bin/python app.py > server.log 2>&1 &
tail -f server.log
```

Stop the server:

```bash
# Kill the process listening on port 5000
kill $(lsof -ti:5000)
```

## Admin UI — how to use

Open `/admin` in the browser. Features:

- Save a Published Calendar URL (optional: friendly name + color). The URL and metadata are persisted in `data/app.db`.
- "Import Calendar Now" triggers the extractor in background (uses Playwright-based tool or direct .ics parsing). Imported events are written to `playwright_captures/events.json` and used for views.
- Add manual events (Admin) — persisted in DB and shown in `/events.json` and calendar views.
- Add/Delete extracurricular events — also persisted and displayed in departures and schedule.
- Delete configured calendars and manual/extracurricular events via Admin buttons.

Notes:
- Each configured calendar row shows a small color swatch (if you set a color).
- If the DB is unavailable, Admin falls back to `config/calendar_config.json` and `config/extracurricular_events.json` as legacy files.

## Storage and important files

- `data/app.db` — SQLite DB with tables:
  - `calendars` (id, url, name, color, enabled, created_at, last_fetched)
  - `manual_events` (id, start, end, title, location, raw, created_at)
  - `extracurricular_events` (id, title, organizer, date, time, location, category, description, created_at)
- `playwright_captures/` — output files from extractor:
  - `events.json` — flattened events used by calendar UI
  - `schedule_by_room.json` / `.csv` — schedule built by `tools/build_schedule_by_room.py`
  - `calendar_full.ics` — raw downloaded ICS (kept)
- `templates/` — Flask Jinja2 templates (UI)

## Periodic importer behavior

On app startup the code launches a background thread that performs an initial import pass and then repeats every 60 minutes. The behavior is:

- Initial run happens immediately when the app starts (no initial sleep).
- Subsequent runs occur every 60 minutes (you can change the interval by editing `periodic_fetcher` call in `app.py`).

If you prefer not to run periodic imports automatically, stop the thread by editing `app.py` where the thread is started (search for `periodic_fetcher`) or run the server with a modified startup flow.

## Playwright / rendering notes

- The extractor uses Playwright when pages require client-side rendering to reveal `.ics` links or network responses. Playwright must be installed and browsers available (see Setup).
- Running Playwright on CI or headless servers may require additional OS dependencies. See Playwright docs for platform-specific notes.

## Troubleshooting

- ModuleNotFoundError: No module named 'flask'
  - Cause: you're running `python app.py` in a Python environment that doesn't have the dependencies installed. Fix:

```bash
# use the project's venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

- Server responds then dies / port in use
  - Check running processes: `lsof -i:5000` / `ps aux | grep app.py` and kill the conflicting PID.

- Logs
  - The app writes to `server.log` if started with nohup; otherwise logs appear on stdout. Use `tail -f server.log` to follow logs.

- Warnings in logs
  - `DeprecationWarning: datetime.utcnow()` — harmless but can be fixed by making timestamps timezone-aware. If you'd like, I can update the code to use `datetime.now(timezone.utc)`.
  - `resource_tracker: leaked semaphore` — usually harmless in short runs; if persistent, we can investigate and mitigate.

## Cleanup & recommended .gitignore

You likely want to ignore the following in git:

```
.venv/
venv/
__pycache__/
playwright_captures/*.stdout.txt
playwright_captures/*.stderr.txt
playwright_captures/page*.html
playwright_captures/json_capture_*.json
server.log
data/app.db
```

## Contributing / extending

- Add new parsers or building mappings in `tools/subject_parser.py`.
- The extractor lives in `tools/extract_published_events.py` and can be run standalone when debugging a URL.

<!-- Removed: optional run.sh / .gitignore / env suggestion per request -->

---
License: MIT
