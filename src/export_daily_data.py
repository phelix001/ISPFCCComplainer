#!/usr/bin/env python3
"""Export daily speed test data as JSON for remote complaint filing.

Usage:
    python -m src.export_daily_data              # Yesterday's data
    python -m src.export_daily_data --date 2026-01-31  # Specific date

Output is JSON that can be piped to a remote complaint filer.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta

from .config import load_config
from .database import Database


def main() -> int:
    parser = argparse.ArgumentParser(description="Export daily speed test data as JSON")
    parser.add_argument("--date", type=str, help="Date (YYYY-MM-DD), default: yesterday")
    parser.add_argument("--env-file", type=str, help="Path to .env file")
    args = parser.parse_args()

    try:
        config = load_config(args.env_file)
    except ValueError as e:
        print(json.dumps({"error": str(e)}))
        return 1

    db = Database(config.db_path)

    # Determine report date
    if args.date:
        try:
            report_date = datetime.strptime(args.date, '%Y-%m-%d')
        except ValueError:
            print(json.dumps({"error": f"Invalid date format: {args.date}"}))
            return 1
    else:
        report_date = datetime.now() - timedelta(days=1)

    tests = db.get_speed_tests_for_date(report_date)

    if not tests:
        print(json.dumps({
            "error": None,
            "date": report_date.strftime('%Y-%m-%d'),
            "tests": [],
            "config": {
                "advertised_speed_mbps": config.advertised_speed_mbps,
                "threshold_percent": config.threshold_percent,
                "threshold_speed_mbps": config.threshold_speed_mbps,
                "isp_name": config.isp_name,
                "isp_account_number": config.isp_account_number,
                "service_address": config.service_address,
                "phone_number": config.phone_number,
                "email": config.email,
                "first_name": config.first_name,
                "last_name": config.last_name,
            }
        }))
        return 0

    # Export all data needed for complaint
    output = {
        "error": None,
        "date": report_date.strftime('%Y-%m-%d'),
        "tests": [
            {
                "timestamp": t.timestamp.isoformat(),
                "download_mbps": t.download_mbps,
                "upload_mbps": t.upload_mbps,
                "ping_ms": t.ping_ms,
                "server": t.server,
            }
            for t in tests
        ],
        "config": {
            "advertised_speed_mbps": config.advertised_speed_mbps,
            "threshold_percent": config.threshold_percent,
            "threshold_speed_mbps": config.threshold_speed_mbps,
            "isp_name": config.isp_name,
            "isp_account_number": config.isp_account_number,
            "service_address": config.service_address,
            "phone_number": config.phone_number,
            "email": config.email,
                "first_name": config.first_name,
                "last_name": config.last_name,
            "fcc_username": config.fcc_username,
            "fcc_password": config.fcc_password,
        }
    }

    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
