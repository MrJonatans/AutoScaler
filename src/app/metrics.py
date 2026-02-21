from prometheus_client import Gauge, Counter

# Define Prometheus metrics
cpu_usage = Gauge('cpu_usage_percent', 'Current CPU usage percentage')
requests_total = Counter('requests_total', 'Total number of requests to /load endpoint')