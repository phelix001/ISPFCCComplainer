import subprocess
import csv
import re
from datetime import datetime
import os
import logging
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for headless environments
import matplotlib.pyplot as plt
import pandas as pd


def read_and_plot(csv_file_path):
    # Read the data from CSV into a DataFrame
    df = pd.read_csv(csv_file_path)
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])

    # Filter to last 24 hours for readable chart
    cutoff = pd.Timestamp.now() - pd.Timedelta(hours=24)
    df = df[df['Timestamp'] >= cutoff]

    # Convert speeds to numeric, dropping N/A values
    df['Download Speed (Mbit/s)'] = pd.to_numeric(df['Download Speed (Mbit/s)'], errors='coerce')
    df['Upload Speed (Mbit/s)'] = pd.to_numeric(df['Upload Speed (Mbit/s)'], errors='coerce')
    df = df.dropna()

    # Calculate average download and upload speeds
    avg_download = df['Download Speed (Mbit/s)'].mean()
    avg_upload = df['Upload Speed (Mbit/s)'].mean()

    # Plotting
    plt.figure(figsize=(12, 6))
    plt.plot(df['Timestamp'], df['Download Speed (Mbit/s)'], label='Download Speed', color='b', marker='o', markersize=3)
    plt.plot(df['Timestamp'], df['Upload Speed (Mbit/s)'], label='Upload Speed', color='g', marker='o', markersize=3)

    # Adding average lines
    plt.axhline(y=avg_download, color='r', linestyle='-', label=f'Average Download ({avg_download:.2f} Mbit/s)')
    plt.axhline(y=avg_upload, color='orange', linestyle='-', label=f'Average Upload ({avg_upload:.2f} Mbit/s)')

    plt.xlabel('Timestamp')
    plt.ylabel('Speed (Mbit/s)')
    plt.title('Internet Speeds Over Time')
    plt.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig('/var/www/html/speed/speedtest_chart.png', dpi=100)
    plt.close()


def run_speedtest():
    # Run speedtest-cli and capture its output
    result = subprocess.run(['/usr/local/bin/speedtest-cli', '--simple'], stdout=subprocess.PIPE, text=True)
    print("stdout:", result.stdout)
    print("stderr:", result.stderr)
    return result.stdout

def parse_speedtest_output(output):
    # Regular expressions to find ping, download, and upload speeds
    ping = re.search(r'Ping: ([\d.]+) ms', output)
    download_speed = re.search(r'Download: ([\d.]+) Mbit/s', output)
    upload_speed = re.search(r'Upload: ([\d.]+) Mbit/s', output)
    
    # Extract values if matches are found
    ping = ping.group(1) if ping else "N/A"
    download_speed = download_speed.group(1) if download_speed else "N/A"
    upload_speed = upload_speed.group(1) if upload_speed else "N/A"
    
    return ping, download_speed, upload_speed

def write_speeds_to_csv(ping, download_speed, upload_speed, csv_file_path):
    # Get the current date and time
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Check if the CSV file exists and if we need to write headers
    write_headers = not os.path.exists(csv_file_path)
    
    with open(csv_file_path, 'a', newline='') as file:
        writer = csv.writer(file)
        if write_headers:
            writer.writerow(["Timestamp", "Ping (ms)", "Download Speed (Mbit/s)", "Upload Speed (Mbit/s)"])
        writer.writerow([now, ping, download_speed, upload_speed])

def main():
    # Path to the CSV file where the results will be saved
    csv_file_path = "/var/www/html/speed/speedtest_results.csv"
    logging.basicConfig(filename='/root/speedcsv_error.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.debug('Entering main script logic')

    # Run speedtest and capture output
    output = run_speedtest()
    logging.debug(output)
    
    # Parse the speedtest-cli output
    ping, download_speed, upload_speed = parse_speedtest_output(output)
    
    # Write the results to a CSV file
    write_speeds_to_csv(ping, download_speed, upload_speed, csv_file_path)
    
        # Plot the data with average high and low speed lines
    read_and_plot(csv_file_path)
    
    print("Speedtest results saved and plotted.")


if __name__ == "__main__":
    main()
