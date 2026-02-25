"""
HQ (High Quality) Signal Filters
==================================
Pluggable algorithms for selecting high-quality CD/MC signals.

Currently supported:
  - breakthrough: Close crosses above EMA24(High) for CD / below EMA24(Low) for MC
  - high_return: Previous N signals had favorable avg return after K bars
"""

import numpy as np
import pandas as pd


def compute_high_return_cd(df, cd_signals, lookback_signals=3, lookback_bars=20, cd_return_threshold=5.0, **kwargs):
    """
    Mark CD signals as high-return if their previous `lookback_signals` CD signals
    had an average return > `cd_return_threshold`% after `lookback_bars` bars.
    
    Args:
        df: DataFrame with OHLCV data (must have 'Close' column)
        cd_signals: Boolean Series of CD signal dates
        lookback_signals: How many previous signals to average (default 3)
        lookback_bars: How many bars forward to measure return (default 20)
        cd_return_threshold: Min avg return % to qualify (default 5.0)
    
    Returns:
        Boolean Series: True where CD signal qualifies as high-return
    """
    close = df['Close']
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    
    result = pd.Series(False, index=df.index)
    signal_indices = np.where(cd_signals)[0]
    
    if len(signal_indices) == 0:
        return result
    
    for i, sig_idx in enumerate(signal_indices):
        # Need at least 1 previous signal to evaluate
        if i < 1:
            continue
        
        # Get previous N signal indices
        prev_indices = signal_indices[max(0, i - lookback_signals):i]
        
        # Compute returns for each previous signal
        returns = []
        for prev_idx in prev_indices:
            future_idx = prev_idx + lookback_bars
            if future_idx < len(close):
                entry_price = close.iloc[prev_idx]
                exit_price = close.iloc[future_idx]
                if entry_price > 0:
                    ret = (exit_price - entry_price) / entry_price * 100
                    returns.append(ret)
        
        # If we have returns and avg exceeds threshold, mark as high-return
        if returns and np.mean(returns) > cd_return_threshold:
            result.iloc[sig_idx] = True
    
    return result


def compute_high_return_mc(df, mc_signals, lookback_signals=3, lookback_bars=20, mc_return_threshold=-5.0, **kwargs):
    """
    Mark MC signals as high-return if their previous `lookback_signals` MC signals
    had an average return < `mc_return_threshold`% after `lookback_bars` bars.
    
    Args:
        df: DataFrame with OHLCV data (must have 'Close' column)
        mc_signals: Boolean Series of MC signal dates
        lookback_signals: How many previous signals to average (default 3)
        lookback_bars: How many bars forward to measure return (default 20)
        mc_return_threshold: Max avg return % to qualify (default -5.0, i.e. must decline)
    
    Returns:
        Boolean Series: True where MC signal qualifies as high-return
    """
    close = df['Close']
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    
    result = pd.Series(False, index=df.index)
    signal_indices = np.where(mc_signals)[0]
    
    if len(signal_indices) == 0:
        return result
    
    for i, sig_idx in enumerate(signal_indices):
        # Need at least 1 previous signal to evaluate
        if i < 1:
            continue
        
        # Get previous N signal indices
        prev_indices = signal_indices[max(0, i - lookback_signals):i]
        
        # Compute returns for each previous signal
        returns = []
        for prev_idx in prev_indices:
            future_idx = prev_idx + lookback_bars
            if future_idx < len(close):
                entry_price = close.iloc[prev_idx]
                exit_price = close.iloc[future_idx]
                if entry_price > 0:
                    ret = (exit_price - entry_price) / entry_price * 100
                    returns.append(ret)
        
        # If we have returns and avg is below threshold (negative), mark as high-return
        if returns and np.mean(returns) < mc_return_threshold:
            result.iloc[sig_idx] = True
    
    return result
