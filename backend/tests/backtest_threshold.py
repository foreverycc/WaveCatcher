#!/usr/bin/env python3
"""
Multi-Index Threshold Backtester
==================================
Sweeps score thresholds, component weights, and interval multipliers
across SOXX/SPACE/CRYPTO/QUANTUM/KWEB to find optimal parameters.

Threshold = minimum score for a signal to be counted. Signals below
the threshold are ignored. Higher threshold → fewer but (ideally) better signals.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app', 'logic'))

import pandas as pd
import numpy as np
import yfinance as yf
from pathlib import Path
from itertools import product
from indicators import (
    compute_cd_indicator, compute_mc_indicator,
    _compute_barslast, _compute_llv, _compute_hhv, _compute_ref
)

DATA_DIR = Path(__file__).parent.parent / 'data'

# ─── Index definitions ──────────────────────────────────────────────────

INDEX_FILES = {
    'SOXX': 'stocks_soxx.tab',
    'SPACE': 'stocks_space.tab',
    'CRYPTO': 'stocks_crypto.tab',
    'QUANTUM': 'stocks_quantum.tab',
    'KWEB': 'stocks_zhonggai.tab',
}

def load_tickers(index_name):
    """Load tickers from a stock list file."""
    filepath = DATA_DIR / INDEX_FILES[index_name]
    if not filepath.exists():
        print(f"  ⚠ File not found: {filepath}")
        return []
    with open(filepath) as f:
        return [line.strip() for line in f if line.strip()]


# ─── Raw Component Extraction ───────────────────────────────────────────

def compute_cd_raw_components(data):
    """Extract raw 0-1 component values for each CD signal."""
    close = data['Close']
    volume = data['Volume']
    if isinstance(close, pd.DataFrame): close = close.iloc[:, 0]
    if isinstance(volume, pd.DataFrame): volume = volume.iloc[:, 0]

    fast_ema = close.ewm(span=12, adjust=False).mean()
    slow_ema = close.ewm(span=26, adjust=False).mean()
    diff = fast_ema - slow_ema
    dea = diff.ewm(span=9, adjust=False).mean()
    mcd = (diff - dea) * 2

    cross_down = (mcd.shift(1) >= 0) & (mcd < 0)
    cross_up = (mcd.shift(1) <= 0) & (mcd > 0)
    n1 = _compute_barslast(cross_down, len(data))
    mm1 = _compute_barslast(cross_up, len(data))

    difl1 = _compute_llv(diff, n1 + 1)
    difl2 = _compute_ref(difl1, mm1 + 1)

    cd_signal = compute_cd_indicator(data).fillna(False).astype(bool)
    signal_indices = np.where(cd_signal)[0]

    rows = []
    for idx in signal_indices:
        d1, d2 = difl1.iloc[idx], difl2.iloc[idx]
        if pd.notna(d1) and pd.notna(d2) and abs(d2) > 1e-10:
            div_raw = min(max((d1 - d2) / abs(d2), 0.0), 1.0)
        else:
            div_raw = 0.5

        lookback = min(50, idx + 1)
        if lookback > 1:
            wc = close.iloc[max(0, idx - lookback + 1):idx + 1]
            w_range = wc.max() - wc.min()
            price_raw = 1.0 - (close.iloc[idx] - wc.min()) / w_range if w_range > 1e-10 else 0.5
        else:
            price_raw = 0.5

        vol_avg = volume.iloc[max(0, idx - 19):idx + 1].mean()
        vol_raw = min(volume.iloc[idx] / vol_avg / 2.0, 1.0) if vol_avg > 0 else 0.5

        rows.append({
            'bar_idx': idx, 'close': close.iloc[idx],
            'comp_divergence': div_raw, 'comp_price': price_raw, 'comp_volume': vol_raw
        })
    return pd.DataFrame(rows)


def compute_mc_raw_components(data):
    """Extract raw 0-1 component values for each MC signal."""
    close = data['Close']
    volume = data['Volume']
    if isinstance(close, pd.DataFrame): close = close.iloc[:, 0]
    if isinstance(volume, pd.DataFrame): volume = volume.iloc[:, 0]

    fast_ema = close.ewm(span=12, adjust=False).mean()
    slow_ema = close.ewm(span=26, adjust=False).mean()
    diff = fast_ema - slow_ema
    dea = diff.ewm(span=9, adjust=False).mean()
    mcd = (diff - dea) * 2

    cross_down = (mcd.shift(1) >= 0) & (mcd < 0)
    cross_up = (mcd.shift(1) <= 0) & (mcd > 0)
    n1 = _compute_barslast(cross_down, len(data))
    mm1 = _compute_barslast(cross_up, len(data))

    difh1 = _compute_hhv(diff, mm1 + 1)
    difh2 = _compute_ref(difh1, n1 + 1)

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
            price_raw = (close.iloc[idx] - wc.min()) / w_range if w_range > 1e-10 else 0.5
        else:
            price_raw = 0.5

        vol_avg = volume.iloc[max(0, idx - 19):idx + 1].mean()
        vol_raw = min(volume.iloc[idx] / vol_avg / 2.0, 1.0) if vol_avg > 0 else 0.5

        rows.append({
            'bar_idx': idx, 'close': close.iloc[idx],
            'comp_divergence': div_raw, 'comp_price': price_raw, 'comp_volume': vol_raw
        })
    return pd.DataFrame(rows)


# ─── Scoring & Returns ──────────────────────────────────────────────────

def score_signals(df, weights):
    w_div, w_price, w_vol = weights
    return df['comp_divergence'] * w_div + df['comp_price'] * w_price + df['comp_volume'] * w_vol


def compute_forward_returns(data, signal_df, periods=[5, 10, 20]):
    close = data['Close']
    if isinstance(close, pd.DataFrame): close = close.iloc[:, 0]
    results = []
    for _, row in signal_df.iterrows():
        idx = int(row['bar_idx'])
        entry = row['close']
        rec = {'bar_idx': idx}
        for p in periods:
            if idx + p < len(data):
                rec[f'ret_{p}'] = (close.iloc[idx + p] - entry) / entry * 100
            else:
                rec[f'ret_{p}'] = np.nan
        rec['comp_divergence'] = row['comp_divergence']
        rec['comp_price'] = row['comp_price']
        rec['comp_volume'] = row['comp_volume']
        results.append(rec)
    return pd.DataFrame(results)


# ─── Data Collection ────────────────────────────────────────────────────

def download_all_data(indices, intervals=['1h', '4h', '1d']):
    """Download price data for all tickers across all indices."""
    period_map = {'1h': '2y', '4h': '2y', '1d': '10y'}
    all_data = {}  # {(index, ticker, interval): DataFrame}

    for idx_name in indices:
        tickers = load_tickers(idx_name)
        print(f"\n  {idx_name}: {len(tickers)} tickers")
        for ticker in tickers:
            for intv in intervals:
                key = (idx_name, ticker, intv)
                try:
                    t = yf.Ticker(ticker)
                    data = t.history(period=period_map.get(intv, '2y'), interval=intv)
                    if not data.empty and len(data) >= 50:
                        all_data[key] = data
                except Exception:
                    pass
        downloaded = sum(1 for k in all_data if k[0] == idx_name)
        print(f"    Downloaded: {downloaded} datasets")

    return all_data


def extract_all_signals(all_data, return_periods=[5, 10, 20]):
    """Extract CD/MC raw components and forward returns for all data."""
    cd_signals = {}  # {(index, ticker, interval): DataFrame}
    mc_signals = {}

    for (idx_name, ticker, intv), data in all_data.items():
        try:
            cd_comps = compute_cd_raw_components(data)
            if not cd_comps.empty:
                cd_ret = compute_forward_returns(data, cd_comps, return_periods)
                cd_signals[(idx_name, ticker, intv)] = cd_ret

            mc_comps = compute_mc_raw_components(data)
            if not mc_comps.empty:
                mc_ret = compute_forward_returns(data, mc_comps, return_periods)
                # Negate returns for MC (negative return = good sell)
                for p in return_periods:
                    mc_ret[f'ret_{p}'] = -mc_ret[f'ret_{p}']
                mc_signals[(idx_name, ticker, intv)] = mc_ret
        except Exception:
            pass

    return cd_signals, mc_signals


# ─── Evaluation ─────────────────────────────────────────────────────────

def evaluate_threshold(signals_dict, weights, threshold, return_col='ret_10'):
    """
    Score all signals with given weights, filter by threshold,
    and compute average return of surviving signals.
    Returns (avg_return, n_signals, n_surviving).
    """
    all_returns = []
    n_total = 0
    n_surviving = 0

    for key, df in signals_dict.items():
        if df.empty:
            continue
        scores = score_signals(df, weights)
        n_total += len(scores)
        mask = scores >= threshold
        n_surviving += mask.sum()
        surviving_returns = df.loc[mask, return_col].dropna()
        all_returns.extend(surviving_returns.tolist())

    if not all_returns:
        return np.nan, n_total, 0

    return np.mean(all_returns), n_total, n_surviving


# ─── Main Backtesting ───────────────────────────────────────────────────

def run_backtest():
    indices = list(INDEX_FILES.keys())
    intervals = ['1h', '4h', '1d']
    return_periods = [5, 10, 20]

    # Parameter grids
    threshold_grid = [0, 10, 20, 30, 40, 50, 60, 70]

    weight_grid = [
        (33, 33, 34),   # Equal
        (50, 30, 20),   # Divergence-heavy
        (50, 20, 30),   # Div + Vol
        (20, 50, 30),   # Price-heavy
        (30, 50, 20),   # Price-focused
        (20, 30, 50),   # Volume-heavy
        (30, 20, 50),   # Vol + Div
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
        (45, 20, 35),   # Balanced div-vol
        (35, 45, 20),   # Balanced price-div
    ]

    interval_weight_grid = [
        {'1h': 1, '2h': 2, '3h': 4, '4h': 8, '1d': 16},   # Exponential (current)
        {'1h': 1, '2h': 1, '3h': 1, '4h': 1, '1d': 1},     # Equal
        {'1h': 1, '2h': 2, '3h': 3, '4h': 4, '1d': 5},     # Linear
        {'1h': 1, '2h': 2, '3h': 3, '4h': 4, '1d': 8},     # Original
        {'1h': 1, '2h': 3, '3h': 5, '4h': 7, '1d': 10},    # Steep linear
        {'1h': 2, '2h': 3, '3h': 4, '4h': 5, '1d': 6},     # Mild linear
        {'1h': 1, '2h': 1, '3h': 2, '4h': 3, '1d': 10},    # 1d-heavy
        {'1h': 1, '2h': 2, '3h': 3, '4h': 5, '1d': 12},    # 1d-heavier
        {'1h': 1, '2h': 2, '3h': 4, '4h': 8, '1d': 32},    # Super exponential
        {'1h': 1, '2h': 2, '3h': 3, '4h': 4, '1d': 4},     # Capped at 4
    ]

    print(f"{'='*80}")
    print(f"MULTI-INDEX THRESHOLD BACKTESTER")
    print(f"Indices: {', '.join(indices)}")
    print(f"{'='*80}")

    # ─── Step 1: Download data ───────────────────────────────────────
    print("\n📥 Step 1: Downloading data for all indices...")
    all_data = download_all_data(indices, intervals)
    print(f"\n  Total datasets: {len(all_data)}")

    # ─── Step 2: Extract signals ─────────────────────────────────────
    print("\n🔍 Step 2: Extracting CD/MC signals and forward returns...")
    cd_signals, mc_signals = extract_all_signals(all_data, return_periods)
    cd_total = sum(len(df) for df in cd_signals.values())
    mc_total = sum(len(df) for df in mc_signals.values())
    print(f"  CD signals: {cd_total} across {len(cd_signals)} (ticker, interval) combos")
    print(f"  MC signals: {mc_total} across {len(mc_signals)} (ticker, interval) combos")

    # ─── Step 3: Joint sweep — Threshold × Weights ───────────────────
    print(f"\n{'─'*80}")
    print("PART A: THRESHOLD × COMPONENT WEIGHT SWEEP")
    print(f"  {len(threshold_grid)} thresholds × {len(weight_grid)} weight combos")
    print(f"{'─'*80}")

    for signal_type, signals_dict in [('CD', cd_signals), ('MC', mc_signals)]:
        print(f"\n{'='*60}")
        print(f"  {signal_type} SIGNALS")
        print(f"{'='*60}")

        results = []
        for weights in weight_grid:
            for threshold in threshold_grid:
                avg_ret, n_total, n_surv = evaluate_threshold(
                    signals_dict, weights, threshold, 'ret_10'
                )
                results.append({
                    'weights': weights,
                    'threshold': threshold,
                    'avg_return': avg_ret,
                    'n_total': n_total,
                    'n_surviving': n_surv,
                    'survival_rate': n_surv / n_total * 100 if n_total > 0 else 0,
                })

        results_df = pd.DataFrame(results).dropna(subset=['avg_return'])
        if results_df.empty:
            print("  No valid results.")
            continue

        # Sort by avg_return, but penalize very low survival counts
        results_df['quality'] = results_df['avg_return'] * np.log1p(results_df['n_surviving'])
        results_df = results_df.sort_values('quality', ascending=False)

        print(f"\n  Top 15 (Weights, Threshold) by quality (return × log(n_surviving)):")
        print(f"  {'Weights':>20s} | {'Thresh':>6s} | {'AvgRet%':>8s} | {'N_Surv':>7s} | {'Surv%':>6s} | {'Quality':>8s}")
        print(f"  {'─'*20}─┼─{'─'*6}─┼─{'─'*8}─┼─{'─'*7}─┼─{'─'*6}─┼─{'─'*8}")
        for _, row in results_df.head(15).iterrows():
            print(f"  {str(row['weights']):>20s} | {row['threshold']:>6.0f} | {row['avg_return']:>8.3f} | {row['n_surviving']:>7.0f} | {row['survival_rate']:>5.1f}% | {row['quality']:>8.2f}")

        # Best per threshold
        print(f"\n  Best weights per threshold level:")
        print(f"  {'Thresh':>6s} | {'Best Weights':>20s} | {'AvgRet%':>8s} | {'N_Surv':>7s} | {'Surv%':>6s}")
        print(f"  {'─'*6}─┼─{'─'*20}─┼─{'─'*8}─┼─{'─'*7}─┼─{'─'*6}")
        for t in threshold_grid:
            t_df = results_df[results_df['threshold'] == t].sort_values('avg_return', ascending=False)
            if not t_df.empty:
                best = t_df.iloc[0]
                print(f"  {t:>6.0f} | {str(best['weights']):>20s} | {best['avg_return']:>8.3f} | {best['n_surviving']:>7.0f} | {best['survival_rate']:>5.1f}%")

    # ─── Step 4: Per-index breakdown ─────────────────────────────────
    print(f"\n{'─'*80}")
    print("PART B: PER-INDEX THRESHOLD ANALYSIS")
    print(f"  Using equal weights (33,33,34) to isolate threshold effect")
    print(f"{'─'*80}")

    equal_weights = (33, 33, 34)

    for signal_type, signals_dict in [('CD', cd_signals), ('MC', mc_signals)]:
        print(f"\n  === {signal_type} Per-Index ===")
        print(f"  {'Index':>8s} | {'Thresh':>6s} | {'AvgRet%':>8s} | {'N_Surv':>7s} | {'Surv%':>6s}")
        print(f"  {'─'*8}─┼─{'─'*6}─┼─{'─'*8}─┼─{'─'*7}─┼─{'─'*6}")

        for idx_name in indices:
            idx_signals = {k: v for k, v in signals_dict.items() if k[0] == idx_name}
            if not idx_signals:
                continue
            for threshold in threshold_grid:
                avg_ret, n_total, n_surv = evaluate_threshold(
                    idx_signals, equal_weights, threshold, 'ret_10'
                )
                surv_pct = n_surv / n_total * 100 if n_total > 0 else 0
                if pd.notna(avg_ret):
                    print(f"  {idx_name:>8s} | {threshold:>6.0f} | {avg_ret:>8.3f} | {n_surv:>7d} | {surv_pct:>5.1f}%")

    # ─── Step 5: Interval weight sweep (with best threshold) ─────────
    print(f"\n{'─'*80}")
    print("PART C: INTERVAL MULTIPLIER SWEEP")
    print(f"  Testing {len(interval_weight_grid)} interval weight configs")
    print(f"{'─'*80}")

    # Find the best (weights, threshold) from Part A for each signal type
    for signal_type, signals_dict in [('CD', cd_signals), ('MC', mc_signals)]:
        print(f"\n  === {signal_type} Interval Weights ===")

        # First find best component weights + threshold
        best_ret = -999
        best_params = (equal_weights, 0)
        for weights in weight_grid:
            for threshold in threshold_grid:
                avg_ret, _, n_surv = evaluate_threshold(
                    signals_dict, weights, threshold, 'ret_10'
                )
                if pd.notna(avg_ret) and n_surv >= 20 and avg_ret > best_ret:
                    best_ret = avg_ret
                    best_params = (weights, threshold)

        best_weights, best_threshold = best_params
        print(f"  Using best weights={best_weights}, threshold={best_threshold}")

        # Now sweep interval weights by evaluating per-interval differently
        intv_results = []
        for iw in interval_weight_grid:
            weighted_ret_sum = 0
            total_weight = 0
            n_total_surv = 0

            for key, df in signals_dict.items():
                if df.empty:
                    continue
                intv = key[2]  # interval
                if intv not in iw:
                    continue
                scores = score_signals(df, best_weights)
                mask = scores >= best_threshold
                surviving = df.loc[mask, 'ret_10'].dropna()
                if len(surviving) > 0:
                    w = iw[intv]
                    weighted_ret_sum += surviving.mean() * w
                    total_weight += w
                    n_total_surv += len(surviving)

            wtd_ret = weighted_ret_sum / total_weight if total_weight > 0 else np.nan
            intv_results.append({
                'config': str(iw),
                'weighted_avg_return': wtd_ret,
                'n_surviving': n_total_surv
            })

        intv_df = pd.DataFrame(intv_results).dropna().sort_values('weighted_avg_return', ascending=False)

        print(f"\n  {'Config':>55s} | {'WtdRet%':>8s} | {'N_Surv':>7s}")
        print(f"  {'─'*55}─┼─{'─'*8}─┼─{'─'*7}")
        for _, row in intv_df.iterrows():
            print(f"  {row['config']:>55s} | {row['weighted_avg_return']:>8.3f} | {row['n_surviving']:>7.0f}")

    # ─── Summary ─────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print("FINAL SUMMARY")
    print(f"{'='*80}")
    print("\nRun the above analysis and update scoring_config.py with optimal values.")
    print("Key decisions: pick thresholds that maximize avg return while keeping")
    print("enough surviving signals (>= 20) for statistical significance.")


if __name__ == '__main__':
    run_backtest()
