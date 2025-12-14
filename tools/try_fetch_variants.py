#!/usr/bin/env python3
import urllib.request
import urllib.parse
import sys

def do_get(url):
    print('\n=== TRY:', url)
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            code = resp.getcode()
            ct = resp.headers.get('Content-Type','')
            body = resp.read(200000)  # read up to 200KB
            text = None
            try:
                text = body.decode('utf-8', errors='replace')
            except Exception:
                text = str(body[:200])
            print('Status:', code)
            print('Content-Type:', ct)
            if text.strip().upper().startswith('BEGIN:VCALENDAR') or 'BEGIN:VCALENDAR' in text.upper():
                print('FOUND: BEGIN:VCALENDAR in body (iCalendar)')
            elif 'text/calendar' in ct.lower():
                print('FOUND: content-type indicates text/calendar')
            elif '<html' in text.lower():
                print('NOTE: response looks like HTML (likely JS shell)')
            else:
                print('NOTE: response appears not to be iCalendar or HTML start; showing first 400 chars:')
                print(text[:400])
    except Exception as e:
        print('ERROR fetching URL:', e)

if __name__ == '__main__':
    base = 'https://outlook.office365.com/calendar/published/173862b98010453296f2a697e45f3b1e@campus.utcluj.ro/daeb64d4bd994c52b4f54d04ba1940ca2236386271423118770/calendar.html'
    candidates = [base]
    if base.endswith('.html'):
        candidates.append(base[:-5] + '.ics')
        candidates.append(base[:-5] + '.ics?')
    candidates.append(base.rstrip('/') + '/calendar.ics')
    # try replacing last segment with calendar.ics
    parts = base.split('/')
    parts[-1] = 'calendar.ics'
    candidates.append('/'.join(parts))
    # try webcal scheme
    candidates.append('webcal://' + urllib.parse.urlparse(base).netloc + urllib.parse.urlparse(base).path)
    # try removing /published/.../calendar.html -> /calendar.ics at top-level domain (less likely)
    parsed = urllib.parse.urlparse(base)
    candidates.append(parsed.scheme + '://' + parsed.netloc + '/calendar.ics')

    # de-dup
    seen = set()
    final = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            final.append(c)

    for url in final:
        do_get(url)

    print('\nDone.')
