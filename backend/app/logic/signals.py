"""
CD / MC signal definition
=========================
The one place that decides which bars carry a CD (buy) or MC (sell) signal, their score and
whether they are HQ. The analysis, the resonance (1234) tables, the API charts and the summary
report all call compute_signals, so a signal means the same thing everywhere.
"""

import pandas as pd

from app.logic.indicators import (
    compute_cd_indicator, compute_mc_indicator, compute_cd_score, compute_mc_score,
    compute_cd_break_through, compute_mc_break_through,
)
from app.logic.hq_filters import compute_high_return_cd, compute_high_return_mc, compute_trend_regime
from app.logic.scoring_config import get_config, DEFAULT_CONFIG
from app.logic.data_loader import unfinished_bars

SIDES = {
    'cd': (compute_cd_indicator, compute_cd_score, compute_cd_break_through, compute_high_return_cd),
    'mc': (compute_mc_indicator, compute_mc_score, compute_mc_break_through, compute_high_return_mc),
}

# Breakthrough HQ: a breakthrough on the signal bar or on any of the previous HQ_RECENT_BARS bars
HQ_RECENT_BARS = 10

# How far back (calendar days) signals are evaluated in the result tables and shown on the price charts,
# so a table's counts match what its chart shows. Older signals may no longer apply.
# Set per interval in the configuration (evaluation.lookback_days).
DEFAULT_SIGNAL_LOOKBACK_DAYS = 365


def signal_lookback_days(interval, config=None):
    if config is None:
        config = get_config()
    days = config.get('evaluation', DEFAULT_CONFIG['evaluation'])['lookback_days']
    return days.get(interval, DEFAULT_SIGNAL_LOOKBACK_DAYS)


def opposite(side):
    return 'mc' if side == 'cd' else 'cd'


def compute_signals(df, side, config=None, interval=None):
    """
    Signals for one side ('cd' or 'mc') on an OHLCV frame.

    Args:
        df: OHLCV DataFrame
        side: 'cd' or 'mc'
        config: scoring config (defaults to the saved config); a report passes the config of its run
        interval: when given, no signal on a bar that is still forming at the moment; also picks the
                  interval's thresholds of the trend_regime HQ filter (daily ones when not given)

    Returns DataFrame indexed like df:
        raw:          the indicator fired
        score:        0-100 signal score (NaN where the indicator did not fire)
        signal:       raw and score >= threshold; this is "a signal" everywhere in the app
        breakthrough: HQ breakthrough event on this bar
        hq:           signal that also passes the configured HQ algorithm
    """
    if config is None:
        config = get_config()
    indicator_fn, score_fn, breakthrough_fn, high_return_fn = SIDES[side]
    weights = config[f'{side}_component_weights']

    raw = indicator_fn(df).fillna(False).infer_objects(copy=False).astype(bool)
    score = score_fn(df, weights=(weights['divergence'], weights['price_position'], weights['volume']))
    signal = raw & score.ge(config[f'{side}_threshold'])
    if interval is not None:
        signal &= ~unfinished_bars(df.index, interval)

    breakthrough = breakthrough_fn(df).fillna(False).astype(bool)
    if config.get('hq_algorithm') == 'high_return':
        hq = signal & high_return_fn(df, signal, **config['hq_high_return'])
    elif config.get('hq_algorithm') == 'trend_regime':
        hq = signal & compute_trend_regime(df, signal, side, interval, **config['hq_trend_regime'])
    else:
        recent = breakthrough.astype(int).rolling(HQ_RECENT_BARS, min_periods=1).max().shift(1).fillna(0).astype(bool)
        hq = signal & (breakthrough | recent)

    return pd.DataFrame({
        'raw': raw,
        'score': score,
        'signal': signal,
        'breakthrough': breakthrough,
        'hq': hq.astype(bool),
    }, index=df.index)
