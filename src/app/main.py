from fastapi import FastAPI
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
import psutil
import time
import math

from .metrics import cpu_usage, requests_total

app = FastAPI(title="AutoScaler Load Simulator", version="1.0.0")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

@app.get("/load")
async def simulate_load(n: int = 1000):
    """Simulate CPU load by calculating factorial of n"""
    start_time = time.time()

    # Increment requests counter
    requests_total.inc()

    # Simulate CPU load
    result = math.factorial(n)

    # Update CPU usage metric
    cpu_percent = psutil.cpu_percent(interval=1)
    cpu_usage.set(cpu_percent)

    end_time = time.time()
    duration = end_time - start_time

    return {
        "result": str(result)[:100] + "..." if len(str(result)) > 100 else str(result),  # Truncate for large results
        "computation_time": duration,
        "cpu_usage": cpu_percent
    }

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest(), {"Content-Type": CONTENT_TYPE_LATEST}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)