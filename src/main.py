"""Main entry point for ISPFCCComplainer."""

import argparse
import sys
from datetime import datetime, timedelta

from .config import load_config, Config
from .database import Database, SpeedTestResult, Complaint
from .speedtest import run_speed_test
from .fcc_complainer import (
    file_fcc_complaint,
    generate_complaint_text,
    generate_daily_summary_complaint,
)
from .email_notifier import (
    send_complaint_notification,
    send_daily_summary_email,
)


def main() -> int:
    """Main entry point.

    Returns:
        Exit code: 0 for success, 1 for error, 2 for complaint filed.
    """
    parser = argparse.ArgumentParser(
        description="Test ISP speed and file FCC complaints when below threshold"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run speed test but don't actually file complaint",
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
        "--history",
        action="store_true",
        help="Show recent speed test history and exit",
    )
    parser.add_argument(
        "--complaints",
        action="store_true",
        help="Show recent complaints and exit",
    )
    parser.add_argument(
        "--daily-report",
        action="store_true",
        help="File complaint based on previous day's failed tests (for cron)",
    )
    parser.add_argument(
        "--report-date",
        type=str,
        help="Date to report on (YYYY-MM-DD format, default: yesterday)",
    )
    parser.add_argument(
        "--email-only",
        action="store_true",
        help="Only send email notification, don't file FCC complaint",
    )
    parser.add_argument(
        "--no-email",
        action="store_true",
        help="Don't send email notifications",
    )
    parser.add_argument(
        "--test-only",
        action="store_true",
        help="Only run speed test and save to database, don't file any complaints",
    )

    args = parser.parse_args()

    try:
        config = load_config(args.env_file)
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        print("Make sure your .env file is set up correctly.", file=sys.stderr)
        return 1

    db = Database(config.db_path)

    # Handle history/complaints display
    if args.history:
        _show_history(db, config)
        return 0

    if args.complaints:
        _show_complaints(db)
        return 0

    # Daily report mode - analyze previous day's tests
    if args.daily_report:
        return _run_daily_report(
            config,
            db,
            args.dry_run,
            not args.show_browser,
            args.report_date,
            args.email_only,
            args.no_email,
        )

    # Run the main speed test flow
    return _run_speed_test_flow(
        config, db, args.dry_run, not args.show_browser, args.no_email, args.test_only
    )


def _run_speed_test_flow(
    config: Config,
    db: Database,
    dry_run: bool,
    headless: bool,
    no_email: bool = False,
    test_only: bool = False,
) -> int:
    """Run speed test and file complaint if needed.

    Returns:
        0 if speed is OK (or test-only mode), 1 for errors, 2 if complaint was filed.
    """
    print(f"ISPFCCComplainer - Testing speed against {config.advertised_speed_mbps} Mbps threshold")
    print(f"Minimum acceptable speed: {config.threshold_speed_mbps:.1f} Mbps ({config.threshold_percent}%)")
    print()

    # Run speed test
    print("Running speed test...")
    try:
        result = run_speed_test()
    except RuntimeError as e:
        print(f"Speed test failed: {e}", file=sys.stderr)
        return 1

    # Save to database
    test_id = db.save_speed_test(result)
    result.id = test_id

    # Display results
    print(f"\nSpeed Test Results:")
    print(f"  Download: {result.download_mbps:.2f} Mbps")
    print(f"  Upload:   {result.upload_mbps:.2f} Mbps")
    print(f"  Ping:     {result.ping_ms:.1f} ms")
    print(f"  Server:   {result.server}")
    print()

    # Check threshold
    percent_of_advertised = (result.download_mbps / config.advertised_speed_mbps) * 100
    print(f"Speed is {percent_of_advertised:.1f}% of advertised {config.advertised_speed_mbps} Mbps")

    # Test-only mode: just save data and exit
    if test_only:
        if result.download_mbps >= config.threshold_speed_mbps:
            print(f"✓ Speed is above {config.threshold_percent}% threshold")
        else:
            print(f"✗ Speed is BELOW {config.threshold_percent}% threshold (logged for daily report)")
        return 0

    if result.download_mbps >= config.threshold_speed_mbps:
        print(f"✓ Speed is above {config.threshold_percent}% threshold - no action needed")
        return 0

    # Speed is below threshold - file complaint
    print(f"✗ Speed is BELOW {config.threshold_percent}% threshold!")
    print()

    if dry_run:
        print("DRY RUN MODE - Complaint will not be filed")
        complaint_text = generate_complaint_text(config, result)
        print("\n--- Complaint text that would be filed: ---")
        print(complaint_text)
        print("--- End complaint text ---\n")

        # Log dry run
        complaint = Complaint(
            id=None,
            timestamp=datetime.now(),
            speed_test_id=test_id,
            complaint_text=complaint_text,
            status="dry_run",
        )
        db.save_complaint(complaint)
        return 2

    # Actually file the complaint
    print("Filing FCC complaint...")
    try:
        success = file_fcc_complaint(
            config, result, dry_run=False, headless=headless
        )

        complaint_text = generate_complaint_text(config, result)
        complaint = Complaint(
            id=None,
            timestamp=datetime.now(),
            speed_test_id=test_id,
            complaint_text=complaint_text,
            status="filed" if success else "failed",
        )
        db.save_complaint(complaint)

        if success:
            print("✓ FCC complaint filed successfully!")
            # Send email notification
            if not no_email and config.email_enabled:
                try:
                    send_complaint_notification(config, complaint_text, "filed")
                    print("✓ Email notification sent")
                except RuntimeError as email_err:
                    print(f"⚠ Failed to send email notification: {email_err}")
            return 2
        else:
            print("✗ Failed to file FCC complaint", file=sys.stderr)
            return 1

    except RuntimeError as e:
        print(f"✗ Failed to file FCC complaint: {e}", file=sys.stderr)

        # Log the failure
        complaint = Complaint(
            id=None,
            timestamp=datetime.now(),
            speed_test_id=test_id,
            complaint_text=generate_complaint_text(config, result),
            status="failed",
        )
        db.save_complaint(complaint)
        return 1


