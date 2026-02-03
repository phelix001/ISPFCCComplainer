#!/usr/bin/env python3
"""
FCC Complaint Filer - Laptop Client

This script runs on your laptop, fetches speed test data from your Pi,
and opens a browser to file the complaint. You solve the Cloudflare captcha
manually, and the script handles the rest.

Setup:
    pip install playwright playwright-stealth
    playwright install chromium

Usage:
    python file_complaint.py                    # Uses defaults
    python file_complaint.py --pi-host pihole   # Custom Pi hostname
    python file_complaint.py --dry-run          # Preview only

Schedule with cron (Mac/Linux) or Task Scheduler (Windows) to run at 9am daily.
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from statistics import mean

# Configuration - edit these for your setup
DEFAULT_PI_HOST = "dietpi"  # SSH hostname for your Pi
DEFAULT_PI_USER = "dietpi"  # SSH username
DEFAULT_PI_PATH = "/home/dietpi/ISPFCCComplainer"  # Path on Pi


def fetch_data_from_pi(host: str, user: str, pi_path: str, date: str | None = None) -> dict:
    """SSH to Pi and fetch speed test data as JSON."""
    cmd = f"cd {pi_path} && ./venv/bin/python -m src.export_daily_data"
    if date:
        cmd += f" --date {date}"

    ssh_cmd = ["ssh", f"{user}@{host}", cmd]

    print(f"Fetching data from {user}@{host}...")
    result = subprocess.run(ssh_cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"SSH failed: {result.stderr}")

    return json.loads(result.stdout)


def generate_complaint_text(data: dict) -> str:
    """Generate complaint text from Pi data."""
    config = data["config"]
    tests = data["tests"]
    report_date = data["date"]

    if not tests:
        return None

    downloads = [t["download_mbps"] for t in tests]
    uploads = [t["upload_mbps"] for t in tests]
    pings = [t["ping_ms"] for t in tests]

    avg_download = mean(downloads)
    min_download = min(downloads)
    max_download = max(downloads)
    avg_upload = mean(uploads)
    avg_ping = mean(pings)

    threshold = config["threshold_speed_mbps"]
    failed_tests = [t for t in tests if t["download_mbps"] < threshold]
    failed_count = len(failed_tests)
    total_count = len(tests)
    failure_rate = (failed_count / total_count) * 100 if total_count > 0 else 0
    avg_percent = (avg_download / config["advertised_speed_mbps"]) * 100

    # Build test details
    test_details = []
    for t in tests:
        ts = datetime.fromisoformat(t["timestamp"])
        percent = (t["download_mbps"] / config["advertised_speed_mbps"]) * 100
        status = "FAILED" if t["download_mbps"] < threshold else "OK"
        test_details.append(
            f"  {ts.strftime('%H:%M:%S')} - "
            f"Down: {t['download_mbps']:>7.2f} Mbps ({percent:>5.1f}%) | "
            f"Up: {t['upload_mbps']:>7.2f} Mbps | "
            f"Ping: {t['ping_ms']:>5.1f} ms | "
            f"{status}"
        )

    test_list = "\n".join(test_details)

    return f"""I am filing this complaint regarding consistently inadequate internet service from {config['isp_name']}.

SERVICE DETAILS:
- Account Number: {config['isp_account_number']}
- Service Address: {config['service_address']}
- Advertised Speed: {config['advertised_speed_mbps']} Mbps
- Minimum Acceptable ({config['threshold_percent']}%): {threshold:.1f} Mbps

DAILY SUMMARY FOR {report_date}:
- Total Speed Tests: {total_count}
- Failed Tests (below {config['threshold_percent']}%): {failed_count} ({failure_rate:.1f}% failure rate)
- Average Download: {avg_download:.2f} Mbps ({avg_percent:.1f}% of advertised)
- Minimum Download: {min_download:.2f} Mbps
- Maximum Download: {max_download:.2f} Mbps
- Average Upload: {avg_upload:.2f} Mbps
- Average Ping: {avg_ping:.1f} ms

