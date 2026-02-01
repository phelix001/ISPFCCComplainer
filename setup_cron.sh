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
echo "What would you like to set up?"
echo "  1) Speed tests only (run periodically, no automatic complaints)"
echo "  2) Speed tests + daily complaint report (recommended)"
echo "  3) Daily complaint report only (assumes tests already running)"
echo ""
read -p "Enter choice [1-3]: " setup_choice

case $setup_choice in
    1) SETUP_TYPE="tests_only" ;;
    2) SETUP_TYPE="tests_and_report" ;;
    3) SETUP_TYPE="report_only" ;;
    *)
        echo "Invalid choice, using tests + daily report"
        SETUP_TYPE="tests_and_report"
        ;;
esac

if [[ "$SETUP_TYPE" == "tests_only" || "$SETUP_TYPE" == "tests_and_report" ]]; then
    echo ""
    echo "Choose how often to run speed tests:"
    echo "  1) Every 4 hours (recommended - 6 tests/day)"
    echo "  2) Every 6 hours (4 tests/day)"
    echo "  3) Every 12 hours (2 tests/day)"
    echo "  4) Once daily"
    echo "  5) Custom (enter your own cron schedule)"
    echo ""
    read -p "Enter choice [1-5]: " test_choice

    case $test_choice in
        1) TEST_SCHEDULE="0 */4 * * *" ;;
        2) TEST_SCHEDULE="0 */6 * * *" ;;
        3) TEST_SCHEDULE="0 */12 * * *" ;;
        4) TEST_SCHEDULE="0 8 * * *" ;;
        5)
            read -p "Enter cron schedule (e.g., '0 */4 * * *'): " TEST_SCHEDULE
            ;;
        *)
            echo "Invalid choice, using default (every 4 hours)"
            TEST_SCHEDULE="0 */4 * * *"
            ;;
    esac
fi

if [[ "$SETUP_TYPE" == "tests_and_report" || "$SETUP_TYPE" == "report_only" ]]; then
    echo ""
    echo "When should the daily complaint report run?"
    echo "  1) 6:00 AM (recommended - summarizes previous day)"
    echo "  2) 8:00 AM"
    echo "  3) 12:00 PM"
    echo "  4) Custom time"
    echo ""
    read -p "Enter choice [1-4]: " report_choice

    case $report_choice in
        1) REPORT_SCHEDULE="0 6 * * *" ;;
        2) REPORT_SCHEDULE="0 8 * * *" ;;
        3) REPORT_SCHEDULE="0 12 * * *" ;;
        4)
            read -p "Enter hour (0-23): " report_hour
            REPORT_SCHEDULE="0 $report_hour * * *"
            ;;
        *)
            echo "Invalid choice, using 6:00 AM"
            REPORT_SCHEDULE="0 6 * * *"
            ;;
    esac

    echo ""
    echo "How should complaints be filed?"
    echo "  1) FCC portal (files actual complaint)"
    echo "  2) Email only (just sends you notification)"
    echo "  3) Dry run (logs only, no filing)"
    echo ""
    read -p "Enter choice [1-3]: " complaint_choice

    case $complaint_choice in
        1) COMPLAINT_MODE="" ;;
        2) COMPLAINT_MODE="--email-only" ;;
        3) COMPLAINT_MODE="--dry-run" ;;
        *)
            echo "Invalid choice, using FCC portal"
            COMPLAINT_MODE=""
            ;;
    esac
fi

# Create the cron commands
TEST_CMD="cd $SCRIPT_DIR && $PYTHON_PATH -m src.main --no-email >> $SCRIPT_DIR/cron.log 2>&1"
REPORT_CMD="cd $SCRIPT_DIR && $PYTHON_PATH -m src.main --daily-report $COMPLAINT_MODE >> $SCRIPT_DIR/cron.log 2>&1"

echo ""
echo "Cron jobs to be added:"
echo ""

if [[ "$SETUP_TYPE" == "tests_only" || "$SETUP_TYPE" == "tests_and_report" ]]; then
    echo "  Speed Test:"
    echo "    Schedule: $TEST_SCHEDULE"
    echo "    Command: $TEST_CMD"
    echo ""
fi

if [[ "$SETUP_TYPE" == "tests_and_report" || "$SETUP_TYPE" == "report_only" ]]; then
    echo "  Daily Report:"
    echo "    Schedule: $REPORT_SCHEDULE"
    echo "    Command: $REPORT_CMD"
    echo ""
fi

read -p "Add these cron jobs? [y/N]: " confirm

if [[ "$confirm" =~ ^[Yy]$ ]]; then
    # Build the new crontab entries
    CRON_ENTRIES=""

    if [[ "$SETUP_TYPE" == "tests_only" || "$SETUP_TYPE" == "tests_and_report" ]]; then
        CRON_ENTRIES="# ISPFCCComplainer speed test\n$TEST_SCHEDULE $TEST_CMD"
    fi

    if [[ "$SETUP_TYPE" == "tests_and_report" || "$SETUP_TYPE" == "report_only" ]]; then
        if [[ -n "$CRON_ENTRIES" ]]; then
            CRON_ENTRIES="$CRON_ENTRIES\n"
        fi
        CRON_ENTRIES="${CRON_ENTRIES}# ISPFCCComplainer daily report\n$REPORT_SCHEDULE $REPORT_CMD"
    fi

    # Add to crontab (remove old ISPFCCComplainer entries first)
    (crontab -l 2>/dev/null | grep -v "ISPFCCComplainer" | grep -v "src.main"; echo -e "$CRON_ENTRIES") | crontab -
    echo ""
    echo "Cron jobs added successfully!"
    echo ""
    echo "To view your cron jobs: crontab -l"
    echo "To remove these jobs: crontab -e (and delete the ISPFCCComplainer lines)"
    echo "Logs will be written to: $SCRIPT_DIR/cron.log"
else
    echo ""
    echo "Cron jobs not added. You can manually add them with:"
    echo "  crontab -e"
    echo ""
    if [[ "$SETUP_TYPE" == "tests_only" || "$SETUP_TYPE" == "tests_and_report" ]]; then
        echo "Speed test line:"
        echo "  $TEST_SCHEDULE $TEST_CMD"
    fi
    if [[ "$SETUP_TYPE" == "tests_and_report" || "$SETUP_TYPE" == "report_only" ]]; then
        echo "Daily report line:"
        echo "  $REPORT_SCHEDULE $REPORT_CMD"
    fi
fi

echo ""
echo "To test the script manually:"
echo "  Speed test:   cd $SCRIPT_DIR && $PYTHON_PATH -m src.main --dry-run"
echo "  Daily report: cd $SCRIPT_DIR && $PYTHON_PATH -m src.main --daily-report --dry-run"
