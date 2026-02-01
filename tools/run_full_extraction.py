#!/usr/bin/env python3
"""
Run extractor sequentially for all enabled calendars in the DB, save per-calendar
events files named events_<hash>.json (sha1(url)[:8]) and then rebuild the
schedule for the range [now - 60 days, now + 60 days].

This is a potentially long-running operation.
"""
import sqlite3
import subprocess
import sys
import os
import hashlib
import pathlib
from datetime import date, timedelta

# Try ICS-first parsing using timetable.parse_ics_from_url to avoid launching
# Playwright when a public .ics feed is available. This is faster and more
# reliable for canonical .ics endpoints.
try:
    # ensure project root is on path when run as a script from different CWDs
    proj_root = pathlib.Path(__file__).parent.parent
    if str(proj_root) not in sys.path:
        sys.path.insert(0, str(proj_root))
    from timetable import parse_ics_from_url
except Exception:
    parse_ics_from_url = None


DB = pathlib.Path('data') / 'app.db'
OUT_DIR = pathlib.Path('playwright_captures')
OUT_DIR.mkdir(exist_ok=True)


def get_enabled_urls(db_path):
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT url, name FROM calendars WHERE enabled = 1 AND url IS NOT NULL")
    rows = cur.fetchall()
    conn.close()
    return rows


def sha8(s: str) -> str:
    return hashlib.sha1(s.encode('utf-8')).hexdigest()[:8]


def run_for_url(url, name=None, env=None):
    print('---')
    print('Extracting:', name or url)
    # Determine the +/-60 day range
    today = date.today()
    from_d = today - timedelta(days=60)
    to_d = today + timedelta(days=60)

    # First attempt: if we have an ICS parser available, try parsing the
    # URL as an .ics feed. This covers both direct .ics URLs and HTML pages
    # that return a calendar when requested directly.
    if parse_ics_from_url is not None:
        try:
            # Many calendars in the CSV are direct .ics links; try parsing
            events = parse_ics_from_url(url, verbose=False)
            # filter events to requested window
            events_in_range = [e for e in events if e.start and from_d <= e.start.date() <= to_d]
            if events_in_range:
                # write per-calendar file
                h = sha8(url)
                ev_out = OUT_DIR / f'events_{h}.json'
                try:
                    OUT_DIR.mkdir(parents=True, exist_ok=True)
                    with open(ev_out, 'w', encoding='utf-8') as f:
                        import json
                        arr = []
                        for e in events_in_range:
                            arr.append({'start': e.start.isoformat() if e.start else None,
                                        'end': e.end.isoformat() if e.end else None,
                                        'title': e.title,
                                        'location': e.location,
                                        'description': e.description,
                                        'source': h})
                        json.dump(arr, f, indent=2, ensure_ascii=False)
                    print('Wrote (ICS) ', ev_out)
                    return True
                except Exception as e:
                    print('Failed to write ICS-derived events file for', url, '->', e)
                    # fall through to HTML extractor fallback
            else:
                # No events in-range from ICS; fall through to HTML extractor
                pass
        except Exception as e:
            # ICS parse failed (not an ICS resource or network error) -> fallback
            print('ICS parse failed for', url, '->', e)

    # Fallback: run the Playwright-based HTML extractor
    cmd = [sys.executable, str(pathlib.Path('tools') / 'extract_published_events.py'), url]
    try:
        proc = subprocess.run(cmd, check=False, env=env)
        rc = proc.returncode
    except Exception as e:
        print('Failed to run extractor for', url, '->', e)
        return False

    # if extractor produced events.json, move to events_<hash>.json
    ev_in = OUT_DIR / 'events.json'
    if ev_in.exists():
        h = sha8(url)
        ev_out = OUT_DIR / f'events_{h}.json'
        try:
            if ev_out.exists():
                ev_out.unlink()
            ev_in.rename(ev_out)
            print('Wrote', ev_out)
        except Exception as e:
            print('Failed to move events.json ->', ev_out, e)
            return False
    else:
        print('No events.json produced for', url)
        # still treat as success if rc==0? mark as failure
        return rc == 0

    return True


def main():
    urls = get_enabled_urls(DB)
    if not urls:
        print('No enabled calendars found in DB')
        return 1

    # Prepare environment for Playwright (preserve any existing variable)
    env = os.environ.copy()
    env.setdefault('PYTHONUTF8', '1')

    total = len(urls)
    ok = 0
    fail = 0
    for url, name in urls:
        success = run_for_url(url, name=name, env=env)
        if success:
            ok += 1
        else:
            fail += 1

    print(f'Extraction finished: {ok} succeeded, {fail} failed, out of {total}')

    # Rebuild schedule for now-60d .. now+60d
    today = date.today()
    from_d = today - timedelta(days=60)
    to_d = today + timedelta(days=60)
    print('Rebuilding schedule from', from_d.isoformat(), 'to', to_d.isoformat())
    cmd = [sys.executable, str(pathlib.Path('tools') / 'build_schedule_by_room.py'), '--from', from_d.isoformat(), '--to', to_d.isoformat()]
    try:
        subprocess.run(cmd, check=False)
        print('Schedule rebuild finished (check playwright_captures/schedule_by_room.json)')
    except Exception as e:
        print('Schedule rebuild failed:', e)
        return 1

    # Write a marker file to indicate the import finished, with a short summary.
    try:
        import json
        from datetime import datetime
        marker = OUT_DIR / 'import_complete.txt'
        info = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'total_calendars': total,
            'succeeded': ok,
            'failed': fail
        }
        with open(marker, 'w', encoding='utf-8') as mf:
            mf.write('Import complete\n')
            mf.write(json.dumps(info, indent=2, ensure_ascii=False))
        print('Import complete — marker written to', marker)
    except Exception as e:
        print('Failed to write import marker:', e)

    return 0


if __name__ == '__main__':
    sys.exit(main())
