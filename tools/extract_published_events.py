#!/usr/bin/env python3
"""Capture and extract published calendar events by intercepting the Outlook SPA JSON responses.

Usage:
  export PLAYWRIGHT_USER_DATA_DIR="$HOME/.playwright_profile"
  python3 tools/extract_published_events.py

The script will:
  - launch Playwright using the persistent profile (so a one-time login in headed mode is preserved)
  - navigate to the published calendar HTML page
  - capture XHR responses that contain calendar item JSON (service.svc?action=GetItem / PublishedCalendar)
  - optionally click visible event elements to force the page to request item details
  - parse captured JSON into Event objects and save to playwright_captures/events.json
  - print a grouped timetable summary to stdout
"""

from __future__ import annotations

import json
import os
import pathlib
import time
from datetime import datetime
from typing import List

from dateutil import parser as dtparser
import sys
import hashlib

# Ensure the process uses UTF-8 for stdout/stderr on Windows where the default
# console encoding can be cp1252. Attempt to reconfigure the IO streams and
# set PYTHONUTF8/PYTHONIOENCODING to help child processes and libraries.
try:
    # Python 3.7+ provides reconfigure for TextIOWrapper
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass
try:
    import os
    os.environ.setdefault('PYTHONUTF8', '1')
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
except Exception:
    pass

# Import parserul inteligent pentru subiecte
from subject_parser import get_parser, learn_from_events, expand_title


