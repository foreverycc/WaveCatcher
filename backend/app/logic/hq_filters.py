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
    open_ = df['Open'] if 'Open' in df else close
    if isinstance(open_, pd.DataFrame):
        open_ = open_.iloc[:, 0]
    
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
            # Only use returns that were already realized at the current signal (no look-ahead)
            if future_idx <= sig_idx:
                # Enter at the open of the bar after the signal, like the evaluation returns
                entry_price = open_.iloc[prev_idx + 1] if prev_idx + 1 < len(open_) else np.nan
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
    open_ = df['Open'] if 'Open' in df else close
    if isinstance(open_, pd.DataFrame):
        open_ = open_.iloc[:, 0]
    
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
            # Only use returns that were already realized at the current signal (no look-ahead)
            if future_idx <= sig_idx:
                # Enter at the open of the bar after the signal, like the evaluation returns
                entry_price = open_.iloc[prev_idx + 1] if prev_idx + 1 < len(open_) else np.nan
                exit_price = close.iloc[future_idx]
                if entry_price > 0:
                    ret = (exit_price - entry_price) / entry_price * 100
                    returns.append(ret)
        
        # If we have returns and avg is below threshold (negative), mark as high-return
        if returns and np.mean(returns) < mc_return_threshold:
            result.iloc[sig_idx] = True
    
    return result


def compute_trend_regime(df, signals, side, interval=None, stock_ema=50, cd_below_ema_pct=None,
                         use_market_cd=True, use_market_mc=True, market_symbol='^SPX', market_ema=50,
                         market_max_above_ema_pct=1.0, market_closes=None, **kwargs):
    """
    Trend / market-regime HQ filter.

    CD: the close is at least cd_below_ema_pct[interval] % below its EMA(stock_ema) (a deep decline,
        not a shallow pullback) and, with use_market_cd, the market index is near or below its EMA.
    MC: with use_market_mc, the market index is near or below its EMA (see market_regime.market_ok).
    """
    from app.logic.market_regime import market_ok
    interval = {'60m': '1h'}.get(interval, interval)
    result = pd.Series(np.asarray(signals, dtype=bool), index=df.index)
    if not result.any():
        return result
    use_market = use_market_cd if side == 'cd' else use_market_mc
    if use_market:
        result &= market_ok(df.index, interval or '1d', market_symbol, market_ema,
                            market_max_above_ema_pct, closes=market_closes)
    if side == 'cd':
        close = df['Close']
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        ema = close.ewm(span=stock_ema, adjust=False).mean()
        threshold = (cd_below_ema_pct or {}).get(interval or '1d', 10.0)
        result &= (close / ema - 1) * 100 <= -threshold
    return result
