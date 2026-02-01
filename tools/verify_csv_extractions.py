#!/usr/bin/env python3
"""Verify that every URL in the Rooms_PUBLISHER CSV has a corresponding
playwright_captures/events_<sha8>.json file and optionally retry missing ones.

Creates:
  - playwright_captures/verify_report.json
  - playwright_captures/missing_urls.txt

Usage:
  python tools/verify_csv_extractions.py        # report only
  python tools/verify_csv_extractions.py --retry  # attempt to re-run missing extractions sequentially

The retry action invokes tools/extract_published_events.py per-URL in sequence
(with a small delay) to avoid concurrent Playwright processes that could
exhaust file descriptors.
"""

import argparse
import csv
import hashlib
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).parent.parent
CSV_CANDIDATES = [ROOT / 'config' / 'Rooms_PUBLISHER_HTML-ICS(in).csv', ROOT / 'Rooms_PUBLISHER_HTML-ICS(in).csv', ROOT / 'playwright_captures' / 'Rooms_PUBLISHER_HTML-ICS(in).csv']
OUT_DIR = ROOT / 'playwright_captures'
OUT_DIR.mkdir(exist_ok=True)


def find_csv_path():
    for p in CSV_CANDIDATES:
        try:
            if p.exists():
                return p
        except Exception:
            continue
    return None


def parse_csv(path):
    rows = []
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        rdr = csv.reader(f)
        first = True
        for row in rdr:
            if first:
                first = False
                hdr = '|'.join(row).lower()
                # heuristics: if header row appears, skip it
                if 'published' in hdr or 'nume_sala' in hdr or 'publishedcalendarurl' in hdr or 'html' in hdr or 'ics' in hdr:
                    continue
            if not row or len(row) < 6:
                continue
            name = (row[0] or '').strip()
            email = (row[1] or '').strip()
            html = (row[4] or '').strip()
            ics = (row[5] or '').strip()
            chosen = ics or html
            if not chosen:
                continue
            rows.append({'name': name, 'email': email, 'html': html, 'ics': ics, 'url': chosen})
    return rows


def sha8(u: str) -> str:
    return hashlib.sha1(u.encode('utf-8')).hexdigest()[:8]


def check_events_file(h: str):
    p = OUT_DIR / f'events_{h}.json'
    if not p.exists():
        return False, 0
    try:
        data = json.load(open(p, 'r', encoding='utf-8'))
        if isinstance(data, list) and len(data) > 0:
            return True, len(data)
        return False, len(data) if isinstance(data, list) else 0
    except Exception:
        return False, 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--retry', action='store_true', help='Attempt to re-run missing extractions sequentially')
    ap.add_argument('--delay', type=float, default=1.0, help='Delay between retries (seconds)')
    ap.add_argument('--limit', type=int, default=0, help='If >0, only process this many rows (useful for testing)')
    args = ap.parse_args()

    csv_path = find_csv_path()
    if not csv_path:
        print('No publisher CSV found in expected locations:')
        for c in CSV_CANDIDATES:
            print('  -', c)
        sys.exit(2)

    rows = parse_csv(csv_path)
    total = len(rows)
    print(f'CSV rows discovered: {total} (using {csv_path})')

    missing = []
    present = []
    for i, r in enumerate(rows):
        if args.limit and i >= args.limit:
            break
        u = r['url']
        h = sha8(u)
        ok, count = check_events_file(h)
        if ok:
            present.append({'idx': i, 'url': u, 'hash': h, 'events': count, 'name': r.get('name')})
        else:
            missing.append({'idx': i, 'url': u, 'hash': h, 'events': count, 'name': r.get('name')})

    report = {
        'csv_path': str(csv_path),
        'total_rows': total,
        'present_count': len(present),
        'missing_count': len(missing),
        'present': present,
        'missing': missing,
        'checked_at': int(time.time())
    }

    report_path = OUT_DIR / 'verify_report.json'
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    missing_list_path = OUT_DIR / 'missing_urls.txt'
    with open(missing_list_path, 'w', encoding='utf-8') as f:
        for m in missing:
            f.write(m['url'] + '\n')

    print('Present:', len(present), ' Missing:', len(missing))
    print('Report written to', report_path)
    print('Missing list written to', missing_list_path)

    if args.retry and missing:
        print('Retrying missing extractions sequentially...')
        script = ROOT / 'tools' / 'extract_published_events.py'
        if not script.exists():
            print('Extractor script not found at', script)
            sys.exit(3)
        for idx, m in enumerate(missing, start=1):
            url = m['url']
            h = m['hash']
            print(f'[{idx}/{len(missing)}] Running extractor for {url} -> hash {h}')
            outf = OUT_DIR / f'extract_retry_{h}.stdout.txt'
            errf = OUT_DIR / f'extract_retry_{h}.stderr.txt'
            try:
                with open(outf, 'w', encoding='utf-8') as of, open(errf, 'w', encoding='utf-8') as ef:
                    rc = subprocess.run([sys.executable, str(script), url], stdout=of, stderr=ef, env={'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'})
                print('rc=', rc.returncode)
            except Exception as e:
                print('failed to run extractor for', url, 'err=', e)
            time.sleep(args.delay)
        print('Retry pass complete; re-run without --retry to regenerate report')


if __name__ == '__main__':
    main()
