"""
Offline tests for the CD/MC indicators and the shared signal definition.

Golden samples: put CSV files exported from Futu in tests/golden/ with columns
time, open, high, low, close, volume, cd, mc (cd / mc = 1 on bars where Futu shows the signal).
Each file is compared bar by bar with the Python port after the first 200 bars; without files that
test is skipped.
"""
import glob
import os
import sys

import numpy as np
import pandas as pd
import pytest

BACKEND = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(BACKEND, 'app', 'logic'))
sys.path.insert(0, BACKEND)

from app.logic import indicators as ind  # noqa: E402
from app.logic import signals as sg  # noqa: E402
from app.logic.signals import compute_signals  # noqa: E402
from app.logic.scoring_config import DEFAULT_CONFIG  # noqa: E402

GOLDEN_DIR = os.path.join(os.path.dirname(__file__), 'golden')


def random_ohlcv(seed, n=800):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.015, n)))
    open_ = np.r_[close[0], close[:-1]] * np.exp(rng.normal(0, 0.005, n))
    index = pd.bdate_range('2022-01-03', periods=n, tz='America/New_York')
    return pd.DataFrame({
        'Open': open_,
        'High': np.maximum(open_, close) * 1.01,
        'Low': np.minimum(open_, close) * 0.99,
        'Close': close,
        'Volume': rng.integers(100_000, 1_000_000, n).astype(float),
    }, index=index)


# --- reference (slow, literal) versions of the Futu functions ---

def ref_barslast(events):
    out, last = [], None
    for i, e in enumerate(events):
        if e:
            last = i
        out.append(0 if last is None else i - last)
    return np.array(out)


def ref_window(values, periods, fn):
    return np.array([fn(values[max(0, i - int(p) + 1):i + 1]) for i, p in enumerate(periods)])


def ref_ref(values, lags):
    return np.array([values[i - int(l)] if i - int(l) >= 0 else np.nan for i, l in enumerate(lags)])


@pytest.mark.parametrize('seed', range(5))
def test_vectorized_helpers_match_reference(seed):
    df = random_ohlcv(seed)
    close = df['Close']
    rng = np.random.default_rng(seed)
    events = pd.Series(rng.random(len(df)) < 0.05, index=df.index)

    barslast = ind._compute_barslast(events, len(df))
    assert np.array_equal(barslast.values, ref_barslast(events.values))

    periods = barslast + 1
    np.testing.assert_allclose(ind._compute_llv(close, periods).values, ref_window(close.values, periods.values, np.min))
    np.testing.assert_allclose(ind._compute_hhv(close, periods).values, ref_window(close.values, periods.values, np.max))
    np.testing.assert_allclose(ind._compute_ref(close, periods).values, ref_ref(close.values, periods.values), equal_nan=True)


@pytest.mark.parametrize('fn', [ind.compute_cd_indicator, ind.compute_mc_indicator])
def test_signals_do_not_repaint(fn):
    """A signal only depends on bars up to its own: cutting off later data never changes it."""
    df = random_ohlcv(7)
    full = fn(df).fillna(False).astype(bool)
    for end in [300, 450, 600]:
        part = fn(df.iloc[:end]).fillna(False).astype(bool)
        assert part.equals(full.iloc[:end])


@pytest.mark.parametrize('side', ['cd', 'mc'])
@pytest.mark.parametrize('algo', ['breakthrough', 'high_return'])
def test_compute_signals_definition(side, algo):
    config = {**DEFAULT_CONFIG, 'hq_algorithm': algo}
    df = random_ohlcv(3)
    s = compute_signals(df, side, config)
    assert s['raw'].any()
    assert not (s['signal'] & ~s['raw']).any()
    assert not (s['hq'] & ~s['signal']).any()
    assert (s.loc[s['signal'], 'score'] >= config[f'{side}_threshold']).all()
    # MACD warm-up: no signals in the first bars
    assert not s['raw'].iloc[:ind.MACD_WARMUP_BARS].any()


def test_no_signal_on_forming_bar():
    df = random_ohlcv(11)
    s = compute_signals(df, 'cd', DEFAULT_CONFIG)
    last = s.index[s['signal']][-1]
    # Pretend the analysis runs during the trading day of the last signal: that daily bar is still forming
    df = df.loc[:last]
    now = last.normalize() + pd.Timedelta(hours=12)
    original = sg.unfinished_bars
    try:
        sg.unfinished_bars = lambda index, interval: original(index, interval, now)
        masked = compute_signals(df, 'cd', DEFAULT_CONFIG, interval='1d')
    finally:
        sg.unfinished_bars = original
    assert not masked['signal'].iloc[-1]
    assert masked['signal'].iloc[:-1].equals(compute_signals(df, 'cd', DEFAULT_CONFIG)['signal'].iloc[:-1])


@pytest.mark.parametrize('path', sorted(glob.glob(os.path.join(GOLDEN_DIR, '*.csv'))) or [None])
def test_golden_samples_match_futu(path):
    if path is None:
        pytest.skip('no Futu exports in tests/golden')
    raw = pd.read_csv(path)
    df = pd.DataFrame({
        'Open': raw['open'], 'High': raw['high'], 'Low': raw['low'],
        'Close': raw['close'], 'Volume': raw['volume'],
    })
    df.index = pd.to_datetime(raw['time'], utc=True)
    for col, fn in [('cd', ind.compute_cd_indicator), ('mc', ind.compute_mc_indicator)]:
        ours = fn(df).fillna(False).astype(bool).values
        futu = raw[col].fillna(0).astype(bool).values
        # Skip the start: our warm-up suppresses early signals and EMAs depend on where the export begins
        start = 200
        mismatch = np.flatnonzero(ours[start:] != futu[start:]) + start
        assert len(mismatch) == 0, f'{os.path.basename(path)} {col}: differs at {list(df.index[mismatch][:10])}'
