"""
Debug: Compare BZ CD signals computed with 1-year vs 2-year data for 3h interval.
This tests whether the data length difference between ticker_signals (365 days)
and process_ticker_1234 (2 years) causes signal differences.
"""
import sys, os

backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(backend_dir, 'app', 'logic'))
sys.path.insert(0, backend_dir)

import pandas as pd
import numpy as np
from indicators import compute_cd_indicator, compute_cd_break_through
from data_loader import download_stock_data
from datetime import timedelta

TICKER = "BZ"

def main():
    print(f"Downloading {TICKER}...")
    data = download_stock_data(TICKER)

    for interval in ['3h', '4h', '1d']:
        df_full = data.get(interval, pd.DataFrame())
        if df_full.empty:
            print(f"[{interval}] No data")
            continue
        
        # Simulate ticker_signals: 365-day cutoff
        now = pd.Timestamp.utcnow()
        if df_full.index.tz is not None:
            now = now.tz_convert(df_full.index.tz)
        cutoff_1y = now - timedelta(days=365)
        df_1y = df_full[df_full.index >= cutoff_1y].copy()
        
        print(f"\n{'='*70}")
        print(f"[{interval}] Full data: {len(df_full)} bars ({df_full.index[0]} to {df_full.index[-1]})")
        print(f"[{interval}] 1y cutoff: {len(df_1y)} bars ({df_1y.index[0]} to {df_1y.index[-1]})")
        
        # Compute CD signals with full data (like process_ticker_1234)
        cd_full = compute_cd_indicator(df_full).fillna(False).infer_objects(copy=False).astype(bool)
        
        # Compute CD signals with 1y data (like ticker_signals)
        cd_1y = compute_cd_indicator(df_1y).fillna(False).infer_objects(copy=False).astype(bool)
        
        # Compare signals in Feb 2026
        full_feb = [d for d in df_full.index[cd_full] if '2026-02' in str(d)]
        y1_feb = [d for d in df_1y.index[cd_1y] if '2026-02' in str(d)]
        
        print(f"\n  CD signals in Feb 2026 (2yr data): {len(full_feb)}")
        for d in full_feb:
            print(f"    {d}")
        
        print(f"  CD signals in Feb 2026 (1yr data): {len(y1_feb)}")
        for d in y1_feb:
            print(f"    {d}")
        
        # Check if there are differences
        full_set = set(str(d) for d in full_feb)
        y1_set = set(str(d) for d in y1_feb)
        
        added = y1_set - full_set
        removed = full_set - y1_set
        
        if added:
            print(f"  ⚠️ ADDED in 1yr (not in 2yr): {added}")
        if removed:
            print(f"  ⚠️ REMOVED in 1yr (was in 2yr): {removed}")
        if not added and not removed:
            print(f"  ✅ No differences")

if __name__ == "__main__":
    main()
