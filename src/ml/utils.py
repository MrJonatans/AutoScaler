import numpy as np
from sklearn.preprocessing import MinMaxScaler

def create_sequences(data, seq_length):
    sequences = []
    targets = []
    for i in range(len(data) - seq_length - 10 + 1):
        seq = data[i:i+seq_length]
        target = data[i+seq_length:i+seq_length+10]
        sequences.append(seq)
        targets.append(target)
    return np.array(sequences), np.array(targets)

def preprocessing(data):
    scaler = MinMaxScaler()
    scaled_data = scaler.fit_transform(data.reshape(-1, 1))
    return scaled_data, scaler