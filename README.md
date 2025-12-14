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

Optional flags:
- `--days N` show only the next N days (default: 7)
- `--from YYYY-MM-DD` and `--to YYYY-MM-DD` to specify an explicit date range

Example:

```bash
python timetable.py <URL> --days 14
```

Web UI
------
You can run a small web interface where users can paste a calendar URL or upload a `.ics` file and view a timetable.

1. Install dependencies (see above).

2. Run the Flask app:

```bash
export FLASK_APP=app.py
flask run --host=127.0.0.1 --port=5000
# or: python app.py
```

3. Open http://127.0.0.1:5000 in a browser.

The web UI will attempt to detect and fetch a linked `.ics` feed from the published page and display events grouped by day. If the published page returns a client-side (JS) rendered page, download the `.ics` manually and upload it via the form.

Run helper (recommended)
------------------------
To avoid accidentally running outside the virtualenv, there's a helper script `run.sh` that activates the venv, installs dependencies, and starts the app.

Make it executable and run it:

```bash
chmod +x run.sh
./run.sh
```

If you prefer to run manually, always activate the venv first:

```bash
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
