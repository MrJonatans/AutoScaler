#!/usr/bin/env python3
"""Collect CPU metrics from Prometheus every N seconds for a given duration.

Usage:
    python scripts/collect_live_data.py --hours 4
    python scripts/collect_live_data.py --hours 4 --output live_data.csv
"""
import csv
import time
import argparse
import json
import urllib.request
import sys
from datetime import datetime


def collect(args):
    out = open(args.output, 'w', newline='')
    writer = csv.writer(out)
    writer.writerow(['timestamp', 'cpu_usage'])
    out.flush()

    start = time.time()
    duration = args.hours * 3600
    interval = args.interval
    last_print = 0

    print(f"Collecting CPU metrics every {interval}s for {args.hours}h → {args.output}")
    print(f"  Prometheus: {args.prometheus}")
    print()

    while True:
        elapsed = time.time() - start
        if elapsed >= duration:
            break

        points = int(elapsed / interval)

        try:
            url = f"{args.prometheus}/api/v1/query?query=avg_over_time(cpu_usage_percent[1m])"
            resp = urllib.request.urlopen(url, timeout=10).read()
            data = json.loads(resp)
            if data['data']['result']:
                ts_str, val = data['data']['result'][0]['value']
                ts_human = datetime.fromtimestamp(int(ts_str)).strftime('%Y-%m-%d %H:%M:%S')
                writer.writerow([ts_human, f"{float(val):.1f}"])
                out.flush()

                if int(elapsed) // 60 > last_print // 60:
                    remaining_m = int((duration - elapsed) // 60)
                    print(f"  [{points:>3d}] {ts_human} CPU={val}%  remaining={remaining_m}m")
                last_print = int(elapsed)
        except Exception as e:
            print(f"  [!] collect error: {e}", file=sys.stderr)

        time.sleep(interval)

    out.close()
    total_points = int(elapsed / interval)
    print(f"\n✅ Done: {total_points} points saved to {args.output}")


if __name__ == '__main__':
    p = argparse.ArgumentParser(description="Collect CPU metrics from Prometheus")
    p.add_argument('--prometheus', default='http://192.168.31.41:30909',
                   help='Prometheus URL (default: http://192.168.31.41:30909)')
    p.add_argument('--output', default='live_data.csv',
                   help='Output CSV file (default: live_data.csv)')
    p.add_argument('--hours', type=float, default=4,
                   help='Collection duration in hours (default: 4)')
    p.add_argument('--interval', type=int, default=60,
                   help='Polling interval in seconds (default: 60)')
    args = p.parse_args()
    collect(args)
