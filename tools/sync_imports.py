#!/usr/bin/env python3
"""
Safe sync/import script for calendars and buildings.

Usage:
  python tools/sync_imports.py --csv path/to/new_calendars.csv [--db data/app.db]

Behavior:
 - Adds a `source` column to `calendars` (SQLite ALTER TABLE ADD COLUMN) if missing and sets existing rows to 'server'.
 - For each row in the CSV (columns: url,name,building,room,color,enabled,upn):
     - If a calendar with the same url does not exist -> INSERT with source='import'.
     - If exists and source == 'import' -> UPDATE the provided fields.
     - If exists and source == 'server' -> SKIP (do not overwrite server-managed rows).

This allows you to safely push your locally added calendars/buildings to a remote VM DB
without clobbering records that the server or other processes manage.
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path
from typing import Dict, Any, List


DEFAULT_DB = Path('data') / 'app.db'


def get_columns(conn: sqlite3.Connection) -> List[str]:
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(calendars)")
    cols = [r[1] for r in cur.fetchall()]
    return cols


def ensure_source_column(conn: sqlite3.Connection):
    cols = get_columns(conn)
    if 'source' in cols:
        return
    print('Adding source column to calendars (existing rows will be marked as server)')
    cur = conn.cursor()
    cur.execute("ALTER TABLE calendars ADD COLUMN source TEXT DEFAULT 'server'")
    conn.commit()


def read_csv(path: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with path.open('r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows


def normalize_bool(v: str) -> int:
    if v is None:
        return 0
    v = v.strip().lower()
    return 1 if v in ('1', 'true', 'yes', 'y', 'on') else 0


def sync_rows(conn: sqlite3.Connection, rows: List[Dict[str, str]]):
    cur = conn.cursor()
    cols = get_columns(conn)
    allowed = set(cols) & set(['url', 'name', 'building', 'room', 'color', 'enabled', 'upn', 'source'])
    print('Allowed columns detected in DB:', allowed)

    for r in rows:
        url = (r.get('url') or '').strip()
        if not url:
            print('Skipping row without url:', r)
            continue

        cur.execute('SELECT rowid, source FROM calendars WHERE url = ?', (url,))
        found = cur.fetchone()
        if not found:
            # Insert new row
            data = {}
            for c in ('url', 'name', 'building', 'room', 'color', 'upn'):
                if c in allowed and r.get(c) is not None:
                    data[c] = r.get(c)
            if 'enabled' in allowed:
                data['enabled'] = normalize_bool(r.get('enabled', '1'))
            data['source'] = 'import'

            keys = ','.join(data.keys())
            placeholders = ','.join('?' for _ in data)
            vals = list(data.values())
            sql = f'INSERT INTO calendars ({keys}) VALUES ({placeholders})'
            cur.execute(sql, vals)
            print('Inserted new calendar:', url)
        else:
            rowid, source = found
            if source != 'import':
                print('Skipping existing server-managed calendar (won\'t overwrite):', url)
                continue
            # Update only allowed fields for import-source rows
            updates = {}
            for c in ('name', 'building', 'room', 'color', 'upn'):
                if c in allowed and r.get(c) is not None:
                    updates[c] = r.get(c)
            if 'enabled' in allowed and r.get('enabled') is not None:
                updates['enabled'] = normalize_bool(r.get('enabled'))
            if updates:
                set_clause = ','.join(f"{k} = ?" for k in updates)
                vals = list(updates.values()) + [rowid]
                sql = f'UPDATE calendars SET {set_clause} WHERE rowid = ?'
                cur.execute(sql, vals)
                print('Updated imported calendar:', url)
            else:
                print('No updatable fields for', url)

    conn.commit()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--csv', required=True, help='Path to CSV with new calendars')
    p.add_argument('--db', default=str(DEFAULT_DB), help='Path to SQLite DB (default: data/app.db)')
    args = p.parse_args()

    dbp = Path(args.db)
    if not dbp.exists():
        print('DB not found:', dbp)
        return

    rows = read_csv(Path(args.csv))
    if not rows:
        print('No rows found in CSV')
        return

    conn = sqlite3.connect(str(dbp))
    ensure_source_column(conn)
    sync_rows(conn, rows)
    conn.close()
    print('Sync complete')


if __name__ == '__main__':
    main()
