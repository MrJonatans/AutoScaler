import asyncio
import threading
import time
import math
from fastapi import FastAPI, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
import psutil

from .metrics import cpu_usage, requests_total


app = FastAPI(title="AutoScaler Load Simulator", version="1.0.0")

_process_cpu = psutil.Process()


async def _work(duration: float):
    """CPU‑intensive work — runs in thread pool, doesn't block event loop."""
    def _burn():
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            _ = math.factorial(500)
    await asyncio.to_thread(_burn)


def _monitor_loop():
    """Background: measure process CPU every 2 seconds and push to Prometheus."""
    _process_cpu.cpu_percent(interval=0)
    time.sleep(0.5)
    _process_cpu.cpu_percent(interval=0)
    while True:
        cpu = _process_cpu.cpu_percent(interval=1)
        cpu_usage.set(cpu)


threading.Thread(target=_monitor_loop, daemon=True).start()


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/load")
async def load(n: int = 1000):
    """Synchronous CPU burn proportional to n (runs in thread pool)."""
    requests_total.inc()

    # Smooth log-linear interpolation: n=100 → 0.01s, n=5_000_000 → 10s
    # duration = 0.01 * (n / 100) ** 0.7  (sub-linear so high n doesn't explode)
    import math
    n_clamped = max(100, min(5_000_000, n))
    ratio = n_clamped / 100
    duration = 0.01 * (ratio ** 0.7)

    start = time.time()
    await _work(duration)
    elapsed = time.time() - start

    return {"duration_s": round(elapsed, 2)}



@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
