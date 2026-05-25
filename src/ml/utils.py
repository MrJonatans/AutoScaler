import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

# Prediction horizon in minutes (how far ahead the model should forecast)
# With 1-min data: PREDICTION_HORIZON = 1 means predict 1 min ahead
PREDICTION_HORIZON_MINUTES = 1

# Sequence length: how many past minutes the model sees
SEQUENCE_LENGTH = 60  # 60 minutes = 1 hour of history

def create_time_features(timestamps):
    """
    Create cyclical time features from timestamps.
    
    Args:
        timestamps: pandas DatetimeIndex or Series of datetime values
    
    Returns:
        np.array of shape (len(timestamps), 4) with:
        - hour_sin, hour_cos (cyclical hour of day)
        - day_sin, day_cos (cyclical day of week)
    """
    if isinstance(timestamps, pd.Series):
        timestamps = pd.DatetimeIndex(timestamps)
    
    # Hour of day (0-23) → cyclical encoding
    hours = timestamps.hour + timestamps.minute / 60.0  # fractional hour
    hour_sin = np.sin(2 * np.pi * hours / 24)
    hour_cos = np.cos(2 * np.pi * hours / 24)
    
    # Day of week (0=Monday, 6=Sunday) → cyclical encoding
    day_of_week = timestamps.dayofweek
    day_sin = np.sin(2 * np.pi * day_of_week / 7)
    day_cos = np.cos(2 * np.pi * day_of_week / 7)
    
    return np.column_stack([hour_sin, hour_cos, day_sin, day_cos])

def create_sequences(data, seq_length=SEQUENCE_LENGTH, prediction_horizon=PREDICTION_HORIZON_MINUTES):
    """
    Create input sequences and targets for single-horizon prediction.
    
    For 15-minute ahead prediction with 1-minute data:
    - Input: last seq_length minutes (default: 60 = 1 hour)
    - Target: CPU usage at minute (current + seq_length + prediction_horizon - 1)
    """
    sequences = []
    targets = []
    for i in range(len(data) - seq_length - prediction_horizon + 1):
        seq = data[i:i+seq_length]
        # Predict the value exactly 'prediction_horizon' steps ahead
        target = data[i + seq_length + prediction_horizon - 1]
        sequences.append(seq)
        targets.append(target)
    return np.array(sequences), np.array(targets).reshape(-1, 1)

def preprocessing(data):
    scaler = MinMaxScaler()
    scaled_data = scaler.fit_transform(data.reshape(-1, 1))
    return scaled_data, scaler