def main():
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print("playwright not available. Install with: pip install playwright && playwright install")
        raise

    # Determine URL to fetch. Priority: CLI arg -> EXTRACT_URL env -> hardcoded default
    url = None
    if len(sys.argv) > 1 and sys.argv[1].strip():
        url = sys.argv[1].strip()
    else:
        url = os.environ.get('EXTRACT_URL')

    if not url:
        # fallback default (kept for backwards compatibility)
        url = 'https://outlook.office365.com/calendar/published/173862b98010453296f2a697e45f3b1e@campus.utcluj.ro/daeb64d4bd994c52b4f54d04ba1940ca2236386271423118770/calendar.html'
    user_data_dir = os.environ.get('PLAYWRIGHT_USER_DATA_DIR', os.path.expanduser('~/.playwright_profile'))
    out_dir = pathlib.Path('playwright_captures')
    out_dir.mkdir(exist_ok=True)

    print('Using PLAYWRIGHT_USER_DATA_DIR:', user_data_dir)
    print('Extracting URL:', url)

    captured_json_texts = []
    captured_urls = []

    with sync_playwright() as p:
        # Use persistent context so we can reuse a logged-in session
        context = p.chromium.launch_persistent_context(user_data_dir, headless=True)
        page = context.new_page()

        def on_response(resp):
            try:
                u = resp.url
                if 'service.svc' in u and ('GetItem' in u or 'PublishedCalendar' in u or 'GetItems' in u):
                    # attempt to read JSON body
                    try:
                        j = resp.json()
                    except Exception:
                        try:
                            txt = resp.text()
                            j = json.loads(txt)
                        except Exception:
                            j = None
                    if j is not None:
                        # avoid duplicates
                        if u not in captured_urls:
                            captured_urls.append(u)
                            captured_json_texts.append(j)
                            idx = len(captured_json_texts) - 1
                            fname = out_dir / f'json_capture_{idx}.json'
                            with open(fname, 'w', encoding='utf-8') as f:
                                json.dump(j, f, indent=2, ensure_ascii=False)
                            print('Captured:', u, '->', fname)
            except Exception as e:
                print('on_response error', e)

        page.on('response', on_response)

        print('Navigating to page...')
        try:
            page.goto(url, wait_until='networkidle', timeout=60000)
        except Exception as e:
            print('goto exception (continuing):', e)

        # give page a moment to load
        time.sleep(1.0)

        # Attempt to click visible event items to trigger GetItem requests
        # Use a set of heuristics similar to the Console snippet
        selectors = ['[role="listitem"]', '[data-eventid]', '[data-event-id]', '.calendar-event', '.event', '[data-automationid]']
        elements = []
        for sel in selectors:
            try:
                found = page.query_selector_all(sel)
                if found:
                    elements.extend(found)
            except Exception:
                pass

        # Best-effort: navigate several months back and forward to force the
        # SPA to request additional date windows. This helps capture events
        # outside the initial visible month. We try several likely nav
        # button selectors (aria-label/title/text) and click them.
        try:
            nav_prev_selectors = [
                'button[aria-label*="Previous"]',
                'button[aria-label*="Prev"]',
                'button[title*="Previous"]',
                'button[title*="Prev"]',
                'text=Previous',
                'text=Prev'
            ]
            nav_next_selectors = [
                'button[aria-label*="Next"]',
                'button[aria-label*="Next month"]',
                'button[title*="Next"]',
                'button[title*="Next month"]',
                'text=Next'
            ]

            def _try_click_any(selectors_list):
                for s in selectors_list:
                    try:
                        el = page.query_selector(s)
                        if el:
                            el.click(timeout=1500)
                            return True
                    except Exception:
                        continue
                return False

            # Click previous 3 times (go back ~3 months)
            for _ in range(3):
                if not _try_click_any(nav_prev_selectors):
                    break
                # wait for any network activity
                page.wait_for_timeout(400)

            # Click next 6 times (to go forward past original state)
            for _ in range(6):
                if not _try_click_any(nav_next_selectors):
                    break
                page.wait_for_timeout(400)

            # Finally, return to original roughly by clicking previous 3 times
            for _ in range(3):
                if not _try_click_any(nav_prev_selectors):
                    break
                page.wait_for_timeout(300)
        except Exception:
            pass

        # limit how many elements we try to click
        max_clicks = 40
        clicks = 0
        print(f'Found {len(elements)} candidate elements to click (trying up to {max_clicks})')
        for el in elements:
            if clicks >= max_clicks:
                break
            try:
                # scroll into view and click
                el.scroll_into_view_if_needed()
                el.click(timeout=2000)
                clicks += 1
                # short wait for any network activity
                page.wait_for_timeout(300)
            except Exception:
                # ignore click failures
                pass

        # wait a bit for any late responses
        time.sleep(1.0)

        # Save a final snapshot of the page HTML for debugging
        try:
            html = page.content()
            (out_dir / 'page_after_clicks.html').write_text(html, encoding='utf-8')
            print('Saved page_after_clicks.html')
        except Exception:
            pass

        context.close()

    # parse captured JSONs into simple event dicts
    events = []
    for j in captured_json_texts:
        try:
            body = j.get('Body') if isinstance(j, dict) else None
            if not body:
                # sometimes envelope under 'd' or similar
                body = j
            # traverse common paths: Body.ResponseMessages.Items[..]
            items = None
            try:
                items = body['ResponseMessages']['Items']
            except Exception:
                items = body.get('ResponseMessages', {}).get('Items') if isinstance(body, dict) else None

            if not items:
                continue

            for block in items:
                # Find inner lists in common locations: block['Items'] or block['RootFolder']['Items']
                inner = []
                if isinstance(block, dict) and 'Items' in block:
                    inner = block.get('Items') or []
                elif isinstance(block, dict) and 'RootFolder' in block and isinstance(block['RootFolder'], dict):
                    inner = block['RootFolder'].get('Items') or []

                for it in inner:
                    # look for CalendarItem shape
                    try:
                        typ = it.get('__type', '') if isinstance(it, dict) else ''
                    except Exception:
                        typ = ''
                    if typ.startswith('CalendarItem') or (isinstance(it, dict) and 'Start' in it and 'Subject' in it):
                        start_s = it.get('Start')
                        end_s = it.get('End')
                        subj = it.get('Subject') or it.get('Title') or ''
                        loc = None
                        if isinstance(it.get('Location'), dict):
                            loc = it['Location'].get('DisplayName')
                        # parse datetimes
                        try:
                            start = dtparser.parse(start_s) if start_s else None
                        except Exception:
                            start = None
                        try:
                            end = dtparser.parse(end_s) if end_s else None
                        except Exception:
                            end = None
                        events.append({'start': start.isoformat() if start else None, 'end': end.isoformat() if end else None, 'title': subj, 'location': loc, 'raw': it})
        except Exception as e:
            print('parse capture error', e)

    # Învață mapping-urile din titlurile complete (ex: "Functional programming (FP) - ...")
    # și apoi expandează abrevierile în toate titlurile
    learned = learn_from_events(events)
    if learned:
        print(f'Învățat {len(learned)} mapping-uri din titluri:')
        for abbrev, name in sorted(learned.items()):
            print(f'  {abbrev} -> {name}')
    
    # Aplică expandarea pe toate evenimentele
    for ev in events:
        ev['title'] = expand_title(ev.get('title') or '')

    # dedupe by ItemId if available
    deduped = []
    seen_ids = set()
    for ev in events:
        raw = ev.get('raw') or {}
        iid = None
        if isinstance(raw, dict):
            iid = raw.get('ItemId', {}).get('Id') if raw.get('ItemId') else None
        key = iid or (ev.get('title','') + '|' + (ev.get('start') or ''))
        if key not in seen_ids:
            seen_ids.add(key)
            deduped.append(ev)

    # Salvează și mapping-urile învățate pentru utilizare în UI
    from subject_parser import get_mappings
    mappings_file = out_dir / 'subject_mappings.json'
    with open(mappings_file, 'w', encoding='utf-8') as f:
        json.dump(get_mappings(), f, indent=2, ensure_ascii=False)
    print(f'Saved subject mappings to {mappings_file}')

    # save results
    out_file = out_dir / 'events.json'
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(deduped, f, indent=2, ensure_ascii=False, default=str)
    print('Saved extracted events to', out_file)

    # pretty-print a small timetable summary
    if deduped:
        from collections import defaultdict

        groups = defaultdict(list)
        for ev in deduped:
            start_iso = ev.get('start')
            if start_iso:
                try:
                    d = dtparser.parse(start_iso).date()
                except Exception:
                    d = None
            else:
                d = None
            groups[str(d)].append(ev)

        for day in sorted(groups.keys()):
            print('\n===', day)
            for ev in groups[day]:
                s = ev.get('start') or ''
                e = ev.get('end') or ''
                title = ev.get('title') or ''
                loc = ev.get('location') or ''
                print(f'  {s:25} -> {e:25}  {title}  @ {loc}')
    else:
        print('No events extracted from captured responses.')


if __name__ == '__main__':
    main()
