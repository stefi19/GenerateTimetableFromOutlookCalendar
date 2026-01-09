#!/usr/bin/env python3
"""Assign colors to calendars in data/app.db that don't have one.

Colors are chosen deterministically from a palette using a hash of the URL so
re-running the script won't reassign different colors and will avoid duplication.
"""
import sqlite3
import hashlib
from pathlib import Path

DB_PATH = Path('data') / 'app.db'

PALETTE = [
    '#003366', '#0066cc', '#28a745', '#dc3545', '#fd7e14', '#6f42c1', '#20c997', '#e83e8c',
    '#17a2b8', '#6610f2', '#007bff', '#6610f2', '#e6590f', '#661000'
]


def pick_color_for_url(url: str) -> str:
    h = hashlib.sha1(url.encode('utf-8')).hexdigest()
    v = int(h[:8], 16)
    return PALETTE[v % len(PALETTE)]


def assign_colors():
    if not DB_PATH.exists():
        print('DB not found:', DB_PATH)
        return 1

    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute('SELECT id, url, name, color FROM calendars')
        rows = cur.fetchall()
        updated = 0
        for r in rows:
            cid, url, name, color = r
            if color and str(color).strip():
                continue
            if not url:
                continue
            col = pick_color_for_url(url)
            cur.execute('UPDATE calendars SET color = ? WHERE id = ?', (col, cid))
            updated += 1
        conn.commit()

    print(f'Assigned colors to {updated} calendars')
    return 0


if __name__ == '__main__':
    raise SystemExit(assign_colors())
