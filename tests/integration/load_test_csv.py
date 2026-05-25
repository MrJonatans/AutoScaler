"""
CSV-driven load test — воспроизводит нагрузку из data.csv (30 дней, 1‑мин интервал)
в ускоренном масштабе времени.

Usage:
    # 1 час датасета = 1 минута реального времени (speed=60)
    python tests/integration/load_test_csv.py --csv data.csv --speed 60

    # 30 дней датасета за 30 минут (speed=1440)
    python tests/integration/load_test_csv.py --csv data.csv --speed 1440

    # Только первые 6 часов датасета, без ускорения
    python tests/integration/load_test_csv.py --csv data.csv --max-hours 6 --speed 1

    # Режим time-sync: подстраивает позицию в CSV под текущее время (день+час+мин)
    # Prometheus получает CPU с реальными таймстемпами, модель видит верный паттерн
    python tests/integration/load_test_csv.py --csv data_scaled.csv --speed 1 --time-sync
"""
import argparse
import asyncio
import csv
import sys
import time
import urllib.request
from datetime import datetime, timedelta


BASE_URL = "http://192.168.31.41:30080"


def _n_for_cpu(cpu_pct: float) -> int:
    """Inverse of main.py duration formula: duration = 0.01 * (n/100)^0.7
    CPU% ≈ duration * 100 = (n/100)^0.7  (at ~1 rps concurrency)
    Inverse: n = 100 * CPU_pct^(1/0.7)
    At 10%: n=~2650 (0.1s), at 30%: n=~12900 (0.3s), at 50%: n=~26500 (0.5s)."""
    cpu_pct = min(100.0, max(0.0, cpu_pct))
    n = int(100 * (cpu_pct ** (1/0.7)))
    if n < 100:
        n = 100
    return n


async def send_request(url: str) -> float:
    """Send one GET request in a thread, return elapsed seconds (0 on error)."""
    start = time.monotonic()
    try:
        await asyncio.to_thread(
            lambda: urllib.request.urlopen(url, timeout=30).read()
        )
    except Exception as e:
        print(f"  request error: {e}", file=sys.stderr)
        return 0.0
    return time.monotonic() - start


def load_csv(path: str) -> list[dict]:
    """Load CSV and return rows sorted by timestamp."""
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    rows.sort(key=lambda r: r["timestamp"])
    return rows


def _parse_timestamp(ts_str: str) -> datetime:
    """Parse CSV timestamp string to datetime."""
    return datetime.strptime(ts_str.strip(), "%Y-%m-%d %H:%M:%S")


def _find_sync_index(rows: list[dict]) -> int:
    """Find the best starting index in CSV matching current wall clock time.
    
    Matches on (day_of_week, hour, minute) to ensure Prometheus sees CPU
    values aligned with real-world time patterns.
    """
    now = datetime.now()
    target_dow = now.weekday()  # 0=Monday
    target_hour = now.hour
    target_min = now.minute

    # Build lookup from parsed timestamps
    best_idx = 0
    best_score = float('inf')

    for i, row in enumerate(rows):
        ts = _parse_timestamp(row["timestamp"])
        dow = ts.weekday()
        hour = ts.hour
        minute = ts.minute

        # Score: exact match = 0, off by N minutes = N
        # Prefer same day-of-week, then same hour, then same minute
        dow_diff = (dow - target_dow) % 7
        if dow_diff > 3:
            dow_diff = 7 - dow_diff  # circular: Sat (5) is 1 away from Sun (6)

        hour_diff = abs(hour - target_hour)
        min_diff = abs(minute - target_min)

        # Weight: DOW matters most, then hour, then minute
        score = dow_diff * 1440 + hour_diff * 60 + min_diff

        if score < best_score:
            best_score = score
            best_idx = i

    matched = rows[best_idx]["timestamp"]
    print(f"  Time-sync: current={now.strftime('%a %H:%M')}, "
          f"matched CSV idx={best_idx} ({matched})")
    return best_idx


def print_status(elapsed_real: float, csv_time: str, cpu: float,
                 ok: int, errors: int, avg_lat: float, active: int):
    total = ok + errors
    print(
        f"\r  real_t={elapsed_real:>5.0f}s  "
        f"csv_time={csv_time}  "
        f"cpu={cpu:>5.1f}%  "
        f"active={active:>2d}  "
        f"ok={ok:<4d}  "
        f"err={errors:<2d}  "
        f"avg_lat={avg_lat:.2f}s  "
        f"total={total:<4d}",
        end="", flush=True,
    )


def get_current_cpu(rows: list[dict], elapsed_sim: float, csv_interval_min: int) -> float:
    """Get CPU usage at a given simulated time offset (in seconds)."""
    idx = int(elapsed_sim / (csv_interval_min * 60))
    if idx >= len(rows):
        return 0.0
    return float(rows[idx]["cpu_usage"])


def get_current_cpu_time_sync(rows: list[dict], start_index: int,
                              elapsed_minutes: int) -> tuple[float, str, int]:
    """Get CPU from CSV in time-sync mode: advance cursor by real minutes, wrap around."""
    idx = (start_index + elapsed_minutes) % len(rows)
    cpu = float(rows[idx]["cpu_usage"])
    ts = rows[idx]["timestamp"]
    return cpu, ts, idx


