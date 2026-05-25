import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

def main():
    # Load data
    data_path = Path(__file__).parent.parent / 'data.csv'
    if not data_path.exists():
        print("Error: data.csv not found. Run scripts/generate_data.py first.")
        return

    data = pd.read_csv(data_path)
    data['timestamp'] = pd.to_datetime(data['timestamp'])
    
    print(f"Loaded {len(data)} rows")
    print(f"Time range: {data['timestamp'].min()} to {data['timestamp'].max()}")
    print(f"CPU stats: min={data['cpu_usage'].min():.1f}%, "
          f"max={data['cpu_usage'].max():.1f}%, "
          f"mean={data['cpu_usage'].mean():.1f}%, "
          f"std={data['cpu_usage'].std():.1f}%")

    # Create figure with 2 panels
    fig = plt.figure(figsize=(16, 10))
    
    # 1. Full 7-day view
    ax1 = plt.subplot(2, 1, 1)
    ax1.plot(data['timestamp'], data['cpu_usage'], color='#2196F3', linewidth=0.6, alpha=0.8)
    ax1.set_title('CPU Usage - 7 Days (Mon-Sun, Azure V2, 300s intervals)', fontsize=14, fontweight='bold')
    ax1.set_ylabel('CPU %')
    ax1.set_ylim(0, 100)
    ax1.grid(True, alpha=0.3)
    ax1.axhline(y=70, color='orange', linestyle='--', alpha=0.5, label='Scale-up threshold (70%)')
    ax1.axhline(y=90, color='red', linestyle='--', alpha=0.5, label='Critical (90%)')
    ax1.legend(fontsize=9)
    
    # Vertical lines and labels at 00:00 of each day
    t0 = data['timestamp'].min().floor('D')
    for d in range(8):
        midnight = t0 + pd.Timedelta(days=d)
        if data['timestamp'].min() <= midnight <= data['timestamp'].max():
            ax1.axvline(x=midnight, color='gray', linestyle='--', linewidth=0.5, alpha=0.4)
            day_name = midnight.strftime('%a %d/%m')
            ax1.text(midnight, 96, day_name, ha='center', fontsize=8, color='gray',
                    bbox=dict(boxstyle='round,pad=0.2', facecolor='white', edgecolor='none', alpha=0.7))

    # 2. One typical day (pick Wednesday = day 3 from start + midday)
    start_ts = data['timestamp'].min()
    day_offset = (3 - start_ts.weekday()) % 7  # Wednesday
    day_start = start_ts.floor('D') + pd.Timedelta(days=day_offset)
    day_end = day_start + pd.Timedelta(days=1)
    day_mask = (data['timestamp'] >= day_start) & (data['timestamp'] < day_end)
    day_data = data[day_mask]

    # Fallback if Wednesday doesn't have enough data
    if len(day_data) < 10:
        # Pick the first full day with the most data
        for d in range(7):
            candidate = start_ts.floor('D') + pd.Timedelta(days=d)
            cmask = (data['timestamp'] >= candidate) & (data['timestamp'] < candidate + pd.Timedelta(days=1))
            if cmask.sum() > 200:
                day_start = candidate
                day_end = day_start + pd.Timedelta(days=1)
                day_data = data[cmask]
                break
    
    ax2 = plt.subplot(2, 1, 2)
    ax2.plot(day_data['timestamp'], day_data['cpu_usage'], color='#FF9800', linewidth=1.5, marker='o', markersize=4)
    ax2.set_title(f'CPU Usage - {day_start.strftime("%A %d/%m")} (300s intervals)', fontsize=14, fontweight='bold')
    ax2.set_ylabel('CPU %')
    ax2.set_xlabel('Time')
    ax2.set_ylim(0, 100)
    ax2.grid(True, alpha=0.3)
    
    # Mark each 5-minute data point
    for _, row in day_data.iterrows():
        ax2.axvline(x=row['timestamp'], color='gray', linestyle=':', linewidth=0.3, alpha=0.2)
    
    # Annotate interesting points
    peak_idx = day_data['cpu_usage'].idxmax()
    valley_idx = day_data['cpu_usage'].idxmin()
    ax2.annotate(f'Peak: {day_data.loc[peak_idx, "cpu_usage"]:.0f}%',
                xy=(day_data.loc[peak_idx, 'timestamp'], day_data.loc[peak_idx, 'cpu_usage']),
                xytext=(15, 20), textcoords='offset points',
                arrowprops=dict(arrowstyle='->', color='red'), color='red', fontweight='bold')
    ax2.annotate(f'Min: {day_data.loc[valley_idx, "cpu_usage"]:.0f}%',
                xy=(day_data.loc[valley_idx, 'timestamp'], day_data.loc[valley_idx, 'cpu_usage']),
                xytext=(15, -20), textcoords='offset points',
                arrowprops=dict(arrowstyle='->', color='blue'), color='blue', fontweight='bold')

    plt.tight_layout()
    
    # Save plot
    output_path = Path(__file__).parent.parent / 'data_visualization.png'
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\nPlot saved to: {output_path}")
    
    plt.show()
    print("Close the plot window to exit.")

if __name__ == '__main__':
    main()