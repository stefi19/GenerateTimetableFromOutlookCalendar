#!/usr/bin/env python3
import sqlite3, csv, pathlib, json, sys
csv_path = '/app/Rooms_PUBLISHER_HTML-ICS(in).csv'
db_path = '/app/data/app.db'

def norm_url(u):
    if not u: return ''
    u = u.strip().rstrip('/')
    if u.startswith('http://'):
        u = u[len('http://'):]
    elif u.startswith('https://'):
        u = u[len('https://'):]
    return u

print('CSV exists:', pathlib.Path(csv_path).exists(), file=sys.stderr)
print('DB exists:', pathlib.Path(db_path).exists(), file=sys.stderr)

def build_csv_map(csv_path):
    csv_map = {}
    if pathlib.Path(csv_path).exists():
        with open(csv_path, newline='', encoding='utf-8') as f:
            rdr = csv.reader(f)
            next(rdr, None)
            for row in rdr:
                if not row or len(row) < 6:
                    continue
                name = row[0].strip(); email = row[1].strip(); html = norm_url(row[4].strip()); ics = norm_url(row[5].strip())
                if html:
                    csv_map[html] = email
                if ics:
                    csv_map[ics] = email
    return csv_map


def main():
    csv_map = build_csv_map(csv_path)
    print('csv_map size:', len(csv_map), file=sys.stderr)

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute('SELECT id,name,upn,url FROM calendars')
        rows = cur.fetchall()

        matches = []
        for rid, name, upn, url in rows:
            nurl = norm_url(url or '')
            matched = None
            if nurl in csv_map:
                matched = csv_map[nurl]
            else:
                if nurl.endswith('.html'):
                    alt = nurl[:-5] + '.ics'
                    matched = csv_map.get(alt)
                elif nurl.endswith('.ics'):
                    alt = nurl[:-4] + '.html'
                    matched = csv_map.get(alt)
            if matched:
                matches.append({'id': rid, 'name': name, 'upn': upn, 'url': url, 'norm_url': nurl, 'email': matched})

        out = {'csv_map_size': len(csv_map), 'matched_count': len(matches), 'matches': matches[:50]}
        print(json.dumps(out, ensure_ascii=False, indent=2))
    finally:
        conn.close()


if __name__ == '__main__':
    main()
