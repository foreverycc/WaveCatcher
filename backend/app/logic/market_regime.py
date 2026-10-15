"""
Market regime for the HQ filter
===============================
Whether the market index (default ^SPX, daily) is at most `max_above_ema_pct` % above its EMA.
Backtests on the stock lists (2024-2026, train before / test after 2025-10) showed CD and MC signals
did better relative to the rest of the market when the index was near or below its EMA50.

Intraday bars use the previous completed trading day, a daily bar uses its own day (the signal is
taken at the close), so no bar sees market data from its future.
"""
import logging
import time

import pandas as pd

logger = logging.getLogger(__name__)

_CACHE = {}
_CACHE_SECONDS = 600


def _index_closes(symbol):
    hit = _CACHE.get(symbol)
    if hit and time.time() - hit[0] < _CACHE_SECONDS:
        return hit[1]
    closes = pd.Series(dtype=float)
    try:
        from app.logic.db_utils import load_price_history
        df = load_price_history(symbol, '1d')
        if not df.empty:
            closes = df['Close'].astype(float)
            closes.index = pd.DatetimeIndex(closes.index).normalize()
            closes = closes[~closes.index.duplicated(keep='last')].sort_index()
    except Exception as e:
        logger.warning(f"Market regime: could not load {symbol}: {e}")
    if closes.empty:
        logger.warning(f"Market regime: no daily data for {symbol}; the market condition is not applied")
    _CACHE[symbol] = (time.time(), closes)
    return closes


def market_ok(index, interval, symbol='^SPX', ema_period=50, max_above_ema_pct=1.0, closes=None):
    """
    Boolean array aligned to `index`: True where the market index closed at most max_above_ema_pct %
    above its EMA (on the bar's own day for '1d', the previous trading day for intraday bars).
    All True when no index data is available.
    """
    idx = pd.DatetimeIndex(index)
    if closes is None:
        closes = _index_closes(symbol)
    if closes is None or len(closes) < ema_period:
        return pd.Series(True, index=idx).values
    ema = closes.ewm(span=ema_period, adjust=False).mean()
    ok = (closes / ema - 1) * 100 <= max_above_ema_pct
    days = (idx.tz_localize(None) if idx.tz is not None else idx).normalize()
    if interval != '1d':
        days = days - pd.Timedelta(days=1)  # last completed day before the bar's day
    # as-of lookup: latest index day on or before `days`
    pos = ok.index.searchsorted(days, side='right') - 1
    vals = ok.values[pos.clip(0)]
    vals[pos < 0] = True
    return vals.astype(bool)
