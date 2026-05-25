import pickle
import torch
import torch.nn as nn
import pandas as pd
import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.preprocessing import MinMaxScaler

from torch.utils.data import DataLoader, TensorDataset
from .model import LSTMModel
from .utils import create_sequences, preprocessing, create_time_features, PREDICTION_HORIZON_MINUTES, SEQUENCE_LENGTH

def evaluate_model(model, test_loader, scaler):
    """Evaluate model and return metrics + predictions/actuals in original scale"""
    model.eval()
    predictions_scaled = []
    actuals_scaled = []
    
    with torch.no_grad():
        for X_batch, y_batch in test_loader:
            outputs = model(X_batch)
            predictions_scaled.extend(outputs.numpy().flatten())
            actuals_scaled.extend(y_batch.numpy().flatten())
    
    # Inverse transform to original CPU % scale
    predictions = scaler.inverse_transform(np.array(predictions_scaled).reshape(-1, 1)).flatten()
    actuals = scaler.inverse_transform(np.array(actuals_scaled).reshape(-1, 1)).flatten()
    
    # Calculate metrics
    mae = mean_absolute_error(actuals, predictions)
    rmse = np.sqrt(mean_squared_error(actuals, predictions))
    
    # MAPE — avoid division by zero
    nonzero_mask = actuals > 0.1
    mape = np.mean(np.abs((actuals[nonzero_mask] - predictions[nonzero_mask]) / actuals[nonzero_mask])) * 100
    
    # R² score
    ss_res = np.sum((actuals - predictions) ** 2)
    ss_tot = np.sum((actuals - np.mean(actuals)) ** 2)
    r2 = 1 - (ss_res / (ss_tot + 1e-10))
    
    return {
        'mae': mae,
        'rmse': rmse,
        'mape': mape,
        'r2': r2
    }, predictions, actuals

def plot_evaluation(actuals, predictions, metrics, save_path='model_evaluation.png'):
    """Create evaluation plots"""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # Plot 1: Time series comparison (first 500 samples)
    ax1 = axes[0, 0]
    n_show = min(500, len(actuals))
    ax1.plot(actuals[:n_show], label='Actual CPU', alpha=0.7, linewidth=1)
    ax1.plot(predictions[:n_show], label='Predicted CPU (1 min ahead)', alpha=0.7, linewidth=1)
    ax1.set_xlabel('Time step')
    ax1.set_ylabel('CPU Usage (%)')
    ax1.set_title(f'Actual vs Predicted CPU (first {n_show} test samples)')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Scatter plot
    ax2 = axes[0, 1]
    ax2.scatter(actuals, predictions, alpha=0.3, s=2)
    min_val = min(actuals.min(), predictions.min())
    max_val = max(actuals.max(), predictions.max())
    ax2.plot([min_val, max_val], [min_val, max_val], 'r--', label='Perfect prediction')
    ax2.set_xlabel('Actual CPU (%)')
    ax2.set_ylabel('Predicted CPU (%)')
    ax2.set_title('Prediction vs Actual (scatter)')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # Plot 3: Error distribution
    ax3 = axes[1, 0]
    errors = predictions - actuals
    ax3.hist(errors, bins=50, alpha=0.7, edgecolor='black')
    ax3.axvline(x=0, color='r', linestyle='--', label='Zero error')
    ax3.set_xlabel('Prediction Error (% CPU)')
    ax3.set_ylabel('Frequency')
    ax3.set_title('Error Distribution')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    # Plot 4: Metrics summary
    ax4 = axes[1, 1]
    ax4.axis('off')
    metrics_text = (
        f"Model Evaluation Metrics\n"
        f"{'='*25}\n\n"
        f"MAE : {metrics['mae']:.2f} %CPU\n"
        f"RMSE: {metrics['rmse']:.2f} %CPU\n"
        f"MAPE: {metrics['mape']:.2f}%\n"
        f"R2  : {metrics['r2']:.4f}\n\n"
        f"Settings:\n"
        f"- Sequence: {SEQUENCE_LENGTH} min\n"
        f"- Horizon: {PREDICTION_HORIZON_MINUTES} min\n"
        f"- Test size: {len(actuals)} samples"
    )

    ax4.text(0.1, 0.9, metrics_text, fontsize=13, verticalalignment='top',
             fontfamily='monospace', linespacing=1.5)
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"📈 Evaluation plot saved to {save_path}")

