"""First stored daily bar of each ticker whose history starts late (e.g. a recent IPO)."""
import time

import pandas as pd
from sqlalchemy import text

_cache = {'key': None, 'at': 0.0, 'value': None}
_TTL = 600  # seconds; analysis jobs write prices from another process


def ticker_first_dates(db):
    """{ticker: YYYY-MM-DD} for tickers whose history starts later than the earliest one. Breadth
    shares and scores divide by the stocks that were trading on each day, so a stock does not
    dilute the days before it had data."""
    # Prices change when an analysis run starts or finishes, so the runs table keys the cache
    key = tuple(db.execute(text("SELECT max(id), count(*), sum(status = 'completed') FROM analysis_runs")).fetchone())
    if _cache['key'] == key and time.time() - _cache['at'] < _TTL:
        return _cache['value']
    _cache.update(key=key, at=time.time(), value=_compute(db))
    return _cache['value']


def _compute(db):
    # A GROUP BY over all ~30M bars takes seconds; stepping ticker to ticker through the
    # indexes takes one seek each.
    firsts, ticker = {}, ''
    while True:
        row = db.execute(text("SELECT ticker FROM price_history WHERE ticker > :t ORDER BY ticker LIMIT 1"), {'t': ticker}).fetchone()
        if not row:
            break
        ticker = row[0]
        ts = db.execute(text("SELECT min(timestamp) FROM price_history WHERE ticker = :t AND interval = '1d'"), {'t': ticker}).scalar()
        if ts is not None:
            firsts[ticker] = pd.Timestamp(ts).strftime('%Y-%m-%d')
    if not firsts:
        return {}
    # a week of slack: tickers whose stored history starts a few days later still count from the start
    cutoff = (pd.Timestamp(min(firsts.values())) + pd.Timedelta(days=7)).strftime('%Y-%m-%d')
    return {t: d for t, d in firsts.items() if d > cutoff}
