"""Score distribution: per-ticker histograms of every indicator firing and their total over a run."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.logic import score_distribution as SD  # noqa: E402
from app.logic.resonance import process_ticker_1234  # noqa: E402
from app.logic.signals import compute_signals  # noqa: E402


def test_score_histogram_bins():
    counts = SD.score_histogram([0, 0.9, 1, 52.5, 100, np.nan])
    assert len(counts) == 100
    assert counts[0] == 2 and counts[1] == 1 and counts[52] == 1 and counts[99] == 1
    assert sum(counts) == 5


def test_aggregate_sums_tickers_and_skips_missing():
    a = {'_score_hist': {'cd': {'1d': [1] * 100}, 'mc': {'1h': [2] * 100}}}
    b = {'_score_hist': {'cd': {'1d': [3] * 100}, 'mc': {}}}
    out = SD.aggregate_score_histograms({'A': a, 'B': b, 'C': {}})
    assert out['tickers'] == 2
    assert out['bins'][:3] == [0, 1, 2] and out['bin_width'] == 1
    assert out['cd']['1d'] == [4] * 100 and out['cd']['1h'] == [0] * 100
    assert out['mc']['1h'] == [2] * 100


def test_process_ticker_fills_histogram_with_all_firings():
    rng = np.random.default_rng(0)
    idx = pd.bdate_range('2023-01-02', periods=500)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.02, len(idx)))), index=idx)
    df = pd.DataFrame({'Open': close.shift(1).fillna(close), 'High': close * 1.01, 'Low': close * 0.99,
                       'Close': close, 'Volume': rng.integers(1e5, 1e6, len(idx))}, index=idx)
    hist = {}
    process_ticker_1234('T', {'1d': df}, side='cd', score_hist=hist)
    raw = compute_signals(df, 'cd')
    assert sum(hist['1d']) == int(raw['raw'].sum())
