#!/usr/bin/env python3
"""
Force refresh all enabled calendars from the canonical CSV/DB.

For each enabled calendar this script will:
 - attempt to parse the URL as an .ics feed using timetable.parse_ics_from_url
 - filter events to the range [now-60d, now+60d]
 - if ICS parsing yields events, write playwright_captures/events_<sha8>.json
 - otherwise fall back to the Playwright HTML extractor (tools/extract_published_events.py)

This is a heavier operation and should be run in the container where Playwright
is available. It runs sequentially to avoid too many simultaneous browser
instances.
"""
from __future__ import annotations

import pathlib
import sqlite3
import hashlib
import json
import sys
import os
import subprocess
from datetime import date, timedelta

BASE = pathlib.Path(__file__).parent.parent
DB = BASE / 'data' / 'app.db'
OUT = BASE / 'playwright_captures'

sys.path.insert(0, str(BASE))
from timetable import parse_ics_from_url


def sha8(s: str) -> str:
    return hashlib.sha1(s.encode('utf-8')).hexdigest()[:8]


def get_enabled_urls(db_path):
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT url, name FROM calendars WHERE enabled = 1 AND url IS NOT NULL")
    rows = cur.fetchall()
    conn.close()
    return rows


def write_events_file(url, events):
    OUT.mkdir(exist_ok=True)
    h = sha8(url)
    arr = []
    for e in events:
        try:
            arr.append({
                'start': e.start.isoformat() if e.start else None,
                'end': e.end.isoformat() if e.end else None,
                'title': e.title,
                'location': e.location,
                'description': e.description,
                'source': h,
            })
        except Exception:
            continue
    dest = OUT / f'events_{h}.json'
    with open(dest, 'w', encoding='utf-8') as f:
        json.dump(arr, f, indent=2, ensure_ascii=False)
    return len(arr)


def run_html_extractor(url):
    # run tools/extract_published_events.py which writes OUT/events.json
    env = os.environ.copy()
    env.setdefault('PYTHONUTF8', '1')
    cmd = [sys.executable, str(BASE / 'tools' / 'extract_published_events.py'), url]
    print('HTML extractor fallback for', url)
    try:
        subprocess.run(cmd, check=False, env=env, cwd=str(BASE))
    except Exception as e:
        print('HTML extractor failed to start:', e)


def move_events_json(url):
    h = sha8(url)
    ev_in = OUT / 'events.json'
    ev_out = OUT / f'events_{h}.json'
    if ev_in.exists():
        try:
            if ev_out.exists():
                ev_out.unlink()
            ev_in.rename(ev_out)
            return ev_out
        except Exception as e:
            print('Failed to move events.json ->', ev_out, e)
    return None


def main():
    if not DB.exists():
        print('Database not found at', DB)
        return 2

    urls = get_enabled_urls(DB)
    print('Found', len(urls), 'enabled calendars')
    OUT.mkdir(exist_ok=True)

    today = date.today()
    from_d = today - timedelta(days=60)
    to_d = today + timedelta(days=60)

    total_written = 0
    total_events = 0
    failed = []

    for url, name in urls:
        print('\n=== Processing:', name or url)
        # First try ICS parser
        try:
            evs = parse_ics_from_url(url, verbose=True)
            # filter by range
            evs_in_range = [e for e in evs if from_d <= e.start.date() <= to_d]
            if evs_in_range:
                n = write_events_file(url, evs_in_range)
                total_written += 1
                total_events += n
                print(f'ICS parser: wrote {n} events for {url}')
                continue
            else:
                print('ICS parser found no events in range for', url)
        except Exception as e:
            # verbose parse_ics_from_url may have saved last_ics_response.html for inspection
            print('ICS parse failed or not ICS for', url, '->', e)

        # Fallback to HTML extractor (Playwright)
        run_html_extractor(url)
        moved = move_events_json(url)
        if moved:
            try:
                data = json.load(open(moved, 'r', encoding='utf-8'))
                cnt = len(data) if isinstance(data, list) else 0
            except Exception:
                cnt = 0
            total_written += 1
            total_events += cnt
            print(f'HTML extractor: wrote {cnt} events for {url}')
        else:
            print('No events produced for', url)
            failed.append(url)

    print('\nSummary:')
    print('Files written:', total_written)
    print('Total events:', total_events)
    print('Failures:', len(failed))
    if failed:
        print('\nFailed URLs:')
        for u in failed:
            print(' -', u)

    # rebuild schedule
    print('\nRebuilding aggregated schedule...')
    cmd = [sys.executable, str(BASE / 'tools' / 'build_schedule_by_room.py'), '--from', from_d.isoformat(), '--to', to_d.isoformat()]
    try:
        subprocess.run(cmd, check=False, cwd=str(BASE))
        print('Schedule rebuilt')
    except Exception as e:
        print('Schedule rebuild failed:', e)


if __name__ == '__main__':
    main()
