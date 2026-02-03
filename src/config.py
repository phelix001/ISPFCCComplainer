"""Configuration management for ISPFCCComplainer."""

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv


@dataclass
class Config:
    """Application configuration loaded from environment variables."""

    # Speed test settings
    advertised_speed_mbps: float
    threshold_percent: int

    # FCC credentials
    fcc_username: str
    fcc_password: str

    # ISP and account details
    isp_name: str
    isp_account_number: str

    # Contact information
    service_address: str
    phone_number: str
    email: str
    first_name: str
    last_name: str

    # Database
    db_path: str

    # Email notification settings (optional)
    smtp_server: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_use_tls: bool
    notification_email: str | None  # Where to send notifications

    @property
    def threshold_speed_mbps(self) -> float:
        """Calculate the minimum acceptable speed in Mbps."""
        return self.advertised_speed_mbps * (self.threshold_percent / 100)

    @property
    def email_enabled(self) -> bool:
        """Check if email notifications are configured."""
        return bool(self.smtp_server and self.notification_email)


def load_config(env_path: str | None = None) -> Config:
    """Load configuration from environment variables.

    Args:
        env_path: Optional path to .env file. If None, looks in current directory.

    Returns:
        Config object with all settings.

    Raises:
        ValueError: If required environment variables are missing.
    """
    if env_path:
        load_dotenv(env_path)
    else:
        load_dotenv()

    def get_required(key: str) -> str:
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Missing required environment variable: {key}")
        return value

    return Config(
        advertised_speed_mbps=float(os.getenv("ADVERTISED_SPEED_MBPS", "1000")),
        threshold_percent=int(os.getenv("THRESHOLD_PERCENT", "70")),
        fcc_username=get_required("FCC_USERNAME"),
        fcc_password=get_required("FCC_PASSWORD"),
        isp_name=get_required("ISP_NAME"),
        isp_account_number=get_required("ISP_ACCOUNT_NUMBER"),
        service_address=get_required("SERVICE_ADDRESS"),
        phone_number=get_required("PHONE_NUMBER"),
        email=get_required("EMAIL"),
        first_name=get_required("FIRST_NAME"),
        last_name=get_required("LAST_NAME"),
        db_path=os.getenv("DB_PATH", str(Path.cwd() / "speedtest_history.db")),
        # Optional email notification settings
        smtp_server=os.getenv("SMTP_SERVER"),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_username=os.getenv("SMTP_USERNAME"),
        smtp_password=os.getenv("SMTP_PASSWORD"),
        smtp_use_tls=os.getenv("SMTP_USE_TLS", "true").lower() == "true",
        notification_email=os.getenv("NOTIFICATION_EMAIL"),
    )
