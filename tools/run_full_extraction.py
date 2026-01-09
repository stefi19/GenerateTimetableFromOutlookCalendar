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

    return 0


if __name__ == '__main__':
    sys.exit(main())
