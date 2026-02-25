"""
Debug: Check what CD signals BZ has per interval, especially near Feb 20.
Compare raw CD signals vs breakthrough-filtered (buy_signals).
"""
import sys, os

backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(backend_dir, 'app', 'logic'))
sys.path.insert(0, backend_dir)

import pandas as pd
import numpy as np
from indicators import compute_cd_indicator, compute_cd_break_through
from data_loader import download_stock_data

TICKER = "BZ"

def main():
    print(f"Downloading {TICKER}...")
    data = download_stock_data(TICKER)

    print(f"\n=== BZ Signal Analysis ===")
    for interval in ['1h', '2h', '3h', '4h', '1d']:
        df = data.get(interval, pd.DataFrame())
        if df.empty:
            print(f"[{interval}] No data")
            continue

        cd = compute_cd_indicator(df)
        cd_bool = cd.fillna(False).infer_objects(copy=False).astype(bool)
        
        # Breakthrough
        bt = compute_cd_break_through(df)
        bt_bool = bt.fillna(False).astype(bool)
        bt_recent = bt_bool.rolling(window=10, min_periods=1).max().shift(1).fillna(False).astype(bool)
        buy_signals = (cd_bool & bt_bool) | (cd_bool & bt_recent)
        
        raw_cd_count = cd_bool.sum()
        hq_count = buy_signals.sum()
        
        # Show all signals near Feb 2026
        print(f"\n[{interval}] bars={len(df)}, raw_cd={raw_cd_count}, hq_buy={hq_count}")
        
        recent_cd = df.index[cd_bool]
        recent_cd_near = [d for d in recent_cd if '2026-02' in str(d)]
        
        if recent_cd_near:
            print(f"  CD signals in Feb 2026:")
            for d in recent_cd_near:
                is_bt = bt_bool.get(d, False)
                is_bt_recent = bt_recent.get(d, False)
                is_buy = buy_signals.get(d, False)
                close = df.loc[d, 'Close']
                if isinstance(close, pd.Series):
                    close = close.iloc[0]
                print(f"    {d}  Close={close:.2f}  bt={is_bt}  bt_recent={is_bt_recent}  buy(hq)={is_buy}")
        
        recent_bt = df.index[bt_bool]
        recent_bt_near = [d for d in recent_bt if '2026-02' in str(d)]
        if recent_bt_near:
            print(f"  Breakthrough events in Feb 2026:")
            for d in recent_bt_near:
                close = df.loc[d, 'Close']
                if isinstance(close, pd.Series):
                    close = close.iloc[0]
                print(f"    {d}  Close={close:.2f}")

if __name__ == "__main__":
    main()
