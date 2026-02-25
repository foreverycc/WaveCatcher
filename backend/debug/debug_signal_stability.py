"""
Debug script: Compare KWEB signals computed from data ending Feb 20 vs Feb 23.
Identifies exactly where and why signals change.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app', 'logic'))

import pandas as pd
import numpy as np
import yfinance as yf
from indicators import compute_cd_indicator, compute_cd_break_through, compute_mc_indicator, compute_mc_break_through
from data_loader import transform_1h_data

TICKER = "KWEB"
DATE_A = "2026-02-20"
DATE_B = "2026-02-23"

def download_and_prepare(ticker):
    """Download fresh data for ticker."""
    stock = yf.Ticker(ticker)
    data = {}
    data['1h'] = stock.history(interval='60m', period='2y')
    data['1d'] = stock.history(interval='1d', period='2y')
    if not data['1h'].empty:
        for interval in ['2h', '3h', '4h']:
            data[interval] = transform_1h_data(data['1h'], interval)
    return data

def truncate(data, end_date):
    """Truncate all intervals to end_date."""
    end_ts = pd.Timestamp(end_date)
    truncated = {}
    for interval, df in data.items():
        if df.empty:
            truncated[interval] = df
            continue
        if df.index.tz is not None:
            end_tz = end_ts.tz_localize('UTC').tz_convert(df.index.tz)
        else:
            end_tz = end_ts
        truncated[interval] = df[df.index.date <= end_tz.date()].copy()
    return truncated

def compute_signals(data_dict, interval):
    """Compute CD indicator, breakthrough, and buy_signals for an interval."""
    df = data_dict.get(interval, pd.DataFrame())
    if df.empty:
        return None
    cd = compute_cd_indicator(df)
    bt = compute_cd_break_through(df)
    cd_bool = cd.fillna(False).infer_objects(copy=False).astype(bool)
    bt_bool = bt.fillna(False).astype(bool)
    bt_recent = bt_bool.rolling(window=10, min_periods=1).max().shift(1).fillna(False).astype(bool)
    buy_signals = (cd_bool & bt_bool) | (cd_bool & bt_recent)
    return {
        'df': df,
        'cd': cd_bool,
        'bt': bt_bool,
        'bt_recent': bt_recent,
        'buy_signals': buy_signals,
    }

def compare_around_date(sig_a, sig_b, focus_date, interval, window=5):
    """Compare signals around a focus date between two runs."""
    if sig_a is None or sig_b is None:
        print(f"  [{interval}] No data for one of the runs")
        return

    # Find bars around the focus date
    df_a = sig_a['df']
    df_b = sig_b['df']
    
    focus_ts = pd.Timestamp(focus_date)
    
    # Get dates near focus_date in data A
    dates_a = df_a.index
    if dates_a.tz is not None:
        focus_ts_tz = focus_ts.tz_localize('UTC').tz_convert(dates_a.tz)
    else:
        focus_ts_tz = focus_ts
    
    # Find indices around the focus date
    from datetime import timedelta
    focus_d = focus_ts_tz.date() if hasattr(focus_ts_tz, 'date') else focus_ts_tz
    start_d = focus_d - timedelta(days=window)
    end_d = focus_d + timedelta(days=window)
    mask_a = (dates_a.date >= start_d) & (dates_a.date <= end_d)
    
    focus_indices_a = dates_a[mask_a]
    
    if len(focus_indices_a) == 0:
        print(f"  [{interval}] No data around {focus_date}")
        return
    
    print(f"\n{'='*80}")
    print(f"  [{interval}] Comparing around {focus_date} (±{window} days)")
    print(f"  Data A ends: {dates_a[-1]}  ({len(dates_a)} bars)")
    print(f"  Data B ends: {df_b.index[-1]}  ({len(df_b.index)} bars)")
    print(f"  Data A starts: {dates_a[0]}")
    print(f"  Data B starts: {df_b.index[0]}")
    print(f"{'='*80}")
    
    # Check if data starts differ
    if dates_a[0] != df_b.index[0]:
        print(f"  ⚠️  DATA START DIFFERS: A={dates_a[0]} vs B={df_b.index[0]}")
    
    header = f"  {'Date':>25s}  {'Close':>8s}  {'CD_A':>5s} {'CD_B':>5s} {'BT_A':>5s} {'BT_B':>5s} {'BUY_A':>5s} {'BUY_B':>5s}  {'Δ':>3s}"
    print(header)
    print("  " + "-" * len(header))
    
    changes_found = False
    for ts in focus_indices_a:
        cd_a = sig_a['cd'].get(ts, None)
        bt_a = sig_a['bt'].get(ts, None)
        buy_a = sig_a['buy_signals'].get(ts, None)
        
        # Find matching timestamp in B
        cd_b = sig_b['cd'].get(ts, None) if ts in sig_b['cd'].index else None
        bt_b = sig_b['bt'].get(ts, None) if ts in sig_b['bt'].index else None
        buy_b = sig_b['buy_signals'].get(ts, None) if ts in sig_b['buy_signals'].index else None
        
        close_val = df_a.loc[ts, 'Close']
        if isinstance(close_val, pd.Series):
            close_val = close_val.iloc[0]
        
        # Mark differences
        diff = ""
        if cd_a != cd_b:
            diff += "CD"
        if bt_a != bt_b:
            diff += "BT"
        if buy_a != buy_b:
            diff += "BUY"
        
        marker = " ◀◀◀" if diff else ""
        
        if diff:
            changes_found = True
        
        # Only print rows with signals or differences
        if cd_a or cd_b or bt_a or bt_b or buy_a or buy_b or diff:
            print(f"  {str(ts):>25s}  {close_val:8.2f}  {str(cd_a):>5s} {str(cd_b):>5s} {str(bt_a):>5s} {str(bt_b):>5s} {str(buy_a):>5s} {str(buy_b):>5s}  {diff:>3s}{marker}")
    
    if not changes_found:
        print(f"  ✅ No differences found in [{interval}] around {focus_date}")

def count_signals(data_dict, label):
    """Count total signals per interval."""
    print(f"\n{'='*60}")
    print(f"  Signal counts for {label}")
    print(f"{'='*60}")
    for interval in ['1h', '2h', '3h', '4h', '1d']:
        sig = compute_signals(data_dict, interval)
        if sig is None:
            print(f"  [{interval}] No data")
            continue
        cd_count = sig['cd'].sum()
        bt_count = sig['bt'].sum()
        buy_count = sig['buy_signals'].sum()
        print(f"  [{interval}] CD={cd_count:4d}  BT={bt_count:4d}  BUY(1234)={buy_count:4d}  bars={len(sig['df'])}")

def main():
    print(f"Downloading data for {TICKER}...")
    raw_data = download_and_prepare(TICKER)
    
    print(f"\nTruncating data...")
    data_a = truncate(raw_data, DATE_A)
    data_b = truncate(raw_data, DATE_B)
    
    # Count signals
    count_signals(data_a, f"{TICKER} up to {DATE_A}")
    count_signals(data_b, f"{TICKER} up to {DATE_B}")
    
    # Compare each interval around the focus date
    for interval in ['1h', '2h', '3h', '4h', '1d']:
        sig_a = compute_signals(data_a, interval)
        sig_b = compute_signals(data_b, interval)
        compare_around_date(sig_a, sig_b, DATE_A, interval, window=5)
    
    # Also check: full list of buy_signal dates that differ
    print(f"\n\n{'='*80}")
    print(f"  ALL SIGNAL DIFFERENCES ACROSS FULL DATE RANGE")
    print(f"{'='*80}")
    for interval in ['1h', '2h', '3h', '4h', '1d']:
        sig_a = compute_signals(data_a, interval)
        sig_b = compute_signals(data_b, interval)
        if sig_a is None or sig_b is None:
            continue
        
        # Find common dates
        common_idx = sig_a['buy_signals'].index.intersection(sig_b['buy_signals'].index)
        buy_a = sig_a['buy_signals'].reindex(common_idx, fill_value=False)
        buy_b = sig_b['buy_signals'].reindex(common_idx, fill_value=False)
        
        # Find dates that differ
        diffs = buy_a != buy_b
        if diffs.any():
            print(f"\n  [{interval}] {diffs.sum()} differing BUY signals:")
            for ts in common_idx[diffs]:
                a_val = buy_a[ts]
                b_val = buy_b[ts]
                cd_a = sig_a['cd'].get(ts, '?')
                cd_b = sig_b['cd'].get(ts, '?')
                bt_a = sig_a['bt'].get(ts, '?')
                bt_b = sig_b['bt'].get(ts, '?')
                print(f"    {ts}  BUY: {a_val}->{b_val}  CD: {cd_a}->{cd_b}  BT: {bt_a}->{bt_b}")
        else:
            print(f"\n  [{interval}] ✅ No BUY signal differences on common dates")

if __name__ == "__main__":
    main()
