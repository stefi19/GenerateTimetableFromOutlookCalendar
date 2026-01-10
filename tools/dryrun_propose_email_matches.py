#!/usr/bin/env python3
"""
Dry-run proposer: read Rooms_PUBLISHER CSV and local data/app.db, and produce
proposed email_address assignments for calendars using two strategies:

- owner_only: match by the owner segment present in the calendar URL (the
  segment that contains an @, e.g. a3569...@campus.utcluj.ro)
- owner_hash_prefix: match by owner plus a prefix of the next path segment
  (first N chars), which helps disambiguate multiple calendars owned by the
  same mailbox.

This script does NOT modify the DB. It prints a JSON object with counts and
an array of proposed updates you can review.
"""
import csv
import json
import re
import sqlite3
from pathlib import Path
from collections import defaultdict


CSV_PATHS = [Path('config') / 'Rooms_PUBLISHER_HTML-ICS(in).csv', Path('Rooms_PUBLISHER_HTML-ICS(in).csv')]
DB_PATH = Path('data') / 'app.db'


def load_csv_rows():
    p = next((pp for pp in CSV_PATHS if pp.exists()), None)
    if not p:
        raise SystemExit(f"CSV not found at any of: {CSV_PATHS}")
    rows = []
    with p.open(newline='') as fh:
        rdr = csv.DictReader(fh)
        for r in rdr:
            rows.append(r)
    return rows


def csv_key_tokens(url):
    # return (owner, next_segment) or (None,None)
    if not url:
        return (None, None)
    # strip scheme
    u = re.sub(r'^https?://', '', url.strip(), flags=re.I)
    parts = u.split('/')
    # look for a part that contains '@'
    owner = None
    next_seg = None
    for i, part in enumerate(parts):
        if '@' in part:
            owner = part.lower()
            if i + 1 < len(parts):
                next_seg = parts[i+1].lower()
            break
    return (owner, next_seg)


def build_csv_index(rows):
    owner_index = defaultdict(list)
    owner_hash_index = defaultdict(list)
    for r in rows:
        # CSV columns include PublishedCalendarUrl and PublishedICalUrl and Email_Sala
        url = (r.get('PublishedCalendarUrl') or r.get('PublishedICalUrl') or '').strip()
        email = (r.get('Email_Sala') or r.get('Email') or '').strip()
        if not email:
            continue
        owner, next_seg = csv_key_tokens(url)
        if not owner:
            continue
        owner_index[owner].append((email, url, r))
        if next_seg:
            # store prefixes of next_seg for flexibility
            owner_hash_index[(owner, next_seg[:12])].append((email, url, r))
    return owner_index, owner_hash_index


def load_db_calendars():
    if not DB_PATH.exists():
        raise SystemExit(f"DB not found at {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    # detect if email_address column exists
    cur.execute("PRAGMA table_info(calendars)")
    cols = [r[1] for r in cur.fetchall()]
    if 'email_address' in cols:
        cur.execute('SELECT id, url, email_address FROM calendars')
        rows = [{'id': r[0], 'url': r[1], 'email_address': r[2]} for r in cur.fetchall()]
    else:
        cur.execute('SELECT id, url FROM calendars')
        rows = [{'id': r[0], 'url': r[1], 'email_address': None} for r in cur.fetchall()]
    conn.close()
    return rows


def propose_matches(db_rows, owner_index, owner_hash_index):
    proposals = []
    stats = {'total_db': len(db_rows), 'owner_only_matches': 0, 'owner_hash_matches': 0}
    for row in db_rows:
        if row.get('email_address'):
            # already set in DB, skip
            continue
        url = row.get('url') or ''
        owner, next_seg = csv_key_tokens(url)
        candidate_owner = owner_index.get(owner, []) if owner else []
        ambiguous_owner = len(candidate_owner) != 1
        if owner and candidate_owner and not ambiguous_owner:
            # safe owner-only match
            email = candidate_owner[0][0]
            proposals.append({
                'id': row['id'],
                'url': url,
                'strategy': 'owner_only',
                'proposed_email': email,
                'csv_candidates': len(candidate_owner),
                'ambiguous': False,
            })
            stats['owner_only_matches'] += 1
            continue

        # try owner+hash-prefix
        if owner and next_seg:
            key = (owner, next_seg[:12])
            cand = owner_hash_index.get(key, [])
            ambiguous_hash = len(cand) != 1
            if cand and not ambiguous_hash:
                proposals.append({
                    'id': row['id'],
                    'url': url,
                    'strategy': 'owner_hash_prefix',
                    'proposed_email': cand[0][0],
                    'csv_candidates': len(cand),
                    'ambiguous': False,
                })
                stats['owner_hash_matches'] += 1
                continue

        # no safe unambiguous match
        if owner:
            proposals.append({
                'id': row['id'],
                'url': url,
                'strategy': 'none',
                'proposed_email': None,
                'csv_candidates': len(candidate_owner),
                'ambiguous': True if candidate_owner else False,
            })
        else:
            proposals.append({
                'id': row['id'],
                'url': url,
                'strategy': 'none',
                'proposed_email': None,
                'csv_candidates': 0,
                'ambiguous': False,
            })

    return {'stats': stats, 'proposals': proposals}


def main():
    csv_rows = load_csv_rows()
    owner_index, owner_hash_index = build_csv_index(csv_rows)
    db_rows = load_db_calendars()
    result = propose_matches(db_rows, owner_index, owner_hash_index)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
