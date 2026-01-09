#!/usr/bin/env python3
"""
Worker that periodically extracts events for enabled calendars and updates
per-calendar files preserving past events and replacing only future events.

Behavior:
 - For each enabled calendar URL in `data/app.db`:
   - run `tools/extract_published_events.py <url>` which writes `playwright_captures/events.json` if any
   - if events.json exists, split existing `events_<h>.json` into past (start < today)
     and future (start >= today). Keep past, replace future with newly extracted
     events that are in the future (start >= today).
 - After processing calendars, rebuild schedule for [today - 60d, today + 60d]

The worker runs in a loop with interval specified by env VAR `INTERVAL_SECONDS` (default 3600).
Set `RUN_ONCE=1` to run a single iteration and exit (useful for testing / cron).
"""
from __future__ import annotations

import os
import sys
import subprocess
import hashlib
import json
import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Dict, Any

from dateutil import parser as dtparser


ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / 'data' / 'app.db'
OUT = ROOT / 'playwright_captures'
OUT.mkdir(parents=True, exist_ok=True)


def sha8(s: str) -> str:
    return hashlib.sha1(s.encode('utf-8')).hexdigest()[:8]


def get_enabled_urls(db_path: Path) -> List[Dict[str, str]]:
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT url, name FROM calendars WHERE enabled = 1 AND url IS NOT NULL")
    rows = cur.fetchall()
    conn.close()
    return [{'url': r[0], 'name': r[1]} for r in rows]


def load_json(p: Path):
    try:
        with p.open('r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def save_json(p: Path, data):
    with p.open('w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def is_future_event(ev: Dict[str, Any], today_dt: date) -> bool:
    s = ev.get('start')
    if not s:
        return False
    try:
        d = dtparser.parse(s).date()
        return d >= today_dt
    except Exception:
        return False


def run_extractor_for_url(url: str, env: Dict[str, str]) -> bool:
    cmd = [sys.executable, str(ROOT / 'tools' / 'extract_published_events.py'), url]
    try:
        proc = subprocess.run(cmd, check=False, env=env)
        return proc.returncode == 0
    except Exception:
        return False


def merge_future_events(url: str):
    h = sha8(url)
    out_file = OUT / f'events_{h}.json'
    tmp_in = OUT / 'events.json'
    today_dt = date.today()

    # Load existing events (if any)
    existing = load_json(out_file) if out_file.exists() else []
    past = [e for e in existing if not is_future_event(e, today_dt)]

    # Load newly extracted events (if any)
    new = load_json(tmp_in) if tmp_in.exists() else []
    new_future = [e for e in new if is_future_event(e, today_dt)]

    # Merge: keep past, append new_future, dedupe by (ItemId or title+start)
    merged = past + new_future
    seen = set()
    deduped = []
    for ev in merged:
        raw = ev.get('raw') or {}
        iid = None
        if isinstance(raw, dict):
            try:
                iid = raw.get('ItemId', {}).get('Id') if raw.get('ItemId') else None
            except Exception:
                iid = None
        key = iid or ((ev.get('title') or '') + '|' + (ev.get('start') or ''))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ev)

    # Save merged file
    save_json(out_file, deduped)
    # remove tmp_in so next run starts clean
    try:
        if tmp_in.exists():
            tmp_in.unlink()
    except Exception:
        pass


def rebuild_schedule(from_d: date, to_d: date, env: Dict[str, str]):
    cmd = [sys.executable, str(ROOT / 'tools' / 'build_schedule_by_room.py'), '--from', from_d.isoformat(), '--to', to_d.isoformat()]
    try:
        subprocess.run(cmd, check=False, env=env)
    except Exception as e:
        print('Schedule rebuild failed:', e)


def main():
    INTERVAL = int(os.environ.get('INTERVAL_SECONDS', '3600'))
    RUN_ONCE = os.environ.get('RUN_ONCE', '') in ('1', 'true', 'True')
    env = os.environ.copy()
    env.setdefault('PYTHONUTF8', '1')

    while True:
        print('Worker iteration started:', datetime.utcnow().isoformat())
        urls = get_enabled_urls(DB)
        print(f'Found {len(urls)} enabled calendars')
        succeeded = 0
        failed = 0
        for cal in urls:
            url = cal['url']
            name = cal.get('name') or url
            print('Extracting', name)
            ok = run_extractor_for_url(url, env)
            if not ok:
                print('Extractor returned non-zero for', url)
                failed += 1
                # continue to try to merge any partial capture
            else:
                succeeded += 1
            # merge/update per-calendar file preserving past
            merge_future_events(url)

        print(f'Extraction pass finished. succeeded={succeeded} failed={failed}')

        # Rebuild schedule for -60d .. +60d
        today = date.today()
        from_d = today - timedelta(days=60)
        to_d = today + timedelta(days=60)
        print('Rebuilding schedule', from_d.isoformat(), '->', to_d.isoformat())
        rebuild_schedule(from_d, to_d, env)

        if RUN_ONCE:
            print('RUN_ONCE set: exiting')
            break

        print('Sleeping for', INTERVAL, 'seconds')
        try:
            import time
            time.sleep(INTERVAL)
        except KeyboardInterrupt:
            print('Interrupted; exiting')
            break


if __name__ == '__main__':
    main()
