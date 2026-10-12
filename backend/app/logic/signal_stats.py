"""
Signal statistics helpers
=========================
Shared by the CD/MC evaluation modules and the result tables in stock_analyzer.

Why this exists: picking the best of 101 holding periods on a handful of signals
almost always finds a "good" period even for random signals. To keep the numbers
honest we
  - only consider a small fixed grid of holding periods,
  - measure each signal's excess return against the rest of the stock list over the
    same bars (a stock's own average return is biased: its averaging windows overlap the
    move that triggered the signal),
  - pool all signals of the stock list per interval and holding period, and only trust
    an interval/period whose pooled excess return is clearly different from zero,
  - require a minimum number of samples per stock, and
  - report a walk-forward out-of-sample result where each signal's holding period
    is chosen using only signals whose outcome was already known at that time.
"""

import numpy as np
import pandas as pd

# Holding periods (in bars) eligible as "best period"
BEST_PERIOD_GRID = [1, 2, 3, 5, 10, 15, 20, 30, 50, 100]

# Minimum signals measured at a period before it can be chosen as best
MIN_SAMPLES = 5

# Minimum excess return (%) over the rest of the stock list for the result tables
MIN_EXCESS_RETURN = 5.0

# Minimum earlier signals needed before a walk-forward choice is made
MIN_PRIOR_SIGNALS = 2

# Minimum walk-forward out-of-sample trades required for the result tables
MIN_OOS_COUNT = 3

# Pooled (whole stock list) test: an interval/period has an edge when the mean excess return
# over all signals is at least POOLED_MIN_T standard errors from zero, with standard errors
# clustered by ticker (signals of one stock overlap and are not independent).
# 3.0 rather than 2.0 because ~50 interval x period cells are tested per side: on 60 random-walk
# stocks 2.0 still flagged 3 cells, 3.0 flagged none, while an injected +4% edge passed in 9 of 10 cells.
POOLED_MIN_T = 3.0
POOLED_MIN_TICKERS = 10

# Only keep per-stock results whose interval/period shows a pooled edge
REQUIRE_POOLED_EDGE = False


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
    """
    Add per-signal data needed for the stock-list baseline (signal timestamps and the return at
    each grid period, aligned) and the walk-forward out-of-sample fields to an evaluation result.
    """
    if returns_df is None or returns_df.empty:
        result['signal_dates'] = []
    else:
        df = returns_df.sort_values('date')
        result['signal_dates'] = [pd.Timestamp(d).isoformat() for d in df['date']]
        for p in BEST_PERIOD_GRID:
            col = f'return_{p}'
            result[f'grid_returns_{p}'] = [None if pd.isna(v) else float(v) for v in df[col]] if col in df else []
    result.update(walk_forward_oos(returns_df, data_frame.index, bullish=bullish))
    return result


def universe_forward_returns(all_ticker_data, interval, grid=BEST_PERIOD_GRID):
    """
    For one interval, per period p: (sum, count) of every stock's forward return (%) from each bar,
    indexed by bar timestamp. Used to get "the rest of the stock list" over the same bars.
    """
    per_p = {p: [] for p in grid}
    for ticker, data in all_ticker_data.items():
        df = data.get(interval) if isinstance(data, dict) else None
        if df is None or df.empty or 'Close' not in df:
            continue
        close = df['Close'].astype(float)
        close = close[~close.index.duplicated()]
        for p in grid:
            per_p[p].append(((close.shift(-p) / close - 1) * 100).rename(ticker))
    result = {}
    for p, series in per_p.items():
        if not series:
            continue
        frame = pd.concat(series, axis=1)
        result[p] = (frame.sum(axis=1, min_count=1), frame.count(axis=1))
    return result


def apply_universe_baseline(eval_results, all_ticker_data, bullish=True):
    """
    Fill per-row excess returns against the rest of the stock list over the same bars:
      excess_returns_{p}: per-signal excess list, excess_return_{p}: its mean,
      baseline_return_{p}: mean return of the other stocks over those same windows,
    plus best_period / best_excess_return from the full grid. Rows are updated in place.
    """
    cache = {}
    for row in eval_results:
        interval = row.get('interval')
        if interval not in cache:
            cache[interval] = universe_forward_returns(all_ticker_data, interval)
        universe = cache[interval]
        ticker = row.get('ticker')
        dates = [pd.Timestamp(d) for d in row.get('signal_dates') or []]
        own_close = None
        if ticker in all_ticker_data and isinstance(all_ticker_data[ticker], dict):
            own_df = all_ticker_data[ticker].get(interval)
            if own_df is not None and not own_df.empty:
                own_close = own_df['Close'].astype(float)
                own_close = own_close[~own_close.index.duplicated()]

        for p in BEST_PERIOD_GRID:
            excess, base = [], []
            returns = row.get(f'grid_returns_{p}') or []
            if p in universe and dates and own_close is not None:
                total, count = universe[p]
                own_fwd = (own_close.shift(-p) / own_close - 1) * 100
                for d, r in zip(dates, returns):
                    if r is None or d not in total.index:
                        continue
                    own = own_fwd.get(d, np.nan)
                    n_others = count.get(d, 0) - (0 if pd.isna(own) else 1)
                    if n_others < 1:
                        continue
                    others = (total.get(d) - (0 if pd.isna(own) else own)) / n_others
                    excess.append(r - others)
                    base.append(others)
            row[f'excess_returns_{p}'] = [round(float(x), 3) for x in excess]
            row[f'excess_return_{p}'] = round(float(np.mean(excess)), 2) if excess else None
            row[f'baseline_return_{p}'] = round(float(np.mean(base)), 2) if base else None
            # sample size of the excess measurement
            row[f'excess_count_{p}'] = len(excess)

        best = choose_best_period(row, BEST_PERIOD_GRID, bullish)
        row['best_period'] = best
        row['best_excess_return'] = row.get(f'excess_return_{best}') if best is not None else None
    return eval_results


