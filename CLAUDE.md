# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ISPFCCComplainer is a Python tool that runs on a Pi-hole (or any Linux system) to:
1. Test ISP internet speed using speedtest-cli
2. Log results to SQLite database
3. Automatically file FCC complaints via browser automation when speeds fall below threshold

## Commands

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Run speed test (dry run - no complaint filed)
python -m src.main --dry-run

# Run speed test and file complaint if below threshold
python -m src.main

# Show browser during complaint filing (debugging)
python -m src.main --show-browser

# View speed test history
python -m src.main --history

# View filed complaints
python -m src.main --complaints

# Setup cron job
./setup_cron.sh
```

## Configuration

Copy `.env.example` to `.env` and configure:
- `ADVERTISED_SPEED_MBPS` - Your ISP's advertised speed (default: 1000)
- `THRESHOLD_PERCENT` - File complaint when below this % (default: 70)
- `FCC_USERNAME` / `FCC_PASSWORD` - FCC portal credentials
- `ISP_NAME`, `ISP_ACCOUNT_NUMBER` - Your ISP details
- `SERVICE_ADDRESS`, `PHONE_NUMBER`, `EMAIL` - Contact info for complaint

## Architecture

```
src/
├── config.py         # Environment variable loading (python-dotenv)
├── database.py       # SQLite storage for speed_tests and complaints tables
├── speedtest.py      # Wrapper around speedtest-cli JSON output
├── fcc_complainer.py # Playwright browser automation for FCC portal
└── main.py           # CLI entry point, orchestrates the flow
```

**Flow:** `main.py` loads config → runs speed test → saves to DB → checks threshold → files complaint if needed

## Exit Codes

- `0` - Speed is OK, no action needed
- `1` - Error (config, speedtest, or complaint filing failure)
- `2` - Complaint was filed (or would be filed in dry-run)
