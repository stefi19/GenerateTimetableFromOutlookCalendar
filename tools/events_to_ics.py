#!/usr/bin/env python3
"""Convert extracted events JSON into a full iCalendar (.ics) file.

Reads `playwright_captures/events.json` by default and writes
`playwright_captures/calendar_full.ics` with DTSTART/DTEND, SUMMARY, LOCATION,
and DESCRIPTION (includes parsed professor if found and raw details).

Usage:
  python3 tools/events_to_ics.py --from 2025-11-05 --to 2025-11-11
  python3 tools/events_to_ics.py            # defaults to next 7 days
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, date, timedelta
import pathlib
import re
from dateutil import parser as dtparser


def parse_professor_and_subject(title: str):
    """Heuristics to pull out professor and normalized subject from title.

Examples:
  "Artificial intelligence (AI) - A. Groza - P03 [In-person]" -> subj: AI, prof: A. Groza
  "AI 26B [In-person]" -> subj: AI, prof: None
"""
    if not title:
        return (None, None)

    # remove bracketed tokens like [In-person]
    t = re.sub(r"\[[^\]]+\]", "", title).strip()

    # split on ' - ' which Outlook often uses to separate components
    parts = [p.strip() for p in t.split(' - ') if p.strip()]
    prof = None
    subj = None

    # If there's a parenthetical code like (AI) prefer that as subject
    m = re.search(r"\(([^)]+)\)", t)
    if m:
        subj = m.group(1).strip()

    # If first token contains a code like 'AI' or 'FP' at start, pick that
    if not subj:
        m2 = re.match(r"^\s*([A-Za-z]{1,4})\b", t)
        if m2:
            subj = m2.group(1).strip()

    # For professor, search parts for "Initial. Name" or two capitalized words
    for p in parts[1:]:
        # typical prof patterns: 'A. Groza', 'R. Danescu', 'E. Todoran'
        if re.search(r"[A-Z][a-z]+\s+[A-Z][a-z]+", p) or re.search(r"[A-Z]\.\s*[A-Z][a-z]+", p):
            prof = p
            break

    # if no hyphen-separated prof, try to find a middle pattern in t
    if not prof:
        m3 = re.search(r"([A-Z]\.\s*[A-Z][a-z]+)", t)
        if m3:
            prof = m3.group(1)

    return subj, prof


def format_dt_for_ics(dt: datetime) -> str:
    # produce a timestamp with timezone offset like 20251201T080000+0200
    if dt.tzinfo:
        s = dt.isoformat()
        # convert to format YYYYMMDDTHHMMSS+HHMM
        # dt.strftime doesn't include numeric timezone offset without workaround
        off = dt.strftime('%z')  # +0200
        return dt.strftime('%Y%m%dT%H%M%S') + off
    else:
        return dt.strftime('%Y%m%dT%H%M%S')


def load_events(path: str):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    out = []
    for it in data:
        try:
            start = dtparser.parse(it.get('start')) if it.get('start') else None
        except Exception:
            start = None
        try:
            end = dtparser.parse(it.get('end')) if it.get('end') else None
        except Exception:
            end = None
        title = it.get('title') or ''
        location = it.get('location') or ''
        raw = it.get('raw') or {}
        out.append({'start': start, 'end': end, 'title': title, 'location': location, 'raw': raw})
    return out


def build_ics(events, out_file: pathlib.Path):
    lines = []
    lines.append('BEGIN:VCALENDAR')
    lines.append('VERSION:2.0')
    lines.append('PRODID:-//outlook-calendar-extractor//EN')

    for ev in events:
        st = ev['start']
        end = ev['end']
        if not st or not end:
            continue
        title = ev['title'] or ''
        location = ev['location'] or ''
        subj, prof = parse_professor_and_subject(title)
        summary = title
        uid_src = (title or '') + (location or '') + (st.isoformat() if st else '')
        uid = hashlib.sha1(uid_src.encode('utf-8')).hexdigest() + '@extracted'

        lines.append('BEGIN:VEVENT')
        lines.append('UID:' + uid)
        lines.append('DTSTAMP:' + datetime.utcnow().strftime('%Y%m%dT%H%M%SZ'))
        lines.append('DTSTART:' + format_dt_for_ics(st))
        lines.append('DTEND:' + format_dt_for_ics(end))
        lines.append('SUMMARY:' + summary.replace('\n', ' '))
        if location:
            # try to make a friendly room representation from location
            room = location.split('@', 1)[0]
            lines.append('LOCATION:' + room)
        # build description including professor and raw details
        desc_lines = []
        if prof:
            desc_lines.append('Professor: ' + prof)
        if subj:
            desc_lines.append('Subject code: ' + subj)
        # include raw JSON snippet
        try:
            raw_text = json.dumps(ev.get('raw', {}), ensure_ascii=False)
            desc_lines.append('Raw: ' + raw_text)
        except Exception:
            pass
        # join and escape
        if desc_lines:
            desc = '\n'.join(desc_lines)
            # iCalendar line folding: naive approach, escape newlines
            desc = desc.replace('\n', '\n')
            lines.append('DESCRIPTION:' + desc.replace('\r', ''))

        lines.append('END:VEVENT')

    lines.append('END:VCALENDAR')

    out_file.write_text('\r\n'.join(lines), encoding='utf-8')
    return out_file


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--source', default='playwright_captures/events.json')
    p.add_argument('--from', dest='from_date', help='Start date YYYY-MM-DD')
    p.add_argument('--to', dest='to_date', help='End date YYYY-MM-DD')
    p.add_argument('--days', type=int, default=7)
    return p.parse_args()


def main():
    args = parse_args()
    src = args.source
    if not os.path.exists(src):
        print('Source events file not found:', src)
        return 2
    events = load_events(src)

    today = date.today()
    if args.from_date:
        from_d = dtparser.parse(args.from_date).date()
    else:
        from_d = today
    if args.to_date:
        to_d = dtparser.parse(args.to_date).date()
    else:
        to_d = from_d + timedelta(days=args.days - 1)

    # filter events
    evs = [e for e in events if e['start'] and from_d <= e['start'].date() <= to_d]
    out_dir = pathlib.Path('playwright_captures')
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / 'calendar_full.ics'
    build_ics(evs, out_file)
    print('Wrote iCalendar to:', out_file)
    print('Events included:', len(evs))


if __name__ == '__main__':
    main()
