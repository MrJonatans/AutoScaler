import time
import pickle
import requests
import logging
from typing import Optional
from prometheus_client import start_http_server, Gauge
import torch
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from sklearn.preprocessing import MinMaxScaler

from .config import PROMETHEUS_URL, CPU_QUERY, THRESHOLDS, INTERVAL, SEQUENCE_LENGTH, MODEL_PATH, SCALER_PATH, PREDICTION_HORIZON_MINUTES
from src.ml.model import LSTMModel
from src.ml.utils import create_time_features

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prometheus metric for predicted CPU usage
predicted_cpu = Gauge('predicted_cpu', 'Predicted CPU usage percentage')

class PredictorService:
    def __init__(self):
        self.model: Optional[LSTMModel] = None
        self.feature_scaler: Optional[MinMaxScaler] = None
        self.load_model()
        self.load_scaler()

    def load_model(self):
        """Load the trained LSTM model"""
        try:
            self.model = LSTMModel()
            self.model.load_state_dict(torch.load(MODEL_PATH, map_location='cpu'))
            self.model.eval()
            logger.info("Model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise

    def load_scaler(self):
        """Load the fitted MinMaxScaler (5 features: CPU + 4 time features)"""
        try:
            with open(SCALER_PATH, 'rb') as f:
                self.feature_scaler = pickle.load(f)
            logger.info(f"Scaler loaded from {SCALER_PATH}")
        except Exception as e:
            logger.error(f"Failed to load scaler: {e}")
            raise

    def query_prometheus(self, query, start_time=None, end_time=None, step='15s'):
        """Query Prometheus for metrics, returns (cpu_values, timestamps) tuple"""
        params = {
            'query': query,
            'start': start_time or (datetime.now() - timedelta(minutes=15)).timestamp(),
            'end': end_time or datetime.now().timestamp(),
            'step': step
        }

        try:
            response = requests.get(f"{PROMETHEUS_URL}/api/v1/query_range", params=params)
            response.raise_for_status()
            data = response.json()

            if data['status'] == 'success' and data['data']['result']:
                # Extract values from the time series
                values = data['data']['result'][0]['values']
                timestamps, cpu_values = zip(*values)
                return np.array([float(v) for v in cpu_values]), np.array([int(ts) for ts in timestamps])

            return np.array([]), np.array([])

        except Exception as e:
            logger.error(f"Failed to query Prometheus: {e}")
            return np.array([]), np.array([])

    def _prepare_features(self, cpu_data, timestamps=None):
        """Build 5-feature input: CPU + cyclical time features, then scale.
        
        Args:
            cpu_data: numpy array of CPU usage values
            timestamps: optional numpy array of Unix timestamps (same length as cpu_data)
        Returns:
            numpy array of shape (1, seq_len, 5) ready for model input, or None
        """
        if len(cpu_data) < SEQUENCE_LENGTH:
            return None

        # Take last SEQUENCE_LENGTH values
        cpu_seq = cpu_data[-SEQUENCE_LENGTH:]

        # Generate time features from timestamps or fallback
        if timestamps is not None and len(timestamps) >= SEQUENCE_LENGTH:
            ts_seq = timestamps[-SEQUENCE_LENGTH:]
            time_index = pd.to_datetime(ts_seq, unit='s')
        else:
            now = datetime.now()
            time_index = pd.date_range(end=now, periods=SEQUENCE_LENGTH, freq='1min')

        time_feats = create_time_features(time_index)

        # Combine: CPU (seq_len,1) + time features (seq_len,4) → (seq_len, 5)
        combined = np.column_stack([cpu_seq.reshape(-1, 1), time_feats])

        # Scale using the saved full scaler
        scaled = self.feature_scaler.transform(combined)

        # Reshape to (1, seq_len, 5) for LSTM
        return scaled.reshape(1, SEQUENCE_LENGTH, 5)

    def collect_metrics_sequence(self):
        """Collect the last SEQUENCE_LENGTH CPU metrics with timestamps"""
        # Need enough data for SEQUENCE_LENGTH points with 60s step.
        # Request a window slightly larger than SEQUENCE_LENGTH*60 seconds
        # to ensure Prometheus has enough data to return SEQUENCE_LENGTH points.
        window_seconds = SEQUENCE_LENGTH * 60 + 60
        start_time = (datetime.now() - timedelta(seconds=window_seconds)).timestamp()
        cpu_data, ts_data = self.query_prometheus(CPU_QUERY, start_time=start_time, step='60s')

        if len(cpu_data) < SEQUENCE_LENGTH:
            logger.warning(f"Insufficient data: got {len(cpu_data)}, need {SEQUENCE_LENGTH}")
            return None

        return cpu_data[-SEQUENCE_LENGTH:], ts_data[-SEQUENCE_LENGTH:]

    def predict_cpu_usage(self, input_sequence):
        """Run prediction using the ML model with 5-feature input.
        
        Returns predicted CPU % (in original scale) 15 minutes ahead.
        """
        if self.model is None or self.feature_scaler is None:
            logger.error("Model or scaler not loaded")
            return None

        try:
            cpu_data, ts_data = input_sequence

            # Build 5-feature input and scale
            model_input = self._prepare_features(cpu_data, ts_data)
            if model_input is None:
                logger.warning("Could not prepare features")
                return None

            # Predict (model outputs scaled CPU at t+15min)
            with torch.no_grad():
                output = self.model(torch.tensor(model_input, dtype=torch.float32))
                prediction_scaled = output.numpy().flatten()[0]

            # Inverse transform: build a dummy 5-feature row, replace CPU col, inverse scale
            dummy = np.zeros((1, 5))
            dummy[0, 0] = prediction_scaled
            prediction = self.feature_scaler.inverse_transform(dummy)[0, 0]

            return float(prediction)

        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            return None

    def update_predicted_metric(self, prediction):
        """Update the Prometheus metric with predicted value"""
        if prediction is not None:
            predicted_cpu.set(prediction)
            logger.info(f"Updated predicted_cpu metric: {prediction:.1f}%")

            # Check thresholds for scaling decisions
            if prediction > THRESHOLDS['scale_up']:
                logger.info("🔺 Prediction indicates scale up needed")
            elif prediction < THRESHOLDS['scale_down']:
                logger.info("🔻 Prediction indicates scale down possible")

    def run(self):
        """Main prediction loop"""
        logger.info("Starting predictor service")

        while True:
            try:
                # Collect metrics
                sequence = self.collect_metrics_sequence()

                if sequence is not None:
                    # Make prediction
                    prediction = self.predict_cpu_usage(sequence)

                    # Update metric
                    self.update_predicted_metric(prediction)

                # Wait for next interval
                time.sleep(INTERVAL)

            except KeyboardInterrupt:
                logger.info("Stopping predictor service")
                break
            except Exception as e:
                logger.error(f"Error in prediction loop: {e}")
                time.sleep(60)  # Wait a bit before retrying

def main():
    # Start Prometheus metrics server
    start_http_server(8001)
    logger.info("Metrics server started on port 8001")
    logger.info(f"Predictor will forecast CPU usage {PREDICTION_HORIZON_MINUTES} minutes ahead")

    # Start predictor service
    predictor = PredictorService()
    predictor.run()

if __name__ == '__main__':
    main()
