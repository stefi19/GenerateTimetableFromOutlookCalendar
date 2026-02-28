#!/usr/bin/env python3
"""
Run extractor for all enabled calendars in the DB, save per-calendar
events files named events_<hash>.json (sha1(url)[:8]) and then rebuild the
schedule for the range [now - 60 days, now + 60 days].

Optimized for 32 GB / 16 vCPU:
  - ICS-direct calendars are fetched concurrently via ThreadPoolExecutor
  - Playwright fallback calendars run with configurable concurrency
  - Progress is written after each calendar for admin UI visibility
"""
import sqlite3
import subprocess
import sys
import os
import hashlib
import pathlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
import tempfile
import json

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
    h = sha8(url)
    # Use a per-URL temp directory to avoid clobbering shared events.json
    tmp_out = OUT_DIR / f'_tmp_{h}'
    tmp_out.mkdir(parents=True, exist_ok=True)
    sub_env = dict(env) if env else os.environ.copy()
    sub_env['EXTRACT_OUTPUT_DIR'] = str(tmp_out)
    cmd = [sys.executable, str(pathlib.Path('tools') / 'extract_published_events.py'), url]
    try:
        proc = subprocess.run(cmd, check=False, env=sub_env)
        rc = proc.returncode
    except Exception as e:
        print('Failed to run extractor for', url, '->', e)
        return False

    # if extractor produced events.json in temp dir, move to events_<hash>.json
    ev_in = tmp_out / 'events.json'
    if ev_in.exists():
        ev_out = OUT_DIR / f'events_{h}.json'
        try:
            if ev_out.exists():
                ev_out.unlink()
            ev_in.rename(ev_out)
            print('Wrote', ev_out)
        except Exception as e:
            print('Failed to move events.json ->', ev_out, e)
            return False
        finally:
            try:
                import shutil
                shutil.rmtree(tmp_out, ignore_errors=True)
            except Exception:
                pass
    else:
        print('No events.json produced for', url)
        try:
            import shutil
            shutil.rmtree(tmp_out, ignore_errors=True)
        except Exception:
            pass
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

    # ── Concurrency tuning (from env or defaults for 16 vCPU) ──
    # ICS parsing is I/O-bound (HTTP fetch) so we can run many in parallel.
    # Playwright is memory-heavy (~300 MB per browser) so limit concurrency.
    ics_concurrency = int(os.environ.get('ICS_CONCURRENCY', '8'))
    pw_concurrency = int(os.environ.get('PLAYWRIGHT_CONCURRENCY', '4'))

    total = len(urls)
    ok = 0
    fail = 0
    _progress_lock = __import__('threading').Lock()

    # helper to persist progress after each URL so the admin UI can show
    # real-time counts even if the process is interrupted.
    progress_path = OUT_DIR / 'import_progress.json'
    def write_progress(last=None):
        try:
            info = {'total': total, 'succeeded': ok, 'failed': fail, 'last': last}
            with open(progress_path, 'w', encoding='utf-8') as pf:
                json.dump(info, pf, indent=2, ensure_ascii=False)
        except Exception as e:
            print('Failed to write progress file:', e)

    # ── Phase 1: Try ICS-direct parsing in parallel ──
    # Split calendars into ICS-parseable (fast) and fallback (Playwright).
    ics_succeeded = set()   # URLs that succeeded via ICS
    playwright_queue = []   # (url, name) tuples that need Playwright fallback

    def try_ics(url_name):
        """Attempt ICS parsing for a single URL. Returns (url, name, success)."""
        url, name = url_name
        return (url, name, run_for_url(url, name=name, env=env))

    print(f'Phase 1: Attempting ICS-direct parsing for {total} calendars '
          f'(concurrency={ics_concurrency})...')

    # run_for_url already tries ICS first, then falls back to Playwright.
    # But for the parallel phase, we only want the ICS-fast-path.
    # We'll run all of them in parallel — ICS succeeds fast, Playwright
    # subprocess will serialize naturally via the GIL / subprocess.
    # However, to avoid launching too many Playwright subprocesses at once,
    # we do a two-phase approach:
    #   Phase 1: ICS only (no Playwright fallback) — highly parallel
    #   Phase 2: Playwright fallback for failures — limited concurrency

    def try_ics_only(url_name):
        """Try ICS parsing only (no Playwright fallback). Returns (url, name, success)."""
        url, name = url_name
        if parse_ics_from_url is None:
            return (url, name, False)
        today = date.today()
        from_d = today - timedelta(days=60)
        to_d = today + timedelta(days=60)
        try:
            events = parse_ics_from_url(url, verbose=False)
            events_in_range = [e for e in events if e.start and from_d <= e.start.date() <= to_d]
            if events_in_range:
                h = sha8(url)
                ev_out = OUT_DIR / f'events_{h}.json'
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                arr = []
                for e in events_in_range:
                    arr.append({
                        'start': e.start.isoformat() if e.start else None,
                        'end': e.end.isoformat() if e.end else None,
                        'title': e.title,
                        'location': e.location,
                        'description': e.description,
                        'source': h
                    })
                with open(ev_out, 'w', encoding='utf-8') as f:
                    json.dump(arr, f, indent=2, ensure_ascii=False)
                print(f'  ✓ ICS OK: {name or url} ({len(arr)} events)')
                return (url, name, True)
        except Exception:
            pass
        return (url, name, False)

    try:
        with ThreadPoolExecutor(max_workers=ics_concurrency) as pool:
            futures = {pool.submit(try_ics_only, (url, name)): (url, name)
                       for url, name in urls}
            for future in as_completed(futures):
                url, name, success = future.result()
                if success:
                    with _progress_lock:
                        ok += 1
                        ics_succeeded.add(url)
                        write_progress(last=name or url)
                else:
                    playwright_queue.append((url, name))

        print(f'Phase 1 complete: {ok} succeeded via ICS, '
              f'{len(playwright_queue)} need Playwright fallback')

        # ── Phase 2: Playwright fallback (limited concurrency) ──
        if playwright_queue:
            print(f'Phase 2: Running Playwright extraction for {len(playwright_queue)} '
                  f'calendars (concurrency={pw_concurrency})...')

            def run_playwright_for(url_name):
                url, name = url_name
                print(f'  → Playwright: {name or url}')
                h = sha8(url)
                # Each Playwright subprocess writes to its own temp directory
                # so concurrent instances don't clobber each other's events.json.
                tmp_out = OUT_DIR / f'_tmp_{h}'
                tmp_out.mkdir(parents=True, exist_ok=True)
                sub_env = dict(env)
                sub_env['EXTRACT_OUTPUT_DIR'] = str(tmp_out)
                cmd = [sys.executable, str(pathlib.Path('tools') / 'extract_published_events.py'), url]
                try:
                    proc = subprocess.run(cmd, check=False, env=sub_env)
                    rc = proc.returncode
                except Exception:
                    return (url, name, False)
                # move temp_dir/events.json -> events_<hash>.json in main dir
                ev_in = tmp_out / 'events.json'
                if ev_in.exists():
                    ev_out = OUT_DIR / f'events_{h}.json'
                    try:
                        if ev_out.exists():
                            ev_out.unlink()
                        ev_in.rename(ev_out)
                        print(f'  ✓ Playwright OK: {name or url}')
                    except Exception:
                        return (url, name, False)
                    finally:
                        # clean up temp dir
                        try:
                            import shutil
                            shutil.rmtree(tmp_out, ignore_errors=True)
                        except Exception:
                            pass
                    return (url, name, True)
                # clean up temp dir even if no events.json produced
                try:
                    import shutil
                    shutil.rmtree(tmp_out, ignore_errors=True)
                except Exception:
                    pass
                return (url, name, rc == 0)

            # Playwright launches full browsers, so limit concurrency
            # On 16 vCPU / 32 GB we can safely run 4 browsers at once
            # (each ~300-500 MB RAM + 1-2 CPU cores)
            with ThreadPoolExecutor(max_workers=pw_concurrency) as pool:
                futures = {pool.submit(run_playwright_for, item): item
                           for item in playwright_queue}
                for future in as_completed(futures):
                    url, name, success = future.result()
                    with _progress_lock:
                        if success:
                            ok += 1
                        else:
                            fail += 1
                        write_progress(last=name or url)

        print(f'Extraction finished: {ok} succeeded, {fail} failed, out of {total}')

    except Exception:
        # On unexpected exception we don't write the final import marker
        # because not all calendars were processed. Re-raise so caller
        # (or logs) will show the failure. Progress file contains partial
        # counts.
        raise

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

    # If all calendars were processed, write the final import marker atomically.
    try:
        if ok + fail == total:
            # Before writing the final marker ensure the number of per-calendar
            # files on disk matches the number of calendars. This avoids
            # marking import as ready when files are still missing.
            from datetime import datetime
            marker = OUT_DIR / 'import_complete.txt'
            tmp = OUT_DIR / (marker.name + '.tmp')
            info = {
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'total_calendars': total,
                'succeeded': ok,
                'failed': fail
            }

            # update progress one last time
            try:
                write_progress(last=None)
            except Exception:
                pass

            # wait a short while for filesystem visibility (in case of NFS/overlayfs)
            MAX_RETRIES = 5
            SLEEP_SEC = 1
            files_count = 0
            for attempt in range(MAX_RETRIES):
                try:
                    files_count = len(list(OUT_DIR.glob('events_*.json')))
                except Exception:
                    files_count = 0
                if files_count >= total:
                    break
                time.sleep(SLEEP_SEC)

            # Persist the final files_count into the progress file
            try:
                write_progress(last=None)
                # augment progress file with files_count and finished flag
                prog = OUT_DIR / 'import_progress.json'
                try:
                    prog_j = json.load(open(prog, 'r', encoding='utf-8'))
                except Exception:
                    prog_j = {}
                prog_j['files_count'] = files_count
                prog_j['finished'] = True
                prog_j['finished_at'] = datetime.utcnow().isoformat() + 'Z'
                with open(prog, 'w', encoding='utf-8') as pf:
                    json.dump(prog_j, pf, indent=2, ensure_ascii=False)
            except Exception:
                pass

            if files_count == total:
                try:
                    with open(tmp, 'w', encoding='utf-8') as mf:
                        mf.write('Import complete\n')
                        json.dump(info, mf, indent=2, ensure_ascii=False)
                    tmp.replace(marker)
                    print('Import complete — marker written to', marker)
                except Exception as e:
                    print('Failed to write import marker:', e)
            else:
                print(f'Files on disk ({files_count}) do not match calendar count ({total}); skipping final import marker')
    except Exception as e:
        print('Error while finalizing import marker:', e)

    return 0


if __name__ == '__main__':
    sys.exit(main())
