"""Daily FCC complaint aggregation - files one complaint with all previous day's test data."""

import argparse
import sys
from datetime import datetime, timedelta
from statistics import mean

from .config import load_config, Config
from .database import Database, SpeedTestResult, Complaint
from .fcc_complainer import file_fcc_complaint


def generate_daily_complaint_text(
    config: Config,
    tests: list[SpeedTestResult],
    report_date: datetime,
) -> str:
    """Generate complaint text summarizing all tests from a single day.

    Args:
        config: Application configuration with ISP and threshold details.
        tests: List of all speed tests from the reporting date.
        report_date: The date being reported on.

    Returns:
        Formatted complaint text for the FCC form.
    """
    downloads = [t.download_mbps for t in tests]
    uploads = [t.upload_mbps for t in tests]
    pings = [t.ping_ms for t in tests]

    avg_download = mean(downloads)
    min_download = min(downloads)
    max_download = max(downloads)
    avg_upload = mean(uploads)
    avg_ping = mean(pings)

    failed_tests = [t for t in tests if t.download_mbps < config.threshold_speed_mbps]
    failed_count = len(failed_tests)
    total_count = len(tests)
    failure_rate = (failed_count / total_count) * 100 if total_count > 0 else 0
    avg_percent = (avg_download / config.advertised_speed_mbps) * 100

    # Build individual test results section
    test_details = []
    for t in tests:
        percent = (t.download_mbps / config.advertised_speed_mbps) * 100
        status = "FAILED" if t.download_mbps < config.threshold_speed_mbps else "OK"
        test_details.append(
            f"  {t.timestamp.strftime('%H:%M:%S')} - "
            f"Down: {t.download_mbps:>7.2f} Mbps ({percent:>5.1f}%) | "
            f"Up: {t.upload_mbps:>7.2f} Mbps | "
            f"Ping: {t.ping_ms:>5.1f} ms | "
            f"{status}"
        )

    test_list = "\n".join(test_details)

    return f"""I am filing this complaint regarding consistently inadequate internet service from {config.isp_name}.

SERVICE DETAILS:
- Account Number: {config.isp_account_number}
- Service Address: {config.service_address}
- Advertised Speed: {config.advertised_speed_mbps} Mbps
- Minimum Acceptable ({config.threshold_percent}%): {config.threshold_speed_mbps:.1f} Mbps

DAILY SUMMARY FOR {report_date.strftime('%Y-%m-%d')}:
- Total Speed Tests: {total_count}
- Failed Tests (below {config.threshold_percent}%): {failed_count} ({failure_rate:.1f}% failure rate)
- Average Download: {avg_download:.2f} Mbps ({avg_percent:.1f}% of advertised)
- Minimum Download: {min_download:.2f} Mbps
- Maximum Download: {max_download:.2f} Mbps
- Average Upload: {avg_upload:.2f} Mbps
- Average Ping: {avg_ping:.1f} ms

INDIVIDUAL TEST RESULTS:
{test_list}

COMPLAINT:
On {report_date.strftime('%B %d, %Y')}, I ran {total_count} automated speed tests throughout the day to monitor my internet service from {config.isp_name}. Of these tests, {failed_count} ({failure_rate:.1f}%) fell below {config.threshold_percent}% of my advertised {config.advertised_speed_mbps} Mbps service.

My average download speed for the day was only {avg_download:.2f} Mbps, which is {avg_percent:.1f}% of what I am paying for. This represents a significant and consistent failure by {config.isp_name} to deliver the service I am paying for.

I request that the FCC investigate this pattern of underperformance and require {config.isp_name} to either consistently provide the advertised speeds or adjust my billing to reflect the actual service being delivered.

This complaint was automatically generated from verified speed test data."""


