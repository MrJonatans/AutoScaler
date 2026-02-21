# Configuration constants for the autoscaling predictor

# Prometheus URL for querying metrics
PROMETHEUS_URL = "http://localhost:9090"

# Query for CPU usage metric
CPU_QUERY = 'cpu_usage_percent'

# Thresholds for scaling decisions
THRESHOLDS = {
    'scale_up': 70.0,    # Scale up if predicted CPU > 70%
    'scale_down': 30.0   # Scale down if predicted CPU < 30%
}

# Prediction interval in seconds (5 minutes)
INTERVAL = 300

# Sequence length for ML model input
SEQUENCE_LENGTH = 60

# Model and data paths
MODEL_PATH = 'model.pth'
DATA_PATH = 'data.csv'

# K8s API endpoint (if using direct K8s API instead of Prometheus exporter)
K8S_API_URL = "https://kubernetes.default.svc.cluster.local"