import time
import requests
import logging
from typing import Optional
from prometheus_client import start_http_server, Gauge
import torch
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from sklearn.preprocessing import MinMaxScaler

from .config import PROMETHEUS_URL, CPU_QUERY, THRESHOLDS, INTERVAL, SEQUENCE_LENGTH, MODEL_PATH
from src.ml.model import LSTMModel
from src.ml.utils import preprocessing

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prometheus metric for predicted CPU usage
predicted_cpu = Gauge('predicted_cpu', 'Predicted CPU usage percentage')

class PredictorService:
    def __init__(self):
        self.model: Optional[LSTMModel] = None
        self.scaler: Optional[MinMaxScaler] = None
        self.load_model()

    def load_model(self):
        """Load the trained LSTM model"""
        try:
            self.model = LSTMModel()
            self.model.load_state_dict(torch.load(MODEL_PATH))
            self.model.eval()
            logger.info("Model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise

    def query_prometheus(self, query, start_time=None, end_time=None, step='15s'):
        """Query Prometheus for metrics"""
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
                return np.array([float(v) for v in cpu_values])

            return np.array([])

        except Exception as e:
            logger.error(f"Failed to query Prometheus: {e}")
            return np.array([])

    def collect_metrics_sequence(self):
        """Collect the last SEQUENCE_LENGTH CPU metrics"""
        # Query for recent CPU usage data
        cpu_data = self.query_prometheus(CPU_QUERY)

        if len(cpu_data) < SEQUENCE_LENGTH:
            logger.warning(f"Insufficient data: got {len(cpu_data)}, need {SEQUENCE_LENGTH}")
            return None

        # Take the last SEQUENCE_LENGTH values
        return cpu_data[-SEQUENCE_LENGTH:]

    def predict_cpu_usage(self, input_sequence):
        """Run prediction using the ML model"""
        if self.model is None:
            logger.error("Model not loaded")
            return None

        try:
            # Preprocessing
            scaled_data, self.scaler = preprocessing(input_sequence)

            # Reshape for model input
            input_seq = scaled_data.reshape(1, SEQUENCE_LENGTH, 1)

            # Predict
            with torch.no_grad():
                output = self.model(torch.tensor(input_seq, dtype=torch.float32))
                predictions = output.numpy().flatten()

            # Inverse scale
            predictions = self.scaler.inverse_transform(predictions.reshape(-1, 1)).flatten()

            # Return the first prediction (next time step)
            return predictions[0] if len(predictions) > 0 else None

        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            return None

    def update_predicted_metric(self, prediction):
        """Update the Prometheus metric with predicted value"""
        if prediction is not None:
            predicted_cpu.set(prediction)
            logger.info(f"Updated predicted_cpu metric: {prediction}")

            # Check thresholds for scaling decisions
            if prediction > THRESHOLDS['scale_up']:
                logger.info("Prediction indicates scale up needed")
            elif prediction < THRESHOLDS['scale_down']:
                logger.info("Prediction indicates scale down possible")

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

    # Start predictor service
    predictor = PredictorService()
    predictor.run()

if __name__ == '__main__':
    main()