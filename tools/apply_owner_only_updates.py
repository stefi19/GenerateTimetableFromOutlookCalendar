#!/usr/bin/env python3
"""
Apply owner-only proposals (unambiguous) from proposals_output.json to data/app.db.
This script:
 - reads tools/proposals_output.json
 - filters proposals where strategy=='owner_only' and proposed_email is set
 - for each proposal, updates calendars.email_address only if current value is NULL
 - reports summary of applied updates

Backed-up DB must exist (created before running).
"""
import json
import sqlite3
from pathlib import Path

PROPOSALS = Path('tools') / 'proposals_output.json'
DB = Path('data') / 'app.db'


def main():
    if not PROPOSALS.exists():
        raise SystemExit(f"Proposals file not found: {PROPOSALS}")
    if not DB.exists():
        raise SystemExit(f"DB not found: {DB}")
    doc = json.loads(PROPOSALS.read_text())
    props = [p for p in doc.get('proposals', []) if p.get('strategy')=='owner_only' and p.get('proposed_email')]
    if not props:
        print('No owner_only proposals found')
        return
    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()
    # ensure email_address column exists
    cur.execute("PRAGMA table_info(calendars)")
    cols = [r[1] for r in cur.fetchall()]
    if 'email_address' not in cols:
        print('email_address column not present in DB; adding it (NULLable)')
        cur.execute('ALTER TABLE calendars ADD COLUMN email_address TEXT')
    applied = []
    for p in props:
        pid = p['id']
        email = p['proposed_email']
        cur.execute('SELECT email_address FROM calendars WHERE id=?', (pid,))
        row = cur.fetchone()
        if not row:
            continue
        if row[0] is None:
            cur.execute('UPDATE calendars SET email_address=? WHERE id=?', (email, pid))
            applied.append({'id': pid, 'email': email})
    conn.commit()
    conn.close()
    print({'applied_count': len(applied), 'applied': applied})


if __name__ == '__main__':
    main()
