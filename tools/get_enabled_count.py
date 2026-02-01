#!/usr/bin/env python3
"""Return count of enabled calendars in the DB.

This is used by `entrypoint.sh` to decide whether to start the detached
extractor without executing Python code via stdin (which sets __file__ to
undefined and can break imports that rely on it).
"""
import sqlite3
import pathlib
import os
import sys

db = pathlib.Path(__file__).parent.parent / 'data' / 'app.db'
if not db.exists():
    print(0)
    sys.exit(0)

try:
    conn = sqlite3.connect(str(db))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM calendars WHERE enabled=1 AND url IS NOT NULL")
    r = cur.fetchone()
    print(r[0] if r else 0)
except Exception:
    print(0)
finally:
    try:
        conn.close()
    except Exception:
        pass
