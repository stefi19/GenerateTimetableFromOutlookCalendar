#!/usr/bin/env python3
"""Sync calendars.enabled in data/app.db from the Rooms_PUBLISHER CSV's 'Optiune_Delegat' column.

If Optiune_Delegat is 'TRUE' (case-insensitive) the calendar will be enabled (1), otherwise disabled (0).
Matching is done by PublishedICalUrl first, then PublishedCalendarUrl, and finally by Email_Sala if needed.
"""
import csv
import sqlite3
from pathlib import Path

DB_PATH = Path('data') / 'app.db'


def normalize_bool(val: str) -> int:
    if not val:
        return 0
    v = val.strip().lower()
    return 1 if v in ('true', '1', 'yes', 'y', 't') else 0


def sync(csv_path: Path):
    if not csv_path.exists():
        print('CSV not found:', csv_path)
        return 1
    if not DB_PATH.exists():
        print('DB not found:', DB_PATH)
        return 2

    updated = 0
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                ical = (row.get('PublishedICalUrl') or '').strip()
                cal = (row.get('PublishedCalendarUrl') or '').strip()
                email = (row.get('Email_Sala') or '').strip()
                enabled = normalize_bool(row.get('Optiune_Delegat') or '')

                if ical:
                    cur.execute('UPDATE calendars SET enabled = ? WHERE url = ?', (enabled, ical))
                    if cur.rowcount:
                        updated += cur.rowcount
                        continue
                if cal:
                    cur.execute('UPDATE calendars SET enabled = ? WHERE url = ?', (enabled, cal))
                    if cur.rowcount:
                        updated += cur.rowcount
                        continue
                if email:
                    # try to match by name/email
                    cur.execute('UPDATE calendars SET enabled = ? WHERE name = ? OR url LIKE ?', (enabled, email, f'%{email}%'))
                    if cur.rowcount:
                        updated += cur.rowcount
                        continue
        conn.commit()

    print(f'Updated enabled flag on {updated} rows')
    return 0


if __name__ == '__main__':
    import sys
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('Rooms_PUBLISHER_HTML-ICS(in).csv')
    raise SystemExit(sync(csv_path))
