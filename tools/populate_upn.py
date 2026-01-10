#!/usr/bin/env python3
import sqlite3, re
DB='/app/data/app.db'
conn=sqlite3.connect(DB)
cur=conn.cursor()
cur.execute("SELECT id, url FROM calendars WHERE upn IS NULL OR upn = '' LIMIT 1000")
rows=cur.fetchall()
print('to_process', len(rows))
pattern=re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
updated=0
for rid, url in rows:
    if not url:
        continue
    m=pattern.search(url)
    if m:
        upn=m.group(1)
        try:
            cur.execute("UPDATE calendars SET upn=? WHERE id=?", (upn, rid))
            updated+=1
        except Exception as e:
            print('err', rid, e)
conn.commit()
print('updated', updated)
cur.execute('SELECT COUNT(*) FROM calendars')
print('total', cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM calendars WHERE upn IS NOT NULL AND upn <> ''")
print('with_upn', cur.fetchone()[0])
print('sample:')
cur.execute('SELECT id, url, upn FROM calendars ORDER BY id LIMIT 10')
for r in cur.fetchall():
    print(r)
conn.close()