INDIVIDUAL TEST RESULTS:
{test_list}

COMPLAINT:
On {report_date}, I ran {total_count} automated speed tests throughout the day to monitor my internet service from {config['isp_name']}. Of these tests, {failed_count} ({failure_rate:.1f}%) fell below {config['threshold_percent']}% of my advertised {config['advertised_speed_mbps']} Mbps service.

My average download speed for the day was only {avg_download:.2f} Mbps, which is {avg_percent:.1f}% of what I am paying for. This represents a significant and consistent failure by {config['isp_name']} to deliver the service I am paying for.

I request that the FCC investigate this pattern of underperformance and require {config['isp_name']} to either consistently provide the advertised speeds or adjust my billing to reflect the actual service being delivered.

This complaint was automatically generated from verified speed test data."""


def file_complaint_with_browser(data: dict, complaint_text: str, dry_run: bool = False) -> bool:
    """Open browser and file complaint. User solves captcha manually."""
    from playwright.sync_api import sync_playwright

    config = data["config"]

    if dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN - Would file complaint with this text:")
        print("=" * 60)
        print(complaint_text)
        print("=" * 60 + "\n")
        return True

    # Use persistent context for session storage
    state_path = Path.home() / ".fcc_complaint_session"
    state_path.mkdir(exist_ok=True)

    with sync_playwright() as p:
        print("Opening browser...")
        context = p.chromium.launch_persistent_context(
            str(state_path),
            headless=False,  # Visible browser for captcha solving
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )

        # Try to apply stealth if available
        try:
            from playwright_stealth import Stealth
            stealth = Stealth()
            stealth.apply_stealth_sync(context)
        except ImportError:
            print("Note: playwright-stealth not installed, continuing without stealth")

        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(120000)  # 2 minute timeout

        try:
            # Go to login page
            print("Navigating to FCC login...")
            page.goto("https://consumercomplaints.fcc.gov/hc/en-us/signin")
            page.wait_for_load_state("domcontentloaded")
            time.sleep(2)

            # Check for Cloudflare
            if "moment" in page.title().lower():
                print("\n" + "=" * 60)
                print("CLOUDFLARE CAPTCHA DETECTED")
                print("Please solve the captcha in the browser window!")
                print("=" * 60 + "\n")

                # Wait for captcha to be solved
                for i in range(60):  # Wait up to 5 minutes
                    time.sleep(5)
                    if "moment" not in page.title().lower():
                        print("Captcha solved!")
                        break
                    if i % 6 == 0:
                        print(f"Still waiting for captcha... ({i*5}s)")
                else:
                    raise RuntimeError("Captcha not solved in time")

            time.sleep(2)

            # Check if already logged in
            if "signin" in page.url.lower() or "sign in" in page.title().lower():
                print("Logging in...")
                page.fill('[data-testid="email-input"]', config["fcc_username"])
                page.fill('input[type="password"]', config["fcc_password"])
                page.click('button[type="submit"]')
                page.wait_for_load_state("networkidle")
                time.sleep(3)

                # Verify login
                if "signin" in page.url.lower():
                    raise RuntimeError("Login failed - check credentials")
                print("Login successful!")
            else:
                print("Already logged in from previous session")

            # Navigate to complaint form
            print("Navigating to complaint form...")
            page.goto("https://consumercomplaints.fcc.gov/hc/en-us/requests/new?ticket_form_id=38824")
            page.wait_for_load_state("domcontentloaded")
            time.sleep(3)

            # Fill form
            print("Filling complaint form...")
            subject = f"Internet Speed Below Advertised - {config['isp_name']}"
            page.fill('#request_subject', subject)
            page.fill('#request_description', complaint_text)

            # Try to select "Speed" from dropdown
            try:
                dropdown = page.locator('#request_custom_fields_22609394').locator('..').locator('a.nesty-input').first
                if dropdown.is_visible(timeout=3000):
                    dropdown.click()
                    time.sleep(1)
                    speed_opt = page.locator('li:has-text("Speed")').first
                    if speed_opt.is_visible(timeout=2000):
                        speed_opt.click()
                        print("Selected issue type: Speed")
            except Exception:
                pass

            # Screenshot before submit
            page.screenshot(path=str(state_path / "before_submit.png"))
            print(f"Screenshot saved: {state_path / 'before_submit.png'}")

            # Submit
            print("\n" + "=" * 60)
            print("READY TO SUBMIT")
            print("Review the form in the browser window.")
            print("Press Enter here to submit, or Ctrl+C to cancel...")
            print("=" * 60)
            input()

            submit = page.locator('input[type="submit"][value="Submit"]')
            if not submit.is_visible(timeout=3000):
                submit = page.locator('input[type="submit"]').first
            submit.click()

            print("Clicked submit...")
            time.sleep(5)
            page.wait_for_load_state("domcontentloaded")

            # Screenshot after submit
            page.screenshot(path=str(state_path / "after_submit.png"))
            print(f"Screenshot saved: {state_path / 'after_submit.png'}")

            # Check for success
            if "new" not in page.url.lower():
                print("\nCOMPLAINT SUBMITTED SUCCESSFULLY!")
                return True
            else:
                print("\nWarning: May still be on form page. Check screenshots.")
                return False

        finally:
            print("\nClosing browser (session saved for next time)...")
            context.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="File FCC complaint from laptop using Pi data")
    parser.add_argument("--pi-host", default=DEFAULT_PI_HOST, help=f"Pi hostname (default: {DEFAULT_PI_HOST})")
    parser.add_argument("--pi-user", default=DEFAULT_PI_USER, help=f"Pi username (default: {DEFAULT_PI_USER})")
    parser.add_argument("--pi-path", default=DEFAULT_PI_PATH, help=f"Path on Pi (default: {DEFAULT_PI_PATH})")
    parser.add_argument("--date", help="Date to report (YYYY-MM-DD, default: yesterday)")
    parser.add_argument("--dry-run", action="store_true", help="Show complaint text without filing")
    parser.add_argument("--min-failures", type=int, default=1, help="Minimum failures to file (default: 1)")
    args = parser.parse_args()

    print("=" * 60)
    print("FCC Complaint Filer - Laptop Client")
    print("=" * 60 + "\n")

    # Fetch data from Pi
    try:
        data = fetch_data_from_pi(args.pi_host, args.pi_user, args.pi_path, args.date)
    except Exception as e:
        print(f"Error fetching data: {e}")
        return 1

    if data.get("error"):
        print(f"Error from Pi: {data['error']}")
        return 1

    tests = data.get("tests", [])
    config = data.get("config", {})

    print(f"Date: {data['date']}")
    print(f"Tests found: {len(tests)}")

    if not tests:
        print("No tests for this date. Nothing to file.")
        return 0

    # Calculate failures
    threshold = config.get("threshold_speed_mbps", 700)
    failed = [t for t in tests if t["download_mbps"] < threshold]
    failure_rate = (len(failed) / len(tests)) * 100

    print(f"Failed tests: {len(failed)} ({failure_rate:.1f}%)")
    print(f"Threshold: {threshold:.1f} Mbps")
    print()

    if len(failed) < args.min_failures:
        print(f"Only {len(failed)} failures (minimum: {args.min_failures}). Skipping.")
        return 0

    # Generate complaint
    complaint_text = generate_complaint_text(data)

    if not complaint_text:
        print("Could not generate complaint text.")
        return 1

    # File it
    try:
        success = file_complaint_with_browser(data, complaint_text, args.dry_run)
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\nCancelled by user.")
        return 1
    except Exception as e:
        print(f"Error filing complaint: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
