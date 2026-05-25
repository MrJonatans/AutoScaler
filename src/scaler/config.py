import os

# Configuration constants for the autoscaling predictor
# Values can be overridden via environment variables

# Prometheus URL for querying metrics
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://192.168.31.41:30909")

# Query for CPU usage metric (use avg() to aggregate across all replicas)
CPU_QUERY = os.getenv("CPU_QUERY", "avg_over_time(cpu_usage_percent[1m])")


# Thresholds for scaling decisions
THRESHOLDS = {
    'scale_up': float(os.getenv("THRESHOLD_SCALE_UP", "30.0")),
    'scale_down': float(os.getenv("THRESHOLD_SCALE_DOWN", "30.0"))
}

# Prediction interval in seconds (1 minutes)
INTERVAL = int(os.getenv("PREDICTION_INTERVAL", "60"))

# Sequence length for ML model input
SEQUENCE_LENGTH = int(os.getenv("SEQUENCE_LENGTH", "60"))

# Prediction horizon in minutes (how far ahead the model forecasts)
# With 1-minute data this means the model predicts CPU usage 1 minute in the future
PREDICTION_HORIZON_MINUTES = int(os.getenv("PREDICTION_HORIZON_MINUTES", "1"))

# Model and data paths
MODEL_PATH = os.getenv("MODEL_PATH", "model.pth")
SCALER_PATH = os.getenv("SCALER_PATH", "scaler.pkl")
DATA_PATH = os.getenv("DATA_PATH", "data.csv")


# K8s API endpoint (if using direct K8s API instead of Prometheus exporter)
K8S_API_URL = os.getenv("K8S_API_URL", "https://kubernetes.default.svc.cluster.local")
