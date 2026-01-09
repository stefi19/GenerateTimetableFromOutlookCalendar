#!/usr/bin/env python3
"""
Enable all calendars in the SQLite DB by setting `enabled` = 1 for all rows.
Prints counts before and after. Safe to run multiple times.

Usage:
  python3 tools/enable_all_calendars.py --db data/app.db
"""
import argparse
import sqlite3
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--db', default='data/app.db')
    args = p.parse_args()

    dbp = Path(args.db)
    if not dbp.exists():
        print('DB not found:', dbp)
        return

    conn = sqlite3.connect(str(dbp))
    cur = conn.cursor()

    try:
        cur.execute('SELECT COUNT(*) FROM calendars')
        total = cur.fetchone()[0]
    except Exception as e:
        print('Error reading calendars table:', e)
        conn.close()
        return

    cur.execute('SELECT COUNT(*) FROM calendars WHERE enabled = 1')
    enabled_before = cur.fetchone()[0]

    print(f'Total calendars: {total}')
    print(f'Enabled before: {enabled_before}')

    # Update all
    cur.execute('UPDATE calendars SET enabled = 1 WHERE enabled IS NULL OR enabled = 0')
    conn.commit()

    cur.execute('SELECT COUNT(*) FROM calendars WHERE enabled = 1')
    enabled_after = cur.fetchone()[0]
    print(f'Enabled after: {enabled_after}')

    conn.close()


if __name__ == '__main__':
    main()
