"""Flask web server for speed test dashboard."""

import csv
import io
from datetime import datetime, timedelta
from flask import Flask, render_template_string, jsonify, Response, request

from .config import load_config
from .database import Database

app = Flask(__name__)

# Load config and database
config = load_config()
db = Database(config.db_path)

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Speed Test Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: #1a1a2e;
            color: #eee;
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            flex-wrap: wrap;
            gap: 15px;
        }
        h1 {
            font-size: 1.8rem;
            color: #fff;
        }
        .controls {
            display: flex;
            gap: 15px;
            align-items: center;
        }
        select, button {
            padding: 10px 20px;
            border-radius: 8px;
            border: none;
            font-size: 1rem;
            cursor: pointer;
        }
        select {
            background: #16213e;
            color: #fff;
            border: 1px solid #0f3460;
        }
        button {
            background: #e94560;
            color: #fff;
            transition: background 0.2s;
        }
        button:hover {
            background: #ff6b6b;
        }
        .chart-container {
            background: #16213e;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: #16213e;
            border-radius: 12px;
            padding: 20px;
            text-align: center;
        }
        .stat-card h3 {
            font-size: 0.9rem;
            color: #888;
            margin-bottom: 10px;
        }
        .stat-card .value {
            font-size: 2rem;
            font-weight: bold;
        }
        .stat-card .value.download { color: #4ade80; }
        .stat-card .value.upload { color: #60a5fa; }
        .stat-card .value.ping { color: #fbbf24; }
        .stat-card .unit {
            font-size: 0.9rem;
            color: #888;
        }
        .threshold-line {
            border-top: 2px dashed #e94560;
        }
        .info {
            text-align: center;
            color: #888;
            margin-top: 20px;
            font-size: 0.9rem;
        }
        @media (max-width: 600px) {
            header { flex-direction: column; align-items: stretch; }
            .controls { justify-content: center; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Speed Test Dashboard</h1>
            <div class="controls">
                <select id="daysSelect" onchange="loadData()">
                    <option value="7">Last 7 days</option>
                    <option value="14">Last 14 days</option>
                    <option value="30" selected>Last 30 days</option>
                    <option value="90">Last 90 days</option>
                    <option value="365">Last year</option>
                </select>
                <button onclick="downloadCSV()">Download CSV</button>
            </div>
        </header>

        <div class="stats">
            <div class="stat-card">
                <h3>Latest Download</h3>
                <span class="value download" id="latestDown">--</span>
                <span class="unit">Mbps</span>
            </div>
            <div class="stat-card">
                <h3>Latest Upload</h3>
                <span class="value upload" id="latestUp">--</span>
                <span class="unit">Mbps</span>
            </div>
            <div class="stat-card">
                <h3>Latest Ping</h3>
                <span class="value ping" id="latestPing">--</span>
                <span class="unit">ms</span>
            </div>
            <div class="stat-card">
                <h3>Avg Download</h3>
                <span class="value download" id="avgDown">--</span>
                <span class="unit">Mbps</span>
            </div>
            <div class="stat-card">
                <h3>Avg Upload</h3>
                <span class="value upload" id="avgUp">--</span>
                <span class="unit">Mbps</span>
            </div>
            <div class="stat-card">
                <h3>Tests Run</h3>
                <span class="value" id="testCount" style="color: #c084fc;">--</span>
                <span class="unit">total</span>
            </div>
        </div>

        <div class="chart-container">
            <canvas id="speedChart"></canvas>
        </div>

        <p class="info">
            Advertised speed: {{ advertised_speed }} Mbps |
            Threshold: {{ threshold_percent }}% ({{ threshold_speed }} Mbps) |
            ISP: {{ isp_name }}
        </p>
    </div>

    <script>
        let chart = null;
        let currentData = [];
        const thresholdSpeed = {{ threshold_speed }};

        async function loadData() {
            const days = document.getElementById('daysSelect').value;
            const response = await fetch(`/api/speedtests?days=${days}`);
            const data = await response.json();
            currentData = data.results;
            updateChart(data);
            updateStats(data);
        }

        function updateStats(data) {
            if (data.results.length === 0) {
                document.getElementById('latestDown').textContent = '--';
                document.getElementById('latestUp').textContent = '--';
                document.getElementById('latestPing').textContent = '--';
                document.getElementById('avgDown').textContent = '--';
                document.getElementById('avgUp').textContent = '--';
                document.getElementById('testCount').textContent = '0';
                return;
            }

            const latest = data.results[data.results.length - 1];
            document.getElementById('latestDown').textContent = latest.download_mbps.toFixed(1);
            document.getElementById('latestUp').textContent = latest.upload_mbps.toFixed(1);
            document.getElementById('latestPing').textContent = latest.ping_ms.toFixed(1);

            const avgDown = data.results.reduce((s, r) => s + r.download_mbps, 0) / data.results.length;
            const avgUp = data.results.reduce((s, r) => s + r.upload_mbps, 0) / data.results.length;
            document.getElementById('avgDown').textContent = avgDown.toFixed(1);
            document.getElementById('avgUp').textContent = avgUp.toFixed(1);
            document.getElementById('testCount').textContent = data.results.length;
        }

        function updateChart(data) {
            const ctx = document.getElementById('speedChart').getContext('2d');

            const labels = data.results.map(r => {
                const d = new Date(r.timestamp);
                return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
            });

            const downloadData = data.results.map(r => r.download_mbps);
            const uploadData = data.results.map(r => r.upload_mbps);

            if (chart) {
                chart.destroy();
            }

            chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'Download (Mbps)',
                            data: downloadData,
                            borderColor: '#4ade80',
                            backgroundColor: 'rgba(74, 222, 128, 0.1)',
                            fill: true,
                            tension: 0.3,
                            pointRadius: 4,
                            pointHoverRadius: 6
                        },
                        {
                            label: 'Upload (Mbps)',
                            data: uploadData,
                            borderColor: '#60a5fa',
                            backgroundColor: 'rgba(96, 165, 250, 0.1)',
                            fill: true,
                            tension: 0.3,
                            pointRadius: 4,
                            pointHoverRadius: 6
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    aspectRatio: 2.5,
                    plugins: {
                        legend: {
                            labels: { color: '#fff' }
                        },
                        annotation: {
                            annotations: {
                                thresholdLine: {
                                    type: 'line',
                                    yMin: thresholdSpeed,
                                    yMax: thresholdSpeed,
                                    borderColor: '#e94560',
                                    borderWidth: 2,
                                    borderDash: [5, 5],
                                    label: {
                                        content: 'Threshold',
                                        enabled: true,
                                        position: 'end'
                                    }
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            ticks: { color: '#888', maxTicksLimit: 10 },
                            grid: { color: 'rgba(255,255,255,0.1)' }
                        },
                        y: {
                            ticks: { color: '#888' },
                            grid: { color: 'rgba(255,255,255,0.1)' },
                            beginAtZero: true
                        }
                    }
                }
            });
        }

        function downloadCSV() {
            const days = document.getElementById('daysSelect').value;
            window.location.href = `/api/speedtests/csv?days=${days}`;
        }

        // Load data on page load
        loadData();
    </script>
</body>
</html>
"""


@app.route('/')
@app.route('/speedtest')
def dashboard():
    """Render the speed test dashboard."""
    return render_template_string(
        DASHBOARD_HTML,
        advertised_speed=int(config.advertised_speed_mbps),
        threshold_percent=config.threshold_percent,
        threshold_speed=int(config.threshold_speed_mbps),
        isp_name=config.isp_name
    )


@app.route('/api/speedtests')
def api_speedtests():
    """Get speed test results as JSON."""
    days = request.args.get('days', 30, type=int)

    # Query database for results in the time range
    with db._get_connection() as conn:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        cursor = conn.execute(
            """
            SELECT id, timestamp, download_mbps, upload_mbps, ping_ms, server
            FROM speed_tests
            WHERE timestamp >= ?
            ORDER BY timestamp ASC
            """,
            (cutoff,)
        )
        results = [
            {
                'id': row[0],
                'timestamp': row[1],
                'download_mbps': row[2],
                'upload_mbps': row[3],
                'ping_ms': row[4],
                'server': row[5]
            }
            for row in cursor.fetchall()
        ]

    return jsonify({
        'results': results,
        'threshold_mbps': config.threshold_speed_mbps,
        'advertised_mbps': config.advertised_speed_mbps
    })


@app.route('/api/speedtests/csv')
def api_speedtests_csv():
    """Download speed test results as CSV."""
    days = request.args.get('days', 30, type=int)

    with db._get_connection() as conn:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        cursor = conn.execute(
            """
            SELECT timestamp, download_mbps, upload_mbps, ping_ms, server
            FROM speed_tests
            WHERE timestamp >= ?
            ORDER BY timestamp ASC
            """,
            (cutoff,)
        )
        rows = cursor.fetchall()

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Timestamp', 'Download (Mbps)', 'Upload (Mbps)', 'Ping (ms)', 'Server'])
    writer.writerows(rows)

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=speedtest_results_{days}days.csv'}
    )


def run_server(host='0.0.0.0', port=5000):
    """Run the Flask development server."""
    app.run(host=host, port=port, debug=False)


if __name__ == '__main__':
    run_server()
