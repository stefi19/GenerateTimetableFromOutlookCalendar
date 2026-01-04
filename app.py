from __future__ import annotations

import os
import tempfile
import threading
import time
from collections import defaultdict
import sqlite3
from contextlib import closing
import pathlib
import json
import sys
import subprocess
import hashlib
import functools
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional

from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify, session, Response

from timetable import (
    Event,
    find_ics_url_from_html,
    fetch,
    parse_ics_from_url,
    parse_microformat_vevents,
)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET", "dev-secret")

# Admin authentication
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")  # Change in production!


def check_admin_auth():
    """Check if request has valid admin authentication."""
    auth = request.authorization
    if auth and auth.password == ADMIN_PASSWORD:
        return True
    return session.get('admin_authenticated', False)


def require_admin(f):
    """Decorator to require admin authentication."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not check_admin_auth():
            return Response(
                'Admin authentication required.\n'
                'Please login with the admin password.',
                401,
                {'WWW-Authenticate': 'Basic realm="Admin Area"'}
            )
        return f(*args, **kwargs)
    return decorated


def group_events(events: List[Event], from_date: date, to_date: date):
    groups = defaultdict(list)
    for e in sorted(events, key=lambda ev: ev.start):
        if e.start.date() < from_date or e.start.date() > to_date:
            continue
        groups[e.start.date()].append(e)
    return groups


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint for Docker/load balancers."""
    return jsonify({
        "status": "healthy",
        "service": "utcn-timetable",
        "version": "1.0.0"
    }), 200


@app.route("/", methods=["GET"])
def index():
    """Serve the React SPA frontend directly on root."""
    frontend_dist = pathlib.Path(__file__).parent / 'frontend' / 'dist' / 'index.html'
    if frontend_dist.exists():
        return send_file(frontend_dist)
    return """
    <html>
    <head><title>Frontend Not Built</title></head>
    <body style="font-family: sans-serif; padding: 2rem; text-align: center;">
        <h1>Frontend not built</h1>
        <p>Run <code>cd frontend && npm install && npm run build</code></p>
    </body>
    </html>
    """, 200


# Legacy /app route for backwards compatibility
@app.route('/app')
def spa_index_legacy():
    """Redirect /app to root for backwards compatibility."""
    return redirect('/')


# OLD FRONTEND ROUTE - DISABLED (use /app for React SPA)
# @app.route("/fetch", methods=["POST"])
# def fetch_route(): ... (removed - old Jinja frontend)


def parse_ics_direct(text: str) -> List[Event]:
    # lightweight parse using ics.Calendar as in timetable.parse_ics_from_url
    try:
        from ics import Calendar
    except Exception:
        raise RuntimeError("Missing ics library; install requirements")

    cal = Calendar(text)
    evs: List[Event] = []
    from dateutil import parser as dtparser

    for e in cal.events:
        try:
            start = e.begin.naive
        except Exception:
            start = dtparser.parse(str(e.begin))
        try:
            end = e.end.naive if e.end else None
        except Exception:
            end = dtparser.parse(str(e.end)) if e.end else None
        evs.append(Event(start=start, end=end, title=e.name or "", location=e.location or "", description=e.description or ""))
    return evs


def render_and_find_ics(url: str) -> List[str]:
    """Use Playwright to render a page and return candidate .ics URLs.

    Returns a list of candidate URLs (may be empty)."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        raise RuntimeError("playwright is not installed. Install with: pip install playwright && playwright install")

    candidates = []
    with sync_playwright() as p:
        # If a persistent user data dir is supplied, reuse it so the context can be authenticated.
        user_data_dir = os.environ.get("PLAYWRIGHT_USER_DATA_DIR")
        if user_data_dir:
            # launch_persistent_context returns a BrowserContext
            context = p.chromium.launch_persistent_context(user_data_dir, headless=True)
            page = context.new_page()
            browser = None
        else:
            browser = p.chromium.launch()
            page = browser.new_page()
        # capture network responses that might be calendar data
        responses = []
        saved_files = []

        def safe_name(s: str) -> str:
            import hashlib, urllib.parse

            h = hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]
            u = urllib.parse.quote_plus(s)[:60]
            return f"last_response_{h}_{u}.txt"

        def on_response(resp):
            try:
                ct = resp.headers.get("content-type", "")
                url_ = resp.url
                is_calendar = False
                if "calendar" in ct or url_.lower().endswith(".ics") or ".ics?" in url_.lower() or "calendar" in url_.lower():
                    is_calendar = True
                if is_calendar:
                    # try to read body and save it
                    try:
                        body = resp.text()
                    except Exception:
                        body = None
                    if body:
                        fname = safe_name(url_)
                        with open(fname, "w", encoding="utf-8") as f:
                            f.write(body)
                        saved_files.append(fname)
                        responses.append(url_)
                else:
                    # still record responses that look promising (XHR/json) which might contain feed URLs
                    if resp.request.resource_type == "xhr":
                        try:
                            body = resp.text()
                        except Exception:
                            body = None
                        if body and ("ics" in body.lower() or "calendar" in body.lower() or "subscribe" in body.lower()):
                            fname = safe_name(url_)
                            with open(fname, "w", encoding="utf-8") as f:
                                f.write(body)
                            saved_files.append(fname)
                            responses.append(url_)
            except Exception:
                pass

    page.on("response", on_response)
    page.goto(url, wait_until="networkidle", timeout=30000)

    # find links in DOM that look like .ics
    anchors = page.query_selector_all("a[href]")
    for a in anchors:
        try:
            href = a.get_attribute("href")
            if href and (href.lower().endswith(".ics") or "webcal:" in href.lower() or ".ics?" in href.lower()):
                # resolve relative hrefs
                if href.startswith("/"):
                    base = page.url
                    resolved = base.rstrip("/") + href
                else:
                    resolved = href
                candidates.append(resolved)
        except Exception:
            continue

    # add any network responses
    candidates.extend(responses)

    # dedupe preserving order
    seen = set()
    out = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    # close whichever we opened
    try:
        if browser:
            browser.close()
        else:
            context.close()
    except Exception:
        pass

    # return candidates and saved files
    return out, saved_files


def ensure_schedule(from_date: date, to_date: date):
    """Ensure `playwright_captures/schedule_by_room.json` and CSV exist for the given range.

    This calls the tools/build_schedule_by_room.py script with the requested range
    using the current Python executable. Returns the path to the JSON schedule file
    or raises if generation failed.
    """
    out_dir = pathlib.Path('playwright_captures')
    jpath = out_dir / 'schedule_by_room.json'
    cpath = out_dir / 'schedule_by_room.csv'
    # Before regenerating, merge any per-calendar extracted files (events_<hash>.json)
    try:
        out_dir = pathlib.Path('playwright_captures')
        merged_path = out_dir / 'events.json'
        # find per-calendar files
        parts = list(out_dir.glob('events_*.json'))
        # DON'T include the generic events.json as it's the output file
        # and processing it first would prevent newer events with colors from being added
        merged = []
        seen = set()
        if parts:
            for p in parts:
                try:
                    with open(p, 'r', encoding='utf-8') as f:
                        items = json.load(f)
                except Exception:
                    items = []
                for it in items:
                    # dedupe by raw ItemId if available, otherwise by title+start
                    key = None
                    try:
                        raw = it.get('raw') or {}
                        iid = None
                        if isinstance(raw, dict):
                            iid = raw.get('ItemId', {}).get('Id') if raw.get('ItemId') else None
                        key = iid or (str(it.get('title','')) + '|' + str(it.get('start') or ''))
                    except Exception:
                        key = (str(it.get('title','')) + '|' + str(it.get('start') or ''))
                    if key in seen:
                        continue
                    seen.add(key)
                    # attempt to enrich with calendar color from calendar_map.json
                    try:
                        map_path = out_dir / 'calendar_map.json'
                        if map_path.exists() and it.get('source'):
                            with open(map_path, 'r', encoding='utf-8') as mf:
                                cmap = json.load(mf)
                            meta = cmap.get(it.get('source')) or {}
                            col = meta.get('color')
                            if col:
                                it['color'] = col
                    except Exception:
                        pass
                    merged.append(it)
        # ALWAYS save merged file (even if empty, to clear old events)
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            with open(merged_path, 'w', encoding='utf-8') as f:
                json.dump(merged, f, indent=2, ensure_ascii=False, default=str)
        except Exception:
            pass

    except Exception:
        pass

    # call the build script to regenerate for the requested range
    try:
        script = pathlib.Path('tools') / 'build_schedule_by_room.py'
        if not script.exists():
            raise FileNotFoundError(script)
        cmd = [sys.executable, str(script), '--from', from_date.isoformat(), '--to', to_date.isoformat()]
        subprocess.run(cmd, check=False)
    except Exception as e:
        # swallow but propagate via return
        raise

    if not jpath.exists():
        raise FileNotFoundError(jpath)
    return jpath, cpath


# Background extractor state
extractor_state = {
    'running': False,
    'last_rc': None,
    'last_started': None,
    'stdout_path': None,
    'stderr_path': None,
    'current_calendar': None,
    'progress_message': None,
    'events_extracted': 0,
}

# Scheduler control
periodic_fetch_state = {
    'running': False,
    'last_run': None,
    'last_success': None,
}

# Lock to avoid overlapping periodic runs
_periodic_lock = threading.Lock()


# --------- Simple SQLite helpers ---------
DB_PATH = pathlib.Path('data') / 'app.db'
DB_PATH.parent.mkdir(exist_ok=True)

def get_db_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Create tables if they do not exist."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS calendars (
                id INTEGER PRIMARY KEY,
                url TEXT UNIQUE,
                name TEXT,
                color TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TEXT,
                last_fetched TEXT
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS extracurricular_events (
                id INTEGER PRIMARY KEY,
                title TEXT,
                organizer TEXT,
                date TEXT,
                time TEXT,
                location TEXT,
                category TEXT,
                description TEXT,
                created_at TEXT
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS manual_events (
                id INTEGER PRIMARY KEY,
                start TEXT,
                end TEXT,
                title TEXT,
                location TEXT,
                raw TEXT,
                created_at TEXT
            )
        ''')
        conn.commit()
    # ensure older DBs have the color column
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT color FROM calendars LIMIT 1")
            _ = cur.fetchone()
    except Exception:
        try:
            with get_db_connection() as conn:
                cur = conn.cursor()
                cur.execute('ALTER TABLE calendars ADD COLUMN color TEXT')
                conn.commit()
        except Exception:
            pass

def migrate_from_files():
    """Migrate existing JSON configs into the DB if present."""
    # migrate calendar_config.json
    cfg_file = pathlib.Path('config') / 'calendar_config.json'
    if cfg_file.exists():
        try:
            with open(cfg_file, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            urls = []
            if isinstance(cfg.get('calendar_urls'), list):
                urls = cfg.get('calendar_urls')
            elif cfg.get('calendar_url'):
                urls = [cfg.get('calendar_url')]
            for u in urls:
                if u:
                    add_calendar_url(u)
            # optionally remove file
            try:
                cfg_file.unlink()
            except Exception:
                pass
        except Exception:
            pass

    # migrate extracurricular events
    extras = pathlib.Path('config') / 'extracurricular_events.json'
    if extras.exists():
        try:
            with open(extras, 'r', encoding='utf-8') as f:
                items = json.load(f)
            if isinstance(items, list):
                for it in items:
                    try:
                        ev = {
                            'title': it.get('title'),
                            'organizer': it.get('organizer'),
                            'date': it.get('date'),
                            'time': it.get('time'),
                            'location': it.get('location'),
                            'category': it.get('category'),
                            'description': it.get('description'),
                            'created_at': it.get('created_at') or datetime.now().isoformat()
                        }
                        add_extracurricular_db(ev)
                    except Exception:
                        pass
            try:
                extras.unlink()
            except Exception:
                pass
        except Exception:
            pass

def add_calendar_url(url: str, name: str = None):
    """Add a calendar URL to the database. Returns the calendar ID."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute('INSERT OR IGNORE INTO calendars (url, name, color, enabled, created_at) VALUES (?, ?, ?, 1, ?)',
                        (url, name or '', None, datetime.now().isoformat()))
            conn.commit()
            # Get the ID (either newly inserted or existing)
            cur.execute('SELECT id FROM calendars WHERE url = ?', (url,))
            row = cur.fetchone()
            return row['id'] if row else None
        except Exception:
            return None

