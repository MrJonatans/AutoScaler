# Multi-stage Dockerfile for AutoScaler App
# Build stage: Install dependencies including heavy ones like torch
FROM python:3.11-slim as builder

WORKDIR /app

# Install system dependencies for torch
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Runtime stage: Lightweight image for running the app
FROM python:3.11-slim as runtime

WORKDIR /app

# Install only runtime dependencies
RUN apt-get update && apt-get install -y \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY src/ ./src/

# Expose port
EXPOSE 8000

# Run the app
CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# To adapt for predictor: Change CMD to ["python", "src/scaler/predictor.py"] or similar, depending on how predictor is run.
# If predictor is a script, adjust accordingly.