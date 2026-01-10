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

    # Collect unique URLs
    urls = set()
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader, None)  # Skip header
        print(f"CSV header: {header}")
        total_rows = 0
        valid_rows = 0
        for row in reader:
            total_rows += 1
            if len(row) >= 5:
                valid_rows += 1
                html_url = row[3].strip()
                ics_url = row[4].strip() if len(row) > 4 else ''
                if html_url:
                    urls.add(html_url)
                if ics_url:
                    urls.add(ics_url)
            else:
                print(f"Skipping row {total_rows}: only {len(row)} columns")

    print(f"Total CSV rows: {total_rows}")
    print(f"Valid rows (>=5 columns): {valid_rows}")
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
            cur.execute('INSERT OR IGNORE INTO calendars (url, name, enabled, created_at) VALUES (?, ?, 1, datetime("now"))', (url, f'Calendar {url.split("/")[-1]}'))
            if cur.rowcount > 0:
                added += 1
        except Exception as e:
            print(f"Error adding {url}: {e}")

    conn.commit()
    conn.close()

    print(f"Added {added} new calendars")

if __name__ == '__main__':
    main()