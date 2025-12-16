# Outlook published calendar — Timetable viewer

Small script to download and display a timetable from an Outlook published calendar URL.

Features:
- Detects a linked .ics feed (webcal/http) in the published HTML and parses it.
- Falls back to parsing microformats/hCalendar (common `vevent` markup) if no .ics link.
- Prints events grouped by day and sorted by start time.

Requirements
-----------
- Python 3.8+
- Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Usage
-----
Run the script with the published calendar HTML URL:

```bash
python timetable.py \
  "https://outlook.office365.com/calendar/published/173862b98010453296f2a697e45f3b1e@campus.utcluj.ro/daeb64d4bd994c52b4f54d04ba1940ca2236386271423118770/calendar.html"
```

README.md has been removed and replaced with this small pointer.

Please read `README_UPDATED.md` for the full project documentation and setup instructions.

If you still want the repository to contain a committed virtualenv for instant setup, ensure you commit the `venv/` or `.venv/` directory (the `.gitignore` has been updated to allow that).

source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

If you plan to use the "Render page" option in the UI (to execute client-side JS), also run:

```bash
python -m playwright install
# or to install only Chromium:
python -m playwright install chromium
```


Notes
-----
- If your environment blocks network access or the URL requires authorization, the script will fail to fetch; in that case download the .ics manually and pass the .ics URL or file.
- The script is defensive and attempts to parse common patterns, but published HTML markup may vary. If parsing fails for the page you provided, open an issue and include the page HTML so the parser can be extended.

License: MIT
# GenerateTimetableFromOutlookCalendar
