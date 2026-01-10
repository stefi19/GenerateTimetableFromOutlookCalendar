#!/usr/bin/env python3
"""
Apply token-based matching: extract owner email and hash prefix from calendar URLs
and match against CSV entries (owner+hash_prefix). Only unambiguous matches are applied.

This will update calendars.email_address for rows where email_address is currently NULL.
"""
import csv
import os
import sqlite3
import json
from urllib.parse import urlparse


CSV_CANDIDATES = [
    "/app/config/Rooms_PUBLISHER_HTML-ICS(in).csv",
    "/app/Rooms_PUBLISHER_HTML-ICS(in).csv",
    os.path.join(os.getcwd(), 'Rooms_PUBLISHER_HTML-ICS(in).csv'),
]


def find_csv_path():
    for p in CSV_CANDIDATES:
        if p and os.path.exists(p):
            return p
    return None


def extract_owner_and_hash(url: str):
    """Return (owner_email, hash_segment) or (None,None).
    owner_email is the path segment containing '@campus.utcluj.ro' (or '@').
    hash_segment is the next path segment after owner_email (likely long hex).
    """
    if not url:
        return None, None
    try:
        u = url.strip()
        # strip query and fragment
        p = urlparse(u)
        path = p.path
        parts = [seg for seg in path.split('/') if seg]
        owner = None
        h = None
        for i,seg in enumerate(parts):
            if '@' in seg:
                owner = seg
                # next segment if exists
                if i+1 < len(parts):
                    h = parts[i+1]
                break
        return owner, h
    except Exception:
        return None, None


def build_csv_index(csv_path):
    """Build index mapping (owner, hash_prefix) -> email. Detect ambiguous keys."""
    index = {}
    ambiguous = set()
    rows = 0
    with open(csv_path, newline='', encoding='utf-8') as f:
        rdr = csv.reader(f)
        for row in rdr:
            rows += 1
            if not row or len(row) < 6:
                continue
            email = row[1].strip()
            html = row[4].strip() if len(row) > 4 else ''
            ics = row[5].strip() if len(row) > 5 else ''
            for src in (html, ics):
                if not src:
                    continue
                owner, h = extract_owner_and_hash(src)
                if not owner or not h:
                    continue
                key = (owner.lower(), h[:8])
                if key in index:
                    if index[key] != email:
                        ambiguous.add(key)
                        index[key] = None
                else:
                    index[key] = email
    return index, ambiguous, rows


def apply_matches(db_path, index, ambiguous):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('SELECT id, url, email_address FROM calendars ORDER BY id')
    rows = cur.fetchall()
    updates = []
    applied = 0
    for rid, url, current in rows:
        if current is not None:
            continue
        owner, h = extract_owner_and_hash(url or '')
        if not owner or not h:
            continue
        key = (owner.lower(), h[:8])
        if key in ambiguous:
            continue
        if key in index and index[key]:
            cur.execute('UPDATE calendars SET email_address=? WHERE id=?', (index[key], rid))
            updates.append({'id': rid, 'url': url, 'new': index[key]})
            applied += 1
    conn.commit()
    conn.close()
    return updates


def main():
    csv_path = find_csv_path()
    if not csv_path:
        print(json.dumps({'error': 'csv not found', 'candidates': CSV_CANDIDATES}, indent=2))
        return
    db_path = '/app/data/app.db'
    if not os.path.exists(db_path):
        print(json.dumps({'error': 'db not found', 'path': db_path}, indent=2))
        return

    index, ambiguous, csv_rows = build_csv_index(csv_path)
    print(json.dumps({'csv_rows': csv_rows, 'index_keys': len(index), 'ambiguous': len(ambiguous)}))

    updates = apply_matches(db_path, index, ambiguous)
    print(json.dumps({'applied_updates': len(updates), 'updates_sample': updates[:200]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
