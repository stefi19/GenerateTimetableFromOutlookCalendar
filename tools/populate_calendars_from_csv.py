#!/usr/bin/env python3
"""
Script to populate calendars table with all URLs from the publisher CSV.
Adds unique calendar URLs to the DB for later processing.
"""

import pathlib
import sqlite3
import csv
import sys

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
        if p.exists():
            csv_path = p
            break

    if not csv_path:
        print(f"Error: CSV file '{csv_filename}' not found.")
        sys.exit(1)

    print(f"Using CSV: {csv_path}")

    # Collect unique URLs and names (CSV uses: name, email, ..., html(col4), ics(col5))
    urls = set()
    names_by_url = {}
    import re

    def _format_email_to_name(email: str) -> str:
        if not email:
            return ''
        local = email.split('@', 1)[0]
        parts = re.split(r'[^0-9A-Za-z]+', local)
        parts = [p for p in parts if p and p.lower() != 'room']
        if not parts:
            return local
        out_parts = [p.upper() if not p.isdigit() else p for p in parts]
        return ' '.join(out_parts)

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader, None)  # Skip header if present
        for row in reader:
            # prefer ICS (col 5) then HTML (col 4)
            html_url = row[4].strip() if len(row) > 4 else ''
            ics_url = row[5].strip() if len(row) > 5 else ''
            url = ics_url or html_url
            if not url:
                continue
            urls.add(url)
            # prefer email (col 1) to generate a name, fallback to col 0
            email = row[1].strip() if len(row) > 1 else ''
            if email:
                names_by_url[url] = _format_email_to_name(email)
            else:
                names_by_url[url] = (row[0].strip() if row and len(row) > 0 else f'Calendar {url.split("/")[-1]}')

    print(f"Found {len(urls)} unique URLs")

    # Connect to DB
    db_path = pathlib.Path(__file__).parent.parent / 'data' / 'app.db'
    if not db_path.exists():
        print(f"Error: DB file '{db_path}' not found.")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    added = 0
    for url in urls:
        try:
            name = names_by_url.get(url, f'Calendar {url.split("/")[-1]}')
            cur.execute('INSERT OR IGNORE INTO calendars (url, name, enabled, created_at) VALUES (?, ?, 1, datetime("now"))', (url, name))
            if cur.rowcount > 0:
                added += 1
        except Exception as e:
            print(f"Error adding {url}: {e}")

    conn.commit()
    conn.close()

    print(f"Added {added} new calendars")

if __name__ == '__main__':
    main()