def _run_daily_report(
    config: Config,
    db: Database,
    dry_run: bool,
    headless: bool,
    report_date_str: str | None,
    email_only: bool,
    no_email: bool,
) -> int:
    """Generate and file a daily summary complaint for previous day's failed tests.

    Returns:
        0 if no action needed, 1 for errors, 2 if complaint was filed.
    """
    # Determine which date to report on
    if report_date_str:
        try:
            report_date = datetime.strptime(report_date_str, "%Y-%m-%d")
        except ValueError:
            print(f"Invalid date format: {report_date_str}. Use YYYY-MM-DD.", file=sys.stderr)
            return 1
    else:
        # Default to yesterday
        report_date = datetime.now() - timedelta(days=1)

    date_str = report_date.strftime("%Y-%m-%d")
    print(f"ISPFCCComplainer - Daily Report for {date_str}")
    print(f"Threshold: {config.threshold_speed_mbps:.1f} Mbps ({config.threshold_percent}% of {config.advertised_speed_mbps} Mbps)")
    print()

    # Get all tests and failed tests for the date
    all_tests = db.get_speed_tests_for_date(report_date)
    failed_tests = db.get_failed_tests_for_date(report_date, config.threshold_speed_mbps)

    if not all_tests:
        print(f"No speed tests recorded for {date_str}")
        return 0

    # Display summary
    downloads = [t.download_mbps for t in all_tests]
    avg_download = sum(downloads) / len(downloads)
    min_download = min(downloads)
    max_download = max(downloads)
    failure_rate = (len(failed_tests) / len(all_tests)) * 100 if all_tests else 0

    print(f"Tests recorded: {len(all_tests)}")
    print(f"Failed tests:   {len(failed_tests)} ({failure_rate:.1f}%)")
    print(f"Average speed:  {avg_download:.2f} Mbps")
    print(f"Min speed:      {min_download:.2f} Mbps")
    print(f"Max speed:      {max_download:.2f} Mbps")
    print()

    if not failed_tests:
        print(f"✓ All tests passed threshold on {date_str} - no complaint needed")
        # Send daily summary email if enabled
        if not no_email and config.email_enabled:
            try:
                send_daily_summary_email(config, report_date, all_tests, failed_tests, False)
                print("✓ Daily summary email sent")
            except RuntimeError as e:
                print(f"⚠ Failed to send daily summary email: {e}")
        return 0

    # Check if complaint was already filed today
    if db.was_complaint_filed_for_date(datetime.now()):
        print(f"⚠ A complaint was already filed today - skipping")
        return 0

    # Generate complaint
    complaint_text = generate_daily_summary_complaint(config, report_date, failed_tests, all_tests)

    if dry_run:
        print("DRY RUN MODE - Complaint will not be filed")
        print("\n--- Complaint text that would be filed: ---")
        print(complaint_text)
        print("--- End complaint text ---\n")

        # Log dry run
        worst_test = min(failed_tests, key=lambda t: t.download_mbps)
        complaint = Complaint(
            id=None,
            timestamp=datetime.now(),
            speed_test_id=worst_test.id,
            complaint_text=complaint_text,
            status="dry_run",
        )
        db.save_complaint(complaint)

        # Send email notification for dry run
        if not no_email and config.email_enabled:
            try:
                send_complaint_notification(config, complaint_text, "dry_run", report_date)
                print("✓ Email notification sent (dry run)")
            except RuntimeError as e:
                print(f"⚠ Failed to send email notification: {e}")

        return 2

    # Email only mode - just send notification, don't file with FCC
    if email_only:
        print("EMAIL ONLY MODE - Not filing with FCC")
        if config.email_enabled:
            try:
                send_complaint_notification(config, complaint_text, "filed", report_date)
                print("✓ Email complaint sent")

                # Log as filed (email)
                worst_test = min(failed_tests, key=lambda t: t.download_mbps)
                complaint = Complaint(
                    id=None,
                    timestamp=datetime.now(),
                    speed_test_id=worst_test.id,
                    complaint_text=complaint_text,
                    status="emailed",
                )
                db.save_complaint(complaint)
                return 2
            except RuntimeError as e:
                print(f"✗ Failed to send email: {e}", file=sys.stderr)
                return 1
        else:
            print("✗ Email not configured - nothing to do in email-only mode", file=sys.stderr)
            return 1

    # File the complaint with FCC
    print("Filing FCC complaint...")
    worst_test = min(failed_tests, key=lambda t: t.download_mbps)

    try:
        success = file_fcc_complaint(
            config, worst_test, dry_run=False, headless=headless
        )

        complaint = Complaint(
            id=None,
            timestamp=datetime.now(),
            speed_test_id=worst_test.id,
            complaint_text=complaint_text,
            status="filed" if success else "failed",
        )
        db.save_complaint(complaint)

        if success:
            print("✓ FCC complaint filed successfully!")
            # Send email notification
            if not no_email and config.email_enabled:
                try:
                    send_complaint_notification(config, complaint_text, "filed", report_date)
                    print("✓ Email notification sent")
                except RuntimeError as email_err:
                    print(f"⚠ Failed to send email notification: {email_err}")
            return 2
        else:
            print("✗ Failed to file FCC complaint", file=sys.stderr)
            return 1

    except RuntimeError as e:
        print(f"✗ Failed to file FCC complaint: {e}", file=sys.stderr)

        # Log the failure
        complaint = Complaint(
            id=None,
            timestamp=datetime.now(),
            speed_test_id=worst_test.id,
            complaint_text=complaint_text,
            status="failed",
        )
        db.save_complaint(complaint)
        return 1


