#!/usr/bin/env python3
"""
Enforce CSV email -> calendar mapping.

For every PublishedCalendarUrl and PublishedICalUrl in the CSV, find matching
calendar rows in data/app.db by normalized URL and set calendars.email_address to
the CSV Email_Sala value (overwrite existing value).

Outputs a JSON summary and writes unmatched CSV keys to tools/csv_unmatched.json
for review.
"""
import csv
import json
import re
import sqlite3
from pathlib import Path

CSV_PATHS = [Path('Rooms_PUBLISHER_HTML-ICS(in).csv'), Path('config') / 'Rooms_PUBLISHER_HTML-ICS(in).csv']
DB_PATH = Path('data') / 'app.db'


def normalize_url(u: str) -> str:
    if not u:
        return ''
    u = u.strip()
    u = re.sub(r'^https?://', '', u, flags=re.I)
    if u.endswith('/'):
        u = u[:-1]
    return u.lower()


def load_csv():
    p = next((pp for pp in CSV_PATHS if pp.exists()), None)
    if not p:
        raise SystemExit(f"CSV not found at any of: {CSV_PATHS}")
    rows = []
    with p.open(newline='') as fh:
        rdr = csv.DictReader(fh)
        for r in rdr:
            rows.append(r)
    return rows


def build_map(rows):
    m = {}
    for r in rows:
        email = (r.get('Email_Sala') or r.get('Email') or '').strip()
        cal = (r.get('PublishedCalendarUrl') or '').strip()
        ical = (r.get('PublishedICalUrl') or '').strip()
        if cal:
            m[normalize_url(cal)] = email
        if ical:
            m[normalize_url(ical)] = email
    return m


def apply_map(csv_map):
    if not DB_PATH.exists():
        raise SystemExit(f"DB not found: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(calendars)")
    cols = [r[1] for r in cur.fetchall()]
    if 'email_address' not in cols:
        cur.execute('ALTER TABLE calendars ADD COLUMN email_address TEXT')

    cur.execute('SELECT id, url, email_address FROM calendars')
    db_rows = cur.fetchall()

    updated = []
    matched_csv_keys = set()
    for cid, url, cur_email in db_rows:
        n = normalize_url(url)
        csv_email = csv_map.get(n)
        if csv_email is not None and csv_email != '':
            matched_csv_keys.add(n)
            if cur_email != csv_email:
                cur.execute('UPDATE calendars SET email_address=? WHERE id=?', (csv_email, cid))
                updated.append({'id': cid, 'url': url, 'old': cur_email, 'new': csv_email})

    conn.commit()
    conn.close()
    return updated, matched_csv_keys


def main():
    rows = load_csv()
    csv_map = build_map(rows)
    updates, matched = apply_map(csv_map)
    unmatched = [k for k in csv_map.keys() if k not in matched]
    Path('tools').mkdir(exist_ok=True)
    Path('tools/csv_unmatched.json').write_text(json.dumps(unmatched, indent=2, ensure_ascii=False))
    out = {'csv_keys': len(csv_map), 'matched_csv_keys': len(matched), 'applied_updates': len(updates)}
    out['updates_sample'] = updates[:50]
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
