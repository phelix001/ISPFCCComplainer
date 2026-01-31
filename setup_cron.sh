#!/bin/bash
# Setup script for ISPFCCComplainer cron job

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_PATH="${PYTHON_PATH:-python3}"

echo "ISPFCCComplainer Cron Setup"
echo "=========================="
echo ""
echo "This script will help you set up a cron job to run speed tests automatically."
echo ""
echo "Script directory: $SCRIPT_DIR"
echo "Python path: $PYTHON_PATH"
echo ""

# Check if .env exists
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo "ERROR: .env file not found!"
    echo "Please copy .env.example to .env and fill in your configuration:"
    echo "  cp $SCRIPT_DIR/.env.example $SCRIPT_DIR/.env"
    exit 1
fi

# Check if speedtest-cli is installed
if ! command -v speedtest-cli &> /dev/null; then
    echo "WARNING: speedtest-cli not found in PATH"
    echo "Install it with: pip install speedtest-cli"
fi

# Check if playwright is installed and has browsers
if ! $PYTHON_PATH -c "import playwright" &> /dev/null; then
    echo "WARNING: playwright not installed"
    echo "Install it with: pip install playwright && playwright install chromium"
fi

echo ""
echo "Choose how often to run speed tests:"
echo "  1) Every 4 hours (recommended)"
echo "  2) Every 6 hours"
echo "  3) Every 12 hours"
echo "  4) Once daily"
echo "  5) Custom (enter your own cron schedule)"
echo ""
read -p "Enter choice [1-5]: " choice

case $choice in
    1) CRON_SCHEDULE="0 */4 * * *" ;;
    2) CRON_SCHEDULE="0 */6 * * *" ;;
    3) CRON_SCHEDULE="0 */12 * * *" ;;
    4) CRON_SCHEDULE="0 8 * * *" ;;
    5)
        read -p "Enter cron schedule (e.g., '0 */4 * * *'): " CRON_SCHEDULE
        ;;
    *)
        echo "Invalid choice, using default (every 4 hours)"
        CRON_SCHEDULE="0 */4 * * *"
        ;;
esac

# Create the cron command
CRON_CMD="cd $SCRIPT_DIR && $PYTHON_PATH -m src.main >> $SCRIPT_DIR/cron.log 2>&1"

echo ""
echo "Cron job to be added:"
echo "  Schedule: $CRON_SCHEDULE"
echo "  Command: $CRON_CMD"
echo ""

read -p "Add this cron job? [y/N]: " confirm

if [[ "$confirm" =~ ^[Yy]$ ]]; then
    # Add to crontab
    (crontab -l 2>/dev/null | grep -v "ISPFCCComplainer"; echo "# ISPFCCComplainer speed test"; echo "$CRON_SCHEDULE $CRON_CMD") | crontab -
    echo ""
    echo "Cron job added successfully!"
    echo ""
    echo "To view your cron jobs: crontab -l"
    echo "To remove this job: crontab -e (and delete the ISPFCCComplainer lines)"
    echo "Logs will be written to: $SCRIPT_DIR/cron.log"
else
    echo ""
    echo "Cron job not added. You can manually add it with:"
    echo "  crontab -e"
    echo "Then add this line:"
    echo "  $CRON_SCHEDULE $CRON_CMD"
fi

echo ""
echo "To test the script manually, run:"
echo "  cd $SCRIPT_DIR && $PYTHON_PATH -m src.main --dry-run"
