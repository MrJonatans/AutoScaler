import torch
import pandas as pd
import numpy as np
from .model import LSTMModel
from .utils import preprocessing

def main():
    # Load data
    data = pd.read_csv('data.csv')
    cpu_usage = data['cpu_usage'].values

    # Preprocessing
    scaled_data, scaler = preprocessing(cpu_usage)

    # Take last 60 as input sequence
    input_seq = scaled_data[-60:].reshape(1, 60, 1)

    # Load model
    model = LSTMModel()
    model.load_state_dict(torch.load('model.pth'))
    model.eval()

    # Predict
    with torch.no_grad():
        output = model(torch.tensor(input_seq, dtype=torch.float32))
        predictions = output.numpy().flatten()

    # Inverse scale
    predictions = scaler.inverse_transform(predictions.reshape(-1, 1)).flatten()

    print("Predictions:", predictions)

if __name__ == '__main__':
    main()