async def run_load(args):
    rows = load_csv(args.csv)
    if not rows:
        print("ERROR: empty CSV", file=sys.stderr)
        return

    csv_interval_min = 1  # data.csv has 1-min resolution
    csv_total_seconds = len(rows) * csv_interval_min * 60

    # Time-sync mode: find starting point matching current clock
    if args.time_sync:
        start_index = _find_sync_index(rows)
        print(f"  Mode:             TIME-SYNC (wall clock driven)")
        print(f"  Starting CSV idx: {start_index}")
    else:
        start_index = 0
        print(f"  Mode:             SEQUENTIAL (simulated time driven)")

    # Limit max simulated time
    if args.max_hours:
        max_sim_s = args.max_hours * 3600
    else:
        max_sim_s = csv_total_seconds

    # Real-time budget
    real_total_s = max_sim_s / args.speed

    print(f"Starting CSV-driven load test:")
    print(f"  CSV:              {args.csv} ({len(rows)} rows, {csv_interval_min}-min interval)")
    print(f"  Simulated window: {max_sim_s/3600:.1f}h of data")
    print(f"  Speed:            {args.speed}x")
    print(f"  Real duration:    ~{real_total_s:.0f}s ({real_total_s/60:.1f}min)")
    print(f"  Target URL:       {args.url}/load?n=...")
    print()

    latencies = []
    ok = errors = 0
    active_tasks: set = set()

    start_real = time.monotonic()
    deadline_real = start_real + real_total_s
    last_status = 0

    while True:
        now_real = time.monotonic()
        if now_real >= deadline_real:
            break

        # Current real elapsed time
        elapsed_real = now_real - start_real
        elapsed_sim = elapsed_real * args.speed  # scale to simulated time

        # Get CPU% from CSV
        if args.time_sync:
            # In time-sync mode, advance 1 CSV minute per 60 real seconds
            elapsed_min = int(elapsed_real / 60)
            cpu, csv_ts, csv_idx = get_current_cpu_time_sync(
                rows, start_index, elapsed_min
            )
        else:
            cpu = get_current_cpu(rows, elapsed_sim, csv_interval_min)
            if cpu <= 0 and elapsed_sim > csv_total_seconds:
                break  # past end of data
            csv_ts = rows[0]["timestamp"]
            idx = int(elapsed_sim / (csv_interval_min * 60))
            if idx < len(rows):
                csv_ts = rows[idx]["timestamp"]

        if cpu <= 0:
            # Still possible during ramp-up or if CSV has zeros
            pass

        # Apply ramp-up: gradually increase load from 0 to 100% over rampup seconds
        rampup_factor = min(1.0, elapsed_real / args.rampup) if args.rampup > 0 else 1.0
        cpu_effective = cpu * rampup_factor

        # Determine n value (smooth interpolation)
        n = _n_for_cpu(cpu_effective)

        # Scale concurrency smoothly with CPU: 3 at 0%, up to 15 at 100%
        desired_concurrency = max(1, min(15, int(cpu / 15 + 1)))

        # Spawn tasks to maintain desired concurrency
        while len(active_tasks) < desired_concurrency:
            url = f"{args.url}/load?n={n}"
            task = asyncio.create_task(send_request(url))
            active_tasks.add(task)

        # Wait for at least one to finish
        if active_tasks:
            done, active_tasks = await asyncio.wait(
                active_tasks, return_when=asyncio.FIRST_COMPLETED
            )
            for t in done:
                el = t.result()
                if el > 0:
                    ok += 1
                    latencies.append(el)
                else:
                    errors += 1

        # Print status every 5s real time
        if int(elapsed_real) // 5 > last_status // 5:
            avg = sum(latencies[-100:]) / len(latencies[-100:]) if latencies else 0
            print_status(elapsed_real, csv_ts, cpu,
                         ok, errors, avg, len(active_tasks))
        last_status = int(elapsed_real)

        # Short sleep to avoid busy-wait
        await asyncio.sleep(0.05)

    # Collect remaining tasks
    if active_tasks:
        done, _ = await asyncio.wait(active_tasks)
        for t in done:
            el = t.result()
            if el > 0:
                ok += 1
                latencies.append(el)
            else:
                errors += 1

    total = ok + errors
    avg_lat = sum(latencies) / len(latencies) if latencies else 0
    print(f"\n\nLoad test finished:")
    print(f"  Requests:     {total}")
    print(f"  OK:           {ok}")
    print(f"  Errors:       {errors}")
    print(f"  Avg latency:  {avg_lat:.2f}s")
    print()
    print("Check CPU in Prometheus:")
    print(f"  curl -s 'http://192.168.31.41:30909/api/v1/query?query=cpu_usage_percent'")


def main():
    parser = argparse.ArgumentParser(
        description="CSV-driven load test — replays CPU pattern from data.csv"
    )
    parser.add_argument(
        "--csv", default="data.csv",
        help="Path to CSV with timestamp,cpu_usage (default: data.csv)",
    )
    parser.add_argument(
        "--url", default=BASE_URL,
        help=f"Base URL (default {BASE_URL})",
    )
    parser.add_argument(
        "--speed", type=float, default=60,
        help="Time acceleration factor (default 60 = 1h data = 1min real)",
    )
    parser.add_argument(
        "--max-hours", type=float, default=None,
        help="Limit simulated time to this many hours (default: all data)",
    )
    parser.add_argument(
        "--rampup", type=float, default=300,
        help="Ramp-up duration in real seconds (default: 300 = 5 min)",
    )
    parser.add_argument(
        "--time-sync", action="store_true", default=False,
        help="Sync CSV position to current wall clock (day+hour+minute). "
             "CPU values will match real-world time patterns for Prometheus.",
    )
    args = parser.parse_args()

    asyncio.run(run_load(args))


if __name__ == "__main__":
    main()
