import numpy as np
import pandas as pd
from datetime import datetime, timedelta

def main():
    np.random.seed(42)

    # Generate 14 days of data with 1-minute resolution
    periods = 14 * 24 * 60  # 20160 minutes
    start_date = datetime.now() - timedelta(days=14)
    timestamps = pd.date_range(start=start_date, periods=periods, freq='1min')
    t = np.arange(periods)

    # 1. Base CPU level (never drops to zero)
    base_level = 25.0

    # 2. Sine wave for day/night cycle (low ~4:00, peak ~14:00-16:00)
    # Aligned to start time (15:00): offset 540 min = 9h → peak at hour 14 (14:00)
    daily_cycle = 15 * np.sin(2 * np.pi * (t % 1440 - 540) / 1440) + 15
    daily_cycle = np.clip(daily_cycle, 0, 30)

    # 3. Weekly pattern: weekend (days 6-7) has lower load
    day_of_week = (t // 1440) % 7
    weekend_factor = np.where(day_of_week >= 5, 0.6, 1.0)

    # 4. Plateaus: random periods of sustained load
    cpu = base_level + daily_cycle * weekend_factor
    for i in range(0, periods, 60):
        if np.random.random() < 0.15:  # 15% chance for a plateau
            plateau_level = np.random.uniform(10, 25)
            plateau_duration = np.random.randint(60, 240)  # 1-4 hours
            end = min(i + plateau_duration, periods)
            cpu[i:end] += plateau_level

    # 5. Random spikes (5% probability, 85-95% CPU for 5-15 min)
    for i in range(0, periods, 5):
        if np.random.random() < 0.05:
            spike_peak = np.random.uniform(85, 95)
            spike_duration = np.random.randint(1, 3)  # 1-3 intervals of 5 min = 5-15 min
            end = min(i + spike_duration * 5, periods)
            # Smooth spike shape: rising + falling
            for j in range(i, end):
                fraction = (j - i) / (end - i)
                cpu[j] = max(cpu[j], spike_peak * (1 - abs(fraction - 0.5) * 2))

    # 6. Random noise (±3%)
    noise = np.random.normal(0, 3, periods)
    cpu = cpu + noise

    # Clamp to realistic range 10-99%
    cpu = np.clip(cpu, 10, 99)

    data = pd.DataFrame({'timestamp': timestamps, 'cpu_usage': cpu})
    data.to_csv('data.csv', index=False)
    print(f"Generated {len(data)} rows of synthetic CPU data (14 days, 1-min intervals)")
    print(f"  Range: {cpu.min():.1f}% - {cpu.max():.1f}%")
    print(f"  Mean:  {cpu.mean():.1f}%")
    print(f"  Std:   {cpu.std():.1f}%")

if __name__ == '__main__':
    main()