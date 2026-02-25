"""
Debug: Compare our EMA vs Futu-style EMA (SMA-seeded) for BZ 3h data.
Furtu EMA typically uses SMA of first N values as seed, while pandas ewm(adjust=False)
uses the first value as seed.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app', 'logic'))

import pandas as pd
import numpy as np
from indicators import compute_cd_indicator, _compute_barslast, _compute_llv, _compute_ref
from data_loader import download_stock_data

TICKER = "BZ"

def futu_ema(series, span):
    """Futu-style EMA: SMA of first `span` values as seed, then standard EMA."""
    alpha = 2.0 / (span + 1)
    result = pd.Series(index=series.index, dtype=float)
    # First value: SMA of first `span` values (or less if not enough data)
    n = min(span, len(series))
    result.iloc[:n-1] = np.nan
    result.iloc[n-1] = series.iloc[:n].mean()
    # Then EMA
    for i in range(n, len(series)):
        result.iloc[i] = alpha * series.iloc[i] + (1 - alpha) * result.iloc[i-1]
    return result

def compute_cd_futu_style(data):
    """Our CD indicator but using Futu-style EMA (SMA-seeded)."""
    close = data['Close']
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    
    fast_ema = futu_ema(close, 12)
    slow_ema = futu_ema(close, 26)
    diff = fast_ema - slow_ema
    dea = futu_ema(diff.dropna(), 9)
    # Reindex dea to match diff
    dea = dea.reindex(diff.index)
    mcd = (diff - dea) * 2
    
    cross_down = (mcd.shift(1) >= 0) & (mcd < 0)
    cross_up = (mcd.shift(1) <= 0) & (mcd > 0)
    
    n1 = _compute_barslast(cross_down.fillna(False), len(data))
    mm1 = _compute_barslast(cross_up.fillna(False), len(data))
    
    n1_safe = n1 + 1
    mm1_safe = mm1 + 1
    
    cc1 = _compute_llv(close, n1_safe)
    cc2 = _compute_ref(cc1, mm1_safe)
    cc3 = _compute_ref(cc2, mm1_safe)
    
    difl1 = _compute_llv(diff, n1_safe)
    difl2 = _compute_ref(difl1, mm1_safe)
    difl3 = _compute_ref(difl2, mm1_safe)
    
    aaa = (cc1 < cc2) & (difl1 > difl2) & (mcd.shift(1) < 0) & (diff < 0)
    bbb = (cc1 < cc3) & (difl1 < difl2) & (difl1 > difl3) & (mcd.shift(1) < 0) & (diff < 0)
    ccc = aaa | bbb
    jjj = ccc.shift(1) & (abs(diff.shift(1)) >= abs(diff) * 1.01)
    dxdx = jjj & ~jjj.shift(1, fill_value=False).fillna(False)
    
    return dxdx.fillna(False).astype(bool)

def main():
    print(f"Downloading {TICKER}...")
    data = download_stock_data(TICKER)
    
    for interval in ['3h', '4h', '1d']:
        df = data.get(interval, pd.DataFrame())
        if df.empty:
            continue
        
        # Our current implementation
        cd_ours = compute_cd_indicator(df).fillna(False).infer_objects(copy=False).astype(bool)
        
        # Futu-style EMA
        cd_futu = compute_cd_futu_style(df)
        
        # Compare Feb signals
        ours_feb = [d for d in df.index[cd_ours] if '2026-02' in str(d)]
        futu_feb = [d for d in df.index[cd_futu] if '2026-02' in str(d)]
        
        print(f"\n[{interval}] bars={len(df)}")
        print(f"  Our CD (Feb): {len(ours_feb)}")
        for d in ours_feb:
            print(f"    {d}")
        print(f"  Futu-EMA CD (Feb): {len(futu_feb)}")
        for d in futu_feb:
            print(f"    {d}")
        
        # Show total signal diff
        common = cd_ours.index.intersection(cd_futu.index)
        diffs = cd_ours.reindex(common) != cd_futu.reindex(common)
        total_diff = diffs.sum()
        print(f"  Total signal differences: {total_diff}")
        
        # Show EMA comparison at a few points
        close = df['Close']
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        our_fast = close.ewm(span=12, adjust=False).mean()
        futu_fast = futu_ema(close, 12)
        
        # Compare at Feb 20 point
        feb20_mask = [d for d in df.index if '2026-02-20' in str(d)]
        if feb20_mask:
            d = feb20_mask[0]
            print(f"  EMA12 at {d}: ours={our_fast[d]:.6f}  futu={futu_fast[d]:.6f}  diff={abs(our_fast[d]-futu_fast[d]):.8f}")

if __name__ == "__main__":
    main()