def _show_history(db: Database, config: Config) -> None:
    """Display recent speed test history."""
    tests = db.get_recent_speed_tests(20)

    if not tests:
        print("No speed test history found.")
        return

    print(f"Recent Speed Tests (threshold: {config.threshold_speed_mbps:.1f} Mbps)")
    print("-" * 80)
    print(f"{'Timestamp':<20} {'Download':<12} {'Upload':<12} {'Ping':<10} {'Status':<10}")
    print("-" * 80)

    for test in tests:
        status = "OK" if test.download_mbps >= config.threshold_speed_mbps else "LOW"
        print(
            f"{test.timestamp.strftime('%Y-%m-%d %H:%M'):<20} "
            f"{test.download_mbps:>8.2f} Mbps "
            f"{test.upload_mbps:>8.2f} Mbps "
            f"{test.ping_ms:>6.1f} ms "
            f"{status:<10}"
        )


def _show_complaints(db: Database) -> None:
    """Display recent complaints."""
    complaints = db.get_recent_complaints(20)

    if not complaints:
        print("No complaints filed yet.")
        return

    print("Recent FCC Complaints")
    print("-" * 60)
    print(f"{'Timestamp':<20} {'Speed Test ID':<15} {'Status':<15}")
    print("-" * 60)

    for complaint in complaints:
        print(
            f"{complaint.timestamp.strftime('%Y-%m-%d %H:%M'):<20} "
            f"{complaint.speed_test_id:<15} "
            f"{complaint.status:<15}"
        )


if __name__ == "__main__":
    sys.exit(main())