def main():
    # Load data
    print("Loading data...")
    data = pd.read_csv('data_scaled.csv')
    
    # Parse timestamps and create time features
    data['timestamp'] = pd.to_datetime(data['timestamp'])
    time_features = create_time_features(data['timestamp'])
    
    cpu_usage = data['cpu_usage'].to_numpy().astype(np.float64).reshape(-1, 1)
    
    # Combine CPU + time features
    combined_features = np.column_stack([cpu_usage, time_features])

    
    print(f"Data shape: {combined_features.shape}")
    print(f"  CPU + 4 time features = {combined_features.shape[1]} features")
    print(f"  Total samples: {len(combined_features)}")
    
    # Scale all features together
    scaler = MinMaxScaler()
    scaled_data = scaler.fit_transform(combined_features)

    # Create sequences (using only CPU column for target, full features for input)
    X_list, y_list = [], []
    for i in range(len(scaled_data) - SEQUENCE_LENGTH - PREDICTION_HORIZON_MINUTES + 1):
        # Input: all features (CPU + time) for the sequence window
        X_list.append(scaled_data[i:i+SEQUENCE_LENGTH])
        # Target: CPU only at prediction horizon
        y_list.append(scaled_data[i + SEQUENCE_LENGTH + PREDICTION_HORIZON_MINUTES - 1, 0])
    
    X = np.array(X_list)  # (samples, seq_len, n_features)
    y = np.array(y_list).reshape(-1, 1)  # (samples, 1)
    
    print(f"Sequences: X {X.shape}, y {y.shape}")
    print(f"  Each input: {SEQUENCE_LENGTH} time steps × {combined_features.shape[1]} features")
    
    # Train test split (temporal — keep order)
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]
    
    print(f"Train: {len(X_train)} samples, Test: {len(X_test)} samples")

    # DataLoader
    train_dataset = TensorDataset(torch.tensor(X_train, dtype=torch.float32), torch.tensor(y_train, dtype=torch.float32))
    test_dataset = TensorDataset(torch.tensor(X_test, dtype=torch.float32), torch.tensor(y_test, dtype=torch.float32))
    train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)
    test_loader = DataLoader(test_dataset, batch_size=32, shuffle=False)

    # Model (input_size = CPU + 4 time features = 5)
    n_features = combined_features.shape[1]
    model = LSTMModel(input_size=n_features, hidden_size=64, num_layers=2, output_size=1)
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    
    print(f"\nModel: LSTM(input={n_features}, hidden=64, layers=2, output=1)")
    print("Training...")

    # Train
    for epoch in range(30):
        model.train()
        epoch_loss = 0.0
        for X_batch, y_batch in train_loader:
            optimizer.zero_grad()
            outputs = model(X_batch)
            loss = criterion(outputs, y_batch)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
        
        if (epoch + 1) % 5 == 0:
            print(f'Epoch {epoch+1}/30, Loss: {epoch_loss/len(train_loader):.6f}')

    # Evaluate
    print("\n🔍 Evaluating model on test set...")
    
    # We need a special scaler for the CPU-only target (first column)
    cpu_scaler = MinMaxScaler()
    cpu_scaler.fit(cpu_usage)
    
    metrics, predictions, actuals = evaluate_model(model, test_loader, cpu_scaler)
    
    print(f"\n{'='*40}")
    print("📊 MODEL EVALUATION RESULTS")
    print(f"{'='*40}")
    print(f"  MAE : {metrics['mae']:.2f} %CPU  (средняя абсолютная ошибка)")
    print(f"  RMSE: {metrics['rmse']:.2f} %CPU  (среднеквадратичная ошибка)")
    print(f"  MAPE: {metrics['mape']:.2f}%     (средняя % ошибка)")
    print(f"  R²  : {metrics['r2']:.4f}       (коэффициент детерминации)")
    print(f"{'='*40}")
    
    if metrics['r2'] > 0.7:
        print(" Модель показывает хорошие результаты (R² > 0.7)")
    elif metrics['r2'] > 0.5:
        print(" Модель показывает средние результаты (0.5 < R² < 0.7)")
    else:
        print(" Модель показывает слабые результаты (R² < 0.5)")
    
    print(f"\n Пример оценки: при прогнозе CPU на {PREDICTION_HORIZON_MINUTES} минут вперёд")
    print(f"   средняя ошибка составляет ~{metrics['mae']:.1f}% CPU")
    print(f"   что {'приемлемо' if metrics['mae'] < 10 else 'многовато'} для автоподстройки.")
    
    # Plot evaluation
    plot_evaluation(actuals, predictions, metrics)

    # Save model
    torch.save(model.state_dict(), 'model.pth')
    print(f" Model saved to model.pth")
    
    # Save scaler (5 features: CPU + 4 time features)
    with open('scaler.pkl', 'wb') as f:
        pickle.dump(scaler, f)
    print(f" Scaler saved to scaler.pkl")


if __name__ == '__main__':
    main()


