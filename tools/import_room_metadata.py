#!/usr/bin/env python3
"""Add building and room metadata to calendars table from the Rooms CSV.

It will:
 - ALTER TABLE calendars ADD COLUMN building TEXT
 - ALTER TABLE calendars ADD COLUMN room TEXT
 - For each CSV row, match by PublishedICalUrl or PublishedCalendarUrl (or Email_Sala fallback) and update building/room
 - room is derived as the last segment of Nume_Sala (split by ' - '), trimmed.
"""
import csv
import sqlite3
from pathlib import Path

DB_PATH = Path('data') / 'app.db'
CSV_PATH = Path('Rooms_PUBLISHER_HTML-ICS(in).csv')


def ensure_columns(conn):
    cur = conn.cursor()
    try:
        cur.execute('ALTER TABLE calendars ADD COLUMN building TEXT')
    except Exception:
        pass
    try:
        cur.execute('ALTER TABLE calendars ADD COLUMN room TEXT')
    except Exception:
        pass
    conn.commit()


def extract_room(nume_sala: str) -> str:
    if not nume_sala:
        return ''
    parts = [p.strip() for p in nume_sala.split(' - ') if p.strip()]
    if parts:
        return parts[-1]
    return nume_sala.strip()


def sync_metadata(csv_path: Path):
    if not DB_PATH.exists():
        print('DB not found:', DB_PATH)
        return 2
    if not csv_path.exists():
        print('CSV not found:', csv_path)
        return 1

    with sqlite3.connect(str(DB_PATH)) as conn:
        ensure_columns(conn)
        cur = conn.cursor()
        updated = 0
        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                ical = (row.get('PublishedICalUrl') or '').strip()
                cal = (row.get('PublishedCalendarUrl') or '').strip()
                email = (row.get('Email_Sala') or '').strip()
                building = (row.get('Cladire') or '').strip()
                room = extract_room(row.get('Nume_Sala') or '')

                matched = False
                if ical:
                    cur.execute('UPDATE calendars SET building = ?, room = ? WHERE url = ?', (building or None, room or None, ical))
                    if cur.rowcount:
                        updated += cur.rowcount
                        matched = True
                if not matched and cal:
                    cur.execute('UPDATE calendars SET building = ?, room = ? WHERE url = ?', (building or None, room or None, cal))
                    if cur.rowcount:
                        updated += cur.rowcount
                        matched = True
                if not matched and email:
                    # try matching by name or email substring
                    cur.execute('UPDATE calendars SET building = ?, room = ? WHERE name = ? OR url LIKE ?', (building or None, room or None, email, f'%{email}%'))
                    if cur.rowcount:
                        updated += cur.rowcount
                        matched = True
        conn.commit()

    print(f'Updated building/room on {updated} rows')
    return 0


if __name__ == '__main__':
    import sys
    csvp = Path(sys.argv[1]) if len(sys.argv) > 1 else CSV_PATH
    raise SystemExit(sync_metadata(csvp))
