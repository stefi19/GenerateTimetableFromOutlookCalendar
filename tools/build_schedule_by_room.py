#!/usr/bin/env python3
"""Build a timetable grouped by room from captured events JSON.

Reads `playwright_captures/events.json` by default (or a provided source file),
filters by a date range (--from / --to or --days), extracts subject and room
using the rule: "subject is the first token, room is the token after the first space";
falls back to parsing the `location` field when necessary.

Outputs:
  - pretty-printed timetable grouped by room to stdout
  - saves JSON to `playwright_captures/schedule_by_room.json`
  - saves CSV to `playwright_captures/schedule_by_room.csv`

Usage examples:
  # next 7 days (default)
  python3 tools/build_schedule_by_room.py

  # explicit range
  python3 tools/build_schedule_by_room.py --from 2025-12-01 --to 2025-12-07

  # use a different source file
  python3 tools/build_schedule_by_room.py --source /path/to/events.json
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
import pathlib
import re
from dateutil import parser as dtparser

# Import parserul inteligent pentru subiecte
from subject_parser import get_parser, parse_title, get_mappings


def load_subject_mappings():
    """Încarcă mapping-urile salvate de extract_published_events.py."""
    mappings_file = pathlib.Path('playwright_captures/subject_mappings.json')
    if mappings_file.exists():
        try:
            with open(mappings_file, 'r', encoding='utf-8') as f:
                mappings = json.load(f)
            parser = get_parser()
            for abbrev, name in mappings.items():
                parser.add_mapping(abbrev, name)
            return mappings
        except Exception:
            pass
    return {}


def guess_subject_and_room(title: str, location: str | None):
    """Simpler extraction: return (subject, room, display_title, professor).

    Uses the intelligent subject parser to extract information from the title.
    Falls back to location parsing for room when necessary.
    """
    if not title and not location:
        return (None, None, None, None)

    # Folosește parserul inteligent
    parsed = parse_title(title)
    
    subject = parsed.subject_name or None
    display_title = parsed.display_title or title
    professor = parsed.professor
    
    # Încearcă să găsească camera din titlu sau din location
    room = None
    
    # Mai întâi încearcă să găsească un token de cameră în titlu
    t = (title or '').strip()
    parts = t.split()
    for tok in parts[::-1][:8]:
        rt = normalize_room(tok)
        if rt:
            room = rt
            break

    if not room and location:
        room = room_from_location(location)

    return (subject, room, display_title, professor)


def normalize_room(tok: str) -> str | None:
    """Normalize room token from various formats.

    Examples:
      bt-503 -> BT5.03
      BT5.03 -> BT5.03
      26B -> 26B
      p03 -> P03
    """
    if not tok:
        return None
    t = tok.strip()
    # normalize separators and lowercase for pattern checks
    t = t.replace('/', ' ').replace(',', ' ').strip()
    tl = t.lower()
    # handle common prefixes like 'sala 103', 'room 103'
    m = re.match(r'(?i)^(?:sala|room|rm|s)\s*[:\-\.]?\s*(\d+[A-Za-z]?)(?:\.(\d+))?$', t)
    if m:
        base = m.group(1)
        frac = m.group(2)
        if frac:
            return base.upper() + '.' + frac
        return base.upper()
    # common prefix handling: bt-503 -> BT5.03
    m = re.match(r'(?i)bt[-_]?([0-9]{3})$', tl)
    if m:
        digits = m.group(1)
        return f'BT{int(digits[:-2])}.{digits[-2:]}'
    # p03 or p3 -> P03
    m = re.match(r'(?i)^p0?([0-9]+)$', tl)
    if m:
        return f'P{int(m.group(1)):02d}'
    # tokens like BT5.03 or BT5.3 or A12
    m = re.match(r'^[A-Za-z]+[0-9]+(\.[0-9]+)?$', t)
    if m:
        return t.upper()
    # bare numbers with optional letter
    m = re.match(r'^[0-9]+[A-Za-z]?$|^[A-Za-z]?[0-9]+$', t)
    if m:
        return t.upper()
    # try to extract numeric part from longer tokens, e.g., 'utcn_room_ac_bar_26b'
    m = re.search(r'([0-9]{1,3}[A-Za-z]?)(?:\.[0-9]{1,2})?$', t)
    if m:
        return m.group(1).upper()
    return None


def room_from_location(location: str) -> str | None:
    # take substring before @ and look for room-like tokens anywhere
    loc = location.split('@', 1)[0]
    # split on common separators
    segs = re.split(r'[,_\-\s]+', loc)
    # search segments for a normalized room
    for s in reversed(segs):
        if not s:
            continue
        nr = normalize_room(s)
        if nr:
            return nr
    # try searching the whole string for a room-like pattern
    m = re.search(r'([A-Za-z]{0,3}[0-9]{1,3}(?:\.[0-9]{1,2})?[A-Za-z]?)', loc)
    if m:
        nr = normalize_room(m.group(1))
        if nr:
            return nr
    # fallback: return trimmed loc
    return loc.strip() or None


def extract_professor(title: str, raw: dict | None):
    """Try to extract professor name from title or raw JSON.

    Returns a short string like 'A. Groza' or full name if available.
    """
    if not title and not raw:
        return None

    # Helper to test if a segment looks like a person name
    def looks_like_name(s: str) -> bool:
        s = s.strip()
        # common forms: 'A. Groza', 'A Groza', 'Adrian Groza', 'A. D. Popescu'
        if re.match(r'^[A-Z]\.[A-Za-z\-]+$', s):
            return True
        if re.match(r'^[A-Z]\.[A-Z]\.[A-Za-z\-]+$', s):
            return True
        if re.match(r'^[A-Z][a-z\-]+\s+[A-Z][a-z\-]+', s):
            return True
        if re.match(r'^[A-Z]\.?\s?[A-Za-z\-]+$', s):
            return True
        return False

    # First, split title by separators and look for name-like segments
    parts = [p.strip() for p in re.split(r"\s+-\s+|\(|\)|,|;", title or "") if p.strip()]
    for p in reversed(parts):
        if looks_like_name(p):
            return p

    # also try splitting on ' - ' and take middle/right segment heuristics
    # common pattern: "Subject - Prof - Room" or "Subject - Prof"
    segs = [s.strip() for s in title.split(' - ') if s.strip()]
    if len(segs) >= 2:
        # middle segment is often the professor (e.g. 'Economic law - R. Cordos - 40')
        if looks_like_name(segs[1]):
            return segs[1]
        # try last segment if middle is room-like but contains a name plus room
        if len(segs) >= 3 and looks_like_name(segs[-2]):
            return segs[-2]

    # catch patterns like '- R. Cordos -' anywhere
    m = re.search(r"-\s*([^\-\n]{2,60}?)\s*-", title or "")
    if m:
        cand = m.group(1).strip()
        if looks_like_name(cand):
            return cand

    # Inspect raw JSON fields common in Outlook items
    try:
        if isinstance(raw, dict):
            # Organizer may be a dict with Name
            org = raw.get('Organizer') or raw.get('OrganizerEmail') or None
            if isinstance(org, dict):
                name = org.get('Name') or org.get('DisplayName')
                if name and looks_like_name(name):
                    return name
            # RequiredAttendees or Attendees lists
            for key in ('RequiredAttendees', 'Attendees', 'AttendeesList'):
                val = raw.get(key)
                if isinstance(val, list):
                    for a in val:
                        if isinstance(a, dict):
                            name = a.get('Name') or a.get('DisplayName') or a.get('EmailAddress')
                            if name and looks_like_name(name):
                                return name
            # some raw representations store organizer as a string like 'R. Cordos'
            if isinstance(org, str) and looks_like_name(org):
                return org
            # other keys: 'OrganizerName', 'DisplayName'
            for k in ('OrganizerName', 'DisplayName'):
                v = raw.get(k)
                if isinstance(v, str) and looks_like_name(v):
                    return v
    except Exception:
        pass

    # final regex heuristics in the whole title
    m = re.search(r"([A-Z]\.[A-Z]?\.?\s?[A-Z][a-z\-]+)", title or "")
    if m:
        return m.group(1).strip()

    # if the title ends with two capitalized words, treat them as a person (e.g. '... - R. Slavescu' or '... Functional programming R. Slavescu')
    try:
        toks = [t for t in re.split(r"\s+", (title or '').strip()) if t]
        if len(toks) >= 2:
            cand = toks[-2] + ' ' + toks[-1]
            if looks_like_name(cand):
                return cand
        # also check last single token of form 'R.' + 'Surname' separated by double spaces or similar
        m2 = re.search(r"([A-Z]\.)\s*([A-Z][a-z\-]+)$", title or "")
        if m2:
            return (m2.group(1) + ' ' + m2.group(2)).strip()
    except Exception:
        pass

    return None


def load_events(path: str):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    events = []
    for item in data:
        try:
            start = dtparser.parse(item.get('start')) if item.get('start') else None
        except Exception:
            start = None
        try:
            end = dtparser.parse(item.get('end')) if item.get('end') else None
        except Exception:
            end = None
        title = item.get('title') or item.get('Subject') or ''
        location = item.get('location') or (item.get('raw', {}) or {}).get('Location', {}) and (item.get('raw', {}) or {}).get('Location', {}).get('DisplayName')
        prof = extract_professor(title, item.get('raw'))
        events.append({'start': start, 'end': end, 'title': title, 'location': location, 'raw': item.get('raw'), 'professor': prof})
    return events


def filter_by_date(events, from_d: date, to_d: date):
    out = []
    for ev in events:
        st = ev['start']
        if st is None:
            continue
        d = st.date()
        if d >= from_d and d <= to_d:
            out.append(ev)
    return out


def build_schedule(events):
    # group by room -> date -> list of events
    schedule = defaultdict(lambda: defaultdict(list))
    for ev in events:
        title = ev.get('title') or ''
        location = ev.get('location')
        subj, room, display_title, professor = guess_subject_and_room(title, location)
        if not room:
            room = location or 'UNKNOWN'
        # normalize room string
        room = str(room).strip()
        st = ev.get('start')
        end = ev.get('end')
        day = st.date().isoformat()
        # capture professor if available from the loaded events or parsed from title
        prof = ev.get('professor') or professor or None
        schedule[room][day].append({
            'start': st, 
            'end': end, 
            'title': display_title or title,  # Folosește titlul formatat
            'subject': subj, 
            'location': location, 
            'professor': prof
        })

    # sort events in each day by start
    for room in schedule:
        for day in schedule[room]:
            schedule[room][day].sort(key=lambda x: x['start'] or datetime.min)

    return schedule


def save_outputs(schedule, out_dir: pathlib.Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    jpath = out_dir / 'schedule_by_room.json'
    # convert datetimes to iso and apply optional room aliases
    aliases_path = pathlib.Path('config') / 'room_aliases.json'
    aliases = {}
    if aliases_path.exists():
        try:
            with open(aliases_path, 'r', encoding='utf-8') as af:
                aliases = json.load(af)
        except Exception:
            aliases = {}

    serial = {}
    for room, days in schedule.items():
        out_room = aliases.get(room, room)
        serial[out_room] = {}
        for day, evs in days.items():
            serial[out_room][day] = []
            for e in evs:
                serial[out_room][day].append({'start': e['start'].isoformat() if e['start'] else None, 'end': e['end'].isoformat() if e['end'] else None, 'title': e['title'], 'subject': e['subject'], 'location': e['location'], 'professor': e.get('professor')})
    with open(jpath, 'w', encoding='utf-8') as f:
        json.dump(serial, f, indent=2, ensure_ascii=False)

    # also CSV: room, date, start, end, subject, title, location
    cpath = out_dir / 'schedule_by_room.csv'
    with open(cpath, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['room', 'date', 'start', 'end', 'subject', 'professor', 'title', 'location'])
        for room, days in serial.items():
            for day, evs in days.items():
                for e in evs:
                    w.writerow([room, day, e.get('start'), e.get('end'), e.get('subject'), e.get('professor'), e.get('title'), e.get('location')])

    return jpath, cpath


def pretty_print(schedule):
    # apply aliases for printing if available
    aliases_path = pathlib.Path('config') / 'room_aliases.json'
    aliases = {}
    if aliases_path.exists():
        try:
            with open(aliases_path, 'r', encoding='utf-8') as af:
                aliases = json.load(af)
        except Exception:
            aliases = {}

    for room in sorted(schedule.keys()):
        display = aliases.get(room, room)
        print('\nROOM:', display)
        for day in sorted(schedule[room].keys()):
            print('  ', day)
            for e in schedule[room][day]:
                s = e['start'].strftime('%H:%M') if e['start'] else ''
                eend = e['end'].strftime('%H:%M') if e['end'] else ''
                subj = e.get('subject') or ''
                prof = e.get('professor') or ''
                # show time, subject and optional professor
                if prof:
                    print(f'    {s:5}-{eend:5}  {subj}  - {prof}')
                else:
                    print(f'    {s:5}-{eend:5}  {subj}')


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--source', default='playwright_captures/events.json', help='Path to extracted events JSON')
    p.add_argument('--from', dest='from_date', help='Start date YYYY-MM-DD')
    p.add_argument('--to', dest='to_date', help='End date YYYY-MM-DD')
    p.add_argument('--days', type=int, default=7, help='If --from is given, default to --from + days-1 when --to not provided')
    return p.parse_args()


def main():
    args = parse_args()
    src = args.source
    if not os.path.exists(src):
        print('Source events file not found:', src)
        return 2

    # Încarcă mapping-urile de subiecte salvate anterior
    loaded_mappings = load_subject_mappings()
    if loaded_mappings:
        print(f'Încărcat {len(loaded_mappings)} mapping-uri de subiecte')

    events = load_events(src)
    
    # Învață din evenimentele curente (pentru titluri complete)
    from subject_parser import learn_from_events
    new_mappings = learn_from_events(events)
    if new_mappings:
        print(f'Învățat {len(new_mappings)} noi mapping-uri din evenimente')
    
    today = date.today()
    if args.from_date:
        from_d = dtparser.parse(args.from_date).date()
    else:
        from_d = today
    if args.to_date:
        to_d = dtparser.parse(args.to_date).date()
    else:
        to_d = from_d + timedelta(days=args.days - 1)

    events_f = filter_by_date(events, from_d, to_d)
    schedule = build_schedule(events_f)
    out_dir = pathlib.Path('playwright_captures')
    jpath, cpath = save_outputs(schedule, out_dir)
    print(f'Saved schedule JSON: {jpath} and CSV: {cpath}')
    pretty_print(schedule)


if __name__ == '__main__':
    main()
