"""
US Treasury yields (3-month, 2-year, 10-year) from FRED's public CSV download (no API key).
Cached in data/bond_yields.json and refreshed at most every few hours.
"""
import io
import json
import logging
import os
import time

import pandas as pd
import requests

logger = logging.getLogger(__name__)

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data"))
CACHE_PATH = os.path.join(DATA_DIR, "bond_yields.json")
REFRESH_SECONDS = 6 * 3600
SERIES = {"y3m": "DGS3MO", "y2y": "DGS2", "y10y": "DGS10"}
START = "2000-01-01"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={start}"


def _fetch_series(sid):
    resp = requests.get(FRED_URL.format(sid=sid, start=START), timeout=30,
                        headers={"User-Agent": "Mozilla/5.0 (WaveCatcher)"})
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    date_col = df.columns[0]
    values = pd.to_numeric(df[sid], errors="coerce")  # FRED marks holidays with "."
    return pd.Series(values.values, index=df[date_col].astype(str)).dropna()


def _fetch_yahoo():
    """Fallback when FRED is unreachable: Yahoo has the 13-week and 10-year yields, but no 2-year."""
    import yfinance as yf
    cols = {}
    for key, symbol in (("y3m", "^IRX"), ("y10y", "^TNX")):
        hist = yf.Ticker(symbol).history(start=START, auto_adjust=False)
        if hist is not None and not hist.empty:
            cols[key] = pd.Series(hist["Close"].values, index=hist.index.strftime("%Y-%m-%d"))
    return cols


def _fetch_all():
    try:
        cols = {key: _fetch_series(sid) for key, sid in SERIES.items()}
    except Exception as e:
        logger.warning(f"FRED unavailable ({e}); using Yahoo yields without the 2-year")
        cols = _fetch_yahoo()
    df = pd.DataFrame(cols, columns=list(SERIES)).sort_index()
    df = df.dropna(how="all")
    rows = []
    for date, r in df.iterrows():
        row = {"date": date}
        for key in SERIES:
            v = r.get(key)
            row[key] = None if pd.isna(v) else round(float(v), 3)
        rows.append(row)
    return rows


def _read_cache():
    try:
        with open(CACHE_PATH) as f:
            return json.load(f)
    except Exception:
        return None


def load_bond_yields():
    """Daily yields in percent: [{date, y3m, y2y, y10y}], oldest first."""
    cache = _read_cache()
    if cache and time.time() - cache.get("fetched_at", 0) < REFRESH_SECONDS:
        return cache.get("rows", [])
    try:
        rows = _fetch_all()
        if rows:
            with open(CACHE_PATH, "w") as f:
                json.dump({"fetched_at": time.time(), "rows": rows}, f)
            return rows
    except Exception as e:
        logger.warning(f"Could not fetch bond yields: {e}")
    return (cache or {}).get("rows", [])
