#!/usr/bin/env python3
"""
Script to enforce exact CSV mappings for email addresses, names, and buildings from the publisher CSV.
Updates calendars table with email_address, name, and building from CSV based on URL matches.
"""

import pathlib
import sqlite3
import csv
import sys

def normalize_url(url):
    """Normalize URL by stripping and lowercasing."""
    if not url:
        return ''
    return url.strip().rstrip('/').lower()

def main():
    # Find the CSV file
    csv_filename = 'Rooms_PUBLISHER_HTML-ICS(in).csv'
    csv_paths = [
        pathlib.Path(__file__).parent.parent / 'config' / csv_filename,
        pathlib.Path(__file__).parent.parent / csv_filename,
        pathlib.Path(csv_filename),
    ]
    csv_path = None
    for p in csv_paths:
        print(f"Checking CSV path: {p}")
        if p.exists():
            csv_path = p
            break

    if not csv_path:
        print(f"Error: CSV file '{csv_filename}' not found in any of the expected locations.")
        sys.exit(1)

    print(f"Using CSV: {csv_path}")

    # Build CSV map: normalized_url -> (email, name, building)
    csv_map = {}
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader, None)  # Skip header
        for row in reader:
            if len(row) < 6:
                continue
            name = row[0].strip()
            email = row[1].strip()
            building = row[2].strip() if len(row) > 2 else ''
            html_url = row[4].strip() if len(row) > 4 else ''
            ics_url = row[5].strip() if len(row) > 5 else ''
            
            for url in (html_url, ics_url):
                if url:
                    key = normalize_url(url)
                    csv_map[key] = (email, name, building)

    print(f"CSV keys: {len(csv_map)}")

    # Connect to DB
    db_path = pathlib.Path('data') / 'app.db'
    if not db_path.exists():
        print(f"Error: DB file '{db_path}' not found.")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # Get all calendars
    cur.execute('SELECT id, url, name, building, email_address FROM calendars')
    calendars = cur.fetchall()

    matched = 0
    updated = 0
    for cal_id, url, current_name, current_building, current_email in calendars:
        key = normalize_url(url)
        if key in csv_map:
            matched += 1
            csv_email, csv_name, csv_building = csv_map[key]
            # Update if different
            updates = {}
            if current_email != csv_email:
                updates['email_address'] = csv_email
            if current_name != csv_name:
                updates['name'] = csv_name
            if current_building != csv_building:
                updates['building'] = csv_building
            
            if updates:
                set_clause = ', '.join(f'{k} = ?' for k in updates)
                values = list(updates.values()) + [cal_id]
                cur.execute(f'UPDATE calendars SET {set_clause} WHERE id = ?', values)
                updated += 1
                print(f"Updated calendar {cal_id}: {updates}")

    conn.commit()
    conn.close()

    print(f"Matched CSV keys: {matched}")
    print(f"Applied updates: {updated}")

if __name__ == '__main__':
    main()