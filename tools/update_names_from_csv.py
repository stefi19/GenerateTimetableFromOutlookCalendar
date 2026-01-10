#!/usr/bin/env python3
import csv, sqlite3, os, json

# Prefer the mounted config path so the container sees changes without copying files.
csv_candidates = [
    "/app/config/Rooms_PUBLISHER_HTML-ICS(in).csv",
    "/app/Rooms_PUBLISHER_HTML-ICS(in).csv",
]
csv_path = None
for p in csv_candidates:
    if os.path.exists(p):
        csv_path = p
        break
if not csv_path:
    # fall back to current working dir path (useful for local runs)
    local = os.path.join(os.getcwd(), 'Rooms_PUBLISHER_HTML-ICS(in).csv')
    if os.path.exists(local):
        csv_path = local
db_path = "/app/data/app.db"

if not os.path.exists(csv_path):
    print(json.dumps({"error": "CSV not found", "path": csv_path}))
    raise SystemExit(1)
if not os.path.exists(db_path):
    print(json.dumps({"error": "DB not found", "path": db_path}))
    raise SystemExit(1)

# read csv and build mappings
by_upn = {}
by_html = {}
by_ics = {}
with open(csv_path, newline='', encoding='utf-8') as f:
    reader = csv.reader(f)
    for row in reader:
        if not row:
            continue
        # expected columns: 0:display name, 1:upn, 2:org, 3:enabled, 4:html_url, 5:ics_url
        name = row[0].strip() if len(row) > 0 else ''
        upn = row[1].strip() if len(row) > 1 else ''
        html = row[4].strip() if len(row) > 4 else ''
        ics = row[5].strip() if len(row) > 5 else ''
        if upn:
            by_upn[upn] = name
        if html:
            by_html[html.rstrip('/')] = name
        if ics:
            by_ics[ics.rstrip('/')] = name

# helper to normalize urls for matching (strip trailing slashes)
def norm(u):
    return u.strip().rstrip('/') if u else u

conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute('SELECT id, name, upn, url FROM calendars')
rows = cur.fetchall()
updated = []
for rid, name, upn, url in rows:
    cur_name = name.strip() if name else ''
    candidates = []
    # match by url exact (html)
    if url:
        nurl = norm(url)
        if nurl in by_html:
            candidates.append(by_html[nurl])
        # try alternate .html/.ics variants
        if nurl.endswith('.html'):
            alt = nurl[:-5] + '.ics'
            if alt in by_ics:
                candidates.append(by_ics[alt])
        if nurl.endswith('.ics'):
            alt = nurl[:-4] + '.html'
            if alt in by_html:
                candidates.append(by_html[alt])
    # match by upn (csv upn keys)
    if upn and upn in by_upn:
        candidates.append(by_upn[upn])
    # remove empty candidates, and dedupe keep first
    candidates = [c for c in candidates if c]
    if not candidates:
        continue
    new_name = candidates[0]
    # decide whether to update: if current name empty OR evidently not friendly
    bad_name = False
    if not cur_name:
        bad_name = True
    else:
        low = cur_name.lower()
        if upn and low == upn.lower():
            bad_name = True
        if 'utcn_room' in low or '@campus.utcluj.ro' in low or low in ('', 'test'):
            bad_name = True
    if bad_name and new_name and new_name != cur_name:
        cur.execute('UPDATE calendars SET name=? WHERE id=?', (new_name, rid))
        updated.append({'id': rid, 'old': cur_name, 'new': new_name, 'upn': upn, 'url': url})

conn.commit()
print(json.dumps({'total_rows': len(rows), 'updated': len(updated), 'samples': updated[:40]}, ensure_ascii=False, indent=2))
conn.close()
