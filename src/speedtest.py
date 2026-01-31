"""Speed testing module using speedtest-cli."""

import subprocess
import json
from datetime import datetime
from .database import SpeedTestResult


def run_speed_test() -> SpeedTestResult:
    """Run a speed test and return the results.

    Uses speedtest-cli in JSON mode for reliable parsing.

    Returns:
        SpeedTestResult with download/upload speeds, ping, and server info.

    Raises:
        RuntimeError: If speedtest-cli fails to run.
    """
    try:
        result = subprocess.run(
            ["speedtest-cli", "--json"],
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout
        )

        if result.returncode != 0:
            raise RuntimeError(f"speedtest-cli failed: {result.stderr}")

        data = json.loads(result.stdout)

        # speedtest-cli returns speeds in bits per second, convert to Mbps
        download_mbps = data["download"] / 1_000_000
        upload_mbps = data["upload"] / 1_000_000
        ping_ms = data["ping"]
        server = f"{data['server']['sponsor']} ({data['server']['name']})"

        return SpeedTestResult(
            id=None,
            timestamp=datetime.now(),
            download_mbps=round(download_mbps, 2),
            upload_mbps=round(upload_mbps, 2),
            ping_ms=round(ping_ms, 2),
            server=server,
        )

    except subprocess.TimeoutExpired:
        raise RuntimeError("Speed test timed out after 2 minutes")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse speedtest-cli output: {e}")
    except KeyError as e:
        raise RuntimeError(f"Unexpected speedtest-cli output format: missing {e}")
