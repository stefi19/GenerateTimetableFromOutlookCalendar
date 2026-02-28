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


def load_calendar_map(db_path: Path, out_dir: Path):
    cmap = {}
    map_path = out_dir / 'calendar_map.json'
    try:
        if map_path.exists():
            with map_path.open('r', encoding='utf-8') as f:
                cmap = json.load(f)
    except Exception:
        cmap = {}
    # supplement from DB rows
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("SELECT url, name, color, building, room FROM calendars WHERE url IS NOT NULL")
        for url, name, color, building, room in cur.fetchall():
            if not url:
                continue
            h = hashlib.sha1(url.encode('utf-8')).hexdigest()[:8]
            if h not in cmap:
                cmap[h] = {'url': url, 'name': name or '', 'color': color, 'building': building, 'room': room}
        conn.close()
    except Exception:
        pass
    return cmap


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
    """Run the Playwright extractor for a single URL.

    Each invocation writes to its own temp directory (via EXTRACT_OUTPUT_DIR)
    so concurrent calls don't clobber each other's events.json.
    Returns True on success.
    """
    h = sha8(url)
    tmp_out = OUT / f'_tmp_{h}'
    tmp_out.mkdir(parents=True, exist_ok=True)
    sub_env = dict(env)
    sub_env['EXTRACT_OUTPUT_DIR'] = str(tmp_out)
    cmd = [sys.executable, str(ROOT / 'tools' / 'extract_published_events.py'), url]
    try:
        proc = subprocess.run(cmd, check=False, env=sub_env)
        ok = proc.returncode == 0
    except Exception:
        ok = False
    # Move events.json from temp dir to the shared dir as events_<h>.tmp.json
    # so merge_future_events can pick it up without races.
    tmp_events = tmp_out / 'events.json'
    staging = OUT / f'events_{h}.tmp.json'
    if tmp_events.exists():
        try:
            if staging.exists():
                staging.unlink()
            tmp_events.rename(staging)
        except Exception:
            pass
    # clean up temp dir
    try:
        import shutil
        shutil.rmtree(tmp_out, ignore_errors=True)
    except Exception:
        pass
    return ok


def merge_future_events(url: str):
    h = sha8(url)
    out_file = OUT / f'events_{h}.json'
    # Read from the staging file written by run_extractor_for_url
    tmp_in = OUT / f'events_{h}.tmp.json'
    today_dt = date.today()

    # Load existing events (if any)
    existing = load_json(out_file) if out_file.exists() else []
    # Keep past events within the ±60 day window (don't accumulate unbounded history)
    cutoff_past = today_dt - timedelta(days=60)
    past = []
    for e in existing:
        if is_future_event(e, today_dt):
            continue  # will be replaced by new_future
        # check if event is within the past 60-day window
        s = e.get('start')
        if s:
            try:
                d = dtparser.parse(s).date()
                if d < cutoff_past:
                    continue  # too old, prune
            except Exception:
                pass
        past.append(e)

    # Load newly extracted events (if any)
    new = load_json(tmp_in) if tmp_in.exists() else []
    new_future = [e for e in new if is_future_event(e, today_dt)]

    # Merge: keep past, append new_future, dedupe by (ItemId or title+start)
    merged = past + new_future
    merged_candidates = past + new_future
    # try to enrich events missing location from calendar_map or DB
    cmap = load_calendar_map(DB, OUT)
    for ev in merged_candidates:
        try:
            if not ev.get('location') or ev.get('location') in ('', ' - ', None):
                meta = None
                src = ev.get('source')
                if src and str(src) in cmap:
                    meta = cmap.get(str(src))
                else:
                    # fallback to file hash h
                    meta = cmap.get(h)
                if meta:
                    room_meta = meta.get('room') if isinstance(meta, dict) else None
                    name_meta = meta.get('name') if isinstance(meta, dict) else None
                    if room_meta:
                        ev['room'] = room_meta
                        ev['location'] = room_meta
                    elif name_meta:
                        ev['location'] = name_meta
        except Exception:
            pass
    seen = set()
    deduped = []

    def score_event(e):
        s = 0
        r = (e.get('room') or e.get('location') or '').strip()
        if r and r not in ('', ' - ', 'UNKNOWN'):
            s += 50
        if e.get('end'):
            s += 20
        if e.get('professor'):
            s += 5
        if e.get('color'):
            s += 2
        return s

    for ev in merged_candidates:
        raw = ev.get('raw') or {}
        iid = None
        if isinstance(raw, dict):
            try:
                iid = raw.get('ItemId', {}).get('Id') if raw.get('ItemId') else None
            except Exception:
                iid = None
        key = iid or ((ev.get('title') or '') + '|' + (ev.get('start') or ''))
        if key in seen:
            # find previous and replace if current has a better score
            for i, existing in enumerate(deduped):
                try:
                    raw_ex = existing.get('raw') or {}
                    iid_ex = raw_ex.get('ItemId', {}).get('Id') if raw_ex.get('ItemId') else None
                except Exception:
                    iid_ex = None
                key_ex = iid_ex or ((existing.get('title') or '') + '|' + (existing.get('start') or ''))
                if key_ex == key:
                    if score_event(ev) > score_event(existing):
                        deduped[i] = ev
                    break
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
    PW_CONCURRENCY = int(os.environ.get('PLAYWRIGHT_CONCURRENCY', '4'))
    env = os.environ.copy()
    env.setdefault('PYTHONUTF8', '1')

    while True:
        print('Worker iteration started:', datetime.utcnow().isoformat())
        urls = get_enabled_urls(DB)
        print(f'Found {len(urls)} enabled calendars')
        succeeded = 0
        failed = 0

        # ── Concurrent extraction (optimized for 16 vCPU / 32 GB) ──
        # Each extraction launches a Playwright browser subprocess.
        # Limit concurrency to avoid OOM (each browser ~300-500 MB).
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading
        _lock = threading.Lock()

        def extract_and_merge(cal):
            url = cal['url']
            name = cal.get('name') or url
            print(f'  → Extracting: {name}')
            # Each URL now writes to its own temp directory (via EXTRACT_OUTPUT_DIR)
            # and stages output as events_<hash>.tmp.json, so no serialization needed.
            ok = run_extractor_for_url(url, env)
            if not ok:
                print(f'  ✗ Extractor failed for: {url}')
            else:
                print(f'  ✓ Extractor OK for: {name}')
            # merge/update per-calendar file preserving past
            merge_future_events(url)
            return ok

        with ThreadPoolExecutor(max_workers=PW_CONCURRENCY) as pool:
            futures = {pool.submit(extract_and_merge, cal): cal for cal in urls}
            for future in as_completed(futures):
                try:
                    ok = future.result()
                except Exception:
                    ok = False
                with _lock:
                    if ok:
                        succeeded += 1
                    else:
                        failed += 1

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
