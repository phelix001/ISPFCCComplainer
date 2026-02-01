"""FCC complaint automation using Playwright."""

from datetime import datetime
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeout

from .config import Config
from .database import SpeedTestResult


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
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()

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
            browser.close()


def _login_to_fcc(page: Page, config: Config) -> None:
    """Login to the FCC Consumer Complaints portal."""
    print("Logging into FCC Consumer Complaints portal...")

    page.goto("https://consumercomplaints.fcc.gov/hc/en-us/signin")
    page.wait_for_load_state("networkidle")

    # Fill login form
    page.fill('input[name="email"], input[type="email"]', config.fcc_username)
    page.fill('input[name="password"], input[type="password"]', config.fcc_password)

    # Click sign in button
    page.click('input[type="submit"], button[type="submit"]')
    page.wait_for_load_state("networkidle")

    # Verify login succeeded by checking we're no longer on signin page
    if "signin" in page.url.lower():
        raise RuntimeError("FCC login failed - check credentials")

    print("Successfully logged into FCC portal")


def _navigate_to_new_complaint(page: Page) -> None:
    """Navigate to the new complaint form for internet issues."""
    print("Navigating to new complaint form...")

    # Go to the main complaints page
    page.goto("https://consumercomplaints.fcc.gov/hc/en-us/requests/new")
    page.wait_for_load_state("networkidle")

    # Select Internet complaint type if there's a category selector
    # The FCC form structure may vary, so we try multiple approaches
    try:
        # Look for internet/broadband category
        internet_option = page.locator('text=Internet, text=Broadband').first
        if internet_option.is_visible():
            internet_option.click()
            page.wait_for_load_state("networkidle")
    except Exception:
        pass  # Category may already be selected or form structure differs

    print("On new complaint form")


def _fill_complaint_form(page: Page, config: Config, complaint_text: str) -> None:
    """Fill out the FCC complaint form fields."""
    print("Filling complaint form...")

    # Common form fields - the FCC form may have various field names
    # We try multiple selectors for each field type

    # Provider/Company name
    _try_fill_field(page, [
        'input[name*="provider"]',
        'input[name*="company"]',
        'input[name*="carrier"]',
        '#request_custom_fields_*[placeholder*="provider"]',
    ], config.isp_name)

    # Account number
    _try_fill_field(page, [
        'input[name*="account"]',
        '#request_custom_fields_*[placeholder*="account"]',
    ], config.isp_account_number)

    # Phone number
    _try_fill_field(page, [
        'input[name*="phone"]',
        'input[type="tel"]',
    ], config.phone_number)

    # Email (may be pre-filled from login)
    _try_fill_field(page, [
        'input[name*="email"]:not([readonly])',
    ], config.email)

    # Service address
    _try_fill_field(page, [
        'input[name*="address"]',
        'textarea[name*="address"]',
    ], config.service_address)

    # Main complaint description/details
    _try_fill_field(page, [
        'textarea[name*="description"]',
        'textarea[name*="details"]',
        'textarea[name*="complaint"]',
        'textarea#request_description',
        'textarea',
    ], complaint_text)

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
    print("Submitting complaint...")

    # Find and click the submit button
    submit_selectors = [
        'button[type="submit"]',
        'input[type="submit"]',
        'button:has-text("Submit")',
        'button:has-text("File")',
    ]

    for selector in submit_selectors:
        try:
            button = page.locator(selector).first
            if button.is_visible(timeout=2000):
                button.click()
                page.wait_for_load_state("networkidle")

                # Check for success indicators
                if "thank" in page.content().lower() or "submitted" in page.content().lower():
                    return

                # Check we're not still on the form with errors
                if "error" in page.content().lower():
                    raise RuntimeError("Form submission returned errors")

                return
        except PlaywrightTimeout:
            continue

    raise RuntimeError("Could not find or click submit button")
