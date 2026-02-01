"""Email notification for ISPFCCComplainer."""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from .config import Config
from .database import SpeedTestResult


def send_notification_email(
    config: Config,
    subject: str,
    body: str,
) -> bool:
    """Send an email notification.

    Args:
        config: Application configuration with SMTP settings.
        subject: Email subject line.
        body: Email body text.

    Returns:
        True if email was sent successfully.

    Raises:
        RuntimeError: If email sending fails.
    """
    if not config.email_enabled:
        raise RuntimeError("Email notifications not configured")

    msg = MIMEMultipart()
    msg["From"] = config.smtp_username or config.email
    msg["To"] = config.notification_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    try:
        if config.smtp_use_tls:
            server = smtplib.SMTP(config.smtp_server, config.smtp_port)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(config.smtp_server, config.smtp_port)

        if config.smtp_username and config.smtp_password:
            server.login(config.smtp_username, config.smtp_password)

        server.sendmail(
            config.smtp_username or config.email,
            config.notification_email,
            msg.as_string(),
        )
        server.quit()
        return True

    except Exception as e:
        raise RuntimeError(f"Failed to send email: {e}")


def send_complaint_notification(
    config: Config,
    complaint_text: str,
    status: str,
    date: datetime | None = None,
) -> bool:
    """Send notification about a filed FCC complaint.

    Args:
        config: Application configuration.
        complaint_text: The complaint that was filed.
        status: Status of the complaint (filed, failed, dry_run).
        date: Date the complaint is for (for daily summaries).

    Returns:
        True if notification was sent.
    """
    date_str = date.strftime("%Y-%m-%d") if date else datetime.now().strftime("%Y-%m-%d")

    if status == "filed":
        subject = f"FCC Complaint Filed - {config.isp_name} - {date_str}"
        intro = "An FCC complaint has been automatically filed against your ISP."
    elif status == "dry_run":
        subject = f"FCC Complaint (DRY RUN) - {config.isp_name} - {date_str}"
        intro = "A complaint WOULD have been filed (dry run mode)."
    else:
        subject = f"FCC Complaint FAILED - {config.isp_name} - {date_str}"
        intro = "WARNING: Failed to file FCC complaint. Manual action may be needed."

    body = f"""{intro}

Date: {date_str}
ISP: {config.isp_name}
Advertised Speed: {config.advertised_speed_mbps} Mbps
Threshold: {config.threshold_percent}% ({config.threshold_speed_mbps:.1f} Mbps)

--- COMPLAINT TEXT ---
{complaint_text}
--- END COMPLAINT ---

This is an automated notification from ISPFCCComplainer.
"""

    return send_notification_email(config, subject, body)


def send_daily_summary_email(
    config: Config,
    date: datetime,
    all_tests: list[SpeedTestResult],
    failed_tests: list[SpeedTestResult],
    complaint_filed: bool,
) -> bool:
    """Send a daily summary email of speed tests.

    Args:
        config: Application configuration.
        date: Date being summarized.
        all_tests: All speed tests for the day.
        failed_tests: Tests that failed to meet threshold.
        complaint_filed: Whether a complaint was filed.

    Returns:
        True if email was sent.
    """
    date_str = date.strftime("%Y-%m-%d")

    if not all_tests:
        subject = f"Speed Test Summary - {date_str} - No Tests"
        body = f"""Daily Speed Test Summary for {date_str}

No speed tests were recorded for this date.

This is an automated notification from ISPFCCComplainer.
"""
    else:
        # Calculate stats
        downloads = [t.download_mbps for t in all_tests]
        avg_download = sum(downloads) / len(downloads)
        min_download = min(downloads)
        max_download = max(downloads)

        failure_rate = (len(failed_tests) / len(all_tests)) * 100 if all_tests else 0

        status = "COMPLAINT FILED" if complaint_filed else "OK" if not failed_tests else "FAILURES DETECTED"
        subject = f"Speed Test Summary - {date_str} - {status}"

        body = f"""Daily Speed Test Summary for {date_str}

ISP: {config.isp_name}
Advertised Speed: {config.advertised_speed_mbps} Mbps
Threshold: {config.threshold_percent}% ({config.threshold_speed_mbps:.1f} Mbps)

SUMMARY:
- Total Tests: {len(all_tests)}
- Failed Tests: {len(failed_tests)} ({failure_rate:.1f}%)
- Average Download: {avg_download:.2f} Mbps ({(avg_download/config.advertised_speed_mbps)*100:.1f}% of advertised)
- Min Download: {min_download:.2f} Mbps
- Max Download: {max_download:.2f} Mbps

COMPLAINT STATUS: {"Filed" if complaint_filed else "Not Filed"}

"""
        if failed_tests:
            body += "FAILED TESTS:\n"
            for test in failed_tests:
                pct = (test.download_mbps / config.advertised_speed_mbps) * 100
                body += f"  - {test.timestamp.strftime('%H:%M:%S')}: {test.download_mbps:.2f} Mbps ({pct:.1f}%)\n"
            body += "\n"

        body += """This is an automated notification from ISPFCCComplainer.
"""

    return send_notification_email(config, subject, body)
