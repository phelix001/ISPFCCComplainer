"""FCC complaint automation using Playwright."""

import os
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeout
from playwright_stealth import Stealth

from .config import Config
from .database import SpeedTestResult

# Persistent browser storage for session cookies
BROWSER_STATE_PATH = Path(__file__).parent.parent / "browser_state"


def generate_daily_summary_complaint(
    config: Config,
    date: datetime,
    failed_tests: list[SpeedTestResult],
    all_tests: list[SpeedTestResult],
) -> str:
    """Generate complaint text summarizing a day's speed tests.

    Args:
        config: Application configuration.
        date: The date being complained about.
        failed_tests: List of tests that failed to meet threshold.
        all_tests: All tests for the day.

    Returns:
        Formatted complaint text for the FCC form.
    """
    date_str = date.strftime("%Y-%m-%d")

    # Calculate statistics
    downloads = [t.download_mbps for t in all_tests]
    uploads = [t.upload_mbps for t in all_tests]
    pings = [t.ping_ms for t in all_tests]

    avg_download = sum(downloads) / len(downloads)
    avg_upload = sum(uploads) / len(uploads)
    avg_ping = sum(pings) / len(pings)
    min_download = min(downloads)
    max_download = max(downloads)
    failure_rate = (len(failed_tests) / len(all_tests)) * 100
    avg_pct = (avg_download / config.advertised_speed_mbps) * 100

    worst_test = min(all_tests, key=lambda t: t.download_mbps)
    worst_pct = (worst_test.download_mbps / config.advertised_speed_mbps) * 100

    return f"""I am filing this complaint regarding inadequate internet service from {config.isp_name}.

SERVICE DETAILS:
- Account Number: {config.isp_account_number}
- Service Address: {config.service_address}
- Advertised Speed: {config.advertised_speed_mbps} Mbps
- Minimum Acceptable ({config.threshold_percent}%): {config.threshold_speed_mbps:.1f} Mbps

DAILY SUMMARY FOR {date_str}:
- Total Speed Tests: {len(all_tests)}
- Tests Below Threshold: {len(failed_tests)} ({failure_rate:.1f}%)
- Average Download Speed: {avg_download:.2f} Mbps ({avg_pct:.1f}% of advertised)
- Average Upload Speed: {avg_upload:.2f} Mbps
- Average Ping: {avg_ping:.1f} ms
- Minimum Download Speed: {min_download:.2f} Mbps
- Maximum Download Speed: {max_download:.2f} Mbps

WORST RESULT:
- Date/Time: {worst_test.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
- Download Speed: {worst_test.download_mbps:.2f} Mbps ({worst_pct:.1f}% of advertised)
- Upload Speed: {worst_test.upload_mbps:.2f} Mbps
- Ping: {worst_test.ping_ms:.1f} ms
- Test Server: {worst_test.server}

ALL SPEED TESTS FOR {date_str}:
{_format_all_tests(all_tests, config.advertised_speed_mbps, config.threshold_speed_mbps)}

COMPLAINT:
I am paying for {config.advertised_speed_mbps} Mbps internet service but on {date_str}, my average download speed was only {avg_download:.2f} Mbps ({avg_pct:.1f}% of advertised). Out of {len(all_tests)} speed tests conducted, {len(failed_tests)} ({failure_rate:.1f}%) showed download speeds below the {config.threshold_percent}% threshold.

The worst test showed only {worst_test.download_mbps:.2f} Mbps ({worst_pct:.1f}% of advertised speed).

This represents a consistent failure by {config.isp_name} to deliver the service I am paying for. I request that the FCC investigate this matter and require {config.isp_name} to either provide the advertised speeds or adjust my billing accordingly.

This complaint was automatically generated based on automated speed testing throughout the day."""


def _format_all_tests(
    tests: list[SpeedTestResult], advertised_mbps: float, threshold_mbps: float
) -> str:
    """Format all tests for the complaint, marking failures."""
    lines = []
    for test in tests:
        pct = (test.download_mbps / advertised_mbps) * 100
        status = "FAIL" if test.download_mbps < threshold_mbps else "OK"
        lines.append(
            f"  [{status}] {test.timestamp.strftime('%H:%M:%S')}: "
            f"{test.download_mbps:.2f} Mbps down, {test.upload_mbps:.2f} Mbps up, "
            f"{test.ping_ms:.1f}ms ping ({pct:.1f}%)"
        )
    return "\n".join(lines)


