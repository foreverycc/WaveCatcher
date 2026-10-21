"""
Distribution of CD/MC signal scores, to help pick the score thresholds.

Each analysis run counts, per side and interval, every bar where the indicator fired (before the
score threshold is applied) into 1-point score bins, and saves the totals over all tickers.
"""
import numpy as np

BIN_WIDTH = 1  # finest resolution; the chart merges bins to the width picked there
BIN_EDGES = np.arange(0, 100 + BIN_WIDTH, BIN_WIDTH)  # 0, 1, ..., 100 (last bin includes 100)
INTERVALS = ['1h', '2h', '3h', '4h', '1d']


def score_histogram(scores):
    """Counts of scores per bin, as a list of ints."""
    values = np.asarray(scores, dtype=float)
    values = values[~np.isnan(values)]
    counts, _ = np.histogram(np.clip(values, 0, 100), bins=BIN_EDGES)
    return counts.astype(int).tolist()


def aggregate_score_histograms(all_ticker_data):
    """Sum the per-ticker histograms (stored under data['_score_hist']) into one per side and interval."""
    n_bins = len(BIN_EDGES) - 1
    totals = {side: {intv: [0] * n_bins for intv in INTERVALS} for side in ('cd', 'mc')}
    tickers = 0
    for data in all_ticker_data.values():
        hist = data.get('_score_hist') if isinstance(data, dict) else None
        if not hist:
            continue
        tickers += 1
        for side in ('cd', 'mc'):
            for intv, counts in (hist.get(side) or {}).items():
                if intv in totals[side] and len(counts) == n_bins:
                    totals[side][intv] = [a + b for a, b in zip(totals[side][intv], counts)]
    return {
        'bin_width': BIN_WIDTH,
        'bins': BIN_EDGES[:-1].astype(int).tolist(),
        'tickers': tickers,
        'cd': totals['cd'],
        'mc': totals['mc'],
    }
