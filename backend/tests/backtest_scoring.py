#!/usr/bin/env python3
"""
CD/MC Scoring System Backtester
================================
Tests different component weights and interval multipliers using QQQ data
to find the optimal scoring configuration.

Two optimization axes:
1. Component weights: [divergence, price_position, volume] summing to 100
2. Interval multipliers: weights for [1h, 2h, 3h, 4h, 1d]

Performance metric: Rank-biserial correlation between signal score and 
forward returns (higher score should predict better returns).
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app', 'logic'))

import pandas as pd
import numpy as np
import yfinance as yf
from itertools import product
from indicators import (
    compute_cd_indicator, compute_mc_indicator,
    _compute_barslast, _compute_llv, _compute_hhv, _compute_ref
)


# ─── Raw Component Extraction ───────────────────────────────────────────

def compute_cd_raw_components(data):
    """
    For each CD signal, compute the 3 raw component values (each 0-1 range).
    Returns DataFrame with columns: [date, comp_divergence, comp_price, comp_volume, close]
    """
    close = data['Close']
    volume = data['Volume']
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    if isinstance(volume, pd.DataFrame):
        volume = volume.iloc[:, 0]

    # MACD internals
    fast_ema = close.ewm(span=12, adjust=False).mean()
    slow_ema = close.ewm(span=26, adjust=False).mean()
    diff = fast_ema - slow_ema
    dea = diff.ewm(span=9, adjust=False).mean()
    mcd = (diff - dea) * 2

    cross_down = (mcd.shift(1) >= 0) & (mcd < 0)
    cross_up = (mcd.shift(1) <= 0) & (mcd > 0)
    n1 = _compute_barslast(cross_down, len(data))
    mm1 = _compute_barslast(cross_up, len(data))
    n1_safe = n1 + 1
    mm1_safe = mm1 + 1

    difl1 = _compute_llv(diff, n1_safe)
    difl2 = _compute_ref(difl1, mm1_safe)

    cd_signal = compute_cd_indicator(data).fillna(False).astype(bool)
    signal_indices = np.where(cd_signal)[0]

    rows = []
    for idx in signal_indices:
        # Divergence (0-1)
        d1, d2 = difl1.iloc[idx], difl2.iloc[idx]
        if pd.notna(d1) and pd.notna(d2) and abs(d2) > 1e-10:
            div_raw = min(max((d1 - d2) / abs(d2), 0.0), 1.0)
        else:
            div_raw = 0.5

        # Price position (0-1, lower = better for buy → inverted)
        lookback = min(50, idx + 1)
        if lookback > 1:
            wc = close.iloc[max(0, idx - lookback + 1):idx + 1]
            w_range = wc.max() - wc.min()
            if w_range > 1e-10:
                price_raw = 1.0 - (close.iloc[idx] - wc.min()) / w_range
            else:
                price_raw = 0.5
        else:
            price_raw = 0.5

        # Volume (0-1)
        vol_avg = volume.iloc[max(0, idx - 19):idx + 1].mean()
        if vol_avg > 0:
            vol_raw = min(volume.iloc[idx] / vol_avg / 2.0, 1.0)
        else:
            vol_raw = 0.5

        rows.append({
            'date': data.index[idx],
            'bar_idx': idx,
            'comp_divergence': div_raw,
            'comp_price': price_raw,
            'comp_volume': vol_raw,
            'close': close.iloc[idx]
        })

    return pd.DataFrame(rows)


def compute_mc_raw_components(data):
    """Same as CD but for MC (sell) signals."""
    close = data['Close']
    volume = data['Volume']
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    if isinstance(volume, pd.DataFrame):
        volume = volume.iloc[:, 0]

    fast_ema = close.ewm(span=12, adjust=False).mean()
    slow_ema = close.ewm(span=26, adjust=False).mean()
    diff = fast_ema - slow_ema
    dea = diff.ewm(span=9, adjust=False).mean()
    mcd = (diff - dea) * 2

    cross_down = (mcd.shift(1) >= 0) & (mcd < 0)
    cross_up = (mcd.shift(1) <= 0) & (mcd > 0)
    n1 = _compute_barslast(cross_down, len(data))
    mm1 = _compute_barslast(cross_up, len(data))
    n1_safe = n1 + 1
    mm1_safe = mm1 + 1

    difh1 = _compute_hhv(diff, mm1_safe)
    difh2 = _compute_ref(difh1, n1_safe)

    mc_signal = compute_mc_indicator(data).fillna(False).astype(bool)
    signal_indices = np.where(mc_signal)[0]

    rows = []
    for idx in signal_indices:
        d1, d2 = difh1.iloc[idx], difh2.iloc[idx]
        if pd.notna(d1) and pd.notna(d2) and abs(d2) > 1e-10:
            div_raw = min(max((d2 - d1) / abs(d2), 0.0), 1.0)
        else:
            div_raw = 0.5

        lookback = min(50, idx + 1)
        if lookback > 1:
            wc = close.iloc[max(0, idx - lookback + 1):idx + 1]
            w_range = wc.max() - wc.min()
            if w_range > 1e-10:
                price_raw = (close.iloc[idx] - wc.min()) / w_range  # higher = better sell
            else:
                price_raw = 0.5
        else:
            price_raw = 0.5

        vol_avg = volume.iloc[max(0, idx - 19):idx + 1].mean()
        if vol_avg > 0:
            vol_raw = min(volume.iloc[idx] / vol_avg / 2.0, 1.0)
        else:
            vol_raw = 0.5

        rows.append({
            'date': data.index[idx],
            'bar_idx': idx,
            'comp_divergence': div_raw,
            'comp_price': price_raw,
            'comp_volume': vol_raw,
            'close': close.iloc[idx]
        })

    return pd.DataFrame(rows)


# ─── Return Calculation ──────────────────────────────────────────────────

def compute_forward_returns(data, signal_df, periods=[5, 10, 20, 30]):
    """
    Compute forward returns after each signal.
    For CD (buy): positive return = good
    For MC (sell): negative return = good (we negate so higher = better)
    """
    close = data['Close']
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    results = []
    for _, row in signal_df.iterrows():
        idx = row['bar_idx']
        entry_price = row['close']
        record = {'date': row['date'], 'bar_idx': idx}
        
        for p in periods:
            if idx + p < len(data):
                exit_price = close.iloc[idx + p]
                record[f'ret_{p}'] = (exit_price - entry_price) / entry_price * 100
            else:
                record[f'ret_{p}'] = np.nan
        
        # Copy raw components
        record['comp_divergence'] = row['comp_divergence']
        record['comp_price'] = row['comp_price']
        record['comp_volume'] = row['comp_volume']
        results.append(record)

    return pd.DataFrame(results)


# ─── Scoring Function ───────────────────────────────────────────────────

def score_signals(df, weights):
    """
    Apply component weights to compute a score.
    weights = (w_div, w_price, w_vol) summing to 100
    """
    w_div, w_price, w_vol = weights
    return (
        df['comp_divergence'] * w_div +
        df['comp_price'] * w_price +
        df['comp_volume'] * w_vol
    )


# ─── Performance Metric ─────────────────────────────────────────────────

def evaluate_score_quality(df, score_col='score', return_col='ret_10'):
    """
    Evaluate how well scores predict returns.
    Returns dict with:
    - correlation: Pearson correlation between score and return
    - top_half_avg: avg return of top-50% scores
    - bot_half_avg: avg return of bottom-50% scores
    - lift: top_half_avg - bot_half_avg (positive = scores work)
    - top_quarter_avg: avg return of top-25% scores
    """
    valid = df[[score_col, return_col]].dropna()
    if len(valid) < 4:
        return {'correlation': np.nan, 'top_half_avg': np.nan, 'bot_half_avg': np.nan, 
                'lift': np.nan, 'top_quarter_avg': np.nan, 'n_signals': len(valid)}
    
    corr = valid[score_col].corr(valid[return_col])
    
    median_score = valid[score_col].median()
    top_half = valid[valid[score_col] >= median_score][return_col]
    bot_half = valid[valid[score_col] < median_score][return_col]
    
    q75 = valid[score_col].quantile(0.75)
    top_quarter = valid[valid[score_col] >= q75][return_col]
    
    return {
        'correlation': corr,
        'top_half_avg': top_half.mean() if len(top_half) > 0 else np.nan,
        'bot_half_avg': bot_half.mean() if len(bot_half) > 0 else np.nan,
        'lift': (top_half.mean() - bot_half.mean()) if len(top_half) > 0 and len(bot_half) > 0 else np.nan,
        'top_quarter_avg': top_quarter.mean() if len(top_quarter) > 0 else np.nan,
        'n_signals': len(valid)
    }


# ─── Main Backtesting ───────────────────────────────────────────────────

def run_backtest():
    ticker = 'QQQ'
    intervals = ['1h', '2h', '3h', '4h', '1d']
    
    # Define periods to map to each interval
    # For intraday intervals, use the max data yfinance allows
    interval_periods = {
        '1h': '2y',
        '2h': '2y',  
        '3h': 'max',  # yfinance may not support 3h, we'll try
        '4h': 'max',
        '1d': '10y'
    }
    
    # Return measurement periods (in bars after signal)
    return_periods = [5, 10, 15, 20, 30]
    
    # Component weight candidates: (divergence, price_position, volume), sum=100
    weight_grid = [
        (33, 33, 34),   # Baseline (equal)
        (50, 30, 20),   # Divergence-heavy
        (50, 20, 30),   # Divergence + Volume
        (20, 50, 30),   # Price-heavy
        (30, 50, 20),   # Price-focused
        (20, 30, 50),   # Volume-heavy
        (30, 20, 50),   # Volume + Divergence
        (40, 40, 20),   # Div + Price
        (40, 20, 40),   # Div + Volume
        (20, 40, 40),   # Price + Volume
        (60, 20, 20),   # Strong divergence
        (20, 60, 20),   # Strong price
        (20, 20, 60),   # Strong volume
        (70, 15, 15),   # Dominant divergence
        (15, 70, 15),   # Dominant price
        (15, 15, 70),   # Dominant volume
        (45, 35, 20),   # Balanced div-price
        (45, 20, 35),   # Balanced div-volume
        (35, 45, 20),   # Balanced price-div
    ]
    
    print(f"{'='*80}")
    print(f"CD/MC SCORING SYSTEM BACKTESTER — {ticker}")
    print(f"{'='*80}")
    
    # ─── Step 1: Download data for all intervals ─────────────────────
    print("\n📥 Downloading data...")
    all_data = {}
    for intv in intervals:
        period = interval_periods.get(intv, '2y')
        try:
            t = yf.Ticker(ticker)
            data = t.history(period=period, interval=intv)
            if not data.empty:
                all_data[intv] = data
                print(f"  {intv}: {len(data)} bars ({data.index[0].strftime('%Y-%m-%d')} to {data.index[-1].strftime('%Y-%m-%d')})")
            else:
                print(f"  {intv}: No data returned")
        except Exception as e:
            print(f"  {intv}: Error downloading: {e}")
    
    if not all_data:
        print("ERROR: No data downloaded. Aborting.")
        return
    
    # ─── Step 2: Extract raw components for all intervals ────────────
    print("\n🔍 Extracting signal components...")
    cd_all = {}  # interval -> DataFrame of raw components + forward returns
    mc_all = {}
    
    for intv, data in all_data.items():
        # CD signals
        cd_comps = compute_cd_raw_components(data)
        if not cd_comps.empty:
            cd_returns = compute_forward_returns(data, cd_comps, return_periods)
            cd_all[intv] = cd_returns
            print(f"  CD {intv}: {len(cd_returns)} signals")
        else:
            print(f"  CD {intv}: No signals")
        
        # MC signals
        mc_comps = compute_mc_raw_components(data)
        if not mc_comps.empty:
            mc_returns = compute_forward_returns(data, mc_comps, return_periods)
            # For MC, negate returns (negative return = good sell signal)
            for p in return_periods:
                mc_returns[f'ret_{p}'] = -mc_returns[f'ret_{p}']
            mc_all[intv] = mc_returns
            print(f"  MC {intv}: {len(mc_returns)} signals")
        else:
            print(f"  MC {intv}: No signals")
    
    # ─── Step 3: Grid search over component weights ──────────────────
    print(f"\n{'─'*80}")
    print("PART A: COMPONENT WEIGHT OPTIMIZATION")
    print(f"{'─'*80}")
    print(f"Testing {len(weight_grid)} weight combinations × {len(return_periods)} return periods")
    print(f"Primary metric: 'lift' = avg return of top-50% scores − avg return of bottom-50%\n")
    
    best_cd_results = []
    best_mc_results = []
    
    for signal_type, signal_data in [('CD', cd_all), ('MC', mc_all)]:
        print(f"\n{'='*60}")
        print(f"  {signal_type} SIGNAL COMPONENT WEIGHTS")
        print(f"{'='*60}")
        
        all_weight_results = []
        
        for weights in weight_grid:
            weight_perf = {'weights': weights}
            
            for intv, df in signal_data.items():
                if df.empty:
                    continue
                # Score all signals with these weights
                df_copy = df.copy()
                df_copy['score'] = score_signals(df_copy, weights)
                
                for p in return_periods:
                    ret_col = f'ret_{p}'
                    if ret_col not in df_copy.columns:
                        continue
                    metrics = evaluate_score_quality(df_copy, 'score', ret_col)
                    key = f'{intv}_p{p}'
                    weight_perf[f'{key}_lift'] = metrics['lift']
                    weight_perf[f'{key}_corr'] = metrics['correlation']
                    weight_perf[f'{key}_top25'] = metrics['top_quarter_avg']
                    weight_perf[f'{key}_n'] = metrics['n_signals']
            
            all_weight_results.append(weight_perf)
        
        # Compute average lift across all intervals and return periods
        results_df = pd.DataFrame(all_weight_results)
        lift_cols = [c for c in results_df.columns if c.endswith('_lift')]
        corr_cols = [c for c in results_df.columns if c.endswith('_corr')]
        top25_cols = [c for c in results_df.columns if c.endswith('_top25')]
        
        if lift_cols:
            results_df['avg_lift'] = results_df[lift_cols].mean(axis=1)
            results_df['avg_corr'] = results_df[corr_cols].mean(axis=1)
            results_df['avg_top25'] = results_df[top25_cols].mean(axis=1)
            
            # Sort by average lift
            results_df = results_df.sort_values('avg_lift', ascending=False)
            
            print(f"\n  Top 10 weight combinations (sorted by avg lift):")
            print(f"  {'Weights':>20s} | {'Avg Lift':>10s} | {'Avg Corr':>10s} | {'Avg Top25':>10s}")
            print(f"  {'─'*20}─┼─{'─'*10}─┼─{'─'*10}─┼─{'─'*10}")
            for _, row in results_df.head(10).iterrows():
                w = row['weights']
                print(f"  {str(w):>20s} | {row['avg_lift']:>10.3f} | {row['avg_corr']:>10.3f} | {row['avg_top25']:>10.3f}")
            
            # Detail: breakdown by interval for the best weight
            best = results_df.iloc[0]
            best_w = best['weights']
            print(f"\n  Best weights: {best_w}")
            print(f"  Breakdown by interval and period:")
            print(f"  {'Interval':>10s} | {'Period':>8s} | {'Lift':>10s} | {'Corr':>10s} | {'Top25%':>10s} | {'N':>6s}")
            print(f"  {'─'*10}─┼─{'─'*8}─┼─{'─'*10}─┼─{'─'*10}─┼─{'─'*10}─┼─{'─'*6}")
            for intv in sorted(signal_data.keys()):
                for p in return_periods:
                    key = f'{intv}_p{p}'
                    lift_val = best.get(f'{key}_lift', np.nan)
                    corr_val = best.get(f'{key}_corr', np.nan)
                    top25_val = best.get(f'{key}_top25', np.nan)
                    n_val = best.get(f'{key}_n', 0)
                    if pd.notna(lift_val):
                        print(f"  {intv:>10s} | {f'p{p}':>8s} | {lift_val:>10.3f} | {corr_val:>10.3f} | {top25_val:>10.3f} | {int(n_val):>6d}")
            
            if signal_type == 'CD':
                best_cd_results = results_df
            else:
                best_mc_results = results_df
    
    # ─── Step 4: Interval weight optimization ────────────────────────
    print(f"\n{'─'*80}")
    print("PART B: INTERVAL MULTIPLIER OPTIMIZATION")
    print(f"{'─'*80}")
    
    # Use the best component weights from Part A
    if isinstance(best_cd_results, pd.DataFrame) and not best_cd_results.empty:
        best_cd_weights = best_cd_results.iloc[0]['weights']
    else:
        best_cd_weights = (33, 33, 34)
    
    if isinstance(best_mc_results, pd.DataFrame) and not best_mc_results.empty:
        best_mc_weights = best_mc_results.iloc[0]['weights']
    else:
        best_mc_weights = (33, 33, 34)

    print(f"  Using CD component weights: {best_cd_weights}")
    print(f"  Using MC component weights: {best_mc_weights}")
    
    # Interval weight candidates
    interval_weight_grid = [
        {'1h': 1, '2h': 2, '3h': 3, '4h': 4, '1d': 8},    # Current
        {'1h': 1, '2h': 1, '3h': 1, '4h': 1, '1d': 1},    # Equal
        {'1h': 1, '2h': 2, '3h': 3, '4h': 4, '1d': 5},    # Linear
        {'1h': 1, '2h': 2, '3h': 4, '4h': 8, '1d': 16},   # Exponential
        {'1h': 1, '2h': 3, '3h': 5, '4h': 7, '1d': 10},   # Steep linear
        {'1h': 2, '2h': 3, '3h': 4, '4h': 5, '1d': 6},    # Mild linear
        {'1h': 1, '2h': 1, '3h': 2, '4h': 3, '1d': 10},   # 1d-heavy
        {'1h': 1, '2h': 2, '3h': 3, '4h': 5, '1d': 12},   # 1d-heavier
        {'1h': 3, '2h': 3, '3h': 3, '4h': 3, '1d': 3},    # All equal (3)
        {'1h': 1, '2h': 2, '3h': 3, '4h': 4, '1d': 4},    # Capped at 4
    ]
    
    for signal_type, signal_data, comp_weights in [
        ('CD', cd_all, best_cd_weights), ('MC', mc_all, best_mc_weights)
    ]:
        print(f"\n  === {signal_type} Interval Weights ===")
        
        intv_results = []
        
        for iw in interval_weight_grid:
            # Simulate aggregation: for each date, sum (score * interval_weight)
            # We treat each interval's signal set independently since we don't have
            # cross-interval aggregation in this backtest. Instead, we evaluate
            # whether heavy-interval signals have bigger returns.
            
            # Strategy: weight the lift from each interval by its multiplier
            # This tests if the interval weightings correctly prioritize 
            # better-performing intervals
            weighted_lift_sum = 0
            total_weight = 0
            detail = {'interval_weights': str(iw)}
            
            for intv, df in signal_data.items():
                if df.empty or intv not in iw:
                    continue
                df_copy = df.copy()
                df_copy['score'] = score_signals(df_copy, comp_weights)
                
                # Use ret_10 as primary metric
                metrics = evaluate_score_quality(df_copy, 'score', 'ret_10')
                w = iw[intv]
                if pd.notna(metrics['lift']):
                    weighted_lift_sum += metrics['lift'] * w
                    total_weight += w
                
                detail[f'{intv}_lift'] = metrics['lift']
                detail[f'{intv}_weight'] = w
                detail[f'{intv}_n'] = metrics['n_signals']
            
            detail['weighted_avg_lift'] = weighted_lift_sum / total_weight if total_weight > 0 else np.nan
            intv_results.append(detail)
        
        intv_df = pd.DataFrame(intv_results).sort_values('weighted_avg_lift', ascending=False)
        
        print(f"\n  Interval weight rankings (by weighted avg lift):")
        print(f"  {'Config':>50s} | {'Wtd Lift':>10s}")
        print(f"  {'─'*50}─┼─{'─'*10}")
        for _, row in intv_df.iterrows():
            print(f"  {row['interval_weights']:>50s} | {row['weighted_avg_lift']:>10.3f}")
    
    # ─── Summary ─────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print("SUMMARY & RECOMMENDATIONS")
    print(f"{'='*80}")
    
    if isinstance(best_cd_results, pd.DataFrame) and not best_cd_results.empty:
        cd_best = best_cd_results.iloc[0]
        print(f"\n  CD Best Component Weights: {cd_best['weights']}")
        print(f"     Avg Lift: {cd_best['avg_lift']:.3f}%")
        print(f"     Avg Correlation: {cd_best['avg_corr']:.3f}")
        print(f"     Avg Top-25% Return: {cd_best['avg_top25']:.3f}%")
    
    if isinstance(best_mc_results, pd.DataFrame) and not best_mc_results.empty:
        mc_best = best_mc_results.iloc[0]
        print(f"\n  MC Best Component Weights: {mc_best['weights']}")
        print(f"     Avg Lift: {mc_best['avg_lift']:.3f}%")
        print(f"     Avg Correlation: {mc_best['avg_corr']:.3f}")
        print(f"     Avg Top-25% Return: {mc_best['avg_top25']:.3f}%")
    
    print(f"\n  Current weights: (33, 33, 34) — compare lift/corr above to see improvement.")


if __name__ == '__main__':
    run_backtest()
