#!/usr/bin/env python3
"""
Verify per-calendar event files exist for all enabled calendars and retry
extraction for missing or empty files sequentially. This is safe to run in
container or locally; it runs the HTML extractor synchronously for each missing
URL to avoid overwhelming Playwright with concurrent browser instances.

The script will also rebuild the aggregated schedule at the end.
"""
import sqlite3
import pathlib
import hashlib
import json
import subprocess
import sys
import os
from datetime import date, timedelta

BASE = pathlib.Path(__file__).parent.parent
DB = BASE / 'data' / 'app.db'
OUT = BASE / 'playwright_captures'


def sha8(s: str) -> str:
    return hashlib.sha1(s.encode('utf-8')).hexdigest()[:8]


def get_enabled_urls(db_path):
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT url, name FROM calendars WHERE enabled = 1 AND url IS NOT NULL")
    rows = cur.fetchall()
    conn.close()
    return rows


def check_files(urls):
    missing = []
    empty = []
    total_events = 0
    OUT.mkdir(exist_ok=True)
    for url, name in urls:
        h = sha8(url)
        f = OUT / f'events_{h}.json'
        if not f.exists():
            missing.append((url, name))
            continue
        try:
            data = json.load(open(f, 'r', encoding='utf-8'))
            if not isinstance(data, list) or len(data) == 0:
                empty.append((url, name, f))
            else:
                total_events += len(data)
        except Exception:
            missing.append((url, name))
    return missing, empty, total_events


def run_extractor_for(url):
    # Run the extractor synchronously for a single URL; it writes events.json
    env = os.environ.copy()
    env.setdefault('PYTHONUTF8', '1')
    cmd = [sys.executable, str(BASE / 'tools' / 'extract_published_events.py'), url]
    print('Running extractor for', url)
    try:
        rc = subprocess.run(cmd, check=False, env=env, cwd=str(BASE))
        return rc.returncode == 0
    except Exception as e:
        print('Extractor failed:', e)
        return False


def move_events_json(url):
    h = sha8(url)
    ev_in = OUT / 'events.json'
    ev_out = OUT / f'events_{h}.json'
    if ev_in.exists():
        try:
            if ev_out.exists():
                ev_out.unlink()
            ev_in.rename(ev_out)
            print('Wrote', ev_out)
            return True
        except Exception as e:
            print('Failed to move events.json ->', ev_out, e)
            return False
    else:
        print('No events.json produced for', url)
        return False


def rebuild_schedule():
    today = date.today()
    from_d = today - timedelta(days=60)
    to_d = today + timedelta(days=60)
    cmd = [sys.executable, str(BASE / 'tools' / 'build_schedule_by_room.py'), '--from', from_d.isoformat(), '--to', to_d.isoformat()]
    print('Rebuilding schedule from', from_d.isoformat(), 'to', to_d.isoformat())
    try:
        subprocess.run(cmd, check=False, cwd=str(BASE))
        print('Schedule rebuild finished')
    except Exception as e:
        print('Schedule rebuild failed:', e)


def main():
    if not DB.exists():
        print('DB not found at', DB)
        sys.exit(2)
    urls = get_enabled_urls(DB)
    print(f'Found {len(urls)} enabled calendars')
    missing, empty, total = check_files(urls)
    print('Existing events files total events:', total)
    print('Missing files:', len(missing), 'Empty files:', len(empty))

    # For missing or empty, run extractor sequentially
    to_fix = [(u,n) for (u,n) in missing] + [(u,n) for (u,n,f) in empty]
    fixed = 0
    failed = 0
    for url, name in to_fix:
        ok = run_extractor_for(url)
        if not ok:
            print('Extractor returned non-zero for', url)
            failed += 1
            continue
        moved = move_events_json(url)
        if moved:
            fixed += 1
        else:
            failed += 1

    print(f'Fixed {fixed} files, failed {failed}')
    # rebuild schedule after fixes
    rebuild_schedule()

    # final counts
    missing2, empty2, total2 = check_files(urls)
    print('After repair: missing:', len(missing2), 'empty:', len(empty2), 'total events:', total2)


if __name__ == '__main__':
    main()
