# FCC Complaint Filer - Laptop Client

This script runs on your laptop to file FCC complaints using speed test data from your Pi.

## How It Works

1. Pi runs speed tests throughout the day (via cron)
2. At 9am, your laptop runs this script
3. Script SSHes to Pi to fetch yesterday's test data
4. Opens a browser - you solve the Cloudflare captcha
5. Script logs in and fills the complaint form
6. You review and press Enter to submit

## Setup

### 1. Copy this folder to your laptop

```bash
scp -r dietpi@<pi-ip>:/home/dietpi/ISPFCCComplainer/laptop_client ~/fcc-complainer
cd ~/fcc-complainer
```

### 2. Install dependencies

```bash
pip install playwright playwright-stealth
playwright install chromium
```

### 3. Set up SSH key authentication (so script can SSH without password)

```bash
# On your laptop, if you don't have a key:
ssh-keygen -t ed25519

# Copy key to Pi:
ssh-copy-id dietpi@<pi-ip>
```

### 4. Test the connection

```bash
python file_complaint.py --dry-run
```

### 5. Schedule to run daily at 9am

**macOS/Linux (cron):**
```bash
crontab -e
# Add this line:
0 9 * * * cd ~/fcc-complainer && /usr/bin/python3 file_complaint.py >> ~/fcc-complaint.log 2>&1
```

**macOS (launchd) - better for laptops that sleep:**

Create `~/Library/LaunchAgents/com.fcc.complainer.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.fcc.complainer</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/YOURUSERNAME/fcc-complainer/file_complaint.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/YOURUSERNAME/fcc-complaint.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOURUSERNAME/fcc-complaint.log</string>
</dict>
</plist>
```

Then load it:
```bash
launchctl load ~/Library/LaunchAgents/com.fcc.complainer.plist
```

## Usage

```bash
# Normal run (yesterday's data)
python file_complaint.py

# Specific date
python file_complaint.py --date 2026-01-31

# Preview only (don't file)
python file_complaint.py --dry-run

# Custom Pi connection
python file_complaint.py --pi-host pihole --pi-user pi

# Only file if 5+ failures
python file_complaint.py --min-failures 5
```

## Configuration

Edit the top of `file_complaint.py` to change defaults:

```python
DEFAULT_PI_HOST = "dietpi"  # Your Pi's hostname or IP
DEFAULT_PI_USER = "dietpi"  # SSH username
DEFAULT_PI_PATH = "/home/dietpi/ISPFCCComplainer"
```

## Session Persistence

After solving the Cloudflare captcha once, the session is saved to `~/.fcc_complaint_session/`. Subsequent runs may not need captcha solving (until the session expires).
