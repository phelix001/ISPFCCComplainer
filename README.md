# ISPFCCComplainer

Automatically test your ISP speed and file FCC complaints when speeds fall below your advertised rate.

## Features

- Runs speed tests on a schedule via cron
- Logs results to SQLite database
- Automatically files FCC complaints when speeds drop below threshold
- Web dashboard to visualize speed test history

## Architecture

This project has two parts that can run on the same machine or be split across two:

- **Speed testing** runs on a cron schedule, measuring your download/upload speeds and logging results to a database. This can run on a headless device (e.g., a Raspberry Pi) since it doesn't need a display.
- **FCC complaint filing** opens a browser to submit complaints to the FCC portal. Because the FCC site uses a captcha, this works best on a machine with a display so the captcha can be solved. If your testing machine has a display, both can run on the same device.

### Single machine setup

Everything runs on one machine. Use this if your device has a display (desktop, laptop, etc.).

### Split setup (headless tester + local filer)

Your headless device (Pi, server, etc.) runs speed tests on a cron. Your local machine SSHs into it to pull the test data, then opens a browser to file the complaint.

## Setup

### 1. Create FCC Account

Register at: https://consumercomplaints.fcc.gov/hc/en-us/signin

### 2. Speed Test Machine (Pi / headless device)

Clone the repo and install dependencies:

```bash
git clone https://github.com/phelix001/ISPFCCComplainer.git
cd ISPFCCComplainer
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your details:

```bash
cp .env.example .env
```

Required `.env` settings:
- `ADVERTISED_SPEED_MBPS` - Your advertised speed (default: 1000)
- `THRESHOLD_PERCENT` - Complaint threshold as % of advertised (default: 70)
- `FCC_USERNAME` / `FCC_PASSWORD` - Your FCC portal credentials
- `ISP_NAME` - Your ISP (e.g., "Verizon Fios")
- `ISP_ACCOUNT_NUMBER` - Your account number
- `SERVICE_ADDRESS` - Your service address
- `PHONE_NUMBER` / `EMAIL` - Contact info for complaints
- `FIRST_NAME` / `LAST_NAME` - Your name for the complaint form

Test that speed testing works:

```bash
source venv/bin/activate
python -m src.main --dry-run
```

Set up a cron job to test speed every 30 minutes. Use `--dry-run` so this machine only records results without trying to file complaints:

```bash
crontab -e
```
```
*/30 * * * * cd /path/to/ISPFCCComplainer && /path/to/venv/bin/python -m src.main --dry-run >> cron.log 2>&1
```

If this machine has a display and you want it to also file complaints, omit `--dry-run`:
```
*/30 * * * * cd /path/to/ISPFCCComplainer && /path/to/venv/bin/python -m src.main >> cron.log 2>&1
```

### 3. Complaint Filing Machine (local, only needed for split setup)

If your speed test machine is headless, set up a separate machine to file complaints.

Install dependencies:

```bash
pip install playwright playwright-stealth
playwright install chromium
```

Copy `file_complaint.py` to your local machine. Edit the defaults at the top of the file to match your setup:

```python
DEFAULT_PI_HOST = "your-pi-hostname"  # SSH hostname for your Pi
DEFAULT_PI_USER = "your-pi-user"      # SSH username
DEFAULT_PI_PATH = "/path/to/ISPFCCComplainer"  # Path on Pi
```

Make sure you can SSH to your Pi without a password prompt (set up SSH keys).

Test it:

```bash
python file_complaint.py --dry-run
```

Schedule it with cron to run daily (e.g., 9 AM):

```
0 9 * * * cd /path/to/fcc-complainer && /path/to/python file_complaint.py >> complaint.log 2>&1
```

### 4. Web Dashboard (Optional)

Install and start the dashboard service on the speed test machine:

```bash
sudo cp speedtest-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable speedtest-dashboard
sudo systemctl start speedtest-dashboard
```

Access at: `http://your-ip:5000/speedtest`

Features:
- Graph of download/upload speeds over time
- Dropdown to select lookback period (7/14/30/90/365 days)
- CSV export of speed test data

## Commands

On the speed test machine:

```bash
# Run speed test (dry run - no complaint filed)
python -m src.main --dry-run

# Run speed test and file complaint if below threshold
python -m src.main

# Show browser during complaint filing (for debugging)
python -m src.main --show-browser

# View speed test history
python -m src.main --history

# View filed complaints
python -m src.main --complaints
```

On the complaint filing machine (split setup):

```bash
# Preview complaint without filing
python file_complaint.py --dry-run

# File complaint using Pi data
python file_complaint.py

# Specify a different Pi host
python file_complaint.py --pi-host mypi --pi-user pi
```

## Exit Codes

- `0` - Speed is OK, no action needed
- `1` - Error occurred
- `2` - Complaint was filed (or would be in dry-run)
