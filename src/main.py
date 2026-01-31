"""Main entry point for ISPFCCComplainer."""

import argparse
import sys
from datetime import datetime

from .config import load_config, Config
from .database import Database, SpeedTestResult, Complaint
from .speedtest import run_speed_test
from .fcc_complainer import file_fcc_complaint, generate_complaint_text


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

    # Run the main speed test flow
    return _run_speed_test_flow(config, db, args.dry_run, not args.show_browser)


def _run_speed_test_flow(
    config: Config, db: Database, dry_run: bool, headless: bool
) -> int:
    """Run speed test and file complaint if needed.

    Returns:
        0 if speed is OK, 1 for errors, 2 if complaint was filed.
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