def main() -> int:
    """Main entry point for daily complaint filing.

    Returns:
        Exit code: 0 for no complaint needed, 1 for error, 2 for complaint filed.
    """
    parser = argparse.ArgumentParser(
        description="File daily FCC complaint summarizing previous day's speed tests"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate complaint but don't actually file it",
    )
    parser.add_argument(
        "--show-browser",
        action="store_true",
        help="Show browser window during complaint filing (for debugging)",
    )
    parser.add_argument(
        "--env-file",
        type=str,
        help="Path to .env file (default: .env in current directory)",
    )
    parser.add_argument(
        "--date",
        type=str,
        help="Date to report on (YYYY-MM-DD format, default: yesterday)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="File complaint even if failure rate is 0%",
    )

    args = parser.parse_args()

    try:
        config = load_config(args.env_file)
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    db = Database(config.db_path)

    # Determine report date
    if args.date:
        try:
            report_date = datetime.strptime(args.date, '%Y-%m-%d')
        except ValueError:
            print(f"Invalid date format: {args.date}. Use YYYY-MM-DD.", file=sys.stderr)
            return 1
    else:
        report_date = datetime.now() - timedelta(days=1)

    print(f"Daily FCC Complaint Generator")
    print(f"Reporting on: {report_date.strftime('%Y-%m-%d')}")
    print(f"Threshold: {config.threshold_speed_mbps:.1f} Mbps ({config.threshold_percent}% of {config.advertised_speed_mbps} Mbps)")
    print()

    # Get all tests for the report date
    tests = db.get_speed_tests_for_date(report_date)

    if not tests:
        print(f"No speed tests found for {report_date.strftime('%Y-%m-%d')}")
        return 0

    # Calculate statistics
    failed_tests = [t for t in tests if t.download_mbps < config.threshold_speed_mbps]
    failure_rate = (len(failed_tests) / len(tests)) * 100

    print(f"Found {len(tests)} speed tests")
    print(f"Failed tests: {len(failed_tests)} ({failure_rate:.1f}%)")
    print()

    # Check if we should file a complaint
    if len(failed_tests) == 0 and not args.force:
        print("No failed tests - no complaint needed.")
        return 0

    # Generate complaint text
    complaint_text = generate_daily_complaint_text(config, tests, report_date)

    if args.dry_run:
        print("=== DRY RUN - Complaint would be filed with this text: ===")
        print(complaint_text)
        print("=== END DRY RUN ===")

        # Log dry run - use first test's ID as reference
        complaint = Complaint(
            id=None,
            timestamp=datetime.now(),
            speed_test_id=tests[0].id,
            complaint_text=complaint_text,
            status="daily_dry_run",
        )
        db.save_complaint(complaint)
        return 2

    # Actually file the complaint
    print("Filing FCC complaint...")

    # Create a synthetic SpeedTestResult for the complaint filing that uses average values
    downloads = [t.download_mbps for t in tests]
    uploads = [t.upload_mbps for t in tests]
    pings = [t.ping_ms for t in tests]

    avg_result = SpeedTestResult(
        id=tests[0].id,
        timestamp=report_date,
        download_mbps=mean(downloads),
        upload_mbps=mean(uploads),
        ping_ms=mean(pings),
        server="Multiple (daily aggregate)",
    )

    try:
        # We need to override the complaint text generation, so we'll do it directly
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not args.show_browser)
            context = browser.new_context()
            page = context.new_page()

            try:
                from .fcc_complainer import (
                    _login_to_fcc,
                    _navigate_to_new_complaint,
                    _fill_complaint_form,
                    _submit_complaint,
                )

                _login_to_fcc(page, config)
                _navigate_to_new_complaint(page)

                # Fill form with our custom complaint text
                print("Filling complaint form...")
                from .fcc_complainer import _try_fill_field

                _try_fill_field(page, [
                    'input[name*="provider"]',
                    'input[name*="company"]',
                    'input[name*="carrier"]',
                ], config.isp_name)

                _try_fill_field(page, [
                    'input[name*="account"]',
                ], config.isp_account_number)

                _try_fill_field(page, [
                    'input[name*="phone"]',
                    'input[type="tel"]',
                ], config.phone_number)

                _try_fill_field(page, [
                    'input[name*="email"]:not([readonly])',
                ], config.email)

                _try_fill_field(page, [
                    'input[name*="address"]',
                    'textarea[name*="address"]',
                ], config.service_address)

                _try_fill_field(page, [
                    'textarea[name*="description"]',
                    'textarea[name*="details"]',
                    'textarea[name*="complaint"]',
                    'textarea#request_description',
                    'textarea',
                ], complaint_text)

                _submit_complaint(page)
                print("FCC complaint successfully filed!")

                # Log success
                complaint = Complaint(
                    id=None,
                    timestamp=datetime.now(),
                    speed_test_id=tests[0].id,
                    complaint_text=complaint_text,
                    status="daily_filed",
                )
                db.save_complaint(complaint)
                return 2

            except Exception as e:
                print(f"Failed to file FCC complaint: {e}", file=sys.stderr)

                # Log failure
                complaint = Complaint(
                    id=None,
                    timestamp=datetime.now(),
                    speed_test_id=tests[0].id,
                    complaint_text=complaint_text,
                    status="daily_failed",
                )
                db.save_complaint(complaint)
                return 1

            finally:
                browser.close()

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