def update_calendar_metadata(url: str, name: str = None, color: str = None):
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute('UPDATE calendars SET name = ?, color = ? WHERE url = ?', (name or '', color or None, url))
            conn.commit()
    except Exception:
        pass

def list_calendar_urls():
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute('SELECT id, url, name, color, enabled, created_at, last_fetched FROM calendars ORDER BY id')
        return [dict(row) for row in cur.fetchall()]

def add_extracurricular_db(ev: dict):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute('''INSERT INTO extracurricular_events (title, organizer, date, time, location, category, description, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                    (ev.get('title'), ev.get('organizer'), ev.get('date'), ev.get('time'), ev.get('location'), ev.get('category'), ev.get('description'), ev.get('created_at')))
        conn.commit()
        return cur.lastrowid

    def delete_calendar_db(cal_id: int):
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute('DELETE FROM calendars WHERE id = ?', (cal_id,))
            conn.commit()

    def delete_manual_db(man_id: int):
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute('DELETE FROM manual_events WHERE id = ?', (man_id,))
            conn.commit()

def add_manual_event_db(ev: dict):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute('''INSERT INTO manual_events (start, end, title, location, raw, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)''',
                    (ev.get('start'), ev.get('end'), ev.get('title'), ev.get('location'), json.dumps(ev.get('raw') or {}), ev.get('created_at')))
        conn.commit()
        return cur.lastrowid

def list_manual_events_db():
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute('SELECT * FROM manual_events ORDER BY start')
        rows = [dict(r) for r in cur.fetchall()]
        # parse raw json
        for r in rows:
            try:
                r['raw'] = json.loads(r.get('raw') or '{}')
            except Exception:
                r['raw'] = {}
        return rows

def list_extracurricular_db():
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute('SELECT * FROM extracurricular_events ORDER BY date, time, id')
        return [dict(row) for row in cur.fetchall()]

def delete_extracurricular_db(ev_id: int):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute('DELETE FROM extracurricular_events WHERE id = ?', (ev_id,))
        conn.commit()


def delete_calendar_db(cal_id: int):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute('DELETE FROM calendars WHERE id = ?', (cal_id,))
        conn.commit()


def delete_manual_db(man_id: int):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute('DELETE FROM manual_events WHERE id = ?', (man_id,))
        conn.commit()


def _run_extractor_background():
    """Internal: run the extractor script and update extractor_state."""
    out_dir = pathlib.Path('playwright_captures')
    out_dir.mkdir(exist_ok=True)
    stdout_path = out_dir / 'extract_stdout.txt'
    stderr_path = out_dir / 'extract_stderr.txt'
    extractor_state['running'] = True
    extractor_state['last_started'] = datetime.utcnow().isoformat()
    extractor_state['stdout_path'] = str(stdout_path)
    extractor_state['stderr_path'] = str(stderr_path)
    script = pathlib.Path('tools') / 'extract_published_events.py'
    cmd = [sys.executable, str(script)]
    try:
        # ensure child python runs use UTF-8 on Windows (avoid cp1252 issues)
        env = os.environ.copy()
        env.setdefault('PYTHONUTF8', '1')
        env.setdefault('PYTHONIOENCODING', 'utf-8')
        with open(stdout_path, 'w', encoding='utf-8') as out_f, open(stderr_path, 'w', encoding='utf-8') as err_f:
            proc = subprocess.run(cmd, stdout=out_f, stderr=err_f, text=True, env=env)
            extractor_state['last_rc'] = proc.returncode
    except Exception as e:
        with open(stderr_path, 'a', encoding='utf-8') as err_f:
            err_f.write(str(e))
        extractor_state['last_rc'] = 1
    finally:
        extractor_state['running'] = False


def _run_extractor_for_url(url: str, calendar_name: str = None) -> int:
    """Run the extractor script for a specific URL (uses CLI arg). Returns returncode."""
    out_dir = pathlib.Path('playwright_captures')
    out_dir.mkdir(exist_ok=True)
    h = hashlib.sha1(url.encode('utf-8')).hexdigest()[:8]
    stdout_path = out_dir / f'extract_{h}.stdout.txt'
    stderr_path = out_dir / f'extract_{h}.stderr.txt'
    
    # Update progress state
    extractor_state['current_calendar'] = calendar_name or url[:50]
    extractor_state['progress_message'] = f'Extracting events from {calendar_name or "calendar"}...'
    extractor_state['events_extracted'] = 0
    
    cmd = [sys.executable, str(pathlib.Path('tools') / 'extract_published_events.py'), url]
    try:
        # force UTF-8 for child process to avoid Windows cp1252 / OEM codepage problems
        env = os.environ.copy()
        env.setdefault('PYTHONUTF8', '1')
        env.setdefault('PYTHONIOENCODING', 'utf-8')
        with open(stdout_path, 'w', encoding='utf-8') as out_f, open(stderr_path, 'w', encoding='utf-8') as err_f:
            proc = subprocess.run(cmd, stdout=out_f, stderr=err_f, text=True, env=env)
            rc = proc.returncode
    except Exception as e:
        with open(stderr_path, 'a', encoding='utf-8') as err_f:
            err_f.write(str(e))
        rc = 1

    # If extractor produced an events.json, tag the events with the source hash
    try:
        out_dir = pathlib.Path('playwright_captures')
        ev_in = out_dir / 'events.json'
        if ev_in.exists():
            h = hashlib.sha1(url.encode('utf-8')).hexdigest()[:8]
            ev_out = out_dir / f'events_{h}.json'
            try:
                with open(ev_in, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = []

            # Update progress with event count
            extractor_state['events_extracted'] = len(data)
            extractor_state['progress_message'] = f'Extracted {len(data)} events from {calendar_name or "calendar"}'

            # Get the color from DB for this calendar
            cal_color = None
            try:
                init_db()
                rows = list_calendar_urls()
                for r in rows:
                    if r.get('url') == url:
                        cal_color = r.get('color')
                        break
            except Exception:
                pass

            # attach source id and color to each event
            for it in data:
                try:
                    it['source'] = h
                    if cal_color:
                        it['color'] = cal_color
                except Exception:
                    pass

            # write per-calendar events file
            try:
                with open(ev_out, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            except Exception:
                pass

            # update mapping file (hash -> url/name/color)
            try:
                map_path = out_dir / 'calendar_map.json'
                cmap = {}
                if map_path.exists():
                    with open(map_path, 'r', encoding='utf-8') as f:
                        cmap = json.load(f)
                # attempt to get name/color from DB
                name = None
                color = None
                try:
                    init_db()
                    rows = list_calendar_urls()
                    for r in rows:
                        if r.get('url') == url:
                            name = r.get('name')
                            color = r.get('color')
                            break
                except Exception:
                    pass
                cmap[h] = {'url': url, 'name': name or '', 'color': color}
                with open(map_path, 'w', encoding='utf-8') as f:
                    json.dump(cmap, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

            # remove the generic events.json to avoid accidental reuse
            try:
                ev_in.unlink()
            except Exception:
                pass

    except Exception:
        pass

    return rc


def periodic_fetcher(interval_minutes: int = 60):
    """Background loop that periodically fetches configured calendar URLs and runs extraction/parsing."""
    global periodic_fetch_state
    # read calendar URLs from DB
    while True:
        try:

            # Avoid overlapping runs
            if not _periodic_lock.acquire(blocking=False):
                # already running
                continue
            periodic_fetch_state['running'] = True
            periodic_fetch_state['last_run'] = datetime.utcnow().isoformat()

            # Read URLs from DB
            urls_with_names = []
            try:
                rows = list_calendar_urls()
                for r in rows:
                    if r.get('enabled') and r.get('url'):
                        urls_with_names.append((r.get('url'), r.get('name')))
            except Exception:
                urls_with_names = []

            # If no URLs configured, skip
            if not urls_with_names:
                periodic_fetch_state['running'] = False
                _periodic_lock.release()
                continue

            # Run extractor for each URL sequentially
            any_success = False
            for u, name in urls_with_names:
                rc = _run_extractor_for_url(u, name)
                if rc == 0:
                    any_success = True

            if any_success:
                periodic_fetch_state['last_success'] = datetime.utcnow().isoformat()

        except Exception:
            pass
        finally:
            periodic_fetch_state['running'] = False
            try:
                _periodic_lock.release()
            except Exception:
                pass
        # Sleep until next run
        time.sleep(interval_minutes * 60)


# Flag to ensure we only start the periodic fetcher once
_periodic_fetcher_started = False
_periodic_fetcher_lock = threading.Lock()

def start_periodic_fetcher_if_needed(interval_minutes: int = 60):
    """Start the periodic fetcher thread if not already started. Safe to call multiple times."""
    global _periodic_fetcher_started
    with _periodic_fetcher_lock:
        if _periodic_fetcher_started:
            return False
        _periodic_fetcher_started = True
    try:
        t = threading.Thread(target=periodic_fetcher, args=(interval_minutes,), daemon=True)
        t.start()
        print(f'Started periodic calendar fetcher (runs every {interval_minutes} minutes)')
        return True
    except Exception as e:
        print(f'Failed to start periodic fetcher: {e}')
        return False


# Start the periodic fetcher on module import (works with Gunicorn)
# This runs once when the app is loaded
start_periodic_fetcher_if_needed(60)


# OLD FRONTEND ROUTE - DISABLED (use /app for React SPA)
# @app.route('/schedule', methods=['GET', 'POST'])
# def schedule_view(): ... (removed - old Jinja frontend)


@app.route('/calendars.json')
def calendars_json():
    """Return the calendar map with source hashes, names, and colors from DB."""
    try:
        init_db()
        calendars = list_calendar_urls()
        result = {}
        for cal in calendars:
            url = cal.get('url', '')
            # Calculate hash the same way as in _run_extractor_for_url (SHA1, not MD5)
            url_hash = hashlib.sha1(url.encode('utf-8')).hexdigest()[:8]
            result[url_hash] = {
                'name': cal.get('name') or f"Calendar {cal.get('id')}",
                'color': cal.get('color'),
                'url': url
            }
        return jsonify(result)
    except Exception:
        pass
    return jsonify({})


@app.route('/events.json')
def events_json():
    """Return flattened events for FullCalendar or API clients.

    Query params: from, to, subject, professor
    Always fetches and stores events for the next 2 months by default.
    """
    # Import the event parser
    try:
        from tools.event_parser import parse_event, parse_title, parse_location
    except ImportError:
        parse_event = None
        parse_title = None
        parse_location = None
    from_s = request.values.get('from')
    to_s = request.values.get('to')
    subject_filter = (request.values.get('subject') or '').strip().lower()
    professor_filter = (request.values.get('professor') or '').strip().lower()
    room_filter = (request.values.get('room') or '').strip().lower()
    today = date.today()
    
    # Always ensure we have 2 months of events stored
    two_months_from_now = today + timedelta(days=60)
    
    try:
        from_date = date.fromisoformat(from_s) if from_s else today
    except Exception:
        from_date = today
    try:
        to_date = date.fromisoformat(to_s) if to_s else two_months_from_now
    except Exception:
        to_date = two_months_from_now

    # ensure schedule exists
    try:
        jpath, cpath = ensure_schedule(from_date, to_date)
    except Exception:
        # No schedule available yet - return empty array (not 500 error)
        return jsonify([])

    if not jpath or not os.path.exists(jpath):
        return jsonify([])

    with open(jpath, 'r', encoding='utf-8') as f:
        schedule = json.load(f)

    events = []
    for room, days in schedule.items():
        for day, evs in days.items():
            for e in evs:
                start = e.get('start')
                end = e.get('end')
                title = e.get('title') or ''
                location = e.get('location') or ''
                
                # Use event parser to extract structured data
                parsed_subject = ''
                parsed_prof = ''
                parsed_building = ''
                parsed_room = ''
                display_title = title
                
                if parse_event:
                    try:
                        parsed = parse_event(e)
                        parsed_subject = parsed.get('subject', '')
                        parsed_prof = parsed.get('professor', '')
                        parsed_building = parsed.get('building', '')
                        parsed_room = parsed.get('room', '')
                        display_title = parsed.get('display_title', '') or title
                    except Exception:
                        pass
                
                # Fallback to existing data if parser didn't find anything
                subject = parsed_subject or (e.get('subject') or '')
                prof = parsed_prof or (e.get('professor') or '')
                building = parsed_building or ''
                room_parsed = parsed_room or room

                hay = (title + ' ' + subject + ' ' + display_title).lower()
                if subject_filter and subject_filter not in hay:
                    continue
                if professor_filter and professor_filter not in (prof or '').lower():
                    continue
                if room_filter and room_filter not in room.lower() and room_filter not in room_parsed.lower():
                    continue

                ev = {
                    'title': title,
                    'display_title': display_title,
                    'start': start,
                    'end': end,
                    'room': room_parsed or room,
                    'building': building,
                    'subject': subject,
                    'professor': prof,
                    'location': location,
                    'color': None,
                    'source': e.get('source') if isinstance(e, dict) else None,
                    'calendar_name': None,
                    'year': '',
                    'group': '',
                    'group_display': '',
                }
                # resolve color and calendar_name from merged metadata or calendar_map.json
                try:
                    # if schedule already had a color (merged), preserve it
                    if isinstance(e, dict) and e.get('color'):
                        ev['color'] = e.get('color')

                    src = ev.get('source')
                    if src:
                        map_path = pathlib.Path('playwright_captures') / 'calendar_map.json'
                        if map_path.exists():
                            try:
                                with open(map_path, 'r', encoding='utf-8') as mf:
                                    cmap = json.load(mf)
                                meta = cmap.get(src) or {}
                                if meta.get('color') and not ev['color']:
                                    ev['color'] = meta.get('color')
                                if meta.get('name'):
                                    ev['calendar_name'] = meta.get('name')
                            except Exception:
                                pass
                except Exception:
                    # ignore any errors resolving calendar metadata
                    pass

                # Try to parse group/year from calendar_name or subject/display_title
                try:
                    from tools.event_parser import parse_group_from_string
                    sample = ev.get('calendar_name') or ev.get('subject') or ev.get('display_title') or ''
                    grp = parse_group_from_string(sample)
                    if grp and isinstance(grp, dict):
                        ev['year'] = grp.get('year', '')
                        ev['group'] = grp.get('group', '')
                        ev['group_display'] = grp.get('display', '')
                except Exception:
                    pass

                events.append(ev)

    # Append manual admin events from DB
    try:
        init_db()
        manual = list_manual_events_db()
        from dateutil import parser as dtparser
        for me in manual:
            try:
                if not me.get('start'):
                    continue
                start_dt = me.get('start')
                # filter by range (string ISO)
                try:
                    d = dtparser.parse(start_dt).date()
                except Exception:
                    continue
                if d < from_date or d > to_date:
                    continue
                ev_obj = {
                    'title': me.get('title'),
                    'display_title': me.get('title'),
                    'start': me.get('start'),
                    'end': me.get('end'),
                    'room': me.get('location') or '',
                    'subject': '',
                    'professor': '',
                    'location': me.get('location') or '',
                    'color': '#004080',
                    'manual': True,
                }
                events.append(ev_obj)
            except Exception:
                continue
    except Exception:
        pass

    # Append extracurricular events from DB so they appear in the calendar with a distinct color
    try:
        init_db()
        extra_events = list_extracurricular_db()
        from dateutil import parser as dtparser
        for xe in extra_events:
            d = xe.get('date')
            if not d:
                continue
            try:
                ev_date = dtparser.parse(d).date()
            except Exception:
                continue
            if ev_date < from_date or ev_date > to_date:
                continue
            time_s = (xe.get('time') or '').strip()
            if time_s:
                start_iso = f"{ev_date.isoformat()}T{time_s}:00"
            else:
                start_iso = ev_date.isoformat()
            try:
                from tools.event_parser import parse_title
                parsed = parse_title(xe.get('title', '') or '')
                disp = parsed.display_title
                subj = parsed.subject
            except Exception:
                disp = xe.get('title')
                subj = ''
            ev_obj = {
                'title': xe.get('title'),
                'display_title': disp,
                'start': start_iso,
                'end': None,
                'room': xe.get('location') or '',
                'subject': subj,
                'professor': xe.get('organizer') or '',
                'location': xe.get('location') or '',
                'color': '#7c3aed',  # purple for extracurricular
                'extracurricular': True,
            }
            events.append(ev_obj)
    except Exception:
        pass

    return jsonify(events)


@app.route('/export_room')
def export_room():
    """Render a printable timetable for a single room and optionally export to PDF/PNG.

    Query params: room (required), from, to, format=pdf|png
    """
    room = (request.values.get('room') or '').strip()
    if not room:
        return "Missing 'room' parameter", 400

    from_s = request.values.get('from')
    to_s = request.values.get('to')
    today = date.today()
    try:
        from_date = date.fromisoformat(from_s) if from_s else today
    except Exception:
        from_date = today
    try:
        to_date = date.fromisoformat(to_s) if to_s else from_date + timedelta(days=6)
    except Exception:
        to_date = from_date + timedelta(days=6)

    try:
        jpath, cpath = ensure_schedule(from_date, to_date)
    except Exception as e:
        return f'Failed to build schedule: {e}', 500

    with open(jpath, 'r', encoding='utf-8') as f:
        schedule = json.load(f)

    # collect events for room
    events = []
    for r, days in schedule.items():
        if r.lower() != room.lower():
            continue
        for day, evs in days.items():
            try:
                day_date = date.fromisoformat(day)
            except Exception:
                continue
            if day_date < from_date or day_date > to_date:
                continue
            for e in evs:
                events.append({
                    'date': day,
                    'start': e.get('start'),
                    'end': e.get('end'),
                    'title': e.get('title'),
                    'subject': e.get('subject'),
                    'professor': e.get('professor') or '',
                    'location': e.get('location') or '',
                })

    # sort events by date and start time
    events.sort(key=lambda x: (x['date'], x.get('start') or ''))

    html = render_template('room_print.html', room=room, events=events, from_date=from_date, to_date=to_date)

    fmt = (request.values.get('format') or 'pdf').lower()
    if fmt not in ('pdf', 'png', 'jpg', 'jpeg'):
        fmt = 'pdf'

    # If client requested PDF/PNG, try to render with Playwright
    if fmt in ('pdf', 'png', 'jpg', 'jpeg'):
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            return "Playwright is not available on the server; cannot export to PDF/image.", 500

        tmpd = pathlib.Path(tempfile.mkdtemp(prefix='export_room_'))
        html_path = tmpd / 'room.html'
        out_path = tmpd / ('room.pdf' if fmt == 'pdf' else 'room.png')
        with open(html_path, 'w', encoding='utf-8') as fh:
            fh.write(html)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto('file://' + str(html_path.resolve()))
                page.wait_for_timeout(250)
                if fmt == 'pdf':
                    page.pdf(path=str(out_path), format='A4', print_background=True)
                else:
                    page.screenshot(path=str(out_path), full_page=True)
                browser.close()
        except Exception as e:
            return f'Failed to render export: {e}', 500

        # send file as attachment
        filename = f"{room.replace(' ', '_')}_{from_date.isoformat()}_{to_date.isoformat()}.{out_path.suffix.lstrip('.') }"
        # use download_name for newer Flask versions
        try:
            return send_file(str(out_path), as_attachment=True, download_name=filename)
        except TypeError:
            return send_file(str(out_path), as_attachment=True)

    # fallback: return HTML
    return html


@app.route('/generate_events', methods=['POST'])
def generate_events():
    """Run the extractor script as a subprocess and show its output as diagnostics.

    This will call `tools/extract_published_events.py` using the same Python executable.
    """
    # Start extractor in background thread and return immediately with JSON
    script = pathlib.Path('tools') / 'extract_published_events.py'
    if not script.exists():
        return jsonify({'error': 'Extractor script not found: tools/extract_published_events.py'}), 404

    # If already running, return status
    if extractor_state.get('running'):
        return jsonify({'started': False, 'message': 'Extractor already running'}), 200

    # spawn background thread
    t = threading.Thread(target=_run_extractor_background, daemon=True)
    t.start()
    return jsonify({'started': True, 'message': 'Extractor started'}), 202


@app.route('/generate_status')
def generate_status():
    """Return current extractor status and small tails of logs."""
    state = dict(extractor_state)
    # attach small tails of logs if available
    try:
        if state.get('stdout_path') and os.path.exists(state['stdout_path']):
            with open(state['stdout_path'], 'r', encoding='utf-8') as f:
                data = f.read()
                state['stdout_tail'] = data[-300:]
        else:
            state['stdout_tail'] = ''
    except Exception:
        state['stdout_tail'] = ''
    try:
        if state.get('stderr_path') and os.path.exists(state['stderr_path']):
            with open(state['stderr_path'], 'r', encoding='utf-8') as f:
                data = f.read()
                state['stderr_tail'] = data[-300:]
        else:
            state['stderr_tail'] = ''
    except Exception:
        state['stderr_tail'] = ''

    return jsonify(state)


@app.route('/download/<path:filename>')
def download_file(filename: str):
    # only allow downloads from playwright_captures
    safe_dir = pathlib.Path('playwright_captures').resolve()
    target = (safe_dir / filename).resolve()
    if not str(target).startswith(str(safe_dir)):
        return "Not allowed", 403
    if not target.exists():
        return "Not found", 404
    return send_file(str(target), as_attachment=True)


@app.route('/__last_response')
def last_response():
    path = 'last_ics_response.html'
    if os.path.exists(path):
        return send_file(path)
    return "No last response saved.", 404


@app.route('/__saved/<path:fname>')
def saved_response(fname: str):
    # Only serve files that were created by our safe_name pattern
    if not fname.startswith("last_response_"):
        return "Not allowed", 403
    if os.path.exists(fname):
        return send_file(fname)
    return "Not found", 404


@app.route('/departures')
def departures_view():
    """Departure board style view - shows today's and tomorrow's classes by building."""
    from dateutil import parser as dtparser
    
    # Add tools directory to path for imports
    tools_dir = pathlib.Path(__file__).parent / 'tools'
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    
    try:
        from event_parser import parse_location, parse_title, parse_event
    except ImportError:
        from tools.event_parser import parse_location, parse_title, parse_event
    
    # Building list for the dropdown
    BUILDINGS = ['Baritiu', 'DAIC', 'Dorobantilor', 'Observatorului', 'Memorandumului']
    
    # Get selected building from query params (default: show all)
    selected_building = request.args.get('building', '').lower()
    
    # Load events
    events_file = pathlib.Path('playwright_captures/events.json')
    if not events_file.exists():
        return render_template('departures.html', 
                             events_by_day={}, 
                             buildings=BUILDINGS,
                             selected_building=selected_building,
                             current_time=datetime.now(),
                             error="No events file found. Please go to Admin to import a calendar.")
    
    with open(events_file, 'r', encoding='utf-8') as f:
        all_events = json.load(f)

    # Also append extracurricular events persisted in DB so they appear on the departure board
    try:
        init_db()
        extra_events = list_extracurricular_db()
        for xe in extra_events:
            d = xe.get('date')
            if not d:
                continue
            t = (xe.get('time') or '').strip()
            if t:
                start = f"{d}T{t}:00"
            else:
                start = d
            evt = {
                'title': xe.get('title'),
                'start': start,
                'end': None,
                'location': xe.get('location') or '',
                'organizer': xe.get('organizer') or '',
                'extracurricular': True,
                'color': '#7c3aed',
            }
            all_events.append(evt)
    except Exception:
        # ignore DB errors and continue with file-based events
        pass
    
    # Get current datetime
    now = datetime.now()
    today = now.date()
    tomorrow = today + timedelta(days=1)
    
    # Parse and filter events for today and tomorrow
    events_today = defaultdict(list)
    events_tomorrow = defaultdict(list)
    has_today_events = False
    
    for ev in all_events:
        start_str = ev.get('start')
        if not start_str:
            continue
        
        try:
            start_dt = dtparser.parse(start_str)
            if start_dt.tzinfo:
                start_dt = start_dt.replace(tzinfo=None)
        except Exception:
            continue
        
        event_date = start_dt.date()
        
        # Only today or tomorrow
        if event_date not in (today, tomorrow):
            continue
        
        # For today, only events that haven't ended yet
        if event_date == today:
            end_str = ev.get('end')
            if end_str:
                try:
                    end_dt = dtparser.parse(end_str)
                    if end_dt.tzinfo:
                        end_dt = end_dt.replace(tzinfo=None)
                    if end_dt < now:
                        continue  # Already ended
                except Exception:
                    pass
        
        # Parse location
        location = ev.get('location') or ''
        parsed_loc = parse_location(location)
        building_name = parsed_loc.get('building', '') or 'Other'
        building_code = building_name.lower() if building_name else 'other'
        room = parsed_loc.get('room', '') or ''
        
        # Filter by building if selected
        if selected_building and building_code != selected_building:
            continue
        
        # Parse title
        title = ev.get('title') or ''
        parsed_title = parse_title(title)
        
        # Build event info
        event_info = {
            'start': start_dt,
            'end_str': end_str if 'end_str' in dir() else ev.get('end'),
            'time': start_dt.strftime('%H:%M'),
            'subject': parsed_title.subject,
            'display_title': parsed_title.display_title,
            'professor': parsed_title.professor or '',
            'room': room,
            'room_display': room,
            'building_code': building_code,
            'building_name': building_name,
            'is_now': event_date == today and start_dt <= now,
            'date': event_date,
            'color': ev.get('color') if isinstance(ev, dict) else None,
        }
        
        if event_date == today:
            events_today[building_name].append(event_info)
            has_today_events = True
        else:
            events_tomorrow[building_name].append(event_info)
    
    # Sort events by start time within each building
    for building in events_today:
        events_today[building].sort(key=lambda x: x['start'])
    for building in events_tomorrow:
        events_tomorrow[building].sort(key=lambda x: x['start'])
    
    # Sort buildings alphabetically
    events_today = dict(sorted(events_today.items()))
    events_tomorrow = dict(sorted(events_tomorrow.items()))
    
    # Combine into structure for template
    events_by_day = {}
    if events_today:
        events_by_day['Astăzi'] = events_today
    if events_tomorrow:
        events_by_day['Mâine'] = events_tomorrow
    
    return render_template('departures.html',
                         events_by_day=events_by_day,
                         buildings=BUILDINGS,
                         selected_building=selected_building,
                         current_time=now,
                         has_today_events=has_today_events,
                         error=None)


# =============================================================================
# ADMIN ROUTES (Password Protected)
# =============================================================================

@app.route('/admin')
@require_admin
def admin_view():
    """Admin page for managing calendar imports and events - React version."""
    return render_template('admin_react.html')


@app.route('/admin/api/status', methods=['GET'])
@require_admin
def admin_api_status():
    """API endpoint returning admin status for React frontend."""
    calendars = []
    manual_events = []
    events_count = 0
    last_import = None
    
    try:
        init_db()
        calendars = list_calendar_urls()
        manual_events = list_manual_events_db()
        
        # Get events count from all events_*.json files
        out_dir = pathlib.Path('playwright_captures')
        event_files = list(out_dir.glob('events_*.json'))
        for ef in event_files:
            try:
                with open(ef, 'r', encoding='utf-8') as f:
                    events = json.load(f)
                    events_count += len(events)
                # Track latest import time
                mtime = ef.stat().st_mtime
                if last_import is None or mtime > last_import:
                    last_import = mtime
            except Exception:
                pass
        
        # Also check main events.json if it exists (fallback)
        events_file = pathlib.Path('playwright_captures/events.json')
        if events_file.exists() and not event_files:
            try:
                with open(events_file, 'r', encoding='utf-8') as f:
                    events = json.load(f)
                    events_count = len(events)
                last_import = events_file.stat().st_mtime
            except Exception:
                pass
    except Exception as e:
        pass
    
    return jsonify({
        'calendars': calendars,
        'manual_events': manual_events,
        'events_count': events_count,
        'last_import': last_import,
        'extractor_running': extractor_state.get('running', False),
        'extractor_progress': {
            'current_calendar': extractor_state.get('current_calendar'),
            'message': extractor_state.get('progress_message'),
            'events_extracted': extractor_state.get('events_extracted', 0),
        },
        'periodic_fetcher': {
            'started': _periodic_fetcher_started,
            'running': periodic_fetch_state.get('running', False),
            'last_run': periodic_fetch_state.get('last_run'),
            'last_success': periodic_fetch_state.get('last_success'),
            'interval_minutes': 60
        }
    })


@app.route('/admin/set_calendar_url', methods=['POST'])
@require_admin
def admin_set_calendar_url():
    """Save the calendar URL to config and immediately start importing events."""
    url = request.form.get('calendar_url', '').strip()
    name = request.form.get('calendar_name') or request.form.get('calendar_name', '')
    color = request.form.get('calendar_color') or request.form.get('calendar_color', None)
    
    # Check if this is an API call (wants JSON response)
    wants_json = request.headers.get('Accept', '').startswith('application/json') or request.is_json
    
    if not url:
        if wants_json:
            return jsonify({'success': False, 'error': 'URL is required'}), 400
        return redirect(url_for('admin_view'))

    # Ensure DB initialized and save calendar
    calendar_id = None
    try:
        init_db()
        calendar_id = add_calendar_url(url, name)
        # persist optional metadata (name/color)
        update_calendar_metadata(url, name=name, color=color)
    except Exception:
        # fallback to file if DB unavailable
        config_dir = pathlib.Path('config')
        config_dir.mkdir(exist_ok=True)
        config_file = config_dir / 'calendar_config.json'
        config = {}
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except Exception:
                pass
        config['calendar_url'] = url
        if name:
            config['calendar_name'] = name
        if color:
            config['calendar_color'] = color
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)

    # Immediately start importing events from this calendar in background
    if url and not extractor_state.get('running'):
        t = threading.Thread(target=_run_extractor_for_url, args=(url,), daemon=True)
        t.start()
        import_started = True
    else:
        import_started = False

    if wants_json:
        return jsonify({
            'success': True, 
            'calendar_id': calendar_id,
            'url': url,
            'name': name,
            'import_started': import_started,
            'message': 'Calendar added and import started' if import_started else 'Calendar added (import already in progress)'
        })
    
    return redirect(url_for('admin_view'))


@app.route('/admin/import_calendar', methods=['POST'])
@require_admin
def admin_import_calendar():
    """Trigger calendar import from the configured URL."""
    # Accept optional url, name, color fields and persist the calendar before import
    # Also accept calendar_id from JSON body to import a specific calendar
    url = request.form.get('calendar_url') or request.form.get('url')
    name = request.form.get('calendar_name') or request.form.get('name')
    color = request.form.get('calendar_color') or request.form.get('color')
    
    # Check JSON body for calendar_id
    calendar_id = None
    if request.is_json:
        json_data = request.get_json(silent=True) or {}
        calendar_id = json_data.get('calendar_id')
        if not url:
            url = json_data.get('url')
        if not name:
            name = json_data.get('name')

    # If calendar_id provided, fetch URL from database
    if calendar_id and not url:
        try:
            init_db()
            calendars = list_calendar_urls()
            for cal in calendars:
                if cal.get('id') == calendar_id:
                    url = cal.get('url')
                    break
        except Exception:
            pass

    if url:
        try:
            init_db()
            add_calendar_url(url, name)
            # update metadata (name/color) in case the calendar already existed
            update_calendar_metadata(url, name=name, color=color)
        except Exception:
            pass

    if extractor_state.get('running'):
        return jsonify({'success': False, 'message': 'Import already in progress'}), 200

    # Update extractor state to show we're starting
    extractor_state['running'] = True
    extractor_state['progress_message'] = 'Starting import...'
    extractor_state['events_extracted'] = 0
    extractor_state['current_calendar'] = name or 'calendar'

    # Start extractor in background - use URL if provided, else default
    if url:
        t = threading.Thread(target=_run_extractor_for_url, args=(url, name), daemon=True)
    else:
        t = threading.Thread(target=_run_extractor_background, daemon=True)
    t.start()

    return jsonify({'success': True, 'message': 'Import started', 'url': url}), 202


@app.route('/admin/add_event', methods=['POST'])
@require_admin
def admin_add_event():
    """Manually add an event."""
    from dateutil import parser as dtparser
    
    title = request.form.get('title', '').strip()
    start_date = request.form.get('start_date', '')
    start_time = request.form.get('start_time', '')
    end_time = request.form.get('end_time', '')
    location = request.form.get('location', '').strip()
    building = request.form.get('building', '').strip()
    room = request.form.get('room', '').strip()
    
    if not title or not start_date or not start_time:
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400
    
    # Build location string if building/room provided
    if building and room and not location:
        location = f"utcn_room_ac_{building}_{room}@campus.utcluj.ro"
    
    # Parse datetime
    try:
        start_str = f"{start_date}T{start_time}:00+02:00"
        end_str = f"{start_date}T{end_time}:00+02:00" if end_time else None
    except Exception as e:
        return jsonify({'success': False, 'message': f'Invalid date/time: {e}'}), 400
    
    # Store manual event in DB and also append to playwright_captures/events.json for compatibility
    try:
        init_db()
        new_event = {
            'start': start_str,
            'end': end_str,
            'title': title,
            'location': location,
            'raw': {'manual': True},
            'created_at': datetime.now().isoformat()
        }
        ev_id = add_manual_event_db(new_event)
        # Append to playwright_captures/events.json as before
        events_file = pathlib.Path('playwright_captures/events.json')
        events = []
        if events_file.exists():
            try:
                with open(events_file, 'r', encoding='utf-8') as f:
                    events = json.load(f)
            except Exception:
                events = []
        events.append(new_event)
        events_file.parent.mkdir(exist_ok=True)
        with open(events_file, 'w', encoding='utf-8') as f:
            json.dump(events, f, indent=2, ensure_ascii=False)
        return jsonify({'success': True, 'message': 'Event added successfully', 'id': ev_id})
    except Exception:
        # fallback to previous file-only behavior
        events_file = pathlib.Path('playwright_captures/events.json')
        events = []
        if events_file.exists():
            try:
                with open(events_file, 'r', encoding='utf-8') as f:
                    events = json.load(f)
            except Exception:
                events = []
        new_event = {
            'start': start_str,
            'end': end_str,
            'title': title,
            'location': location,
            'raw': {'manual': True}
        }
        events.append(new_event)
        events_file.parent.mkdir(exist_ok=True)
        with open(events_file, 'w', encoding='utf-8') as f:
            json.dump(events, f, indent=2, ensure_ascii=False)
        return jsonify({'success': True, 'message': 'Event added successfully'})


@app.route('/admin/delete_event', methods=['POST'])
@require_admin
def admin_delete_event():
    """Delete an event by index."""
    try:
        index = int(request.form.get('index', -1))
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid index'}), 400
    
    events_file = pathlib.Path('playwright_captures/events.json')
    if not events_file.exists():
        return jsonify({'success': False, 'message': 'No events file'}), 404
    
    with open(events_file, 'r', encoding='utf-8') as f:
        events = json.load(f)
    
    if index < 0 or index >= len(events):
        return jsonify({'success': False, 'message': 'Index out of range'}), 400
    
    events.pop(index)
    
    with open(events_file, 'w', encoding='utf-8') as f:
        json.dump(events, f, indent=2, ensure_ascii=False)
    
    return jsonify({'success': True, 'message': 'Event deleted'})


@app.route('/admin/delete_calendar', methods=['POST'])
@require_admin
def admin_delete_calendar():
    """Delete a configured calendar by id (returns JSON)."""
    try:
        cal_id = int(request.form.get('id', -1))
    except Exception:
        return jsonify({'success': False, 'message': 'Invalid calendar id'}), 400

    try:
        init_db()
        
        # 1. Get URL to identify files to delete
        url = None
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute('SELECT url FROM calendars WHERE id = ?', (cal_id,))
            row = cur.fetchone()
            if row:
                url = row['url']
        
        if url:
            # 2. Delete associated files
            try:
                h = hashlib.sha1(url.encode('utf-8')).hexdigest()[:8]
                out_dir = pathlib.Path('playwright_captures')
                
                # Delete events file
                events_file = out_dir / f'events_{h}.json'
                if events_file.exists():
                    events_file.unlink()
                
                # Delete log files
                (out_dir / f'extract_{h}.stdout.txt').unlink(missing_ok=True)
                (out_dir / f'extract_{h}.stderr.txt').unlink(missing_ok=True)
                
                # 3. Update calendar_map.json
                map_path = out_dir / 'calendar_map.json'
                if map_path.exists():
                    try:
                        with open(map_path, 'r', encoding='utf-8') as f:
                            cmap = json.load(f)
                        if h in cmap:
                            del cmap[h]
                            with open(map_path, 'w', encoding='utf-8') as f:
                                json.dump(cmap, f, indent=2)
                    except Exception:
                        pass
            except Exception as e:
                print(f"Error cleaning up files for calendar {cal_id}: {e}")

        # 4. Delete from DB
        delete_calendar_db(cal_id)
        
        # 5. Regenerate merged events and schedule
        today = date.today()
        ensure_schedule(today, today + timedelta(days=7))
        
        return jsonify({'success': True, 'message': 'Calendar deleted and events removed'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to delete calendar: {e}'}), 500


@app.route('/admin/update_calendar_color', methods=['POST'])
@require_admin
def admin_update_calendar_color():
    """Update the color of a calendar by id (returns JSON)."""
    try:
        cal_id = int(request.form.get('id', -1))
        color = request.form.get('color', '').strip()
    except Exception:
        return jsonify({'success': False, 'message': 'Invalid parameters'}), 400

    if not color:
        return jsonify({'success': False, 'message': 'Color is required'}), 400

    try:
        init_db()
        with get_db_connection() as conn:
            cur = conn.cursor()
            # Get the URL for this calendar
            cur.execute('SELECT url FROM calendars WHERE id = ?', (cal_id,))
            row = cur.fetchone()
            if not row:
                return jsonify({'success': False, 'message': 'Calendar not found'}), 404
            url = row['url']
            # Update the color
            cur.execute('UPDATE calendars SET color = ? WHERE id = ?', (color, cal_id))
            conn.commit()
        
        # Also update calendar_map.json
        import hashlib
        h = hashlib.sha1(url.encode('utf-8')).hexdigest()[:8]
        map_path = pathlib.Path('playwright_captures') / 'calendar_map.json'
        if map_path.exists():
            try:
                with open(map_path, 'r', encoding='utf-8') as f:
                    cmap = json.load(f)
                if h in cmap:
                    cmap[h]['color'] = color
                    with open(map_path, 'w', encoding='utf-8') as f:
                        json.dump(cmap, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
        
        return jsonify({'success': True, 'message': 'Color updated'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to update color: {e}'}), 500


@app.route('/admin/update_calendar', methods=['POST'])
@require_admin
def admin_update_calendar():
    """Update a calendar's name, color, and enabled status (returns JSON)."""
    try:
        cal_id = int(request.form.get('id', -1))
        name = request.form.get('name', '').strip()
        color = request.form.get('color', '').strip()
        enabled = request.form.get('enabled', '1')
        enabled_bool = enabled in ('1', 'true', 'on', 'True')
    except Exception:
        return jsonify({'success': False, 'message': 'Invalid parameters'}), 400

    try:
        init_db()
        with get_db_connection() as conn:
            cur = conn.cursor()
            # Get the URL for this calendar
            cur.execute('SELECT url FROM calendars WHERE id = ?', (cal_id,))
            row = cur.fetchone()
            if not row:
                return jsonify({'success': False, 'message': 'Calendar not found'}), 404
            url = row['url']
            
            # Update the calendar
            cur.execute('UPDATE calendars SET name = ?, color = ?, enabled = ? WHERE id = ?', 
                       (name, color or None, 1 if enabled_bool else 0, cal_id))
            conn.commit()
        
        # Also update calendar_map.json
        h = hashlib.sha1(url.encode('utf-8')).hexdigest()[:8]
        map_path = pathlib.Path('playwright_captures') / 'calendar_map.json'
        if map_path.exists():
            try:
                with open(map_path, 'r', encoding='utf-8') as f:
                    cmap = json.load(f)
                if h in cmap:
                    cmap[h]['name'] = name
                    cmap[h]['color'] = color
                    with open(map_path, 'w', encoding='utf-8') as f:
                        json.dump(cmap, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
        
        # Update events in events_{h}.json with new color
        if color:
            events_file = pathlib.Path('playwright_captures') / f'events_{h}.json'
            if events_file.exists():
                try:
                    with open(events_file, 'r', encoding='utf-8') as f:
                        events = json.load(f)
                    for ev in events:
                        ev['color'] = color
                    with open(events_file, 'w', encoding='utf-8') as f:
                        json.dump(events, f, indent=2, ensure_ascii=False, default=str)
                except Exception:
                    pass
            
            # Regenerate merged events.json
            try:
                today = date.today()
                ensure_schedule(today, today + timedelta(days=7))
            except Exception:
                pass
        
        return jsonify({'success': True, 'message': 'Calendar updated'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to update calendar: {e}'}), 500


@app.route('/admin/delete_manual', methods=['POST'])
@require_admin
def admin_delete_manual():
    """Delete a manual event by id (returns JSON)."""
    try:
        man_id = int(request.form.get('id', -1))
    except Exception:
        return jsonify({'success': False, 'message': 'Invalid event id'}), 400

    try:
        init_db()
        delete_manual_db(man_id)
        return jsonify({'success': True, 'message': 'Manual event deleted'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to delete manual event: {e}'}), 500


# =============================================================================
# EXTRACURRICULAR EVENTS ROUTES
# =============================================================================

@app.route('/events')
def extracurricular_events_view():
    """View extracurricular events."""
    # Read events from DB
    try:
        init_db()
        events = list_extracurricular_db()
    except Exception:
        # fallback to file
        events_file = pathlib.Path('config/extracurricular_events.json')
        events = []
        if events_file.exists():
            try:
                with open(events_file, 'r', encoding='utf-8') as f:
                    events = json.load(f)
            except Exception:
                events = []
    
    # Sort by date
    from dateutil import parser as dtparser
    for ev in events:
        try:
            ev['_date'] = dtparser.parse(ev.get('date', ''))
        except:
            ev['_date'] = datetime.max
    events.sort(key=lambda x: x['_date'])
    
    # Get unique categories for filtering
    categories = sorted(set(ev.get('category', 'Other') for ev in events))
    
    # Parse titles so UI shows cleaned/display titles (apply subject parsing rules)
    try:
        from tools.event_parser import parse_title
        for ev in events:
            try:
                parsed = parse_title(ev.get('title', '') or '')
                ev['display_title'] = parsed.display_title
                ev['subject'] = parsed.subject
            except Exception:
                ev['display_title'] = ev.get('title')
                ev['subject'] = ev.get('subject', '')
    except Exception:
        # If parser not available, fallback to raw title
        for ev in events:
            ev['display_title'] = ev.get('title')
            ev['subject'] = ev.get('subject', '')

    return render_template('extracurricular.html', events=events, categories=categories)


@app.route('/events/add', methods=['POST'])
def add_extracurricular_event():
    """Add a new extracurricular event."""
    title = request.form.get('title', '').strip()
    organizer = request.form.get('organizer', '').strip()
    date_str = request.form.get('date', '').strip()
    time_str = request.form.get('time', '').strip()
    location = request.form.get('location', '').strip()
    category = request.form.get('category', '').strip()
    description = request.form.get('description', '').strip()
    
    if not title or not date_str:
        return jsonify({'success': False, 'message': 'Title and date are required'}), 400
    
    # Store in DB
    try:
        init_db()
        new_event = {
            'title': title,
            'organizer': organizer,
            'date': date_str,
            'time': time_str,
            'location': location,
            'category': category or 'Other',
            'description': description,
            'created_at': datetime.now().isoformat()
        }
        ev_id = add_extracurricular_db(new_event)
        return jsonify({'success': True, 'message': 'Event added successfully', 'id': ev_id})
    except Exception:
        # fallback to file-based storage
        events_file = pathlib.Path('config/extracurricular_events.json')
        events_file.parent.mkdir(exist_ok=True)
        events = []
        if events_file.exists():
            try:
                with open(events_file, 'r', encoding='utf-8') as f:
                    events = json.load(f)
            except Exception:
                events = []
        new_event = {
            'id': len(events) + 1,
            'title': title,
            'organizer': organizer,
            'date': date_str,
            'time': time_str,
            'location': location,
            'category': category or 'Other',
            'description': description,
            'created_at': datetime.now().isoformat()
        }
        events.append(new_event)
        with open(events_file, 'w', encoding='utf-8') as f:
            json.dump(events, f, indent=2, ensure_ascii=False)
        return jsonify({'success': True, 'message': 'Event added successfully'})


@app.route('/events/delete', methods=['POST'])
def delete_extracurricular_event():
    """Delete an extracurricular event."""
    try:
        event_id = int(request.form.get('id', -1))
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid event ID'}), 400
    
    # Try DB deletion first
    try:
        init_db()
        delete_extracurricular_db(event_id)
        return jsonify({'success': True, 'message': 'Event deleted'})
    except Exception:
        # fallback to file
        events_file = pathlib.Path('config/extracurricular_events.json')
        if not events_file.exists():
            return jsonify({'success': False, 'message': 'No events file'}), 404
        with open(events_file, 'r', encoding='utf-8') as f:
            events = json.load(f)
        events = [ev for ev in events if ev.get('id') != event_id]
        with open(events_file, 'w', encoding='utf-8') as f:
            json.dump(events, f, indent=2, ensure_ascii=False)
        return jsonify({'success': True, 'message': 'Event deleted'})


# ─────────────────────────────────────────────────────────────────────────────
# React SPA frontend routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/frontend/<path:filename>')
def frontend_static(filename):
    """Serve built frontend assets from frontend/dist."""
    frontend_dist = pathlib.Path(__file__).parent / 'frontend' / 'dist'
    return send_file(frontend_dist / filename)


@app.route('/departures.json')
def departures_json():
    """Return events for today and tomorrow as JSON for the departures board."""
    from dateutil import parser as dtparser
    
    today = date.today()
    tomorrow = today + timedelta(days=1)
    
    # Load events from schedule
    events_file = pathlib.Path('playwright_captures/events.json')
    all_events = []
    
    if events_file.exists():
        with open(events_file, 'r', encoding='utf-8') as f:
            try:
                loaded = json.load(f)
            except Exception:
                loaded = []
            # mark origin for debugging
            for it in loaded:
                if isinstance(it, dict):
                    it.setdefault('_origin', 'events_json')
            all_events = loaded
    
    # Also load from schedule_by_room.json if available
    schedule_file = pathlib.Path('playwright_captures/schedule_by_room.json')
    if schedule_file.exists():
        with open(schedule_file, 'r', encoding='utf-8') as f:
            schedule = json.load(f)
        for room, days in schedule.items():
            for day, evs in days.items():
                for e in evs:
                    e['room'] = room
                    # mark origin for debugging
                    if isinstance(e, dict):
                        e.setdefault('_origin', 'schedule_by_room')
                    all_events.append(e)
    
    # Add extracurricular events from DB
    try:
        init_db()
        extra_events = list_extracurricular_db()
        for xe in extra_events:
            d = xe.get('date')
            if not d:
                continue
            t = (xe.get('time') or '').strip()
            start = f"{d}T{t}:00" if t else d
            evt = {
                'title': xe.get('title'),
                'start': start,
                'end': None,
                'location': xe.get('location') or '',
                'room': xe.get('location') or '',
                'color': '#7c3aed',
                'extracurricular': True,
                '_origin': 'extracurricular',
            }
            all_events.append(evt)
    except Exception:
        pass
    
    # Add manual events from DB
    try:
        manual = list_manual_events_db()
        for me in manual:
            evt = {
                'title': me.get('title'),
                'start': me.get('start'),
                'end': me.get('end'),
                'location': me.get('location') or '',
                'room': me.get('location') or '',
                'color': '#004080',
                'manual': True,
                '_origin': 'manual',
            }
            all_events.append(evt)
    except Exception:
        pass
    
    # Filter for today and tomorrow
    filtered = []
    for ev in all_events:
        start_str = ev.get('start')
        if not start_str:
            continue
        try:
            start_dt = dtparser.parse(start_str)
            event_date = start_dt.date()
            if event_date in (today, tomorrow):
                filtered.append(ev)
        except Exception:
            continue

    # Deduplicate events: events.json may contain the same items as schedule_by_room.json
    # Use raw.ItemId.Id when available, otherwise fallback to title|start|location key.
    # Improved deduplication: prefer events with more populated fields when duplicates
    deduped = []
    seen_map = {}  # map key_start_loc -> index in deduped
    # Prepare duplicates debug file
    try:
        debug_out_dir = pathlib.Path('playwright_captures')
        debug_out_dir.mkdir(parents=True, exist_ok=True)
        dup_log_path = debug_out_dir / 'duplicates_debug.jsonl'
    except Exception:
        dup_log_path = None

    def _log_duplicate(existing, incoming, key, reason=''):
        try:
            if not dup_log_path:
                return
            import time, json
            rec = {
                'ts': datetime.utcnow().isoformat(),
                'key': key,
                'reason': reason,
                'existing': {
                    'title': existing.get('title'),
                    'start': existing.get('start'),
                    'room': existing.get('room'),
                    'origin': existing.get('_origin') if isinstance(existing, dict) else None,
                },
                'incoming': {
                    'title': incoming.get('title'),
                    'start': incoming.get('start'),
                    'room': incoming.get('room'),
                    'origin': incoming.get('_origin') if isinstance(incoming, dict) else None,
                }
            }
            with open(dup_log_path, 'a', encoding='utf-8') as df:
                df.write(json.dumps(rec, ensure_ascii=False) + '\n')
        except Exception:
            pass
    import re

    def _normalize_location_for_key(ev: dict) -> str:
        """Return a compact location token suitable for dedupe keys.

        Prefer structured 'room' when present. Otherwise try to extract a
        reasonable room token from the free-form 'location' string (e.g.
        'Sala 40', 'Room 40', last numeric token). Fall back to the raw
        location trimmed.
        """
        room = (ev.get('room') or '').strip()
        if room:
            return room
        loc = (ev.get('location') or '').strip()
        if not loc:
            return ''
        # try common patterns
        m = re.search(r'sala\s*([A-Za-z0-9\-]+)', loc, flags=re.IGNORECASE)
        if m:
            return m.group(1)
        m = re.search(r'room\s*([A-Za-z0-9\-]+)', loc, flags=re.IGNORECASE)
        if m:
            return m.group(1)
        # last numeric token
        nums = re.findall(r'(\d+[A-Za-z\-]?)', loc)
        if nums:
            return nums[-1]
        # fallback: use trimmed, lowercased location (shortened)
        return loc.lower()
    for ev in filtered:
        try:
            raw = ev.get('raw') or {}
            iid = None
            if isinstance(raw, dict):
                try:
                    iid = raw.get('ItemId', {}).get('Id') if raw.get('ItemId') else None
                except Exception:
                    iid = None

            # If ItemId available, use a dedicated key
            if iid:
                pkey = f'ID:{iid}'
                if pkey in seen_map:
                    # compare scores and replace if new event is richer
                    idx = seen_map[pkey]
                    existing = deduped[idx]
                    def score(x):
                        return int(bool(x.get('room'))) + int(bool(x.get('professor'))) + int(bool(x.get('calendar_name'))) + int(bool(x.get('subject')))
                    if score(ev) > score(existing):
                        _log_duplicate(existing, ev, pkey, reason='iid_better_score')
                        deduped[idx] = ev
                else:
                    seen_map[pkey] = len(deduped)
                    deduped.append(ev)
                continue

            start = str(ev.get('start') or '').strip()
            loc = _normalize_location_for_key(ev)
            norm_title = str(ev.get('title') or '').strip().lower()
            key_start_loc = f'SL:{start}|{loc}'

            if key_start_loc in seen_map:
                idx = seen_map[key_start_loc]
                existing = deduped[idx]
                def score(x):
                    return int(bool(x.get('room'))) + int(bool(x.get('professor'))) + int(bool(x.get('calendar_name'))) + int(bool(x.get('subject')))
                if score(ev) > score(existing):
                    _log_duplicate(existing, ev, key_start_loc, reason='sl_better_score')
                    deduped[idx] = ev
                # else keep existing
            else:
                seen_map[key_start_loc] = len(deduped)
                deduped.append(ev)
        except Exception:
            deduped.append(ev)
    filtered = deduped
    
    # ensure buildings var exists even if enrichment fails
    buildings = {}

    # Enrich events with calendar_name and parsed group/year when possible
    try:
        map_path = pathlib.Path('playwright_captures') / 'calendar_map.json'
        cmap = {}
        if map_path.exists():
            try:
                with open(map_path, 'r', encoding='utf-8') as mf:
                    cmap = json.load(mf)
            except Exception:
                cmap = {}
        # load parser utilities (for group/year, and richer location/title parsing)
        try:
            from tools.event_parser import parse_group_from_string, parse_event
        except Exception:
            parse_group_from_string = None
            parse_event = None

        for ev in filtered:
            try:
                src = ev.get('source')
                if src and cmap.get(src) and cmap.get(src).get('name'):
                    ev['calendar_name'] = cmap.get(src).get('name')
                else:
                    ev['calendar_name'] = ev.get('calendar_name') if ev.get('calendar_name') is not None else None

                # Enrich event using backend parser when available. This ensures we have
                # structured 'room' and 'building' values instead of free-form location strings.
                if parse_event:
                    try:
                        parsed = parse_event(ev)
                        # prefer parsed structured values (room/building) when available
                        ev['room'] = (parsed.get('room') or ev.get('room') or '')
                        ev['building'] = (parsed.get('building') or ev.get('building') or '')
                        ev['professor'] = (parsed.get('professor') or ev.get('professor') or None)
                        ev['subject'] = (parsed.get('subject') or ev.get('subject') or ev.get('title'))
                        ev['display_title'] = (parsed.get('display_title') or ev.get('display_title') or ev.get('title'))
                    except Exception:
                        # ignore parsing failure per-event
                        ev['room'] = ev.get('room') or ''
                        ev['building'] = ev.get('building') or ''
                else:
                    ev['room'] = ev.get('room') or ''
                    ev['building'] = ev.get('building') or ''

                # parse group/year
                sample = ev.get('calendar_name') or ev.get('subject') or ev.get('title') or ''
                if parse_group_from_string:
                    try:
                        grp = parse_group_from_string(sample)
                        if grp and isinstance(grp, dict):
                            ev['year'] = grp.get('year', '')
                            ev['group'] = grp.get('group', '')
                            ev['group_display'] = grp.get('display', '')
                        else:
                            ev['year'] = ''
                            ev['group'] = ''
                            ev['group_display'] = ''
                    except Exception:
                        ev['year'] = ''
                        ev['group'] = ''
                        ev['group_display'] = ''
                else:
                    ev['year'] = ev.get('year', '') or ''
                    ev['group'] = ev.get('group', '') or ''
                    ev['group_display'] = ev.get('group_display', '') or ''
            except Exception:
                # tolerate per-event failures
                ev['calendar_name'] = ev.get('calendar_name') if ev.get('calendar_name') is not None else None
                ev['year'] = ev.get('year', '') or ''
                ev['group'] = ev.get('group', '') or ''
                ev['group_display'] = ev.get('group_display', '') or ''

    except Exception:
        # ignore enrichment failures
        pass

    # Extract buildings from enriched events (prefer structured 'building' field)
    buildings = {}
    for ev in filtered:
        b = (ev.get('building') or '').strip()
        # normalize empty vs None
        if b:
            # keep unique canonical building names
            if b not in buildings:
                buildings[b] = b
        else:
            # fallback: try to extract building code from room (e.g. BT503 -> BT)
            room = (ev.get('room') or '').strip()
            if room:
                import re
                m = re.match(r'^([A-Z]{1,3})', room.upper())
                if m:
                    code = m.group(1)
                    if code not in buildings:
                        buildings[code] = code
    
    return jsonify({
        'events': filtered,
        'buildings': buildings,
        'today': today.isoformat(),
        'tomorrow': tomorrow.isoformat()
    })


if __name__ == "__main__":
    # Periodic fetcher is already started at module import level
    # (see start_periodic_fetcher_if_needed call above)

    # Initialize DB and migrate any existing JSON configuration into it
    try:
        init_db()
        migrate_from_files()
        print('Initialized DB and migrated existing configs (if any).')
    except Exception:
        print('DB initialization or migration failed; continuing with file-based config if present.')

    # Disable the auto-reloader to avoid Playwright event-loop lifecycle issues
    # when the Flask debug reloader spawns child processes.
    # Allow overriding the port using the PORT environment variable so the
    # server can be started on a different port when 5000 is in use by the
    # system (e.g. macOS AirPlay Receiver). Default remains 5000.
    import os
    port = int(os.environ.get('PORT', '5000'))
    app.run(debug=True, use_reloader=False, port=port)
