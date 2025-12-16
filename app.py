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
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional

from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify

from timetable import (
    Event,
    find_ics_url_from_html,
    fetch,
    parse_ics_from_url,
    parse_microformat_vevents,
)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET", "dev-secret")


def group_events(events: List[Event], from_date: date, to_date: date):
    groups = defaultdict(list)
    for e in sorted(events, key=lambda ev: ev.start):
        if e.start.date() < from_date or e.start.date() > to_date:
            continue
        groups[e.start.date()].append(e)
    return groups


@app.route("/", methods=["GET"])
def index():
    # Redirect root to the schedule view — we no longer show the URL upload page
    return redirect(url_for('schedule_view'))


@app.route("/fetch", methods=["POST"])
def fetch_route():
    url = request.form.get("url", "").strip()
    days = int(request.form.get("days") or 7)
    from_s = request.form.get("from")
    to_s = request.form.get("to")

    today = date.today()
    if from_s:
        from_date = date.fromisoformat(from_s)
    else:
        from_date = today
    if to_s:
        to_date = date.fromisoformat(to_s)
    else:
        to_date = from_date + timedelta(days=days - 1)

    events: List[Event] = []

    # If file uploaded, parse it
    ics_file = request.files.get("icsfile")
    if ics_file and ics_file.filename:
        content = ics_file.read().decode("utf-8")
        try:
            # parse via parse_ics_from_url by saving temp file and calling it
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=".ics")
            tf.write(content.encode("utf-8"))
            tf.close()
            # reuse parse_ics_from_url by passing file:// path won't work; instead, parse here
            events = parse_ics_direct(content)
        finally:
            try:
                os.unlink(tf.name)
            except Exception:
                pass
    elif url:
        render_flag = bool(request.form.get("render"))

        diagnostics = {}
        if render_flag:
            # Try headless render to find .ics or calendar network responses
            try:
                ics_candidates, saved_files = render_and_find_ics(url)
            except Exception as e:
                return render_template("results.html", error=f"Render failed: {e}")

            # try each candidate
            diagnostics["candidates"] = ics_candidates
            diagnostics["saved_files"] = saved_files
            for cand in ics_candidates:
                try:
                    events = parse_ics_from_url(cand, verbose=True)
                    diagnostics["used_candidate"] = cand
                    break
                except Exception:
                    events = []

            if not events:
                # fetch static HTML as fallback
                try:
                    html = fetch(url)
                except Exception as e:
                    return render_template("results.html", error=f"Failed to fetch URL: {e}")
                events = parse_microformat_vevents(html)
                # include last response file if it exists
                if os.path.exists("last_ics_response.html"):
                    diagnostics["last_response_file"] = "last_ics_response.html"
        else:
            try:
                html = fetch(url)
            except Exception as e:
                return render_template("results.html", error=f"Failed to fetch URL: {e}")

            ics_url = find_ics_url_from_html(html, url)
            if ics_url:
                try:
                    events = parse_ics_from_url(ics_url, verbose=True)
                except Exception:
                    # fallback
                    events = parse_microformat_vevents(html)
            else:
                events = parse_microformat_vevents(html)
    else:
        return redirect(url_for("index"))

    grouped = group_events(events, from_date, to_date)
    # Apply subject parsing to events so templates can show cleaned/display titles
    try:
        from tools.subject_parser import parse_title
        for day, evs in grouped.items():
            for ev in evs:
                try:
                    parsed = parse_title(ev.title or '')
                    # attach display_title and subject to Event instance for templates
                    setattr(ev, 'display_title', parsed.display_title)
                    setattr(ev, 'subject', parsed.subject_name)
                    # if professor not set, use parsed professor
                    if not getattr(ev, 'professor', None) and parsed.professor:
                        setattr(ev, 'professor', parsed.professor)
                except Exception:
                    setattr(ev, 'display_title', ev.title)
                    setattr(ev, 'subject', '')
    except Exception:
        # parser not available — ignore
        pass
    return render_template("results.html", grouped=grouped, from_date=from_date, to_date=to_date, diagnostics=diagnostics)


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
        # include untagged events.json if present
        generic = out_dir / 'events.json'
        if generic.exists():
            parts.insert(0, generic)
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
            # save merged file
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
    with get_db_connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute('INSERT OR IGNORE INTO calendars (url, name, color, enabled, created_at) VALUES (?, ?, ?, 1, ?)',
                        (url, name or '', None, datetime.now().isoformat()))
            conn.commit()
        except Exception:
            pass

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
        cur.execute('SELECT id, url, name, enabled, created_at, last_fetched FROM calendars ORDER BY id')
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


