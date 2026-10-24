"""
Per-ticker weights of a stock list (e.g. market cap), kept next to the list as
<list file>.weights.json = {"AAPL": 3.4e12, ...}. Used for the weighted breadth score.
"""
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor

import yfinance as yf

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


def _market_cap(ticker):
    try:
        t = yf.Ticker(ticker)
        cap = None
        try:
            cap = t.fast_info.get('market_cap') if hasattr(t.fast_info, 'get') else t.fast_info.market_cap
        except Exception:
            cap = None
        if not cap:
            cap = (t.info or {}).get('marketCap')
        return float(cap) if cap and cap > 0 else None
    except Exception as e:
        logger.warning(f"Market cap lookup failed for {ticker}: {e}")
        return None


def fetch_market_caps(tickers, workers=8):
    """{ticker: market cap} for the tickers yfinance knows, and the list of tickers it could not size."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        caps = dict(zip(tickers, pool.map(_market_cap, tickers)))
    found = {t: c for t, c in caps.items() if c}
    return found, [t for t in tickers if t not in found]


def refresh_market_cap_weights(list_file, tickers=None):
    """Re-fetch market caps for a stock list and save them as its weights.
    Tickers whose market cap can't be fetched keep their previous weight. Never raises."""
    try:
        if tickers is None:
            with open(list_file) as f:
                tickers = [l.strip() for l in f if l.strip()]
        tickers = list(dict.fromkeys(t.upper() for t in tickers))
        if not tickers:
            return {}
        found, missing = fetch_market_caps(tickers, workers=16)
        old = load_weights(list_file)
        merged = {t: found.get(t, old.get(t)) for t in tickers if t in found or t in old}
        saved = save_weights(list_file, merged)
        logger.info(f"Updated market-cap weights for {os.path.basename(list_file)}: "
                    f"{len(found)}/{len(tickers)} fetched" + (f", missing {missing}" if missing else ""))
        return saved
    except Exception as e:
        logger.warning(f"Market-cap weight refresh failed for {list_file}: {e}")
        return {}
