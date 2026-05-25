import pytest
import torch
import numpy as np
import pandas as pd
from unittest.mock import patch, MagicMock
from src.ml.model import LSTMModel
from src.ml.train import main as train_main
from src.ml.predict import main as predict_main
from src.ml.utils import create_sequences, preprocessing

class TestLSTMModel:
    def test_model_initialization(self):
        model = LSTMModel()
        assert model.hidden_size == 50
        assert model.num_layers == 2
        assert isinstance(model.lstm, torch.nn.LSTM)
        assert isinstance(model.fc, torch.nn.Linear)

    def test_model_forward(self):
        model = LSTMModel()
        x = torch.randn(32, 60, 1)  # batch_size, seq_len, input_size
        output = model(x)
        assert output.shape == (32, 1)  # output_size = 1 (15-minute ahead prediction)

    @patch('pandas.read_csv')
    @patch('torch.save')
    def test_training_with_mock_data(self, mock_save, mock_read_csv):
        # Mock data
        mock_data = pd.DataFrame({'cpu_usage': np.random.rand(200)})
        mock_read_csv.return_value = mock_data

        # Mock torch.save to avoid saving file
        mock_save.return_value = None

        # Run training (should not raise exception)
        try:
            train_main()
        except Exception as e:
            pytest.fail(f"Training failed with exception: {e}")

        # Check that save was called
        mock_save.assert_called_once()

    @patch('pandas.read_csv')
    @patch('torch.load')
    @patch('builtins.print')
    def test_predict_with_mock_data(self, mock_print, mock_load, mock_read_csv):
        # Mock data
        mock_data = pd.DataFrame({'cpu_usage': np.random.rand(100)})
        mock_read_csv.return_value = mock_data

        # Create a mock model to get the state dict keys
        mock_model = LSTMModel()
        mock_state_dict = mock_model.state_dict()
        mock_load.return_value = mock_state_dict

        # Run predict (should not raise exception)
        try:
            predict_main()
        except Exception as e:
            pytest.fail(f"Prediction failed with exception: {e}")

        # Check that print was called
        mock_print.assert_called()

class TestUtils:
    def test_create_sequences(self):
        data = np.arange(100)
        seq_length = 10
        prediction_horizon = 15
        X, y = create_sequences(data, seq_length, prediction_horizon)
        expected_samples = len(data) - seq_length - prediction_horizon + 1
        assert X.shape[0] == y.shape[0]
        assert X.shape[0] == expected_samples
        assert X.shape[1] == seq_length
        assert y.shape[1] == 1  # single value: 15-minute ahead prediction

    def test_preprocessing(self):
        data = np.random.rand(100)
        scaled, scaler = preprocessing(data)
        assert scaled.shape == (100, 1)
        assert scaled.min() >= 0
        assert scaled.max() <= 1
        # Test inverse transform
        original = scaler.inverse_transform(scaled)
        assert np.allclose(original.flatten(), data, atol=1e-5)
