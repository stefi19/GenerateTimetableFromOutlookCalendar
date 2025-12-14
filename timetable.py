#!/usr/bin/env python3
"""Download and display a timetable from an Outlook published calendar HTML page.

Behavior:
- Fetch the HTML page.
- Try to find a linked .ics (or webcal) feed and parse it with the `ics` library.
- If no .ics feed is found, try to parse microformat `vevent` items from the HTML.
- Print events grouped by date.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime, date, timedelta
from typing import List, Optional

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dtparser

try:
    from ics import Calendar
except Exception:
    Calendar = None  # type: ignore


class Event:
    def __init__(self, start: datetime, end: Optional[datetime], title: str, location: Optional[str] = None, description: Optional[str] = None):
        self.start = start
        self.end = end
        self.title = title.strip() if title else ""
        self.location = location or ""
        self.description = description or ""

    def day(self) -> date:
        return self.start.date()

    def timestr(self) -> str:
        if self.end:
            return f"{self.start.strftime('%H:%M')}–{self.end.strftime('%H:%M')}"
        return self.start.strftime('%H:%M')


def fetch(url: str) -> str:
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.text


def find_ics_url_from_html(html: str, base_url: str) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")
    # First try anchors with .ics or webcal
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith(".ics") or href.lower().startswith("webcal:") or ".ics?" in href.lower():
            # make absolute if needed
            return requests.compat.urljoin(base_url, href)

    # Some published pages embed a link rel="alternate" type="text/calendar"
    for link in soup.find_all("link", href=True):
        if link.get("type", "").startswith("text/calendar") or link.get("href", "").lower().endswith(".ics"):
            return requests.compat.urljoin(base_url, link["href"])

    # Search raw HTML for any http(s)/webcal link that mentions .ics
    import re

    m = re.search(r'(https?://[^"\s]+?\.ics)', html, re.IGNORECASE)
    if m:
        return m.group(1)

    m = re.search(r'(webcal://[^"\s]+?\.ics)', html, re.IGNORECASE)
    if m:
        return m.group(1)

    # Try some common variants: replace .html with .ics, append .ics
    if base_url.endswith(".html"):
        cand = base_url[:-5] + ".ics"
        return cand

    if not base_url.endswith(".ics"):
        cand2 = base_url.rstrip("/") + "/calendar.ics"
        return cand2

    return None


def parse_ics_from_url(ics_url: str, verbose: bool = False) -> List[Event]:
    """Try to fetch and parse an .ics URL.

    If the server returns non-ICS content, save it to a file for inspection when verbose=True.
    """
    if Calendar is None:
        raise RuntimeError("ics library not installed; please pip install -r requirements.txt")

    headers = {"Accept": "text/calendar, text/plain, */*;q=0.1"}
    resp = requests.get(ics_url, headers=headers)
    resp.raise_for_status()

    body = resp.text
    ct = resp.headers.get("Content-Type", "")
    # Quick detection: ICS files start with BEGIN:VCALENDAR
    if body.lstrip().upper().startswith("BEGIN:VCALENDAR") or "text/calendar" in ct:
        cal = Calendar(body)
        events: List[Event] = []
        for e in cal.events:
            # ics.Event has .begin and .end as Arrow/pendulum-like objects
            try:
                start = e.begin.naive
            except Exception:
                start = dtparser.parse(str(e.begin))
            try:
                end = e.end.naive if e.end else None
            except Exception:
                end = dtparser.parse(str(e.end)) if e.end else None
            events.append(Event(start=start, end=end, title=e.name or "", location=e.location or "", description=e.description or ""))
        return events

    # Not recognized as an ICS response
    if verbose:
        # save response for inspection
        fname = "last_ics_response.html"
        with open(fname, "w", encoding="utf-8") as f:
            f.write(body)
        print(f"Received non-ICS content from '{ics_url}' (Content-Type: {ct}). Saved body to {fname} for inspection.")
    raise RuntimeError("Response from .ics URL did not contain an iCalendar. Try opening the URL in a browser or download the .ics manually.")


def parse_microformat_vevents(html: str) -> List[Event]:
    soup = BeautifulSoup(html, "html.parser")
    evs = []
    # Look for elements with class vevent
    for ve in soup.select(".vevent"):
        # summary/title
        title_node = ve.select_one(".summary, .fn")
        title = title_node.get_text(strip=True) if title_node else ve.get_text(strip=True)

        # dtstart / dtend (could be abbr[title] or time/datetime attributes)
        def extract_dt(selector_list):
            for sel in selector_list:
                node = ve.select_one(sel)
                if not node:
                    continue
                # look for title attribute (often contains ISO datetime)
                if node.has_attr("title"):
                    return node["title"]
                if node.has_attr("datetime"):
                    return node["datetime"]
                # otherwise text
                txt = node.get_text(strip=True)
                if txt:
                    return txt
            return None

        start_s = extract_dt([".dtstart", "abbr.dtstart", "time.dtstart", ".start"]) or extract_dt(["time", "abbr"])
        end_s = extract_dt([".dtend", "abbr.dtend", "time.dtend", ".end"]) or None

        if not start_s:
            # fallback: sometimes event has data-start attribute
            if ve.has_attr("data-start"):
                start_s = ve["data-start"]

        if not start_s:
            # can't parse this event
            continue

        try:
            start = dtparser.parse(start_s)
        except Exception:
            continue

        end = None
        if end_s:
            try:
                end = dtparser.parse(end_s)
            except Exception:
                end = None

        loc_node = ve.select_one(".location, .loc")
        location = loc_node.get_text(strip=True) if loc_node else None

        desc_node = ve.select_one(".description, .note")
        description = desc_node.get_text(strip=True) if desc_node else None

        evs.append(Event(start=start, end=end, title=title, location=location, description=description))

    return evs


def display_events(events: List[Event], from_date: Optional[date] = None, to_date: Optional[date] = None) -> None:
    if not events:
        print("No events found.")
        return

    events_sorted = sorted(events, key=lambda e: e.start)
    grouped = defaultdict(list)
    for e in events_sorted:
        d = e.day()
        if from_date and d < from_date:
            continue
        if to_date and d > to_date:
            continue
        grouped[d].append(e)

    for d in sorted(grouped.keys()):
        print(d.strftime("%A, %Y-%m-%d"))
        for e in grouped[d]:
            loc = f" @ {e.location}" if e.location else ""
            print(f"  {e.timestr():10}  {e.title}{loc}")
        print()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Display timetable from a published Outlook calendar HTML URL")
    parser.add_argument("url", help="Published calendar HTML URL or local .ics file path")
    parser.add_argument("--days", type=int, default=7, help="Show only the next N days (default 7)")
    parser.add_argument("--from", dest="from_date", help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", help="End date YYYY-MM-DD")
    parser.add_argument("--verbose", action="store_true", help="Show verbose diagnostics and save non-ICS responses to disk")

    args = parser.parse_args(argv)

    events: List[Event] = []

    import os

    # If user passed a local .ics file path, parse it directly
    if os.path.exists(args.url) and args.url.lower().endswith(".ics"):
        try:
            with open(args.url, "r", encoding="utf-8") as f:
                text = f.read()
            if Calendar is None:
                raise RuntimeError("ics library not available; install dependencies")
            cal = Calendar(text)
            for e in cal.events:
                try:
                    start = e.begin.naive
                except Exception:
                    start = dtparser.parse(str(e.begin))
                try:
                    end = e.end.naive if e.end else None
                except Exception:
                    end = dtparser.parse(str(e.end)) if e.end else None
                events.append(Event(start=start, end=end, title=e.name or "", location=e.location or "", description=e.description or ""))
        except Exception as e:
            print(f"Failed to parse local .ics file: {e}")
            return 3
    else:
        try:
            html = fetch(args.url)
        except Exception as e:
            print(f"Failed to fetch URL: {e}")
            return 2

        # If an .ics URL is present, prefer that
        ics_url = find_ics_url_from_html(html, args.url)

        if ics_url:
            print(f"Found calendar feed: {ics_url}")
            try:
                events = parse_ics_from_url(ics_url, verbose=args.verbose)
            except Exception as e:
                if args.verbose:
                    print(f"Failed to parse .ics feed: {e}")
                # fallback to microformat parsing of HTML
                events = parse_microformat_vevents(html)
        else:
            events = parse_microformat_vevents(html)

    # determine date range
    today = date.today()
    from_d = None
    to_d = None
    if args.from_date:
        from_d = dtparser.parse(args.from_date).date()
    else:
        from_d = today

    if args.to_date:
        to_d = dtparser.parse(args.to_date).date()
    else:
        to_d = from_d + timedelta(days=args.days - 1)

    display_events(events, from_date=from_d, to_date=to_d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
