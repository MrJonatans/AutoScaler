import numpy as np
import pandas as pd

def main():
    # Generate synthetic data: sinusoid + noise
    timestamps = pd.date_range(start='2020-01-01', periods=10000, freq='1min')
    t = np.arange(10000)
    cpu_usage = 50 + 20 * np.sin(2 * np.pi * t / 1440) + np.random.normal(0, 5, 10000)
    data = pd.DataFrame({'timestamp': timestamps, 'cpu_usage': cpu_usage})
    data.to_csv('data.csv', index=False)

if __name__ == '__main__':
    main()