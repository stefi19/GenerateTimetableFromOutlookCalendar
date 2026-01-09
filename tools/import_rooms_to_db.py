#!/usr/bin/env python3
"""
Import calendars from the Rooms_PUBLISHER CSV into the application's SQLite DB.

Usage:
  python tools/import_rooms_to_db.py Rooms_PUBLISHER_HTML-ICS(in).csv

This script inserts rows into data/app.db -> calendars (url, name, color, enabled, created_at).
It uses INSERT OR IGNORE so existing URLs are skipped. If a calendar exists with empty name,
the script will update the name when a non-empty name is available.
"""
import csv
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


DB_PATH = Path('data') / 'app.db'


def ensure_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS calendars (
                id INTEGER PRIMARY KEY,
                url TEXT UNIQUE,
                name TEXT,
                color TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TEXT,
                last_fetched TEXT
            )
        ''')
        conn.commit()


def import_csv(csv_path: Path):
    if not csv_path.exists():
        print(f"CSV file not found: {csv_path}")
        return 1

    ensure_db()

    inserted = 0
    skipped = 0
    updated_name = 0

    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Prefer PublishedICalUrl, fallback to PublishedCalendarUrl
                ical = (row.get('PublishedICalUrl') or '').strip()
                cal = (row.get('PublishedCalendarUrl') or '').strip()
                url = ical or cal
                if not url:
                    # Nothing to import for this row
                    skipped += 1
                    continue
                name = (row.get('Nume_Sala') or row.get('Email_Sala') or '').strip()

                # Insert or ignore based on unique url
                cur.execute('INSERT OR IGNORE INTO calendars (url, name, color, enabled, created_at) VALUES (?, ?, ?, 1, ?)',
                            (url, name or '', None, datetime.utcnow().isoformat()))
                if cur.rowcount > 0:
                    inserted += 1
                else:
                    # existing row - if name empty in DB and current name non-empty, update it
                    if name:
                        cur.execute('SELECT name FROM calendars WHERE url = ?', (url,))
                        r = cur.fetchone()
                        db_name = r[0] if r else None
                        if not db_name:
                            cur.execute('UPDATE calendars SET name = ? WHERE url = ?', (name, url))
                            updated_name += 1
                    skipped += 1
        conn.commit()

    print(f"Imported: {inserted}, Skipped(existing/no-url): {skipped}, Updated names: {updated_name}")
    return 0


def main(argv):
    if len(argv) < 2:
        print("Usage: python tools/import_rooms_to_db.py <csv-file>")
        return 2
    csv_path = Path(argv[1])
    return import_csv(csv_path)


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
