#!/usr/bin/env python3
"""
Open the published calendar URL in a visible Playwright browser using the persistent profile.
Run with your venv active and PLAYWRIGHT_USER_DATA_DIR set to the profile you logged into.

Usage:
  source .venv/bin/activate
  export PLAYWRIGHT_USER_DATA_DIR="$HOME/.playwright_profile"
  python tools/playwright_headed_open.py

The script opens a browser window. Use Cmd+Option+I to open DevTools, switch to Network, filter for `.ics` or `calendar`, then reload the page.
When you're done, close the browser window and press Enter in the terminal to exit the script.
"""
from playwright.sync_api import sync_playwright
import os

URL = 'https://outlook.office365.com/calendar/published/173862b98010453296f2a697e45f3b1e@campus.utcluj.ro/daeb64d4bd994c52b4f54d04ba1940ca2236386271423118770/calendar.html'


def main():
    user_data_dir = os.environ.get('PLAYWRIGHT_USER_DATA_DIR', os.path.expanduser('~/.playwright_profile'))
    print('Using PLAYWRIGHT_USER_DATA_DIR=', user_data_dir)
    print('Launching headed browser. Please open DevTools (Cmd+Option+I) -> Network and reload the page to look for .ics or text/calendar requests.')
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(user_data_dir, headless=False)
        page = context.new_page()
        page.goto(URL)
        input('When you are finished inspecting the page, close the browser window and press Enter here to exit...')
        context.close()


if __name__ == '__main__':
    main()
