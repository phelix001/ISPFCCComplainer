"""Manually save FCC login session by solving Cloudflare challenge interactively.

Run this script on a machine with a display (or via VNC/X forwarding):
    python -m src.save_session

This will open a browser where you can manually:
1. Solve the Cloudflare captcha
2. Login to the FCC portal
3. The session will be saved for automated use

After running this once, the daily_complaint.py script should work without manual intervention.
"""

import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from .config import load_config
from .fcc_complainer import BROWSER_STATE_PATH


def main() -> int:
    """Open browser for manual login and session saving."""
    print("FCC Session Saver")
    print("=" * 60)
    print()
    print("This will open a browser window where you need to:")
    print("1. Solve the Cloudflare 'Verify you are human' checkbox")
    print("2. Login with your FCC credentials")
    print("3. Wait until you see the dashboard")
    print("4. Press Enter in this terminal to save the session")
    print()
    print(f"Session will be saved to: {BROWSER_STATE_PATH}")
    print()

    try:
        config = load_config()
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    BROWSER_STATE_PATH.mkdir(exist_ok=True)

    with sync_playwright() as p:
        # Open visible browser with persistent context
        context = p.chromium.launch_persistent_context(
            str(BROWSER_STATE_PATH),
            headless=False,  # Must be visible for manual interaction
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )

        # Apply stealth
        stealth = Stealth()
        stealth.apply_stealth_sync(context)

        page = context.pages[0] if context.pages else context.new_page()

        print("Opening FCC login page...")
        page.goto("https://consumercomplaints.fcc.gov/hc/en-us/signin")

        print()
        print("=" * 60)
        print("WAITING FOR YOU TO:")
        print("  1. Solve the Cloudflare captcha (click the checkbox)")
        print("  2. Login with your FCC credentials:")
        print(f"     Email: {config.fcc_username}")
        print("  3. Wait for the dashboard to load")
        print()
        print("Press Enter here when you're logged in and see the dashboard...")
        print("=" * 60)

        input()

        print()
        print(f"Current page: {page.title()}")
        print(f"URL: {page.url}")

        # Verify we're logged in
        if "sign" in page.url.lower() or "signin" in page.title().lower():
            print()
            print("WARNING: It looks like you might not be logged in yet.")
            print("The session will be saved anyway. Try running the complaint script to test.")
        else:
            print()
            print("SUCCESS! You appear to be logged in.")

        print()
        print("Saving session...")
        context.close()

        print(f"Session saved to: {BROWSER_STATE_PATH}")
        print()
        print("You can now run the daily complaint script:")
        print("  python -m src.daily_complaint")
        print()
        return 0


if __name__ == "__main__":
    sys.exit(main())
