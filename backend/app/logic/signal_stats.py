"""
Signal statistics helpers
=========================
Shared by the CD/MC evaluation modules and the result tables in stock_analyzer.

Why this exists: picking the best of 101 holding periods on a handful of signals
almost always finds a "good" period even for random signals. To keep the numbers
honest we
  - only consider a small fixed grid of holding periods,
  - compare against the no-signal baseline (average forward return of every bar),
  - require a minimum number of samples, and
  - report a walk-forward out-of-sample result where each signal's holding period
    is chosen using only signals whose outcome was already known at that time.
"""

import numpy as np
import pandas as pd

# Holding periods (in bars) eligible as "best period"
BEST_PERIOD_GRID = [1, 2, 3, 5, 10, 15, 20, 30, 50, 100]

# Minimum signals measured at a period before it can be chosen as best
MIN_SAMPLES = 5

# Minimum excess return (%) over the no-signal baseline for the result tables
MIN_EXCESS_RETURN = 5.0

# Minimum earlier signals needed before a walk-forward choice is made
MIN_PRIOR_SIGNALS = 2

# Minimum walk-forward out-of-sample trades required for the result tables
MIN_OOS_COUNT = 3


def baseline_returns(close, grid=BEST_PERIOD_GRID):
    """Average forward return (%) over all bars for each period: what holding without a signal earns."""
    close = pd.Series(close).astype(float)
    result = {}
    for p in grid:
        fwd = (close.shift(-p) / close - 1) * 100
        fwd = fwd.dropna()
        result[p] = round(float(fwd.mean()), 2) if len(fwd) else np.nan
    return result


def walk_forward_oos(returns_df, data_index, grid=BEST_PERIOD_GRID, bullish=True, min_prior=MIN_PRIOR_SIGNALS):
    """
    Walk-forward out-of-sample returns.

    For each signal k, choose the holding period from `grid` using only earlier signals j whose
    return at that period was already realized at signal k (idx_j + p <= idx_k), then record signal k's
    own return at the chosen period.

    Returns dict with oos_avg_return, oos_success_rate, oos_count.
    """
    empty = {'oos_avg_return': None, 'oos_success_rate': None, 'oos_count': 0}
    if returns_df is None or returns_df.empty:
        return empty

    df = returns_df.sort_values('date').reset_index(drop=True)
    idxs = [data_index.get_loc(d) for d in df['date']]
    oos = []
    for k in range(len(df)):
        best_p, best_score = None, None
        for p in grid:
            col = f'return_{p}'
            if col not in df:
                continue
            prior = [df.at[j, col] for j in range(k)
                     if idxs[j] + p <= idxs[k] and pd.notna(df.at[j, col])]
            if len(prior) < min_prior:
                continue
            score = float(np.mean(prior))
            if best_score is None or (score > best_score if bullish else score < best_score):
                best_p, best_score = p, score
        if best_p is None:
            continue
        value = df.at[k, f'return_{best_p}']
        if pd.notna(value):
            oos.append(float(value))

    if not oos:
        return empty
    wins = [r > 0 for r in oos] if bullish else [r < 0 for r in oos]
    return {
        'oos_avg_return': round(float(np.mean(oos)), 2),
        'oos_success_rate': round(float(np.mean(wins) * 100), 2),
        'oos_count': len(oos),
    }


def add_signal_stats(result, returns_df, data_frame, bullish=True):
    """Add baseline, excess return, per-row best period and walk-forward OOS fields to an evaluation result."""
    baseline = baseline_returns(data_frame['Close'])
    for p in BEST_PERIOD_GRID:
        result[f'baseline_return_{p}'] = baseline[p]
        avg = result.get(f'avg_return_{p}')
        has_samples = result.get(f'test_count_{p}', 0) > 0
        result[f'excess_return_{p}'] = round(avg - baseline[p], 2) if has_samples and pd.notna(baseline[p]) else None

    best = choose_best_period(result, BEST_PERIOD_GRID, bullish)
    result['best_period'] = best
    result['best_excess_return'] = result.get(f'excess_return_{best}') if best is not None else None

    result.update(walk_forward_oos(returns_df, data_frame.index, bullish=bullish))
    return result


def choose_best_period(row, grid, bullish=True, min_samples=MIN_SAMPLES):
    """Period in `grid` with the best excess return among periods with at least `min_samples` signals."""
    best_p, best_val = None, None
    for p in grid:
        val = row.get(f'excess_return_{p}')
        if val is None or pd.isna(val) or row.get(f'test_count_{p}', 0) < min_samples:
            continue
        if best_val is None or (val > best_val if bullish else val < best_val):
            best_p, best_val = p, val
    return best_p


def select_best_rows(df, grid, bullish=True, one_per_ticker=True):
    """
    Pick a best holding period per row from `grid`, keep rows that beat the baseline by
    MIN_EXCESS_RETURN with at least 50% success rate and whose walk-forward out-of-sample
    return points the same way, and (optionally) the best row per ticker.

    Note: on 60 simulated random-walk stocks, about half still passed the in-sample filters;
    the out-of-sample gate removes only some of them. Per-stock results on ~2 years of data stay noisy.
    """
    if df.empty:
        return df.copy()
    rows = []
    for _, row in df.iterrows():
        row = row.to_dict()
        p = choose_best_period(row, grid, bullish)
        if p is None:
            continue
        row['best_period'] = p
        row['avg_return'] = row[f'avg_return_{p}']
        row['exp_return'] = row[f'avg_return_{p}']
        row['excess_return'] = row[f'excess_return_{p}']
        row['baseline_return'] = row.get(f'baseline_return_{p}')
        row['success_rate'] = row[f'success_rate_{p}']
        row['test_count'] = row[f'test_count_{p}']
        rows.append(row)
    out = pd.DataFrame(rows)
    if out.empty:
        return out

    if bullish:
        out = out[out['excess_return'] >= MIN_EXCESS_RETURN]
    else:
        out = out[out['excess_return'] <= -MIN_EXCESS_RETURN]
    out = out[out['success_rate'] >= 50]
    oos = pd.to_numeric(out.get('oos_avg_return'), errors='coerce')
    oos_count = pd.to_numeric(out.get('oos_count'), errors='coerce').fillna(0)
    out = out[(oos_count >= MIN_OOS_COUNT) & ((oos > 0) if bullish else (oos < 0))]
    if out.empty or not one_per_ticker:
        return out

    key = out['excess_return'] if bullish else -out['excess_return']
    return out.loc[key.groupby(out['ticker']).idxmax()]