def _run_extractor_for_url(url: str) -> int:
    """Run the extractor script for a specific URL (uses CLI arg). Returns returncode."""
    out_dir = pathlib.Path('playwright_captures')
    out_dir.mkdir(exist_ok=True)
    h = hashlib.sha1(url.encode('utf-8')).hexdigest()[:8]
    stdout_path = out_dir / f'extract_{h}.stdout.txt'
    stderr_path = out_dir / f'extract_{h}.stderr.txt'
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
            h = h = hashlib.sha1(url.encode('utf-8')).hexdigest()[:8]
            ev_out = out_dir / f'events_{h}.json'
            try:
                with open(ev_in, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = []

            # attach source id to each event
            for it in data:
                try:
                    it['source'] = h
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
            urls = []
            try:
                rows = list_calendar_urls()
                for r in rows:
                    if r.get('enabled') and r.get('url'):
                        urls.append(r.get('url'))
            except Exception:
                urls = []

            # If no URLs configured, skip
            if not urls:
                periodic_fetch_state['running'] = False
                _periodic_lock.release()
                continue

            # Run extractor for each URL sequentially
            any_success = False
            for u in urls:
                rc = _run_extractor_for_url(u)
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



@app.route('/schedule', methods=['GET', 'POST'])
def schedule_view():
    # form inputs
    from_s = request.values.get('from')
    to_s = request.values.get('to')
    today = date.today()
    if from_s:
        from_date = date.fromisoformat(from_s)
    else:
        from_date = today
    if to_s:
        to_date = date.fromisoformat(to_s)
    else:
        # default to 7-day range when `to` not provided
        to_date = from_date + timedelta(days=6)

    try:
        jpath, cpath = ensure_schedule(from_date, to_date)
    except Exception as e:
        return render_template('results.html', error=f'Failed to build schedule: {e}')

    # load JSON schedule (full)
    with open(jpath, 'r', encoding='utf-8') as f:
        schedule = json.load(f)

    # preserve original full schedule for dropdown population
    full_schedule = schedule

    # optional filters
    subject_filter = (request.values.get('subject') or '').strip()
    professor_filter = (request.values.get('professor') or '').strip()
    room_filter = (request.values.get('room') or '').strip()

    # apply filters to create a filtered schedule for display
    sf = subject_filter.lower()
    pf = professor_filter.lower()
    rf = room_filter.lower()
    if sf or pf or rf:
        filtered = {}
        for room, days in schedule.items():
            ndays = {}
            for day, evs in days.items():
                new_evs = []
                for e in evs:
                    title = (e.get('title') or '')
                    subj = (e.get('subject') or '')
                    prof_field = (e.get('professor') or '')
                    hay = (title + ' ' + subj).lower()
                    prof_hay = prof_field.lower() if prof_field else title.lower()
                    ok = True
                    if sf and sf not in hay:
                        ok = False
                    if pf and pf not in prof_hay:
                        ok = False
                    if rf and rf not in room.lower():
                        ok = False
                    if ok:
                        new_evs.append(e)
                if new_evs:
                    ndays[day] = new_evs
            if ndays:
                filtered[room] = ndays
        schedule = filtered

    # Extract available subjects, professors and rooms for dropdowns from the full schedule
    subjects = set()
    professors = set()
    rooms = set()
    for room, days in full_schedule.items():
        rooms.add(room)
        for day, evs in days.items():
            for e in evs:
                title = e.get('title') or ''
                subj = e.get('subject') or ''
                prof = e.get('professor') or ''

                # Prefer parser-derived subject/display_title when available
                try:
                    from tools.subject_parser import parse_title
                    parsed = parse_title(e.get('display_title') or title)
                    if parsed and parsed.subject_name:
                        subj = parsed.subject_name
                        # update schedule entry for consistency
                        e['subject'] = subj
                        e['display_title'] = parsed.display_title
                    if not prof and parsed and parsed.professor:
                        prof = parsed.professor
                        e['professor'] = prof
                except Exception:
                    # parser not available — keep raw values
                    pass

                if subj:
                    subjects.add(subj)
                if prof:
                    professors.add(prof)
                else:
                    # fallback: rudimentary professor heuristic: look for two capitalized words in title
                    import re
                    m = re.search(r"\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b", title)
                    if m:
                        professors.add(m.group(1))

    subjects = sorted(s for s in subjects if s)
    professors = sorted(p for p in professors if p)
    rooms = sorted(r for r in rooms if r)

    # schedule is { room: { date: [ {start,end,title,subject,location}, ... ] } }
    return render_template('schedule.html', schedule=schedule, from_date=from_date, to_date=to_date, subject=subject_filter, professor=professor_filter, subjects=subjects, professors=professors, rooms=rooms, room=room_filter)



@app.route('/events.json')
def events_json():
    """Return flattened events for FullCalendar or API clients.

    Query params: from, to, subject, professor
    """
    from_s = request.values.get('from')
    to_s = request.values.get('to')
    subject_filter = (request.values.get('subject') or '').strip().lower()
    professor_filter = (request.values.get('professor') or '').strip().lower()
    room_filter = (request.values.get('room') or '').strip().lower()
    today = date.today()
    try:
        from_date = date.fromisoformat(from_s) if from_s else today
    except Exception:
        from_date = today
    try:
        to_date = date.fromisoformat(to_s) if to_s else from_date + timedelta(days=6)
    except Exception:
        to_date = from_date + timedelta(days=6)

    # ensure schedule exists
    try:
        jpath, cpath = ensure_schedule(from_date, to_date)
    except Exception:
        return jsonify({'error': 'schedule not available'}), 500

    with open(jpath, 'r', encoding='utf-8') as f:
        schedule = json.load(f)

    events = []
    for room, days in schedule.items():
        for day, evs in days.items():
            for e in evs:
                start = e.get('start')
                end = e.get('end')
                title = e.get('title') or ''
                subject = (e.get('subject') or '')
                location = e.get('location') or ''
                # use stored professor when available, otherwise fallback to a heuristic
                prof = e.get('professor') or ''
                if not prof:
                    import re
                    m = re.search(r"\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b", title)
                    if m:
                        prof = m.group(1)

                hay = (title + ' ' + subject).lower()
                if subject_filter and subject_filter not in hay:
                    continue
                if professor_filter and professor_filter not in (prof or '').lower():
                    continue
                if room_filter and room_filter not in room.lower():
                    continue

                ev = {
                    'title': title,
                    'display_title': e.get('display_title') or title,
                    'start': start,
                    'end': end,
                    'room': room,
                    'subject': subject,
                    'professor': prof,
                    'location': location,
                    'color': None,
                    'source': e.get('source') if isinstance(e, dict) else None,
                }
                # resolve color from merged metadata or calendar_map.json
                try:
                    # if schedule already had a color (merged), preserve it
                    if isinstance(e, dict) and e.get('color'):
                        ev['color'] = e.get('color')
                    else:
                        src = ev.get('source')
                        if src:
                            map_path = pathlib.Path('playwright_captures') / 'calendar_map.json'
                            if map_path.exists():
                                try:
                                    with open(map_path, 'r', encoding='utf-8') as mf:
                                        cmap = json.load(mf)
                                    meta = cmap.get(src) or {}
                                    if meta.get('color'):
                                        ev['color'] = meta.get('color')
                                except Exception:
                                    pass
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
                from tools.subject_parser import parse_title
                parsed = parse_title(xe.get('title', '') or '')
                disp = parsed.display_title
                subj = parsed.subject_name
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
    
    from subject_parser import parse_location, parse_title, get_parser, learn_from_events, get_all_buildings
    
    # Get selected building from query params (default: show all)
    selected_building = request.args.get('building', '').lower()
    
    # Load events
    events_file = pathlib.Path('playwright_captures/events.json')
    if not events_file.exists():
        return render_template('departures.html', 
                             events_by_day={}, 
                             buildings=get_all_buildings(),
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
    
    # Learn subject mappings from events
    learn_from_events(all_events)
    
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
        building_code = parsed_loc.building_code or 'other'
        building_name = parsed_loc.building_name or 'Other'
        room = parsed_loc.room_normalized or parsed_loc.room or ''
        
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
            'subject': parsed_title.subject_name,
            'display_title': parsed_title.display_title,
            'professor': parsed_title.professor or '',
            'room': room,
            'room_display': parsed_loc.display_name,
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
                         buildings=get_all_buildings(),
                         selected_building=selected_building,
                         current_time=now,
                         has_today_events=has_today_events,
                         error=None)


# =============================================================================
# ADMIN ROUTES
# =============================================================================

@app.route('/admin')
def admin_view():
    """Admin page for managing calendar imports and events."""
    # Get first configured calendar URL from DB if present
    calendar_url = ''
    calendar_name = ''
    calendar_color = None
    try:
        init_db()
        rows = list_calendar_urls()
        if rows:
            calendar_url = rows[0].get('url')
            calendar_name = rows[0].get('name') or ''
            calendar_color = rows[0].get('color') or None
    except Exception:
        # fallback to config file
        config_file = pathlib.Path('config/calendar_config.json')
        calendar_url = ''
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    calendar_url = config.get('calendar_url', '')
                    calendar_name = config.get('calendar_name', '')
                    calendar_color = config.get('calendar_color', None)
            except Exception:
                pass
    
    # Get events stats
    events_file = pathlib.Path('playwright_captures/events.json')
    events_count = 0
    last_import = None
    if events_file.exists():
        try:
            with open(events_file, 'r', encoding='utf-8') as f:
                events = json.load(f)
                events_count = len(events)
            # Get file modification time
            import os
            mtime = os.path.getmtime(events_file)
            last_import = datetime.fromtimestamp(mtime)
        except Exception:
            pass
    
    # Get extractor status
    extractor_running = extractor_state.get('running', False)
    
    # Load configured calendars, extracurricular and manual events for management
    calendars = []
    extracurricular = []
    manual_events = []
    try:
        init_db()
        calendars = list_calendar_urls()
        extracurricular = list_extracurricular_db()
        manual_events = list_manual_events_db()
    except Exception:
        # fall back to file-based lists if DB unavailable
        try:
            cfg_file = pathlib.Path('config') / 'calendar_config.json'
            if cfg_file.exists():
                with open(cfg_file, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    url = cfg.get('calendar_url')
                    if url:
                        calendars = [{'id': 0, 'url': url, 'name': ''}]
        except Exception:
            pass

    return render_template('admin.html',
                         calendar_url=calendar_url,
                         calendar_name=calendar_name,
                         calendar_color=calendar_color,
                         events_count=events_count,
                         last_import=last_import,
                         extractor_running=extractor_running,
                         calendars=calendars,
                         extracurricular=extracurricular,
                         manual_events=manual_events)


@app.route('/admin/set_calendar_url', methods=['POST'])
def admin_set_calendar_url():
    """Save the calendar URL to config."""
    url = request.form.get('calendar_url', '').strip()
    name = request.form.get('calendar_name') or request.form.get('calendar_name', '')
    color = request.form.get('calendar_color') or request.form.get('calendar_color', None)
    if not url:
        return redirect(url_for('admin_view'))

    # Ensure DB initialized
    try:
        init_db()
        add_calendar_url(url, name)
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

    return redirect(url_for('admin_view'))


@app.route('/admin/import_calendar', methods=['POST'])
def admin_import_calendar():
    """Trigger calendar import from the configured URL."""
    # Accept optional url, name, color fields and persist the calendar before import
    url = request.form.get('calendar_url') or request.form.get('url')
    name = request.form.get('calendar_name') or request.form.get('name')
    color = request.form.get('calendar_color') or request.form.get('color')

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

    # Start extractor in background
    t = threading.Thread(target=_run_extractor_background, daemon=True)
    t.start()

    return jsonify({'success': True, 'message': 'Import started'}), 202


@app.route('/admin/add_event', methods=['POST'])
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
def admin_delete_calendar():
    """Delete a configured calendar by id (returns JSON)."""
    try:
        cal_id = int(request.form.get('id', -1))
    except Exception:
        return jsonify({'success': False, 'message': 'Invalid calendar id'}), 400

    try:
        init_db()
        delete_calendar_db(cal_id)
        return jsonify({'success': True, 'message': 'Calendar deleted'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to delete calendar: {e}'}), 500


@app.route('/admin/delete_manual', methods=['POST'])
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
        from tools.subject_parser import parse_title
        for ev in events:
            try:
                parsed = parse_title(ev.get('title', '') or '')
                ev['display_title'] = parsed.display_title
                ev['subject'] = parsed.subject_name
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


if __name__ == "__main__":
    # Start periodic fetcher thread (runs every 30 minutes) before launching the app.
    try:
        t = threading.Thread(target=periodic_fetcher, args=(60,), daemon=True)
        t.start()
        print('Started periodic calendar fetcher (initial run now, then every 60 minutes)')
    except Exception:
        print('Failed to start periodic fetcher')

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
