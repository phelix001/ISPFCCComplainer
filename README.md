# ISPFCCComplainer

Automatically test your ISP speed and file FCC complaints when speeds fall below your advertised rate.

## Features

- Runs speed tests on a schedule via cron
- Logs results to SQLite database
- Automatically files FCC complaints when speeds drop below threshold
- Web dashboard to visualize speed test history

## Setup

### 1. Create FCC Account

Register at: https://consumercomplaints.fcc.gov/hc/en-us/signin

### 2. Install Dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium --with-deps
```

### 3. Configure

Copy `.env.example` to `.env` and fill in your details:

```bash
cp .env.example .env
```

Required settings:
- `FCC_USERNAME` / `FCC_PASSWORD` - Your FCC portal credentials
- `ISP_NAME` - Your ISP (e.g., "Verizon Fios")
- `ISP_ACCOUNT_NUMBER` - Your account number
- `SERVICE_ADDRESS` - Your service address
- `PHONE_NUMBER` / `EMAIL` - Contact info for complaints
- `ADVERTISED_SPEED_MBPS` - Your advertised speed (default: 1000)
- `THRESHOLD_PERCENT` - File complaint when below this % (default: 70)

### 4. Test

```bash
source venv/bin/activate
python -m src.main --dry-run
```

### 5. Set Up Cron Job

Run speed tests every 4 hours:

```bash
./setup_cron.sh
```

Or manually add to crontab:
```
0 */4 * * * cd /path/to/ISPFCCComplainer && /path/to/venv/bin/python -m src.main >> cron.log 2>&1
```

### 6. Web Dashboard (Optional)

Install and start the dashboard service:

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

## Exit Codes

- `0` - Speed is OK, no action needed
- `1` - Error occurred
- `2` - Complaint was filed (or would be in dry-run)
