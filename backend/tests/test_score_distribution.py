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


def test_company_breadth_counts_distinct_tickers_per_day():
    from app.logic.stock_analyzer import aggregate_company_breadth
    rows = [
        {'ticker': 'A', 'interval': '1h', 'signal_date': '2026-10-01 10:30:00'},
        {'ticker': 'A', 'interval': '1d', 'signal_date': '2026-10-01 00:00:00'},
        {'ticker': 'B', 'interval': '4h', 'signal_date': '2026-10-01 13:30:00'},
        {'ticker': 'C', 'interval': '1d', 'signal_date': '2026-10-02 00:00:00'},
    ]
    assert aggregate_company_breadth(rows) == [{'date': '2026-10-01', 'count': 2, 'tickers': ['A', 'B']},
                                               {'date': '2026-10-02', 'count': 1, 'tickers': ['C']}]
    assert aggregate_company_breadth(rows, ticker_list=['B', 'C']) == [{'date': '2026-10-01', 'count': 1, 'tickers': ['B']},
                                                                       {'date': '2026-10-02', 'count': 1, 'tickers': ['C']}]
    assert aggregate_company_breadth([]) == []


def test_company_breadth_keeps_per_ticker_interval_scores():
    from app.logic.stock_analyzer import aggregate_company_breadth
    rows = [
        {'ticker': 'A', 'interval': '1h', 'signal_date': '2026-10-01 10:30:00', 'indicator_score': 30},
        {'ticker': 'A', 'interval': '1h', 'signal_date': '2026-10-01 14:30:00', 'indicator_score': 10},
        {'ticker': 'A', 'interval': '1d', 'signal_date': '2026-10-01 00:00:00', 'indicator_score': 50},
        {'ticker': 'B', 'interval': '4h', 'signal_date': '2026-10-01 13:30:00', 'indicator_score': None},
    ]
    out = aggregate_company_breadth(rows)
    assert out == [{'date': '2026-10-01', 'count': 2, 'tickers': ['A', 'B'],
                    'scores': {'A': {'1h': 40.0, '1d': 50.0}}}]


def test_stock_weights_roundtrip(tmp_path, monkeypatch):
    from app.services import stock_weights as W
    monkeypatch.setattr(W, 'DATA_DIR', str(tmp_path))
    assert W.load_weights('stocks_x.tab') == {}
    saved = W.save_weights('stocks_x.tab', {'aapl': 3.0, 'MSFT': 2, ' ': 1, 'BAD': -1})
    assert saved == {'AAPL': 3.0, 'MSFT': 2.0}
    assert W.load_weights('stocks_x.tab') == saved
    monkeypatch.setattr(W, '_market_cap', lambda t: {'AAPL': 10.0}.get(t))
    assert W.fetch_market_caps(['AAPL', 'ZZZ']) == ({'AAPL': 10.0}, ['ZZZ'])


def test_refresh_market_cap_weights_keeps_old_for_missing(tmp_path, monkeypatch):
    from app.services import stock_weights as sw
    monkeypatch.setattr(sw, 'DATA_DIR', str(tmp_path))
    lst = tmp_path / 'demo.tab'
    lst.write_text('AAA\nBBB\nCCC\n')
    sw.save_weights(str(lst), {'BBB': 5, 'CCC': 7})
    monkeypatch.setattr(sw, 'fetch_market_caps', lambda t, workers=8: ({'AAA': 100.0, 'CCC': 9.0}, ['BBB']))
    out = sw.refresh_market_cap_weights(str(lst))
    assert out == {'AAA': 100.0, 'BBB': 5.0, 'CCC': 9.0}
    assert sw.load_weights(str(lst)) == out
