"""
Per-ticker weights of a stock list (e.g. market cap), kept next to the list as
<list file>.weights.json = {"AAPL": 3.4e12, ...}. Used for the weighted breadth score.
"""
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor

import time

import yfinance as yf

from app.logic.data_loader import call_with_rate_limit_retry, is_rate_limit_error

logger = logging.getLogger(__name__)

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data"))


def weights_path(list_file):
    return os.path.join(DATA_DIR, f"{os.path.basename(list_file)}.weights.json")


def load_weights(list_file):
    path = weights_path(list_file)
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        return {str(k).upper(): float(v) for k, v in data.items() if v is not None and float(v) >= 0}
    except Exception as e:
        logger.warning(f"Could not read weights {path}: {e}")
        return {}


def save_weights(list_file, weights):
    clean = {str(k).strip().upper(): float(v) for k, v in weights.items() if str(k).strip() and v is not None and float(v) >= 0}
    with open(weights_path(list_file), 'w') as f:
        json.dump(clean, f, indent=1, sort_keys=True)
    return clean


def _market_cap_once(ticker):
    t = yf.Ticker(ticker)
    try:
        cap = t.fast_info['marketCap']
    except Exception as e:
        if is_rate_limit_error(e):
            raise
        cap = None
    if not cap:
        cap = (t.info or {}).get('marketCap')
    return cap


def _market_cap(ticker):
    try:
        cap = call_with_rate_limit_retry(_market_cap_once, ticker, label=f'{ticker} market cap')
        return float(cap) if cap and cap > 0 else None
    except Exception as e:
        logger.warning(f"Market cap lookup failed for {ticker}: {e}")
        return None


def fetch_market_caps(tickers, workers=4):
    """{ticker: market cap} for the tickers yfinance knows, and the list of tickers it could not size."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        caps = dict(zip(tickers, pool.map(_market_cap, tickers)))
    found = {t: c for t, c in caps.items() if c}
    return found, [t for t in tickers if t not in found]


MARKET_CAP_MAX_AGE = 12 * 3600  # seconds; market caps move slowly, so refresh at most twice a day


def refresh_market_cap_weights(list_file, tickers=None, max_age=MARKET_CAP_MAX_AGE):
    """Re-fetch market caps for a stock list and save them as its weights, unless they were
    refreshed within the last max_age seconds.
    Tickers whose market cap can't be fetched keep their previous weight. Never raises."""
    try:
        if tickers is None:
            with open(list_file) as f:
                tickers = [l.strip() for l in f if l.strip()]
        tickers = list(dict.fromkeys(t.upper() for t in tickers))
        if not tickers:
            return {}
        old = load_weights(list_file)
        path = weights_path(list_file)
        if max_age and os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age:
            return old
        found, missing = fetch_market_caps(tickers)

        merged = {t: found.get(t, old.get(t)) for t in tickers if t in found or t in old}
        saved = save_weights(list_file, merged)
        logger.info(f"Updated market-cap weights for {os.path.basename(list_file)}: "
                    f"{len(found)}/{len(tickers)} fetched" + (f", missing {missing}" if missing else ""))
        return saved
    except Exception as e:
        logger.warning(f"Market-cap weight refresh failed for {list_file}: {e}")
        return {}


CAP_HISTORY_STEP = 5  # trading days between samples (market caps move slowly)


def cap_history_path(list_file):
    return os.path.join(DATA_DIR, f"{os.path.basename(list_file)}.cap_history.json")


def build_cap_history(list_file, tickers=None):
    """Each ticker's daily close relative to its latest close, sampled every CAP_HISTORY_STEP
    trading days back from the latest day, saved next to the list. Today's market-cap weight
    times this ratio approximates the market cap on that day (shares outstanding taken as
    constant). Ratios are integers in 1/10000; null before the ticker had data (e.g. an IPO).
    Returns {"dates": [...], "ratios": {ticker: [...]}}. Never raises."""
    empty = {"dates": [], "ratios": {}}
    try:
        import pandas as pd
        from app.db.database import SessionLocal
        from app.db.models import PriceBar
        if tickers is None:
            with open(os.path.join(DATA_DIR, os.path.basename(list_file))) as f:
                tickers = [l.strip() for l in f if l.strip()]
        tickers = list(dict.fromkeys(t.upper() for t in tickers if not t.startswith('^')))
        if not tickers:
            return empty
        db = SessionLocal()
        try:
            rows = db.query(PriceBar.ticker, PriceBar.timestamp, PriceBar.close).filter(
                PriceBar.interval == '1d', PriceBar.ticker.in_(tickers)).all()
        finally:
            db.close()
        if not rows:
            return empty
        df = pd.DataFrame(rows, columns=['ticker', 'ts', 'close']).dropna()
        df['date'] = pd.to_datetime(df['ts']).dt.strftime('%Y-%m-%d')
        closes = df.pivot_table(index='date', columns='ticker', values='close', aggfunc='last').sort_index().ffill()
        ratios = closes / closes.iloc[-1]
        dates = list(ratios.index)[::-1][::CAP_HISTORY_STEP][::-1]
        sampled = ratios.loc[dates]
        out = {"dates": dates, "ratios": {
            t: [None if pd.isna(v) else int(round(float(v) * 10000)) for v in sampled[t]] for t in sampled.columns}}
        with open(cap_history_path(list_file), 'w') as f:
            json.dump(out, f, separators=(',', ':'))
        logger.info(f"Saved cap history for {os.path.basename(list_file)}: {len(out['ratios'])} tickers, {len(dates)} samples")
        return out
    except Exception as e:
        logger.warning(f"Cap history failed for {list_file}: {e}")
        return empty


def load_cap_history(list_file):
    """Saved cap history of a list, built on first use."""
    path = cap_history_path(list_file)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not read cap history {path}: {e}")
    return build_cap_history(list_file)
