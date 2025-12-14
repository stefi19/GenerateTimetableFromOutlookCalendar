"""
Run this once to create a persistent Playwright profile and log in to Outlook.

Usage:
  source .venv/bin/activate
  python playwright_login.py

A browser window will open. Log in to your Microsoft/Outlook account there. When finished,
close the browser window or press Enter in the terminal to finish.
"""
from playwright.sync_api import sync_playwright
import os

DEFAULT_PROFILE = os.path.expanduser("~/.playwright_profile")

def main():
    user_data_dir = os.environ.get("PLAYWRIGHT_USER_DATA_DIR", DEFAULT_PROFILE)
    print(f"Using Playwright user data dir: {user_data_dir}")
    os.makedirs(user_data_dir, exist_ok=True)

    with sync_playwright() as p:
        # Launch a persistent context in headed mode so you can log in interactively
        context = p.chromium.launch_persistent_context(user_data_dir, headless=False)
        page = context.new_page()
        page.goto("https://outlook.office.com")
        print("Please log in in the opened browser window. After login completes, press Enter here.")
        input()
        context.close()


if __name__ == "__main__":
    main()