def choose_best_period(row, grid, bullish=True, min_samples=MIN_SAMPLES):
    """Period in `grid` with the best excess return among periods with at least `min_samples` signals."""
    best_p, best_val = None, None
    for p in grid:
        val = row.get(f'excess_return_{p}')
        if val is None or pd.isna(val) or row.get(f'excess_count_{p}', 0) < min_samples:
            continue
        if best_val is None or (val > best_val if bullish else val < best_val):
            best_p, best_val = p, val
    return best_p


def pooled_stats(df_eval, grid=BEST_PERIOD_GRID, bullish=True):
    """
    Pool every signal of the stock list per interval and holding period.

    Uses each signal's excess return over the rest of the stock list. The mean gets a
    ticker-clustered standard error, a 95% interval and a t value.
    Returns a list of dict rows (one per interval x period).
    """
    rows = []
    if df_eval.empty:
        return rows
    for interval, group in df_eval.groupby('interval'):
        for p in grid:
            col = f'excess_returns_{p}'
            if col not in group:
                continue
            per_ticker = [np.asarray(x, dtype=float) for x in group[col] if isinstance(x, list) and x]
            n = sum(len(x) for x in per_ticker)
            if n == 0:
                continue
            mean = float(np.concatenate(per_ticker).mean())
            k = len(per_ticker)
            # Cluster-robust (by ticker) standard error of the mean
            se = float(np.sqrt(sum((x - mean).sum() ** 2 for x in per_ticker)) / n) if k > 1 else np.nan
            t = mean / se if se and se > 0 else np.nan
            wins = float(np.mean([v > 0 if bullish else v < 0 for x in per_ticker for v in x]) * 100)
            significant = bool(k >= POOLED_MIN_TICKERS and pd.notna(t) and (t >= POOLED_MIN_T if bullish else t <= -POOLED_MIN_T))
            rows.append({
                'interval': interval,
                'period': p,
                'signals': n,
                'tickers': k,
                'mean_excess_return': round(mean, 3),
                'ci95_low': round(mean - 1.96 * se, 3) if pd.notna(se) else None,
                'ci95_high': round(mean + 1.96 * se, 3) if pd.notna(se) else None,
                't_stat': round(t, 2) if pd.notna(t) else None,
                'beat_market_rate': round(wins, 1),
                'has_edge': significant,
            })
    return rows


def pooled_edges(pooled_rows):
    """{(interval, period): mean_excess_return} for interval/periods with a pooled edge."""
    return {(r['interval'], r['period']): r['mean_excess_return'] for r in pooled_rows if r['has_edge']}


def select_best_rows(df, grid, bullish=True, one_per_ticker=True, edges=None):
    """
    Pick a best holding period per row from `grid`, keep rows that beat the rest of the stock list by
    MIN_EXCESS_RETURN with at least 50% success rate and whose walk-forward out-of-sample
    return points the same way, and (optionally) the best row per ticker.

    Per-stock results on ~2 years of data are noisy, so with REQUIRE_POOLED_EDGE only periods where
    the whole stock list shows an edge (`edges`, from pooled_edges) can be chosen for an interval.
    """
    if df.empty:
        return df.copy()
    rows = []
    for _, row in df.iterrows():
        row = row.to_dict()
        row_grid = grid
        if REQUIRE_POOLED_EDGE and edges is not None:
            row_grid = [p for p in grid if (row['interval'], p) in edges]
        p = choose_best_period(row, row_grid, bullish)
        if p is None:
            continue
        row['best_period'] = p
        row['avg_return'] = row[f'avg_return_{p}']
        row['exp_return'] = row[f'avg_return_{p}']
        row['excess_return'] = row[f'excess_return_{p}']
        row['baseline_return'] = row.get(f'baseline_return_{p}')
        row['success_rate'] = row[f'success_rate_{p}']
        row['test_count'] = row[f'test_count_{p}']
        row['pooled_excess_return'] = edges.get((row['interval'], p)) if edges is not None else None
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
