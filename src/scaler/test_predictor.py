import unittest
import numpy as np
import torch
from unittest.mock import patch, MagicMock

from .predictor import PredictorService
from .config import SEQUENCE_LENGTH
from src.ml.utils import preprocessing

class TestPredictorService(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures"""
        self.predictor = PredictorService()

    def test_load_model(self):
        """Test that model loads successfully"""
        self.assertIsNotNone(self.predictor.model)
        if self.predictor.model is not None:
            self.assertFalse(self.predictor.model.training)  # Should be in eval mode

    def test_predict_cpu_usage_with_valid_data(self):
        """Test prediction with valid input sequence"""
        # Create a simple test sequence
        test_sequence = np.sin(np.linspace(0, 4*np.pi, SEQUENCE_LENGTH)) * 20 + 50  # Similar to training data

        prediction = self.predictor.predict_cpu_usage(test_sequence)

        # Should return a float value or None
        self.assertIsNotNone(prediction)
        if prediction is not None:
            self.assertIsInstance(prediction, (float, np.float32, np.float64))
            # Should be in reasonable range (0-100 for CPU %)
            self.assertGreaterEqual(prediction, 0)
            self.assertLessEqual(prediction, 100)

    def test_predict_cpu_usage_with_insufficient_data(self):
        """Test prediction with insufficient data"""
        short_sequence = np.array([50.0, 51.0])  # Too short

        prediction = self.predictor.predict_cpu_usage(short_sequence)

        # Should handle gracefully
        self.assertIsNone(prediction)

    @patch('src.scaler.predictor.requests.get')
    def test_query_prometheus_success(self, mock_get):
        """Test successful Prometheus query"""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'success',
            'data': {
                'result': [{
                    'values': [
                        [1640995200, '45.5'],
                        [1640995260, '46.2'],
                        [1640995320, '47.1']
                    ]
                }]
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = self.predictor.query_prometheus('cpu_usage_percent')

        self.assertEqual(len(result), 3)
        self.assertAlmostEqual(result[0], 45.5)
        self.assertAlmostEqual(result[1], 46.2)
        self.assertAlmostEqual(result[2], 47.1)

    @patch('src.scaler.predictor.requests.get')
    def test_query_prometheus_failure(self, mock_get):
        """Test Prometheus query failure"""
        mock_get.side_effect = Exception("Connection error")

        result = self.predictor.query_prometheus('cpu_usage_percent')

        self.assertEqual(len(result), 0)

    def test_collect_metrics_sequence_insufficient_data(self):
        """Test collecting metrics when insufficient data available"""
        with patch.object(self.predictor, 'query_prometheus', return_value=np.array([50.0, 51.0])):
            result = self.predictor.collect_metrics_sequence()
            self.assertIsNone(result)

    def test_collect_metrics_sequence_sufficient_data(self):
        """Test collecting metrics when sufficient data available"""
        test_data = np.random.rand(SEQUENCE_LENGTH + 10) * 100
        with patch.object(self.predictor, 'query_prometheus', return_value=test_data):
            result = self.predictor.collect_metrics_sequence()
            self.assertIsNotNone(result)
            if result is not None:
                self.assertEqual(len(result), SEQUENCE_LENGTH)
                np.testing.assert_array_equal(result, test_data[-SEQUENCE_LENGTH:])

    def test_update_predicted_metric(self):
        """Test updating the predicted metric"""
        test_prediction = 75.5

        # This should not raise an exception
        self.predictor.update_predicted_metric(test_prediction)

        # Test with None (should not update)
        self.predictor.update_predicted_metric(None)

    def test_preprocessing_scaler(self):
        """Test that preprocessing creates a scaler"""
        test_data = np.array([40.0, 50.0, 60.0, 70.0])

        scaled_data, scaler = preprocessing(test_data)

        self.assertIsNotNone(scaler)
        self.assertEqual(scaled_data.shape, (4, 1))

        # Test inverse transform
        original = scaler.inverse_transform(scaled_data)
        np.testing.assert_array_almost_equal(original.flatten(), test_data)

if __name__ == '__main__':
    unittest.main()