def generate_complaint_text(
    config: Config, speed_result: SpeedTestResult
) -> str:
    """Generate the complaint text based on speed test results.

    Args:
        config: Application configuration with ISP and threshold details.
        speed_result: The speed test result that triggered the complaint.

    Returns:
        Formatted complaint text for the FCC form.
    """
    percent_of_advertised = (speed_result.download_mbps / config.advertised_speed_mbps) * 100

    return f"""I am filing this complaint regarding inadequate internet service from {config.isp_name}.

SERVICE DETAILS:
- Account Number: {config.isp_account_number}
- Service Address: {config.service_address}
- Advertised Speed: {config.advertised_speed_mbps} Mbps
- Minimum Acceptable ({config.threshold_percent}%): {config.threshold_speed_mbps:.1f} Mbps

SPEED TEST RESULTS:
- Date/Time: {speed_result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
- Download Speed: {speed_result.download_mbps:.2f} Mbps ({percent_of_advertised:.1f}% of advertised)
- Upload Speed: {speed_result.upload_mbps:.2f} Mbps
- Ping: {speed_result.ping_ms:.1f} ms
- Test Server: {speed_result.server}

COMPLAINT:
I am paying for {config.advertised_speed_mbps} Mbps internet service but consistently receiving speeds far below what is advertised. The speed test above shows I am receiving only {percent_of_advertised:.1f}% of my advertised speed, which is below the {config.threshold_percent}% threshold I consider acceptable.

This represents a failure by {config.isp_name} to deliver the service I am paying for. I request that the FCC investigate this matter and require {config.isp_name} to either provide the advertised speeds or adjust my billing accordingly.

This complaint was automatically generated and filed due to repeated speed test failures."""


