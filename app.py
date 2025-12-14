from __future__ import annotations

import os
import tempfile
import threading
import time
from collections import defaultdict
from datetime import date, timedelta, datetime
from typing import List
import json
import subprocess
import sys
import pathlib

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
        with open(stdout_path, 'w', encoding='utf-8') as out_f, open(stderr_path, 'w', encoding='utf-8') as err_f:
            proc = subprocess.run(cmd, stdout=out_f, stderr=err_f, text=True)
            extractor_state['last_rc'] = proc.returncode
    except Exception as e:
        with open(stderr_path, 'a', encoding='utf-8') as err_f:
            err_f.write(str(e))
        extractor_state['last_rc'] = 1
    finally:
        extractor_state['running'] = False



@app.route('/schedule', methods=['GET', 'POST'])
def schedule_view():
    # form inputs
    from_s = request.values.get('from')
    to_s = request.values.get('to')
    days = int(request.values.get('days') or 7)
    today = date.today()
    if from_s:
        from_date = date.fromisoformat(from_s)
    else:
        from_date = today
    if to_s:
        to_date = date.fromisoformat(to_s)
    else:
        to_date = from_date + timedelta(days=days - 1)

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
                subj = e.get('subject')
                title = e.get('title') or ''
                prof = e.get('professor') or ''
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
                    'start': start,
                    'end': end,
                    'room': room,
                    'subject': subject,
                    'professor': prof,
                    'location': location,
                }
                events.append(ev)

    return jsonify(events)


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


if __name__ == "__main__":
    # Disable the auto-reloader to avoid Playwright event-loop lifecycle issues
    # when the Flask debug reloader spawns child processes.
    app.run(debug=True, use_reloader=False)
