#!/usr/bin/env python3
"""
Gateway Metrics Plotter

Plots LoRaWAN gateway performance metrics from CSV data.
Shows CPU, memory, network, and LoRa packet statistics.

Usage:
    python plot_gateway_metrics.py gateway_metrics.csv
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path
import sys

def plot_gateway_metrics(csv_file):
    """
    Read gateway metrics CSV and create comprehensive plots
    
    Args:
        csv_file: Path to gateway_metrics.csv
    """
    
    # Read CSV
    try:
        df = pd.read_csv(csv_file)
    except FileNotFoundError:
        print(f"Error: File not found: {csv_file}")
        sys.exit(1)
    
    # Convert timestamp to datetime
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Create figure with multiple subplots
    fig = plt.figure(figsize=(16, 12))
    fig.suptitle('LoRaWAN Gateway Metrics Analysis', fontsize=16, fontweight='bold')
    
    # ===== 1. CPU Usage =====
    ax1 = plt.subplot(3, 3, 1)
    ax1.plot(df['elapsed_s'], df['cpu_pct'], 'b-', label='CPU Total', linewidth=2)
    ax1.plot(df['elapsed_s'], df['cpu_user'], 'g--', label='User', alpha=0.7)
    ax1.plot(df['elapsed_s'], df['cpu_sys'], 'r--', label='System', alpha=0.7)
    ax1.fill_between(df['elapsed_s'], 0, df['cpu_pct'], alpha=0.2)
    ax1.set_xlabel('Time (seconds)')
    ax1.set_ylabel('CPU (%)')
    ax1.set_title('CPU Usage')
    ax1.legend(fontsize=8)
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim(0, 100)
    
    # ===== 2. Memory Usage =====
    ax2 = plt.subplot(3, 3, 2)
    ax2.plot(df['elapsed_s'], df['mem_used_pct'], 'purple', linewidth=2, marker='o', markersize=3)
    ax2.fill_between(df['elapsed_s'], 0, df['mem_used_pct'], alpha=0.2, color='purple')
    ax2.set_xlabel('Time (seconds)')
    ax2.set_ylabel('Memory Usage (%)')
    ax2.set_title('Memory Utilization')
    ax2.grid(True, alpha=0.3)
    ax2.set_ylim(0, 100)
    
    # ===== 3. Load Average =====
    ax3 = plt.subplot(3, 3, 3)
    ax3.plot(df['elapsed_s'], df['load_1'], 'r-', label='1-min', linewidth=2, marker='.')
    ax3.plot(df['elapsed_s'], df['load_5'], 'orange', label='5-min', linewidth=2, marker='.')
    ax3.plot(df['elapsed_s'], df['load_15'], 'g-', label='15-min', linewidth=2, marker='.')
    ax3.set_xlabel('Time (seconds)')
    ax3.set_ylabel('Load Average')
    ax3.set_title('System Load')
    ax3.legend(fontsize=8)
    ax3.grid(True, alpha=0.3)
    
    # ===== 4. Network RX Delta (packets received) =====
    ax4 = plt.subplot(3, 3, 4)
    ax4.bar(df['elapsed_s'], df['net_rx_delta'], width=0.5, alpha=0.7, color='blue', label='RX')
    ax4.set_xlabel('Time (seconds)')
    ax4.set_ylabel('Bytes/sample')
    ax4.set_title('Network RX Delta')
    ax4.grid(True, alpha=0.3, axis='y')
    
    # ===== 5. Network TX Delta (packets sent) =====
    ax5 = plt.subplot(3, 3, 5)
    ax5.bar(df['elapsed_s'], df['net_tx_delta'], width=0.5, alpha=0.7, color='green', label='TX')
    ax5.set_xlabel('Time (seconds)')
    ax5.set_ylabel('Bytes/sample')
    ax5.set_title('Network TX Delta')
    ax5.grid(True, alpha=0.3, axis='y')
    
    # ===== 6. LoRa RX/TX Counts =====
    ax6 = plt.subplot(3, 3, 6)
    ax6.plot(df['elapsed_s'], df['rx_total'], 'b-', label='RX Total', linewidth=2, marker='o', markersize=4)
    ax6.plot(df['elapsed_s'], df['tx_total'], 'r-', label='TX Total', linewidth=2, marker='s', markersize=4)
    ax6.set_xlabel('Time (seconds)')
    ax6.set_ylabel('Packet Count')
    ax6.set_title('LoRa Packet Counts')
    ax6.legend(fontsize=8)
    ax6.grid(True, alpha=0.3)
    
    # ===== 7. CRC Error Rate =====
    ax7 = plt.subplot(3, 3, 7)
    ax7.plot(df['elapsed_s'], df['crc_error_rate_pct'], 'r-', linewidth=2, marker='x')
    ax7.fill_between(df['elapsed_s'], 0, df['crc_error_rate_pct'], alpha=0.2, color='red')
    ax7.set_xlabel('Time (seconds)')
    ax7.set_ylabel('CRC Error Rate (%)')
    ax7.set_title('LoRa CRC Errors')
    ax7.grid(True, alpha=0.3)
    ax7.set_ylim(0, max(df['crc_error_rate_pct'].max() + 5, 5))
    
    
    """
    # ===== 8. Data Rate Distribution =====
    ax8 = plt.subplot(3, 3, 8)
        # Get latest readings
        latest_idx = len(df) - 1
        dr_data = [
            df.loc[latest_idx, 'rx_dr0'] or 0,
            df.loc[latest_idx, 'rx_dr1'] or 0,
            df.loc[latest_idx, 'rx_dr2'] or 0,
            df.loc[latest_idx, 'rx_dr3'] or 0,
            df.loc[latest_idx, 'rx_dr4'] or 0,
            df.loc[latest_idx, 'rx_dr5'] or 0,
        ]
        colors_dr = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']
        bars = ax8.bar(range(6), dr_data, color=colors_dr, alpha=0.7)
        ax8.set_xlabel('Data Rate (SF7-12)')
        ax8.set_ylabel('Packet Count')
        ax8.set_title('LoRa Data Rate Distribution (Latest)')
        ax8.set_xticks(range(6))
        ax8.set_xticklabels(['DR0\n(SF12)', 'DR1\n(SF11)', 'DR2\n(SF10)', 'DR3\n(SF9)', 'DR4\n(SF8)', 'DR5\n(SF7)'])
        ax8.grid(True, alpha=0.3, axis='y')
        
        # Add value labels on bars
        for bar in bars:
            height = bar.get_height()
            if height > 0:
                ax8.text(bar.get_x() + bar.get_width()/2., height,
                        f'{int(height)}', ha='center', va='bottom', fontsize=8)
        
    """

    # ===== 9. System Load vs CPU =====
    ax9 = plt.subplot(3, 3, 9)
    ax9_2 = ax9.twinx()
    
    line1 = ax9.plot(df['elapsed_s'], df['cpu_pct'], 'b-', linewidth=2, label='CPU %', marker='o', markersize=3)
    line2 = ax9_2.plot(df['elapsed_s'], df['load_1'], 'r-', linewidth=2, label='Load 1-min', marker='s', markersize=3)
    
    ax9.set_xlabel('Time (seconds)')
    ax9.set_ylabel('CPU (%)', color='b')
    ax9_2.set_ylabel('Load Average', color='r')
    ax9.tick_params(axis='y', labelcolor='b')
    ax9_2.tick_params(axis='y', labelcolor='r')
    ax9.set_title('CPU vs System Load')
    ax9.grid(True, alpha=0.3)
    
    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax9.legend(lines, labels, loc='upper left', fontsize=8)
    
    plt.tight_layout()
    
    # Save figure
    output_file = csv_file.replace('.csv', '_plot.png')
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"✓ Plot saved to: {output_file}")
    
    # Print summary statistics
    print("\n" + "="*60)
    print("GATEWAY METRICS SUMMARY")
    print("="*60)
    
    print(f"\n📊 Time Range: {df['elapsed_s'].min():.1f}s - {df['elapsed_s'].max():.1f}s")
    print(f"📊 Gateway ID: {df['gateway_id'].iloc[0]}")
    
    print(f"\n💻 CPU USAGE:")
    print(f"   Average: {df['cpu_pct'].mean():.1f}%")
    print(f"   Peak:    {df['cpu_pct'].max():.1f}%")
    print(f"   Idle:    {df['cpu_pct'].min():.1f}%")
    
    print(f"\n🧠 MEMORY USAGE:")
    print(f"   Average: {df['mem_used_pct'].mean():.1f}%")
    print(f"   Peak:    {df['mem_used_pct'].max():.1f}%")
    print(f"   Total:   {df['mem_total_mb'].iloc[0]:.0f} MB")
    
    print(f"\n📡 LoRa PACKETS:")
    print(f"   Total RX: {df['rx_total'].max():.0f}")
    print(f"   Total TX: {df['tx_total'].max():.0f}")
    if df['rx_total'].max() > 0:
        print(f"   RX Rate: {(df['rx_delta'].sum() / df['elapsed_s'].max()):.2f} pkt/sec")
    
    print(f"\n⚠️  ERROR RATES:")
    print(f"   CRC Errors: {df['rx_crc_error'].max():.0f} total")
    print(f"   CRC Error Rate: {df['crc_error_rate_pct'].max():.2f}%")
    
    print(f"\n🌐 NETWORK I/O:")
    print(f"   Total RX: {df['net_rx_bytes'].max() / (1024**2):.2f} MB")
    print(f"   Total TX: {df['net_tx_bytes'].max() / (1024**2):.2f} MB")
    
    print(f"\n📈 LOAD AVERAGE:")
    print(f"   1-min:  {df['load_1'].mean():.2f}")
    print(f"   5-min:  {df['load_5'].mean():.2f}")
    print(f"   15-min: {df['load_15'].mean():.2f}")
    
    print("\n" + "="*60)
    
    plt.show()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
    else:
        # Default to gateway_metrics.csv in current directory
        csv_file = "gateway_metrics.csv"
        if not Path(csv_file).exists():
            print("Usage: python plot_gateway_metrics.py <path_to_gateway_metrics.csv>")
            print("\nExample:")
            print("  python plot_gateway_metrics.py gateway_metrics.csv")
            sys.exit(1)
    
    plot_gateway_metrics(csv_file)
