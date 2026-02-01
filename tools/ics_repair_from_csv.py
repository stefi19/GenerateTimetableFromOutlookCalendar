#!/usr/bin/env python3
"""ICS-first repair: read CSV (publisher) and for every .ics URL that lacks
a corresponding playwright_captures/events_<sha8>.json file, parse the ICS
and write the per-calendar JSON file. This is safe to run repeatedly.
"""
import csv
import hashlib
import json
import time
import sys
from pathlib import Path

# Ensure project root is on sys.path so `import timetable` works when this
# script is executed from tools/ (subprocess cwd may vary).
proj_root = Path(__file__).parent.parent.resolve()
if str(proj_root) not in sys.path:
    sys.path.insert(0, str(proj_root))
# Also tolerate being executed in environments where project root isn't
# discoverable; `/app` is the container working directory for the app.
if '/app' not in sys.path:
    sys.path.insert(0, '/app')

from timetable import parse_ics_from_url


def find_csv_path():
    candidates = [
        Path('config/Rooms_PUBLISHER_HTML-ICS(in).csv'),
        Path('Rooms_PUBLISHER_HTML-ICS(in).csv'),
        Path('playwright_captures/Rooms_PUBLISHER_HTML-ICS(in).csv'),
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def main():
    csvp = find_csv_path()
    if not csvp:
        print('No publisher CSV found; nothing to repair')
        return 2

    outdir = Path('playwright_captures')
    outdir.mkdir(exist_ok=True)

    urls = []
    with open(csvp, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            ics = row[5].strip() if len(row) > 5 else ''
            html = row[4].strip() if len(row) > 4 else ''
            url = ics or html
            if not url:
                continue
            if url.lower().endswith('.ics'):
                urls.append(url)

    missing = []
    for url in urls:
        sha = hashlib.sha1(url.encode('utf-8')).hexdigest()[:8]
        dest = outdir / f'events_{sha}.json'
        if not dest.exists():
            missing.append((url, dest))

    print('Found', len(urls), 'ICS URLs, missing to repair:', len(missing))
    created = 0
    failed = 0
    for i, (url, dest) in enumerate(missing, 1):
        print(f'[{i}/{len(missing)}] Parsing: {url}')
        try:
            evs = parse_ics_from_url(url, verbose=False)
            arr = []
            for e in evs:
                arr.append({
                    'start': e.start.isoformat() if getattr(e, 'start', None) else None,
                    'end': e.end.isoformat() if getattr(e, 'end', None) else None,
                    'title': getattr(e, 'title', None),
                    'location': getattr(e, 'location', None),
                    'description': getattr(e, 'description', None)
                })
            with open(dest, 'w', encoding='utf-8') as f:
                json.dump(arr, f, indent=2, ensure_ascii=False)
            print(' Wrote', dest.name, 'len', len(arr))
            created += 1
        except Exception as exc:
            print(' Failed to parse/write:', exc)
            failed += 1
        time.sleep(0.15)

    # report summary
    all_files = list(outdir.glob('events_*.json'))
    nonzero = 0
    for p in all_files:
        try:
            data = json.load(open(p, 'r', encoding='utf-8'))
            if isinstance(data, list) and len(data) > 0:
                nonzero += 1
        except Exception:
            pass

    print('\nRepair finished. created=', created, 'failed=', failed, 'total_events_files=', len(all_files), 'non-empty=', nonzero)
    return 0


if __name__ == '__main__':
    sys.exit(main())
