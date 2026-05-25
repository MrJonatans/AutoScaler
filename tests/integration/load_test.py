"""
Gradual ramp-up load test with burst for AutoScaler.

Usage:
    python tests/integration/load_test.py [options]

Sends concurrent HTTP requests to /load endpoint, gradually increasing
load, with an optional second burst in the middle, then ramping down.
"""
import argparse
import asyncio
import time
import urllib.request
import sys

BASE_URL = "http://192.168.31.41:30080"
N = 5000000  # CPU burn per request (~5s per request)


def get_target_concurrency(elapsed: float, args) -> int:
    """Determine how many concurrent users there should be at time *elapsed*.

    Phases:
      1. Ramp-up:    0 → *concurrency*  over *ramp_up* seconds
      2. Steady:      hold *concurrency*
      3. Burst:       *burst_concurrency* from *burst_at* for *burst_duration*
      4. Steady:      hold *burst_concurrency*
      5. Ramp-down:   *burst_concurrency* → 0 over *ramp_down* seconds
    """
    # Phase 1: ramp-up
    if elapsed < args.ramp_up:
        ratio = elapsed / args.ramp_up
        return max(1, int(args.concurrency * ratio))

    # Phase 2: steady before burst
    if elapsed < args.burst_at:
        return args.concurrency

    # Phase 3: burst (second wave)
    burst_end = args.burst_at + args.burst_duration
    if elapsed < burst_end:
        return args.burst_concurrency

    # Phase 4: steady after burst
    steady_end = args.duration - args.ramp_down
    if elapsed < steady_end:
        return args.burst_concurrency

    # Phase 5: ramp-down
    remaining = args.duration - elapsed
    ratio = remaining / args.ramp_down
    return max(1, int(args.burst_concurrency * ratio))


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


def print_status(elapsed: float, target: int, active: int,
                 ok: int, errors: int, avg_lat: float):
    """Print a one-line status update."""
    total = ok + errors
    print(
        f"\r  t={elapsed:>5.0f}s  "
        f"target={target:>2d}  "
        f"active={active:>2d}  "
        f"ok={ok:<4d}  "
        f"err={errors:<2d}  "
        f"avg_lat={avg_lat:.2f}s  "
        f"total={total:<4d}",
        end="", flush=True,
    )


async def run_load(args):
    """Main async load test loop."""
    url = f"{args.url}/load?n={N}"
    print(f"Starting load test with gradual ramp-up & burst:")
    print(f"  Target URL:       {url}")
    print(f"  Concurrency:       {args.concurrency}")
    print(f"  Ramp-up:          {args.ramp_up}s")
    print(f"  Burst at:         {args.burst_at}s")
    print(f"  Burst concurrency: {args.burst_concurrency}")
    print(f"  Burst duration:    {args.burst_duration}s")
    print(f"  Ramp-down:        {args.ramp_down}s")
    print(f"  Total duration:   {args.duration}s")
    print()

    active_tasks: set = set()
    latencies = []
    ok = errors = 0
    start_time = time.monotonic()
    deadline = start_time + args.duration
    last_status = 0

    while True:
        now = time.monotonic()
        if now >= deadline:
            break

        elapsed = now - start_time
        target = get_target_concurrency(elapsed, args)

        # Spawn tasks to reach target
        while len(active_tasks) < target:
            task = asyncio.create_task(send_request(url))
            active_tasks.add(task)

        # Add done-callback for each new task to collect results
        # (We'll use a separate collection step)

        # Wait for at least one task to finish
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

        # Print status every 5s
        if int(elapsed) // 5 > last_status // 5:
            avg = sum(latencies) / len(latencies) if latencies else 0
            print_status(elapsed, target, len(active_tasks),
                         ok, errors, avg)
        last_status = int(elapsed)

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

    # Summary
    total = ok + errors
    avg_lat = sum(latencies) / len(latencies) if latencies else 0
    print(f"\n\nLoad test finished:")
    print(f"  Requests:     {total}")
    print(f"  OK:           {ok}")
    print(f"  Errors:       {errors}")
    print(f"  Avg latency:  {avg_lat:.2f}s")
    print()
    print("Check CPU in Prometheus:")
    print(f"  curl -s '{args.url.replace(':30080',':30909')}/api/v1/query?query=cpu_usage_percent'")


def main():
    parser = argparse.ArgumentParser(
        description="AutoScaler load test with gradual ramp-up & burst"
    )
    parser.add_argument(
        "--url", default=BASE_URL,
        help=f"Base URL (default {BASE_URL})",
    )
    parser.add_argument(
        "--concurrency", type=int, default=10,
        help="Peak parallel requests during steady phase (default 10)",
    )
    parser.add_argument(
        "--ramp-up", type=int, default=90,
        help="Seconds to gradually increase to --concurrency (default 90)",
    )
    parser.add_argument(
        "--burst-at", type=int, default=180,
        help="Seconds from start when burst begins (default 180)",
    )
    parser.add_argument(
        "--burst-concurrency", type=int, default=15,
        help="Parallel requests during burst (default 15)",
    )
    parser.add_argument(
        "--burst-duration", type=int, default=120,
        help="How long the burst lasts in seconds (default 120)",
    )
    parser.add_argument(
        "--ramp-down", type=int, default=60,
        help="Seconds to gradually decrease load to 0 at end (default 60)",
    )
    parser.add_argument(
        "--duration", type=int, default=420,
        help="Total test duration in seconds (default 420)",
    )
    args = parser.parse_args()

    asyncio.run(run_load(args))


if __name__ == "__main__":
    main()
