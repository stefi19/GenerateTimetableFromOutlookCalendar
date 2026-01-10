#!/usr/bin/env python3
import sqlite3, csv, json, os, re

def load_csv():
    candidates=["/app/config/Rooms_PUBLISHER_HTML-ICS(in).csv","/app/Rooms_PUBLISHER_HTML-ICS(in).csv","Rooms_PUBLISHER_HTML-ICS(in).csv"]
    path=None
    for p in candidates:
        if os.path.exists(p):
            path=p
            break
    if not path:
        return {}, {}, {}, None
    csv_map, token_map, lastseg_map = {}, {}, {}
    with open(path, newline='', encoding='utf-8') as f:
        rdr=csv.reader(f)
        for row in rdr:
            if not row or len(row)<6:
                continue
            email=row[1].strip()
            html=(row[4].strip() if len(row)>4 else '').rstrip('/')
            ics=(row[5].strip() if len(row)>5 else '').rstrip('/')
            for u in (html, ics):
                if not u: continue
                vl=u.strip()
                vl_l=vl.lower().rstrip('/')
                variants=set([vl_l])
                if vl_l.startswith('http://'):
                    variants.add('https://'+vl_l[len('http://'):])
                if vl_l.startswith('https://'):
                    variants.add('http://'+vl_l[len('https://'):])
                variants.add(vl_l.replace('/owa/','/'))
                variants.add(vl_l.replace('/calendar/published/','/owa/calendar/'))
                for var in variants:
                    csv_map[var.rstrip('/')] = email
                m=re.search(r'([A-Za-z0-9._%+-]+@[^/\\?]+)', vl_l)
                if m:
                    token_map[m.group(1)] = email
                seg = vl_l.split('/')[-1].split('?')[0].replace('.html','').replace('.ics','')
                if seg:
                    lastseg_map[seg] = email
    return csv_map, token_map, lastseg_map, path


def run():
    csv_map, token_map, lastseg_map, csv_path = load_csv()
    conn=sqlite3.connect('/app/data/app.db')
    cur=conn.cursor()
    cur.execute('SELECT id, name, upn, url FROM calendars')
    rows=cur.fetchall()
    stats={'total':len(rows),'exact':0,'proto_flip':0,'no_owa':0,'token':0,'lastseg':0,'matched_any':0}
    matched_ids=set()
    unmatched=[]
    for rid,name,upn,url in rows:
        url_s=(url or '').strip()
        nurl=url_s.lower().rstrip('/')
        found=None
        # exact
        if nurl and nurl in csv_map:
            found=('exact',csv_map[nurl])
            stats['exact']+=1
        # proto flip
        if not found and nurl:
            if nurl.startswith('http://') and ('https://'+nurl[len('http://'):]) in csv_map:
                found=('proto_flip',csv_map['https://'+nurl[len('http://'):]])
                stats['proto_flip']+=1
            elif nurl.startswith('https://') and ('http://'+nurl[len('https://'):]) in csv_map:
                found=('proto_flip',csv_map['http://'+nurl[len('https://'):]])
                stats['proto_flip']+=1
        # remove owa
        if not found and '/owa/' in nurl:
            alt=nurl.replace('/owa/','/')
            if alt in csv_map:
                found=('no_owa',csv_map[alt])
                stats['no_owa']+=1
        # token from upn or url
        if not found:
            if upn and upn in token_map:
                found=('token_upn',token_map[upn])
                stats['token']+=1
            else:
                m2=re.search(r'([A-Za-z0-9._%+-]+@[^/\\?]+)', nurl)
                if m2 and m2.group(1) in token_map:
                    found=('token_url',token_map[m2.group(1)])
                    stats['token']+=1
        # last segment
        if not found and nurl:
            seg=nurl.split('/')[-1].split('?')[0].replace('.html','').replace('.ics','')
            if seg and seg in lastseg_map:
                found=('lastseg', lastseg_map[seg])
                stats['lastseg']+=1
        if found:
            stats['matched_any']+=1
            matched_ids.add(rid)
        else:
            unmatched.append({'id':rid,'name':name,'upn':upn,'url':url_s})
    sample_unmatched=unmatched[:80]
    output={'csv_path':csv_path,'stats':stats,'sample_unmatched':sample_unmatched}
    print(json.dumps(output, ensure_ascii=False, indent=2))

if __name__=='__main__':
    run()
