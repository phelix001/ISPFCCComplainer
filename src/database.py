"""SQLite database for storing speed test history and complaints."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class SpeedTestResult:
    """A single speed test result."""

    id: Optional[int]
    timestamp: datetime
    download_mbps: float
    upload_mbps: float
    ping_ms: float
    server: str

    @classmethod
    def from_row(cls, row: tuple) -> "SpeedTestResult":
        return cls(
            id=row[0],
            timestamp=datetime.fromisoformat(row[1]),
            download_mbps=row[2],
            upload_mbps=row[3],
            ping_ms=row[4],
            server=row[5],
        )


@dataclass
class Complaint:
    """A filed FCC complaint record."""

    id: Optional[int]
    timestamp: datetime
    speed_test_id: int
    complaint_text: str
    status: str  # 'filed', 'failed', 'dry_run'

    @classmethod
    def from_row(cls, row: tuple) -> "Complaint":
        return cls(
            id=row[0],
            timestamp=datetime.fromisoformat(row[1]),
            speed_test_id=row[2],
            complaint_text=row[3],
            status=row[4],
        )


class Database:
    """SQLite database manager for speed tests and complaints."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_tables()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _ensure_tables(self) -> None:
        """Create tables if they don't exist."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS speed_tests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    download_mbps REAL NOT NULL,
                    upload_mbps REAL NOT NULL,
                    ping_ms REAL NOT NULL,
                    server TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS complaints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    speed_test_id INTEGER NOT NULL,
                    complaint_text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    FOREIGN KEY (speed_test_id) REFERENCES speed_tests(id)
                )
            """)
            conn.commit()

    def save_speed_test(self, result: SpeedTestResult) -> int:
        """Save a speed test result and return its ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO speed_tests (timestamp, download_mbps, upload_mbps, ping_ms, server)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    result.timestamp.isoformat(),
                    result.download_mbps,
                    result.upload_mbps,
                    result.ping_ms,
                    result.server,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def save_complaint(self, complaint: Complaint) -> int:
        """Save a complaint record and return its ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO complaints (timestamp, speed_test_id, complaint_text, status)
                VALUES (?, ?, ?, ?)
                """,
                (
                    complaint.timestamp.isoformat(),
                    complaint.speed_test_id,
                    complaint.complaint_text,
                    complaint.status,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def get_recent_speed_tests(self, limit: int = 10) -> list[SpeedTestResult]:
        """Get the most recent speed test results."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, timestamp, download_mbps, upload_mbps, ping_ms, server
                FROM speed_tests
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [SpeedTestResult.from_row(row) for row in cursor.fetchall()]

    def get_recent_complaints(self, limit: int = 10) -> list[Complaint]:
        """Get the most recent complaints."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, timestamp, speed_test_id, complaint_text, status
                FROM complaints
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [Complaint.from_row(row) for row in cursor.fetchall()]

    def get_speed_test_by_id(self, test_id: int) -> Optional[SpeedTestResult]:
        """Get a specific speed test by ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, timestamp, download_mbps, upload_mbps, ping_ms, server
                FROM speed_tests
                WHERE id = ?
                """,
                (test_id,),
            )
            row = cursor.fetchone()
            return SpeedTestResult.from_row(row) if row else None

    def get_speed_tests_for_date(self, date: datetime) -> list[SpeedTestResult]:
        """Get all speed tests for a specific date."""
        date_str = date.strftime('%Y-%m-%d')
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, timestamp, download_mbps, upload_mbps, ping_ms, server
                FROM speed_tests
                WHERE date(timestamp) = ?
                ORDER BY timestamp ASC
                """,
                (date_str,),
            )
            return [SpeedTestResult.from_row(row) for row in cursor.fetchall()]

    def get_daily_complaint_for_date(self, date: datetime) -> Optional[Complaint]:
        """Check if a daily complaint was already filed for a specific date."""
        date_str = date.strftime('%Y-%m-%d')
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, timestamp, speed_test_id, complaint_text, status
                FROM complaints
                WHERE date(timestamp) = ? AND status IN ('filed', 'daily_filed')
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (date_str,),
            )
            row = cursor.fetchone()
            return Complaint.from_row(row) if row else None
