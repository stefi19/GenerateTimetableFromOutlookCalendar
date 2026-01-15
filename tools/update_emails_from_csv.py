#!/usr/bin/env python3
"""
Update calendars.email_address from CSV using conservative normalization.

This script builds a map of normalized calendar URL variants -> email (from CSV's
PublishedCalendarUrl/PublishedICalUrl). It marks ambiguous keys (different CSV
emails producing same normalized key) and skips those. Then for each calendar
in the DB it generates the same set of variants and, when an unambiguous match
is found, updates calendars.email_address.

Runs inside the container (expects /app/config/... or /app/ file) and DB at
/app/data/app.db.
"""
import csv
import os
import sqlite3
import json
from urllib.parse import urlparse


csv_candidates = [
    "/app/config/Rooms_PUBLISHER_HTML-ICS(in).csv",
    "/app/Rooms_PUBLISHER_HTML-ICS(in).csv",
    os.path.join(os.getcwd(), 'Rooms_PUBLISHER_HTML-ICS(in).csv'),
]
csv_path = None
for p in csv_candidates:
    if p and os.path.exists(p):
        csv_path = p
        break
db_path = "/app/data/app.db"

if not csv_path:
    print(json.dumps({"error": "CSV not found", "candidates": csv_candidates}))
    raise SystemExit(1)
if not os.path.exists(db_path):
    print(json.dumps({"error": "DB not found", "path": db_path}))
    raise SystemExit(1)


def variants_for_url(u):
    """Return a set of conservative normalized variants for a URL string."""
    if not u:
        return set()
    u = u.strip()
    v = u.rstrip('/').lower()
    vals = set()
    vals.add(v)
    # scheme variants
    if v.startswith('https://'):
        vals.add('http://' + v[len('https://'):])
    if v.startswith('http://'):
        vals.add('https://' + v[len('http://'):])
    # published <-> owa swap
    if '/calendar/published/' in v:
        vals.add(v.replace('/calendar/published/', '/owa/calendar/'))
    if '/owa/calendar/' in v:
        vals.add(v.replace('/owa/calendar/', '/calendar/published/'))
    # .html <-> .ics
    if v.endswith('.html'):
        vals.add(v[:-5] + '.ics')
    if v.endswith('.ics'):
        vals.add(v[:-4] + '.html')
    # also add variants without scheme (host+path) to be a bit more flexible
    try:
        parsed = urlparse(v)
        if parsed.netloc:
            host_path = parsed.netloc + parsed.path
            vals.add(host_path.rstrip('/'))
    except Exception:
        pass
    return vals


# build csv map, but detect ambiguous keys
def build_csv_map(csv_path):
    csv_map = {}
    ambiguous = set()
    rows_seen = 0
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            rows_seen += 1
            if not row or len(row) < 6:
                continue
            email = row[1].strip()
            html = row[4].strip() if len(row) > 4 else ''
            ics = row[5].strip() if len(row) > 5 else ''
            for source in (html, ics):
                if not source:
                    continue
                for k in variants_for_url(source):
                    if k in csv_map:
                        if csv_map[k] != email:
                            ambiguous.add(k)
                            csv_map[k] = None
                    else:
                        csv_map[k] = email
    return csv_map, ambiguous, rows_seen


def main():
    csv_map, ambiguous, rows_seen = build_csv_map(csv_path)
    # now scan DB and update email_address for unambiguous matches
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute('SELECT id, url, email_address FROM calendars ORDER BY id')
        rows = cur.fetchall()
        updates = []
        matched = 0
        for rid, url, cur_email in rows:
            if not url:
                continue
            found_email = None
            tried_keys = set()
            for k in variants_for_url(url):
                tried_keys.add(k)
                if k in ambiguous:
                    # skip ambiguous
                    continue
                if k in csv_map and csv_map[k]:
                    found_email = csv_map[k]
                    break
            if found_email:
                # only update if different
                if (cur_email or '').strip() != found_email:
                    cur.execute('UPDATE calendars SET email_address=? WHERE id=?', (found_email, rid))
                    updates.append({'id': rid, 'old': cur_email, 'new': found_email, 'tried': list(tried_keys)[:6]})
                matched += 1

        conn.commit()
        print(json.dumps({
            'csv_rows': rows_seen,
            'csv_keys': len(csv_map),
            'ambiguous_keys': len(ambiguous),
            'total_db_calendars': len(rows),
            'matched_candidates': matched,
            'updates': updates[:200]
        }, ensure_ascii=False, indent=2))
    finally:
        conn.close()


if __name__ == '__main__':
    main()
