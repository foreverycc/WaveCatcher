"""
Verification test for CD/MC signal scoring.
Tests that compute_cd_score and compute_mc_score produce valid 0-100 scores
aligned with signal positions.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app', 'logic'))

import pandas as pd
import numpy as np
import yfinance as yf
from indicators import compute_cd_indicator, compute_mc_indicator, compute_cd_score, compute_mc_score


def test_signal_scoring():
    """Download AAPL data and verify scoring functions."""
    print("Downloading AAPL 1d data (2 years)...")
    ticker = yf.Ticker("AAPL")
    data = ticker.history(period="2y", interval="1d")
    
    if data.empty:
        print("ERROR: Failed to download data")
        return False
    
    print(f"Data shape: {data.shape}, range: {data.index[0]} to {data.index[-1]}")
    
    # === Test CD Score ===
    print("\n--- CD Signal Scoring ---")
    cd_signals = compute_cd_indicator(data)
    cd_scores = compute_cd_score(data)
    
    cd_signal_mask = cd_signals.fillna(False).astype(bool)
    cd_signal_count = cd_signal_mask.sum()
    print(f"CD signals found: {cd_signal_count}")
    
    if cd_signal_count == 0:
        print("WARNING: No CD signals found in data")
    else:
        # Check scores are NaN where no signal
        non_signal_scores = cd_scores[~cd_signal_mask]
        assert non_signal_scores.isna().all(), "FAIL: Scores should be NaN where there is no CD signal"
        print("✓ Scores are NaN where no CD signal")
        
        # Check scores are in [0, 100] where signal exists
        signal_scores = cd_scores[cd_signal_mask].dropna()
        assert len(signal_scores) == cd_signal_count, f"FAIL: Expected {cd_signal_count} scores, got {len(signal_scores)}"
        assert (signal_scores >= 0).all(), "FAIL: Some CD scores are below 0"
        assert (signal_scores <= 100).all(), "FAIL: Some CD scores are above 100"
        print(f"✓ All {len(signal_scores)} CD scores in range [0, 100]")
        
        # Print score statistics
        print(f"  Min: {signal_scores.min():.1f}, Max: {signal_scores.max():.1f}, "
              f"Mean: {signal_scores.mean():.1f}, Median: {signal_scores.median():.1f}")
        
        # Print individual scores with dates
        print("  Individual CD scores:")
        for date, score in signal_scores.items():
            price = data.loc[date, 'Close']
            print(f"    {date.strftime('%Y-%m-%d')}: Score={score:.1f}, Price=${price:.2f}")
    
    # === Test MC Score ===
    print("\n--- MC Signal Scoring ---")
    mc_signals = compute_mc_indicator(data)
    mc_scores = compute_mc_score(data)
    
    mc_signal_mask = mc_signals.fillna(False).astype(bool)
    mc_signal_count = mc_signal_mask.sum()
    print(f"MC signals found: {mc_signal_count}")
    
    if mc_signal_count == 0:
        print("WARNING: No MC signals found in data")
    else:
        # Check scores are NaN where no signal
        non_signal_scores = mc_scores[~mc_signal_mask]
        assert non_signal_scores.isna().all(), "FAIL: Scores should be NaN where there is no MC signal"
        print("✓ Scores are NaN where no MC signal")
        
        # Check scores are in [0, 100] where signal exists
        signal_scores = mc_scores[mc_signal_mask].dropna()
        assert len(signal_scores) == mc_signal_count, f"FAIL: Expected {mc_signal_count} scores, got {len(signal_scores)}"
        assert (signal_scores >= 0).all(), "FAIL: Some MC scores are below 0"
        assert (signal_scores <= 100).all(), "FAIL: Some MC scores are above 100"
        print(f"✓ All {len(signal_scores)} MC scores in range [0, 100]")
        
        # Print score statistics
        print(f"  Min: {signal_scores.min():.1f}, Max: {signal_scores.max():.1f}, "
              f"Mean: {signal_scores.mean():.1f}, Median: {signal_scores.median():.1f}")
        
        # Print individual scores with dates
        print("  Individual MC scores:")
        for date, score in signal_scores.items():
            price = data.loc[date, 'Close']
            print(f"    {date.strftime('%Y-%m-%d')}: Score={score:.1f}, Price=${price:.2f}")
    
    print("\n=== ALL TESTS PASSED ===")
    return True


if __name__ == "__main__":
    success = test_signal_scoring()
    sys.exit(0 if success else 1)
