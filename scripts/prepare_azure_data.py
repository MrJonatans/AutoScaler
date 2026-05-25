import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Dataset params
STRIDE_SECONDS = 300           # 5 min between samples (original)
TARGET_INTERVAL_SECONDS = 60  # 1 min after interpolation
ROWS_PER_DAY = 24 * 60 * 60 // TARGET_INTERVAL_SECONDS  # 1440 rows/day
ROWS_PER_30_DAYS = ROWS_PER_DAY * 30  # 43200 rows

def main():
    # Load raw azure trace
    df = pd.read_csv('azure_trace.csv')
    print(f"Loaded {len(df)} rows: {df.columns.tolist()}")
    print(f"CPU range: {df['cpu_usage'].min():.0f} - {df['cpu_usage'].max():.0f}")
    print(f"Mem range: {df['assigned_mem'].min():.0f} - {df['assigned_mem'].max():.0f}")

    # Index 7020 = 2026-05-19 00:00:00 (Tuesday).
    START_INDEX = 1      # Start index
    END_INDEX = 8641     # End index (exclusive) → 8640 rows = 30 days

    # Take data from START_INDEX to END_INDEX
    azure_slice = df.iloc[START_INDEX:END_INDEX].copy()
    
    # Create 5-min timestamps starting from May 19
    week_start = datetime(2026, 5, 19, 0, 0, 0)
    azure_slice['timestamp'] = pd.date_range(start=week_start, periods=len(azure_slice), freq=f'{STRIDE_SECONDS}s')

    # Interpolate from 5-min to 1-min resolution using linear interpolation
    azure_slice.set_index('timestamp', inplace=True)
    
    # Create 1-min index covering the full 30-day range
    target_index = pd.date_range(start=week_start, periods=ROWS_PER_30_DAYS, freq=f'{TARGET_INTERVAL_SECONDS}s')
    
    # Reindex to 1-min, interpolate linearly, reset index
    interpolated = azure_slice.reindex(
        azure_slice.index.union(target_index)
    ).interpolate(method='linear').reindex(target_index).reset_index()
    
    interpolated.rename(columns={'index': 'timestamp'}, inplace=True)
    
    # Normalize CPU usage to 0-100% using min-max scaling on ORIGINAL (non-interpolated) data
    cpu_min = azure_slice['cpu_usage'].min()
    cpu_max = azure_slice['cpu_usage'].max()
    interpolated['cpu_usage'] = (interpolated['cpu_usage'] - cpu_min) / (cpu_max - cpu_min) * 100
    interpolated['cpu_usage'] = interpolated['cpu_usage'].clip(0, 100)

    month_end = interpolated['timestamp'].max()

    print(f"Start index: {START_INDEX} ({week_start})")
    print(f"End index: {END_INDEX}")
    print(f"Date range: {week_start} - {month_end}")
    print(f"30-day rows: {len(interpolated)} (1-min intervals)")

    # Keep only timestamp and cpu_usage
    interpolated = interpolated[['timestamp', 'cpu_usage']]

    # Save
    interpolated.to_csv('data.csv', index=False)
    print(f"\nSaved {len(interpolated)} rows to data.csv (1-min intervals, 30 days)")
    print(f"Normalized CPU stats:")
    print(f"  Min:  {interpolated['cpu_usage'].min():.1f}%")
    print(f"  Max:  {interpolated['cpu_usage'].max():.1f}%")
    print(f"  Mean: {interpolated['cpu_usage'].mean():.1f}%")
    print(f"  Std:  {interpolated['cpu_usage'].std():.1f}%")
    print(f"\nInterpolation: 5-min → 1-min (linear)")

if __name__ == '__main__':
    main()