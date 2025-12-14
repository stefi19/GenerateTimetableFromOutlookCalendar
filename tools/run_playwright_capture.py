#!/usr/bin/env python3
from playwright.sync_api import sync_playwright
import os, pathlib

url = 'https://outlook.office365.com/calendar/published/173862b98010453296f2a697e45f3b1e@campus.utcluj.ro/daeb64d4bd994c52b4f54d04ba1940ca2236386271423118770/calendar.html'
user_data_dir = os.environ.get('PLAYWRIGHT_USER_DATA_DIR', os.path.expanduser('~/.playwright_profile'))
out_dir = pathlib.Path('playwright_captures')
out_dir.mkdir(exist_ok=True)
print('Using user_data_dir:', user_data_dir)
with sync_playwright() as p:
    # Launch persistent context using existing profile (headless)
    context = p.chromium.launch_persistent_context(user_data_dir, headless=True)
    page = context.new_page()
    captured = []
    idx = [0]
    def on_response(resp):
        try:
            u = resp.url
            st = resp.status
            headers = resp.headers
            ct = headers.get('content-type','')
            if 'calendar' in ct.lower() or u.lower().endswith('.ics') or '.ics?' in u.lower() or 'GetAccessToken' in u:
                fname = out_dir / f'resp_{idx[0]}.txt'
                idx[0] += 1
                try:
                    body = resp.text()
                except Exception as e:
                    body = f'<<could not read body: {e}>>'
                with open(fname,'w',encoding='utf-8') as f:
                    f.write(f'URL: {u}\nSTATUS: {st}\nCONTENT-TYPE: {ct}\nHEADERS: {headers}\n\n')
                    f.write(body)
                captured.append((u, st, ct, str(fname)))
        except Exception as e:
            print('on_response error', e)
    page.on('response', on_response)
    print('Navigating...')
    try:
        page.goto(url, wait_until='networkidle', timeout=60000)
    except Exception as e:
        print('goto exception:', e)
    html = page.content()
    (out_dir / 'page.html').write_text(html, encoding='utf-8')
    print('Saved page.html (len=', len(html), ')')
    if captured:
        print('Captured responses:')
        for u,st,ct,fname in captured:
            print(st, ct, u, '->', fname)
    else:
        print('No calendar-like responses captured.')
    context.close()
print('Done')
