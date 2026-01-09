#!/usr/bin/env python3
"""
Parse room strings from a CSV and update the `calendars` table with
`building` and `room` columns for display in the application.

Example formats handled (case-insensitive):
  - "UTCN - AIRI Observatorului 2 - Sala 104"
  - "AIRI Observatorului 2 - Sala 104"
  - "UTCN - Building X - sala 2A"

Usage:
  python3 tools/parse_room_template.py Rooms_PUBLISHER_HTML-ICS(in).csv --db data/app.db

Supports --dry-run (no DB writes) and prints a short summary + samples.
"""
import argparse
import csv
import re
import sqlite3
from pathlib import Path
from typing import Optional, Tuple


def parse_room_string(s: str) -> Optional[Tuple[str, str]]:
    """Parse a string like "UTCN - AIRI Observatorului 2 - Sala 104".

    Returns (building, room) or None if unable to parse.
    """
    if not s:
        return None
    text = s.strip()

    # Try a canonical regex: optional leading UTCN -, then building, then - Sala <room>
    m = re.match(r"^(?:UTCN\s*-\s*)?(?P<building>.*?)\s*-\s*(?:Sala|sala|Room|room|Rm)\s*[:\-]?\s*(?P<room>.+)$", text)
    if m:
        building = m.group('building').strip()
        room = m.group('room').strip()
        # Normalise: remove leading UTCN if present in building
        building = re.sub(r"^UTCN\s*-\s*", "", building, flags=re.I).strip()
        # Remove punctuation around room
        room = room.rstrip(' .,:;')
        # If room like "Sala 104", strip any remaining Sala
        room = re.sub(r'^(?:Sala|sala|Room|room|Rm)\s*[:\-]?\s*', '', room)
        return building, room

    # If no explicit 'Sala' token, try splitting by ' - ' and assume last part is room
    parts = [p.strip() for p in text.split(' - ')]
    if len(parts) >= 2:
        last = parts[-1]
        # If last contains digits (typical room number), accept it as room
        if re.search(r'\d', last):
            building = ' - '.join(parts[:-1]).strip()
            building = re.sub(r"^UTCN\s*-\s*", "", building, flags=re.I).strip()
            room = re.sub(r'^(?:Sala|sala|Room|room|Rm)\s*[:\-]?\s*', '', last).strip()
            return building, room

    # As a last resort, try to find 'Sala <num>' anywhere
    m2 = re.search(r'(?:Sala|sala|Room|room|Rm)\s*[:\-]?\s*(?P<room>\w[\w -]*)', text)
    if m2:
        room = m2.group('room').strip()
        # building will be text without the matched portion
        building = re.sub(m2.group(0), '', text).strip(' -;:,')
        building = re.sub(r"^UTCN\s*-\s*", "", building, flags=re.I).strip()
        return building, room

    return None


def ensure_columns(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(calendars)")
    cols = {r[1] for r in cur.fetchall()}
    if 'building' not in cols:
        cur.execute("ALTER TABLE calendars ADD COLUMN building TEXT")
    if 'room' not in cols:
        cur.execute("ALTER TABLE calendars ADD COLUMN room TEXT")
    conn.commit()


def find_name_field(headers):
    # Prefer exact 'Nume_Sala' or 'Nume Sala', else any header containing 'sala' or 'room'
    candidates = [h for h in headers if h.lower() in ('nume_sala', 'nume sala', 'nume', 'name')]
    if candidates:
        return candidates[0]
    for h in headers:
        if 'sala' in h.lower() or 'room' in h.lower():
            return h
    # fallback to first header
    return headers[0] if headers else None


def main():
    p = argparse.ArgumentParser(description='Parse room strings and update DB with building/room')
    p.add_argument('csvfile', help='CSV file to parse')
    p.add_argument('--db', default='data/app.db', help='SQLite DB path (default data/app.db)')
    p.add_argument('--dry-run', action='store_true', help='Do not update the DB; just print summary')
    p.add_argument('--sample', type=int, default=10, help='How many sample parsed rows to show')
    args = p.parse_args()

    csv_path = Path(args.csvfile)
    if not csv_path.exists():
        print(f"CSV file not found: {csv_path}")
        return

    rows_processed = 0
    parsed = 0
    updated = 0
    samples = []

    with csv_path.open(newline='', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh)
        headers = reader.fieldnames or []
        name_field = find_name_field(headers)
        # Try also to detect published url fields
        url_field = None
        for candidate in ('PublishedICalUrl', 'PublishedCalendarUrl', 'PublishedUrl', 'Url'):
            if candidate in headers:
                url_field = candidate
                break

        # Prepare DB connection
        conn = sqlite3.connect(args.db)
        try:
            ensure_columns(conn)
        except Exception as e:
            print('Warning: could not ensure columns:', e)

        cur = conn.cursor()

        for row in reader:
            rows_processed += 1
            raw = ''
            if name_field and name_field in row:
                raw = (row.get(name_field) or '').strip()
            # If empty and there's a 'Nume_Sala' fallback or other fields, try them
            if not raw:
                # try any header that contains 'sala' or 'room'
                for h in headers:
                    if 'sala' in h.lower() or 'room' in h.lower():
                        raw = (row.get(h) or '').strip()
                        if raw:
                            break

            if not raw:
                continue

            res = parse_room_string(raw)
            if not res:
                # skip unparsable entries
                continue
            building, room = res
            parsed += 1
            if len(samples) < args.sample:
                samples.append((raw, building, room))

            # Attempt to update DB: match by published url if available, else by name
            matched = False
            if url_field and row.get(url_field):
                url_val = row.get(url_field).strip()
                if url_val:
                    cur.execute('SELECT id FROM calendars WHERE url = ? COLLATE NOCASE', (url_val,))
                    r = cur.fetchone()
                    if r:
                        cal_id = r[0]
                        if not args.dry_run:
                            cur.execute('UPDATE calendars SET building = ?, room = ? WHERE id = ?', (building, room, cal_id))
                            conn.commit()
                        updated += 1
                        matched = True

            if not matched:
                # try match by exact name
                cur.execute('SELECT id, name FROM calendars WHERE name = ? COLLATE NOCASE', (raw,))
                r = cur.fetchone()
                if r:
                    cal_id = r[0]
                    if not args.dry_run:
                        cur.execute('UPDATE calendars SET building = ?, room = ? WHERE id = ?', (building, room, cal_id))
                        conn.commit()
                    updated += 1
                    matched = True

            if not matched:
                # try like match (name contains raw)
                cur.execute('SELECT id, name FROM calendars WHERE name LIKE ? COLLATE NOCASE LIMIT 1', (f'%{raw}%',))
                r = cur.fetchone()
                if r:
                    cal_id = r[0]
                    if not args.dry_run:
                        cur.execute('UPDATE calendars SET building = ?, room = ? WHERE id = ?', (building, room, cal_id))
                        conn.commit()
                    updated += 1
                    matched = True

        conn.close()

    print(f'Rows scanned: {rows_processed}')
    print(f'Parsed building/room: {parsed}')
    print(f'DB rows updated: {updated} (dry-run={args.dry_run})')
    if samples:
        print('\nSample parses:')
        for raw, building, room in samples:
            print(f'  "{raw}" -> building="{building}", room="{room}"')


if __name__ == '__main__':
    main()