def file_fcc_complaint(
    config: Config,
    speed_result: SpeedTestResult,
    dry_run: bool = False,
    headless: bool = True,
) -> bool:
    """File an FCC complaint via browser automation.

    Args:
        config: Application configuration with FCC credentials and ISP details.
        speed_result: The speed test result that triggered the complaint.
        dry_run: If True, don't actually submit the complaint.
        headless: If True, run browser in headless mode.

    Returns:
        True if complaint was successfully filed (or would be in dry_run mode).

    Raises:
        RuntimeError: If login or form submission fails.
    """
    complaint_text = generate_complaint_text(config, speed_result)

    if dry_run:
        print("\n=== DRY RUN - Complaint would be filed with this text: ===")
        print(complaint_text)
        print("=== END DRY RUN ===\n")
        return True

    with sync_playwright() as p:
        # Use persistent context to save/restore session state (cookies, localStorage)
        # This allows manually solving Cloudflare once and reusing the session
        BROWSER_STATE_PATH.mkdir(exist_ok=True)
        context = p.chromium.launch_persistent_context(
            str(BROWSER_STATE_PATH),
            headless=headless,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        # Apply stealth mode to bypass Cloudflare bot detection
        stealth = Stealth()
        stealth.apply_stealth_sync(context)
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(60000)  # 60 second timeout

        try:
            # Login to FCC Consumer Complaints portal
            _login_to_fcc(page, config)

            # Navigate to file new complaint
            _navigate_to_new_complaint(page)

            # Fill out the complaint form
            _fill_complaint_form(page, config, complaint_text)

            # Submit the complaint
            _submit_complaint(page)

            print("FCC complaint successfully filed!")
            return True

        except PlaywrightTimeout as e:
            raise RuntimeError(f"Timeout during FCC complaint filing: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to file FCC complaint: {e}")
        finally:
            context.close()


def _login_to_fcc(page: Page, config: Config) -> None:
    """Login to the FCC Consumer Complaints portal."""
    import time
    print("Logging into FCC Consumer Complaints portal...")

    page.goto("https://consumercomplaints.fcc.gov/hc/en-us/signin")
    page.wait_for_load_state("domcontentloaded")
    time.sleep(3)  # Wait for JS to render form

    print(f"  Page title: {page.title()}")
    print(f"  URL: {page.url}")

    # Check if we're stuck on Cloudflare challenge
    if "moment" in page.title().lower() or "cloudflare" in page.content().lower():
        print("  Cloudflare challenge detected, attempting to solve...")

        # Try to find and click the Turnstile checkbox
        try:
            # Wait for iframe to load
            time.sleep(3)

            # Try clicking the checkbox within the Turnstile widget
            # The checkbox is typically inside an iframe
            turnstile_frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"]').first
            checkbox = turnstile_frame.locator('input[type="checkbox"], .ctp-checkbox-label, [role="checkbox"]').first
            if checkbox:
                checkbox.click()
                print("  Clicked Turnstile checkbox")
                time.sleep(5)
        except Exception as e:
            print(f"  Could not click Turnstile checkbox: {e}")

        # Wait up to 60 seconds for Cloudflare to pass
        for i in range(12):
            time.sleep(5)
            title = page.title().lower()
            if "moment" not in title and "cloudflare" not in title.lower():
                print(f"  Cloudflare challenge passed after {(i+1)*5} seconds")
                break
            print(f"  Still waiting... ({(i+1)*5}s)")
        else:
            page.screenshot(path="/tmp/fcc_cloudflare_stuck.png")
            print("  Screenshot saved: /tmp/fcc_cloudflare_stuck.png")
            raise RuntimeError("Cloudflare challenge did not complete after 60 seconds")

    # Fill login form using data-testid selectors
    page.fill('[data-testid="email-input"]', config.fcc_username)
    page.fill('input[type="password"]', config.fcc_password)

    # Click sign in button
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    print(f"  After login URL: {page.url}")
    print(f"  After login title: {page.title()}")

    # Verify login succeeded by checking page title (URL may lag behind)
    title = page.title().lower()
    if "sign in" in title or "signin" in title:
        page.screenshot(path="/tmp/fcc_login_failed.png")
        print("  Screenshot saved to /tmp/fcc_login_failed.png")
        raise RuntimeError("FCC login failed - check credentials")

    print("Successfully logged into FCC portal")


def _navigate_to_new_complaint(page: Page) -> None:
    """Navigate to the new complaint form for internet issues."""
    import time
    print("Navigating to new complaint form...")

    # Go directly to the internet complaint form with ticket_form_id=38824 (Internet)
    page.goto("https://consumercomplaints.fcc.gov/hc/en-us/requests/new?ticket_form_id=38824")
    page.wait_for_load_state("domcontentloaded")
    time.sleep(5)  # Wait for form to fully load

    print(f"  On page: {page.title()}")
    print(f"  URL: {page.url}")

    print("On new complaint form")


def _fill_complaint_form(page: Page, config: Config, complaint_text: str) -> None:
    """Fill out the FCC complaint form fields."""
    import time
    print("Filling complaint form...")

    # Fill the Subject field
    subject = f"Internet Speed Below Advertised - {config.isp_name}"
    page.fill('#request_subject', subject)
    print(f"  Subject: {subject}")

    # Fill the Description field with the full complaint text
    page.fill('#request_description', complaint_text)
    print("  Description filled")

    # Select "Speed" from the Internet Issues dropdown (nesty-input custom dropdown)
    try:
        # Click the dropdown trigger to open it
        dropdown_trigger = page.locator('#request_custom_fields_22609394').locator('..').locator('a.nesty-input').first
        if dropdown_trigger.is_visible(timeout=3000):
            dropdown_trigger.click()
            time.sleep(1)

            # Click on "Speed" option
            speed_option = page.locator('li:has-text("Speed")').first
            if speed_option.is_visible(timeout=2000):
                speed_option.click()
                print("  Selected issue: Speed")
                time.sleep(1)
    except Exception as e:
        print(f"  Could not select issue type: {e}")

    time.sleep(1)
    print("Form filled")


def _try_fill_field(page: Page, selectors: list[str], value: str) -> bool:
    """Try multiple selectors to fill a form field.

    Returns True if any selector matched and was filled.
    """
    for selector in selectors:
        try:
            element = page.locator(selector).first
            if element.is_visible(timeout=1000):
                element.fill(value)
                return True
        except Exception:
            continue
    return False


def _submit_complaint(page: Page) -> None:
    """Submit the complaint form."""
    import time
    print("Submitting complaint...")

    # Take screenshot before submit
    page.screenshot(path="/tmp/fcc_before_submit.png")
    print("  Screenshot saved: /tmp/fcc_before_submit.png")

    # Find and click the submit button
    submit = page.locator('input[type="submit"][value="Submit"]')
    if not submit.is_visible(timeout=5000):
        # Try alternative selectors
        submit = page.locator('input[type="submit"]').first

    submit.click()
    print("  Clicked submit")

    # Wait for response
    time.sleep(5)
    page.wait_for_load_state("domcontentloaded")

    # Take screenshot after submit
    page.screenshot(path="/tmp/fcc_after_submit.png")
    print("  Screenshot saved: /tmp/fcc_after_submit.png")

    # Check for success - look for confirmation indicators
    title = page.title().lower()
    url = page.url.lower()

    print(f"  Page title: {page.title()}")
    print(f"  URL: {page.url}")

    # Check if we're on a confirmation/ticket page (not the form anymore)
    if "new" not in url and ("requests" in url or "tickets" in url):
        print("  Redirected away from form - complaint submitted!")
        return

    # Check page title for confirmation
    if "thank" in title or "confirmation" in title or "submitted" in title:
        print("  Confirmation page detected!")
        return

    # Check if form still visible with errors
    error_messages = page.locator('.error, [class*="error"], [role="alert"]').all()
    visible_errors = [e for e in error_messages if e.is_visible(timeout=1000)]
    if visible_errors:
        for err in visible_errors[:3]:
            print(f"  Error: {err.text_content()}")
        raise RuntimeError("Form has validation errors")

    # If still on the new request form, submission may have failed silently
    if "new" in url:
        print("  Warning: Still on form page after submit")
        raise RuntimeError("Submission may have failed - still on form page")
