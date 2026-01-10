#!/usr/bin/env python3
"""
Apply exact CSV matches: read Rooms_PUBLISHER CSV and update calendars.email_address
for calendars whose URL matches exactly one of the CSV's PublishedCalendarUrl or
PublishedICalUrl (normalized scheme and trailing slash). This enforces CSV as the
source of truth for email mappings.

Behavior:
 - Only updates when the CSV contains a matching URL. If the DB already has a
   different email_address, it will be overwritten to the CSV value (to correct
   prior heuristic assignments).
 - Does not touch calendars that have no exact CSV match.
 - Prints a JSON summary of changes.
"""
import csv
import json
import re
import sqlite3
from pathlib import Path

CSV_PATHS = [Path('config') / 'Rooms_PUBLISHER_HTML-ICS(in).csv', Path('Rooms_PUBLISHER_HTML-ICS(in).csv')]
DB_PATH = Path('data') / 'app.db'


def normalize_url(u: str) -> str:
    if not u:
        return ''
    u = u.strip()
    # remove scheme
    u = re.sub(r'^https?://', '', u, flags=re.I)
    # remove trailing slash
    if u.endswith('/'):
        u = u[:-1]
    return u.lower()


def load_csv_map():
    p = next((pp for pp in CSV_PATHS if pp.exists()), None)
    if not p:
        raise SystemExit(f"CSV not found at any of: {CSV_PATHS}")
    m = {}
    with p.open(newline='') as fh:
        rdr = csv.DictReader(fh)
        for r in rdr:
            email = (r.get('Email_Sala') or r.get('Email') or '').strip()
            cal = (r.get('PublishedCalendarUrl') or '').strip()
            ical = (r.get('PublishedICalUrl') or '').strip()
            if cal:
                m[normalize_url(cal)] = email
            if ical:
                m[normalize_url(ical)] = email
    return m


def apply_matches(csv_map):
    if not DB_PATH.exists():
        raise SystemExit(f"DB not found at {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(calendars)")
    cols = [r[1] for r in cur.fetchall()]
    if 'email_address' not in cols:
        cur.execute('ALTER TABLE calendars ADD COLUMN email_address TEXT')

    cur.execute('SELECT id, url, email_address FROM calendars')
    updates = []
    for cid, url, cur_email in cur.fetchall():
        n = normalize_url(url)
        csv_email = csv_map.get(n)
        if csv_email:
            if cur_email != csv_email:
                updates.append({'id': cid, 'old': cur_email, 'new': csv_email, 'url': url})
                cur.execute('UPDATE calendars SET email_address=? WHERE id=?', (csv_email, cid))
    conn.commit()
    conn.close()
    return updates


def main():
    csv_map = load_csv_map()
    updates = apply_matches(csv_map)
    out = {'csv_keys': len(csv_map), 'applied': len(updates), 'updates': updates}
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
