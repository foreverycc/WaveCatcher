import os
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import logging
import traceback
from fastapi import APIRouter, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc, text, or_, and_

from app.services.engine import job_manager
from app.db.database import SessionLocal
from app.db.models import AnalysisRun, AnalysisResult, PriceBar, OptionChain
from app.logic.db_utils import save_price_history
from app.logic.options import get_option_data
from app.logic.scoring_config import get_config as get_scoring_config, save_config as save_scoring_config, DEFAULT_CONFIG as SCORING_DEFAULTS
from app.logic.signals import compute_signals, signal_lookback_days
from app.logic.fundamentals import ticker_quarterly, aggregate_quarterly, refresh_quarterly
from app.logic.earnings import refresh_earnings, ticker_earnings
from app.services.stock_weights import load_dma_breadth
from app.services.bond_yields import load_bond_yields

logger = logging.getLogger(__name__)

router = APIRouter()

import subprocess
import sys

@router.post("/update-indices")
def update_indices(body: Optional[Dict[str, Any]] = None):
    """Run the script to update index stock lists.
    
    Args:
        body: Optional JSON body with 'indices' key containing list of index keys
              to update. Valid keys: sp500, nasdaq100, dowjones, russell2000,
              soxx, xbi, igv, nasa, lyte, dram, qtup, kweb.
              If not specified, all indices are updated.
    """
    try:
        script_path = os.path.join("backend", "scripts", "fetch_indices.py")
        if not os.path.exists(script_path):
             script_path = os.path.join("scripts", "fetch_indices.py")

        if not os.path.exists(script_path):
            return {"status": "error", "message": f"Script not found at {script_path}"}

        cmd = [sys.executable, script_path]
        # Pass selected indices as arguments if specified.
        # Support mapping from index_config keys (SPX, QQQ, DJI, IWM, SPACE, LIGHT, SAAS, etc.)
        INDEX_KEY_MAP = {
            'spx': 'sp500',
            'sp500': 'sp500',
            'qqq': 'nasdaq100',
            'nasdaq100': 'nasdaq100',
            'dji': 'dowjones',
            'dowjones': 'dowjones',
            'iwm': 'russell2000',
            'russell2000': 'russell2000',
            'soxx': 'soxx',
            'xbi': 'xbi',
            'saas': 'igv',
            'igv': 'igv',
            'space': 'nasa',
            'nasa': 'nasa',
            'light': 'lyte',
            'lyte': 'lyte',
            'storage': 'dram',
            'dram': 'dram',
            'quantum': 'qtup',
            'qtup': 'qtup',
            'kweb': 'kweb',
        }
        if body and 'indices' in body and body['indices']:
            mapped_indices = []
            for k in body['indices']:
                clean_k = str(k).strip().lower()
                fetch_key = INDEX_KEY_MAP.get(clean_k, clean_k)
                mapped_indices.append(fetch_key)
            cmd.extend(mapped_indices)

        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            return {"status": "success", "message": "Indices updated successfully", "output": result.stdout}
        else:
            return {"status": "error", "message": "Script failed", "detail": result.stderr}
            
    except Exception as e:
        logger.error(f"Error updating indices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Index configuration - loaded dynamically from JSON file
from app.services.index_config import load_index_config, save_index_config

class AnalysisRequest(BaseModel):
    stock_list_file: str
    end_date: Optional[str] = None

class MultiIndexRequest(BaseModel):
    indices: List[str]  # e.g., ["SPX", "QQQ", "IWM"]
    end_date: Optional[str] = None

class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: int
    error: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    run_id: Optional[int] = None
    report: Optional[Dict[str, Any]] = None

@router.get("/indices")
def get_available_indices():
    """Get list of available indices for multi-index analysis."""
    index_config = load_index_config()
    data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data"))
    
    indices = []
    for key, config in index_config.items():
        tickers = []
        try:
            stock_list_path = os.path.join(data_dir, config["stock_list"])
            with open(stock_list_path, 'r') as f:
                tickers = [line.strip() for line in f if line.strip()]
                tickers = list(dict.fromkeys(tickers))  # Deduplicate
        except FileNotFoundError:
            logger.warning(f"Stock list not found for {key}: {config['stock_list']}")
        indices.append({
            "key": key, "symbol": config["symbol"],
            "stock_list": config["stock_list"],
            "whitelist": config.get("whitelist", []),
            "blacklist": config.get("blacklist", []),
            "tickers": tickers
        })
    
    return {"indices": indices}


class IndexConfigEntry(BaseModel):
    symbol: str
    stock_list: str
    whitelist: Optional[List[str]] = []
    blacklist: Optional[List[str]] = []


@router.put("/indices")
def update_all_indices(config: Dict[str, IndexConfigEntry]):
    """Replace the entire index configuration."""
    try:
        save_index_config({k: v.dict() for k, v in config.items()})
        return {"status": "success", "count": len(config)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/indices/{key}")
def upsert_index(key: str, entry: IndexConfigEntry):
    """Add or update a single index entry."""
    try:
        config = load_index_config()
        entry_data = entry.dict()
        clean = lambda items: sorted(dict.fromkeys(
            str(t).strip().upper().replace('.', '-') for t in (items or []) if t and str(t).strip()))
        cleaned_bl = clean(entry_data.get("blacklist", []))
        # a ticker on both lists is blocked: the blacklist wins
        cleaned_wl = [t for t in clean(entry_data.get("whitelist", [])) if t not in set(cleaned_bl)]
        entry_data["whitelist"] = cleaned_wl
        entry_data["blacklist"] = cleaned_bl
        previous = config.get(key, {})
        config[key] = entry_data
        save_index_config(config)

        # Sync the tab file: merge the whitelist, drop the blacklist. Tickers taken off the
        # blacklist come back with the next "Update Stock Lists".
        changed = cleaned_wl or cleaned_bl or previous.get("blacklist")
        if changed and entry.stock_list:
            data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data"))
            stock_list_path = os.path.join(data_dir, entry.stock_list)
            if os.path.exists(stock_list_path):
                try:
                    with open(stock_list_path, 'r') as f:
                        existing = [line.strip().upper().replace('.', '-') for line in f if line.strip()]
                    blocked = set(cleaned_bl)
                    merged = sorted(t for t in dict.fromkeys(existing + cleaned_wl) if t not in blocked)
                    if merged != sorted(dict.fromkeys(existing)):
                        with open(stock_list_path, 'w') as f:
                            for item in merged:
                                f.write(f"{item}\n")
                except Exception as ex:
                    logger.warning(f"Could not sync whitelist/blacklist to {entry.stock_list}: {ex}")

        return {"status": "success", "key": key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/indices/{key}")
def delete_index(key: str):
    """Remove an index entry."""
    config = load_index_config()
    if key not in config:
        raise HTTPException(status_code=404, detail=f"Index '{key}' not found")
    del config[key]
    save_index_config(config)
    return {"status": "success", "key": key}

@router.post("/run", response_model=JobStatus)
def run_analysis(request: AnalysisRequest):
    """Start a new analysis job."""
    try:
        # job_manager still manages the background thread/process
        # The process itself now writes to DB
        job_id = job_manager.start_analysis(request.stock_list_file, request.end_date)
        job = job_manager.get_job(job_id)
        return {
            "job_id": job.job_id,
            "status": job.status,
            "progress": job.progress,
            "error": job.error,
            "start_time": job.start_time.isoformat() if job.start_time else None,
            "end_time": job.end_time.isoformat() if job.end_time else None
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/run_multi_index", response_model=JobStatus)
def run_multi_index_analysis(request: MultiIndexRequest):
    """
    Start analysis for multiple indices. Combines all stock lists into unique set,
    runs analysis once, then computes per-index breadth.
    """
    try:
        # Validate indices
        index_config = load_index_config()
        invalid_indices = [idx for idx in request.indices if idx not in index_config]
        if invalid_indices:
            raise HTTPException(status_code=400, detail=f"Invalid indices: {invalid_indices}")
        
        if not request.indices:
            raise HTTPException(status_code=400, detail="At least one index must be selected")
        
        # Start multi-index analysis
        job_id = job_manager.start_multi_index_analysis(request.indices, request.end_date)
        job = job_manager.get_job(job_id)
        return {
            "job_id": job.job_id,
            "status": job.status,
            "progress": job.progress,
            "error": job.error,
            "start_time": job.start_time.isoformat() if job.start_time else None,
            "end_time": job.end_time.isoformat() if job.end_time else None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/status/current", response_model=Optional[JobStatus])
def get_current_status():
    """Get status of the current or last job."""
    job = job_manager.get_current_job()
    if not job:
        return None
    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress": job.progress,
        "error": job.error,
        "run_id": job.run_id,
        "report": job.report,
        "start_time": job.start_time.isoformat() if job.start_time else None,
        "end_time": job.end_time.isoformat() if job.end_time else None
    }

@router.get("/runs")
def get_analysis_runs(db: Session = Depends(get_db)):
    """List all analysis runs."""
    runs = db.query(AnalysisRun).order_by(desc(AnalysisRun.timestamp)).all()
    return [{
        "id": r.id,
        # Append Z to indicate UTC timezone, as timestamps in DB are naive UTC
        "timestamp": r.timestamp.isoformat() + "Z", 
        "status": r.status,
        "stock_list_name": r.stock_list_name
    } for r in runs]

BREADTH_RESULT_TYPES = ["cd_market_breadth_1234", "mc_market_breadth_1234",
                        "cd_company_breadth", "mc_company_breadth",
                        "cd_score_breadth_by_interval", "mc_score_breadth_by_interval"]


def _latest_run_for_stock_list(db, stock_list):
    """(run_id, result key) of the newest completed run with breadth results for this stock list:
    its own run stores them under ticker "ALL", a multi-index run under the stock list name.
    (None, None) when the list was never analysed."""
    row = db.query(AnalysisResult.run_id, AnalysisResult.ticker).join(
        AnalysisRun, AnalysisRun.id == AnalysisResult.run_id
    ).filter(
        AnalysisRun.status == "completed",
        AnalysisResult.result_type.in_(BREADTH_RESULT_TYPES),
        or_(
            and_(AnalysisRun.stock_list_name == stock_list, AnalysisResult.ticker == "ALL"),
            and_(AnalysisRun.stock_list_name == "multi_index", AnalysisResult.ticker == stock_list),
        ),
    ).order_by(desc(AnalysisRun.timestamp), desc(AnalysisRun.id)).first()
    return (row[0], row[1]) if row else (None, None)


# (cache key, built at, result) of /ticker_first_dates
_first_dates_cache = {'key': None, 'at': 0.0, 'value': None}
_FIRST_DATES_TTL = 600  # seconds; analysis jobs write prices from another process


@router.get("/ticker_first_dates")
def get_ticker_first_dates(db: Session = Depends(get_db)):
    """First stored daily bar (YYYY-MM-DD) of every ticker whose history starts later than the
    earliest one, e.g. a recent IPO. Breadth shares and scores divide by the stocks that were
    trading on each day, so a stock does not dilute the days before it had data."""
    import time
    # Prices change when an analysis run starts or finishes, so the runs table keys the cache
    key = tuple(db.execute(text("SELECT max(id), count(*), sum(status = 'completed') FROM analysis_runs")).fetchone())
    cache = _first_dates_cache
    if cache['key'] == key and time.time() - cache['at'] < _FIRST_DATES_TTL:
        return cache['value']
    cache.update(key=key, at=time.time(), value=_compute_ticker_first_dates(db))
    return cache['value']


def _compute_ticker_first_dates(db):
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


# stock list -> (cache key, encoded JSON) of /market_breadth
_breadth_cache: Dict[str, tuple] = {}


@router.get("/market_breadth/{stock_list}")
def get_market_breadth_by_stock_list(
    stock_list: str,
    db: Session = Depends(get_db)
):
    """
    Get market breadth data (CD/MC signal counts per day) for a specific stock list.
    Returns data from the latest completed analysis run for that stock list.
    Also checks multi-index runs where breadth is stored per-index.
    """
    # The newest completed run that analysed this stock list: either its own run (results under
    # ticker "ALL") or a multi-index run (results under the stock list name). Picking per list keeps
    # an index's data after later runs of other indices.
    run_id, key = _latest_run_for_stock_list(db, stock_list)

    # Stored results never change for a run, so the encoded response is reused until a newer
    # run (or a rebuilt DMA breadth file) comes along
    from app.services.stock_weights import dma_breadth_path
    dma_path = dma_breadth_path(stock_list)
    run_time = db.get(AnalysisRun, run_id).timestamp if run_id else None  # ids can be reused after a cleanup
    cache_key = (run_id, run_time, key, os.path.getmtime(dma_path) if os.path.exists(dma_path) else None)
    cached = _breadth_cache.get(stock_list)
    if cached and cached[0] == cache_key:
        return Response(cached[1], media_type='application/json')

    def _result(rtype):
        if not run_id:
            return []
        row = db.query(AnalysisResult).filter(
            AnalysisResult.run_id == run_id,
            AnalysisResult.result_type == rtype,
            AnalysisResult.ticker == key
        ).first()
        return row.data if row and row.data else []

    cd_breadth = _result("cd_market_breadth_1234")
    mc_breadth = _result("mc_market_breadth_1234")

    cd_signal_breadth = _result("cd_signal_breadth_by_interval")
    mc_signal_breadth = _result("mc_signal_breadth_by_interval")
    cd_score_breadth = _result("cd_score_breadth_by_interval")
    mc_score_breadth = _result("mc_score_breadth_by_interval")
    cd_breakthrough_score_breadth = _result("cd_breakthrough_score_by_interval")
    mc_breakthrough_score_breadth = _result("mc_breakthrough_score_by_interval")
    company_breadth = {"cd": _result("cd_company_breadth"), "mc": _result("mc_company_breadth")}
    run_ticker_pairs = [(run_id, key)] if run_id else []

    # Fetch data quality warnings for this run
    data_quality = {}
    for rid, ticker_key in run_ticker_pairs:
        if not data_quality:
            dq_result = db.query(AnalysisResult).filter(
                AnalysisResult.run_id == rid,
                AnalysisResult.result_type == "data_quality_warnings",
                AnalysisResult.ticker == "ALL"
            ).first()
            data_quality = dq_result.data if dq_result and dq_result.data else {}
    
    payload = {
        "cd_breadth": cd_breadth,
        "mc_breadth": mc_breadth,
        "cd_signal_breadth": cd_signal_breadth,
        "mc_signal_breadth": mc_signal_breadth,
        "cd_score_breadth": cd_score_breadth,
        "mc_score_breadth": mc_score_breadth,
        "cd_breakthrough_score_breadth": cd_breakthrough_score_breadth,
        "mc_breakthrough_score_breadth": mc_breakthrough_score_breadth,
        "cd_company_breadth": company_breadth.get('cd', []),
        "mc_company_breadth": company_breadth.get('mc', []),
        "data_quality": data_quality,
        # % of stocks above their 20 / 50 / 200-day moving average, from stored daily prices
        "dma_breadth": load_dma_breadth(stock_list),
        "run_id": run_id
    }
    body = JSONResponse(jsonable_encoder(payload)).body
    if run_id:
        _breadth_cache[stock_list] = (cache_key, body)
    return Response(body, media_type='application/json')

@router.get("/runs/{run_id}/results/{result_type}")
def get_analysis_result(
    run_id: int, 
    result_type: str, 
    ticker: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get specific results for a run, optionally filtered by ticker."""
    
    # 1. First check if we have individual rows stored for this result_type + ticker
    # This matches usage where we might store per-ticker items (not currently used for big blobs, but good practice)
    query = db.query(AnalysisResult).filter(
        AnalysisResult.run_id == run_id,
        AnalysisResult.result_type == result_type
    )
    
    if ticker:
        # If filtering by ticker, only return results for that ticker
        # Note: If data is stored in a master blob with no ticker column, this query might return empty or everything depending on storage
        # Our Logic: "ALL" items usually have ticker='ALL'. Specific items have ticker='AAPL'.
        # If user asks for 'AAPL' and we stored 'AAPL' separately, good.
        # If we stored "ALL" containing 'AAPL', we must fetch "ALL" and filter in python.
        
        # Try finding specific entry first
        specific_result = query.filter(AnalysisResult.ticker == ticker).all()
        if specific_result:
            results = []
            for res in specific_result:
                if res.data:
                    # If data is a list, extend. If dict, append.
                    if isinstance(res.data, list):
                        results.extend(res.data)
                    else:
                        results.append(res.data)
            return results
            
        # The "ALL" blob can be ~100MB of JSON; let SQLite pick out this ticker's rows
        # instead of decoding all of it in Python
        if db.bind.dialect.name == 'sqlite':
            import json as _json
            rows = db.execute(text(
                "SELECT j.value FROM analysis_results r, json_each(r.data) j "
                "WHERE r.run_id = :run AND r.result_type = :rtype AND r.ticker = 'ALL' "
                "AND substr(r.data, 1, 1) = '[' AND json_extract(j.value, '$.ticker') = :ticker "
                "ORDER BY r.id, j.key"
            ), {'run': run_id, 'rtype': result_type, 'ticker': ticker}).fetchall()
            non_array = db.execute(text(
                "SELECT count(*) FROM analysis_results WHERE run_id = :run AND result_type = :rtype "
                "AND ticker = 'ALL' AND substr(data, 1, 1) != '['"
            ), {'run': run_id, 'rtype': result_type}).scalar()
            if not non_array:
                return [_json.loads(v) for (v,) in rows]

    # 2. Fallback or "ALL" query
    # Fetch generic result (ticker="ALL")
    generic_results = query.filter(AnalysisResult.ticker == "ALL").all()
    
    combined_data = []
    for res in generic_results:
        if res.data:
            if isinstance(res.data, list):
                combined_data.extend(res.data)
            else:
                combined_data.append(res.data)
                
    # 3. Apply Ticker Filtering in Python if we fetched a blob and user wants specific ticker
    if ticker and combined_data:
        # Filter the list of dictionaries
        filtered_data = [
            item for item in combined_data 
            if isinstance(item, dict) and item.get('ticker') == ticker
        ]
        return filtered_data
        
    return combined_data

# (run_id, result_type) -> slim rows; a run's results never change once written
_best_metrics_cache: Dict[tuple, list] = {}


@router.get("/runs/{run_id}/results/{result_type}/best_metrics")
def get_best_metrics(run_id: int, result_type: str, db: Session = Depends(get_db)):
    """Each row of an eval result cut down to its best-period metrics. The full rows carry price
    and return histories (~23KB each, ~90MB per result), while tables only show these numbers."""
    key = (run_id, result_type)
    if key not in _best_metrics_cache:
        rows = get_analysis_result(run_id, result_type, None, db)
        slim = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = {'ticker': row.get('ticker'), 'interval': row.get('interval'), 'best_period': row.get('best_period')}
            p = row.get('best_period')
            if p is not None:
                for field in ('avg_return', 'success_rate', 'test_count'):
                    if f'{field}_{p}' in row:
                        item[f'{field}_{p}'] = row[f'{field}_{p}']
            slim.append(item)
        if not slim:
            return slim  # not written yet (run still going) - don't cache
        if len(_best_metrics_cache) >= 8:
            _best_metrics_cache.pop(next(iter(_best_metrics_cache)))
        _best_metrics_cache[key] = slim
    return _best_metrics_cache[key]


@router.get("/price_history/{ticker}/{interval}")
def get_price_history(
    ticker: str,
    interval: str,
    db: Session = Depends(get_db)
):
    """Get price history for a ticker with computed signals."""
    
    # Determine cutoff date based on interval for pruning logic
    # As requested by user:
    # 1d/1w: last 2 years
    # 4h/3h: last 1 year
    # 2h/1h: last 6 month
    # 5m/10m: last 30 days
    # 15min/30m: last 60 days

    now = datetime.utcnow()
    cutoff_date = None

    if interval in ['1w', '1wk']:
        cutoff_date = now - timedelta(days=730) # 2 years
    elif interval in ['1h', '60m', '2h', '3h', '4h', '1d']:
        # Same range as the result tables, so the signals they count are the ones shown here
        cutoff_date = now - timedelta(days=signal_lookback_days('1h' if interval == '60m' else interval))
    elif interval in ['15m', '30m']:
        cutoff_date = now - timedelta(days=60)
    elif interval in ['5m', '10m']:
        cutoff_date = now - timedelta(days=30)
    
    # Base query
    query = db.query(PriceBar).filter(
        PriceBar.ticker == ticker,
        PriceBar.interval == interval
    )

    # Signals are computed on all stored bars (like the analysis), the response only covers the cutoff window.
    # Computing on the window alone would hide signals near its start (MACD warm-up) and could shift others.
    all_prices = query.order_by(PriceBar.timestamp).all()
    prices = [p for p in all_prices if cutoff_date is None or p.timestamp >= cutoff_date]
    
    if not prices:
        return []

    # Convert to DataFrame for indicator calculation
    # We used "Open", "High", "Low", "Close", "Volume" in indicators.py (Case Sensitive often in pandas? logic uses dict keys usually)
    # The indicators.py likely expects DataFrame columns. Let's check keys.
    # Usually yfinance gives Capitalized. indicators.py likely uses Capitalized.
    
    data = [{
        "timestamp": p.timestamp,
        "Open": p.open,
        "High": p.high,
        "Low": p.low,
        "Close": p.close,
        "Volume": p.volume
    } for p in all_prices]
    
    df = pd.DataFrame(data)
    if df.empty:
        return []
        
    df.set_index("timestamp", inplace=True)
    
    # Compute Indicators
    try:
        # Same signal definition as the analysis (score threshold, HQ algorithm, no signal on a forming bar)
        cd = compute_signals(df, 'cd', interval=interval)
        mc = compute_signals(df, 'mc', interval=interval)
        cd_signals, cd_1234, cd_scores = cd['signal'], cd['hq'], cd['score']
        mc_signals, mc_1234, mc_scores = mc['signal'], mc['hq'], mc['score']

        # Vegas Channel EMAs
        df['ema_13'] = df['Close'].ewm(span=13, adjust=False).mean()
        df['ema_21'] = df['Close'].ewm(span=21, adjust=False).mean()
        df['ema_144'] = df['Close'].ewm(span=144, adjust=False).mean()
        df['ema_169'] = df['Close'].ewm(span=169, adjust=False).mean()

        # Requested MAs
        df['ema_20'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['sma_50'] = df['Close'].rolling(window=50).mean()
        df['sma_100'] = df['Close'].rolling(window=100).mean()
        df['sma_200'] = df['Close'].rolling(window=200).mean()

    except Exception as e:
        logger.error(f"Error computing indicators for {ticker}: {e}")
        # Fallback to no signals if error
        cd_signals = cd_1234 = mc_signals = mc_1234 = pd.Series(False, index=df.index)
        cd_scores = mc_scores = pd.Series(np.nan, index=df.index)

    # Construct response
    response = []
    for p in prices:
        # p.timestamp is naive usually. Ensure alignment with df index.
        ts = p.timestamp
        is_cd = bool(cd_signals.get(ts, False))
        is_mc = bool(mc_signals.get(ts, False))
        is_cd_1234 = bool(cd_1234.get(ts, False))
        is_mc_1234 = bool(mc_1234.get(ts, False))
        
        # Ema values
        e13 = df.loc[ts, 'ema_13'] if 'ema_13' in df else None
        e21 = df.loc[ts, 'ema_21'] if 'ema_21' in df else None
        e144 = df.loc[ts, 'ema_144'] if 'ema_144' in df else None
        e169 = df.loc[ts, 'ema_169'] if 'ema_169' in df else None
        
        e20 = df.loc[ts, 'ema_20'] if 'ema_20' in df else None
        s50 = df.loc[ts, 'sma_50'] if 'sma_50' in df else None
        s100 = df.loc[ts, 'sma_100'] if 'sma_100' in df else None
        s200 = df.loc[ts, 'sma_200'] if 'sma_200' in df else None

        # Signal scores
        cd_sc = cd_scores.get(ts, np.nan)
        mc_sc = mc_scores.get(ts, np.nan)

        response.append({
            "time": p.timestamp.isoformat(),
            "open": p.open,
            "high": p.high,
            "low": p.low,
            "close": p.close,
            "volume": p.volume,
            "cd_signal": is_cd,
            "mc_signal": is_mc,
            "cd_score": float(cd_sc) if pd.notna(cd_sc) else None,
            "mc_score": float(mc_sc) if pd.notna(mc_sc) else None,
            "cd_1234_signal": is_cd_1234,
            "mc_1234_signal": is_mc_1234,
            "ema_13": float(e13) if pd.notna(e13) else None,
            "ema_21": float(e21) if pd.notna(e21) else None,
            "ema_144": float(e144) if pd.notna(e144) else None,
            "ema_169": float(e169) if pd.notna(e169) else None,
            "ema_20": float(e20) if pd.notna(e20) else None,
            "sma_50": float(s50) if pd.notna(s50) else None,
            "sma_100": float(s100) if pd.notna(s100) else None,
            "sma_200": float(s200) if pd.notna(s200) else None
        })
        
    return response


@router.get("/ticker_signals/{ticker}")
def get_ticker_signals(ticker: str, db: Session = Depends(get_db)):
    """
    Get per-date aggregated CD/MC signal and score data across all intervals
    for a single ticker. Returns the same shape as index-level breadth data
    so MarketBreadthChart can render per-ticker panels without changes.
    """
    INTERVALS = {
        '1h': timedelta(days=365),
        '2h': timedelta(days=365),
        '3h': timedelta(days=365),
        '4h': timedelta(days=365),
        '1d': timedelta(days=730),
    }

    now = datetime.utcnow()

    # Per-date accumulators
    cd_signal_by_date: Dict[str, Dict[str, int]] = {}   # date -> {interval -> 0/1}
    mc_signal_by_date: Dict[str, Dict[str, int]] = {}
    cd_score_by_date: Dict[str, Dict[str, float]] = {}  # date -> {interval -> score}
    mc_score_by_date: Dict[str, Dict[str, float]] = {}
    cd_1234_by_date: Dict[str, Dict[str, int]] = {}     # date -> {interval -> count}
    mc_1234_by_date: Dict[str, Dict[str, int]] = {}

    for interval, lookback in INTERVALS.items():
        cutoff = now - lookback
        # Signals use all stored bars (like the analysis); only dates within the lookback are reported
        prices = db.query(PriceBar).filter(
            PriceBar.ticker == ticker,
            PriceBar.interval == interval
        ).order_by(PriceBar.timestamp).all()

        if not prices or sum(p.timestamp >= cutoff for p in prices) < 50:
            continue

        df = pd.DataFrame([{
            "timestamp": p.timestamp,
            "Open": p.open, "High": p.high, "Low": p.low,
            "Close": p.close, "Volume": p.volume
        } for p in prices])
        df.set_index("timestamp", inplace=True)

        try:
            cd = compute_signals(df, 'cd', interval=interval)
            mc = compute_signals(df, 'mc', interval=interval)
            cd_sig, cd_1234, cd_sc = cd['signal'], cd['hq'], cd['score']
            mc_sig, mc_1234, mc_sc = mc['signal'], mc['hq'], mc['score']
            logger.info(f"[HQ] {ticker}/{interval}: cd_sig={cd_sig.sum()}, cd_1234={cd_1234.sum()}, mc_sig={mc_sig.sum()}, mc_1234={mc_1234.sum()}")
        except Exception as e:
            logger.warning(f"Error computing signals for {ticker}/{interval}: {e}")
            continue

        # Aggregate into per-date buckets
        for ts in df.index[df.index >= cutoff]:
            date_str = ts.strftime('%Y-%m-%d')

            # CD signal count (0 or 1 per interval per date — take max if multiple bars same date)
            if date_str not in cd_signal_by_date:
                cd_signal_by_date[date_str] = {}
            if cd_sig.get(ts, False):
                cd_signal_by_date[date_str][interval] = 1

            if date_str not in mc_signal_by_date:
                mc_signal_by_date[date_str] = {}
            if mc_sig.get(ts, False):
                mc_signal_by_date[date_str][interval] = 1

            # Scores: only take score if signal is valid (passed threshold)
            sc_cd = cd_sc.get(ts, np.nan)
            if cd_sig.get(ts, False) and pd.notna(sc_cd) and sc_cd > 0:
                if date_str not in cd_score_by_date:
                    cd_score_by_date[date_str] = {}
                cd_score_by_date[date_str][interval] = max(
                    cd_score_by_date[date_str].get(interval, 0), float(sc_cd)
                )

            sc_mc = mc_sc.get(ts, np.nan)
            if mc_sig.get(ts, False) and pd.notna(sc_mc) and sc_mc > 0:
                if date_str not in mc_score_by_date:
                    mc_score_by_date[date_str] = {}
                mc_score_by_date[date_str][interval] = max(
                    mc_score_by_date[date_str].get(interval, 0), float(sc_mc)
                )

            # 1234 counts (per-interval)
            if cd_1234.get(ts, False):
                if date_str not in cd_1234_by_date:
                    cd_1234_by_date[date_str] = {}
                cd_1234_by_date[date_str][interval] = 1
            if mc_1234.get(ts, False):
                if date_str not in mc_1234_by_date:
                    mc_1234_by_date[date_str] = {}
                mc_1234_by_date[date_str][interval] = 1

    # Build response arrays matching existing breadth data shapes
    all_dates = sorted(set(
        list(cd_signal_by_date.keys()) + list(mc_signal_by_date.keys()) +
        list(cd_score_by_date.keys()) + list(mc_score_by_date.keys()) +
        list(cd_1234_by_date.keys()) + list(mc_1234_by_date.keys())
    ))

    cd_signal_breadth = []
    mc_signal_breadth = []
    cd_score_breadth = []
    mc_score_breadth = []
    cd_breadth = []
    mc_breadth = []

    for d in all_dates:
        cd_s = cd_signal_by_date.get(d, {})
        mc_s = mc_signal_by_date.get(d, {})
        cd_sc_d = cd_score_by_date.get(d, {})
        mc_sc_d = mc_score_by_date.get(d, {})

        if any(cd_s.values()) or True:  # Always emit a row for charting continuity
            cd_signal_breadth.append({
                "date": d,
                "count_1h": cd_s.get('1h', 0),
                "count_2h": cd_s.get('2h', 0),
                "count_3h": cd_s.get('3h', 0),
                "count_4h": cd_s.get('4h', 0),
                "count_1d": cd_s.get('1d', 0),
            })

        mc_signal_breadth.append({
            "date": d,
            "count_1h": mc_s.get('1h', 0),
            "count_2h": mc_s.get('2h', 0),
            "count_3h": mc_s.get('3h', 0),
            "count_4h": mc_s.get('4h', 0),
            "count_1d": mc_s.get('1d', 0),
        })

        cd_score_breadth.append({
            "date": d,
            "score_1h": cd_sc_d.get('1h', 0),
            "score_2h": cd_sc_d.get('2h', 0),
            "score_3h": cd_sc_d.get('3h', 0),
            "score_4h": cd_sc_d.get('4h', 0),
            "score_1d": cd_sc_d.get('1d', 0),
            "total_score": sum(cd_sc_d.values()),
        })

        mc_score_breadth.append({
            "date": d,
            "score_1h": mc_sc_d.get('1h', 0),
            "score_2h": mc_sc_d.get('2h', 0),
            "score_3h": mc_sc_d.get('3h', 0),
            "score_4h": mc_sc_d.get('4h', 0),
            "score_1d": mc_sc_d.get('1d', 0),
            "total_score": sum(mc_sc_d.values()),
        })

        cd_1234_d = cd_1234_by_date.get(d, {})
        if any(cd_1234_d.values()):
            cd_breadth.append({
                "date": d,
                "count_1h": cd_1234_d.get('1h', 0),
                "count_2h": cd_1234_d.get('2h', 0),
                "count_3h": cd_1234_d.get('3h', 0),
                "count_4h": cd_1234_d.get('4h', 0),
                "count_1d": cd_1234_d.get('1d', 0),
            })

        mc_1234_d = mc_1234_by_date.get(d, {})
        if any(mc_1234_d.values()):
            mc_breadth.append({
                "date": d,
                "count_1h": mc_1234_d.get('1h', 0),
                "count_2h": mc_1234_d.get('2h', 0),
                "count_3h": mc_1234_d.get('3h', 0),
                "count_4h": mc_1234_d.get('4h', 0),
                "count_1d": mc_1234_d.get('1d', 0),
            })

    # Build breakthrough score arrays (scores only on 1234 breakthrough dates)
    cd_breakthrough_score_breadth = []
    mc_breakthrough_score_breadth = []
    for d in all_dates:
        cd_1234_d = cd_1234_by_date.get(d, {})
        if any(cd_1234_d.values()):
            cd_sc_d = cd_score_by_date.get(d, {})
            # Only include scores for intervals that have a 1234 signal
            bt_scores = {intv: cd_sc_d.get(intv, 0) for intv in cd_1234_d if cd_1234_d[intv]}
            if bt_scores:
                cd_breakthrough_score_breadth.append({
                    "date": d,
                    "score_1h": bt_scores.get('1h', 0),
                    "score_2h": bt_scores.get('2h', 0),
                    "score_3h": bt_scores.get('3h', 0),
                    "score_4h": bt_scores.get('4h', 0),
                    "score_1d": bt_scores.get('1d', 0),
                    "total_score": sum(bt_scores.values()),
                })

        mc_1234_d = mc_1234_by_date.get(d, {})
        if any(mc_1234_d.values()):
            mc_sc_d = mc_score_by_date.get(d, {})
            bt_scores = {intv: mc_sc_d.get(intv, 0) for intv in mc_1234_d if mc_1234_d[intv]}
            if bt_scores:
                mc_breakthrough_score_breadth.append({
                    "date": d,
                    "score_1h": bt_scores.get('1h', 0),
                    "score_2h": bt_scores.get('2h', 0),
                    "score_3h": bt_scores.get('3h', 0),
                    "score_4h": bt_scores.get('4h', 0),
                    "score_1d": bt_scores.get('1d', 0),
                    "total_score": sum(bt_scores.values()),
                })

    return {
        "cd_signal_breadth": cd_signal_breadth,
        "mc_signal_breadth": mc_signal_breadth,
        "cd_score_breadth": cd_score_breadth,
        "mc_score_breadth": mc_score_breadth,
        "cd_breadth": cd_breadth,
        "mc_breadth": mc_breadth,
        "cd_breakthrough_score_breadth": cd_breakthrough_score_breadth,
        "mc_breakthrough_score_breadth": mc_breakthrough_score_breadth,
    }


@router.get("/score_distribution")
def get_score_distribution(db: Session = Depends(get_db)):
    """Score distribution of every CD/MC indicator firing (before the threshold) from the latest run that has one."""
    row = db.query(AnalysisResult, AnalysisRun.timestamp).join(
        AnalysisRun, AnalysisResult.run_id == AnalysisRun.id
    ).filter(
        AnalysisRun.status == "completed",
        AnalysisResult.result_type == "score_distribution",
        AnalysisResult.ticker == "ALL",
    ).order_by(desc(AnalysisRun.timestamp)).first()
    if not row:
        return None
    result, timestamp = row
    return {**(result.data or {}), "run_id": result.run_id, "run_timestamp": timestamp.isoformat() if timestamp else None}


class FundamentalsRequest(BaseModel):
    tickers: List[str]


@router.get("/fundamentals/{ticker}")
def get_fundamentals(ticker: str):
    """Quarterly revenue / gross profit / net income / EPS for one ticker (fetched on demand)."""
    refresh_quarterly(ticker)
    return ticker_quarterly(ticker)


@router.get("/earnings_dates/{ticker}")
def get_earnings_dates(ticker: str):
    """Past and upcoming earnings report dates of a ticker, with time of day and EPS estimate / actual."""
    refresh_earnings(ticker.upper())
    return ticker_earnings(ticker.upper())


@router.post("/fundamentals/aggregate")
def get_fundamentals_aggregate(request: FundamentalsRequest):
    """Calendar-quarter totals over a stock list (same companies in every quarter) and % with EPS up."""
    return aggregate_quarterly(request.tickers)


@router.get("/bond_yields")
def get_bond_yields():
    """US Treasury 3-month / 2-year / 10-year yields (percent), daily from FRED."""
    return load_bond_yields()


@router.get("/options/{ticker}")
def get_options(ticker: str):
    """
    Get option open interest data for nearest day, week, and month.
    """
    try:
        data = get_option_data(ticker)
        if not data:
            raise HTTPException(status_code=404, detail=f"Option data not found for {ticker}")
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@router.get("/logs")
def get_logs(lines: int = 100):
    """Get the last N lines of the backend server log."""
    log_file = "backend_server.log"
    if not os.path.exists(log_file):
        return {"logs": []}
    
    try:
        # Use simple file reading; for very large files seek might be improved but tail is fine for now
        with open(log_file, "r") as f:
            # Read all lines then slice is simplest for now (assuming log rotation keeps it manageable)
            # For robustness with rotating logs, this reads the current active log
            all_lines = f.readlines()
            return {"logs": all_lines[-lines:]}
    except Exception as e:
        logger.error(f"Error reading logs: {e}")
        return {"logs": [f"Error reading logs: {str(e)}"]}

@router.get("/signals_1234/{ticker}")
def get_signals_1234(ticker: str, stock_list: Optional[str] = None, db: Session = Depends(get_db)):
    """Get 1234 CD/MC signal dates for a specific ticker from the latest analysis run.
    With stock_list (an index card), use the newest run that analysed that stock list instead."""
    run_id = _latest_run_for_stock_list(db, stock_list)[0] if stock_list else None
    if not run_id:
        latest_run = db.query(AnalysisRun).order_by(desc(AnalysisRun.id)).first()
        if not latest_run:
            logger.info(f"No analysis run found for signals_1234/{ticker}")
            return {"cd_dates": [], "mc_dates": []}
        run_id = latest_run.id
    logger.info(f"Fetching signals_1234 for ticker={ticker}, run_id={run_id}")
    
    # Fetch CD 1234 results (stored as 'cd_breakout_candidates_summary_1234')
    cd_results = db.query(AnalysisResult).filter(
        AnalysisResult.run_id == run_id,
        AnalysisResult.result_type == "cd_breakout_candidates_summary_1234",
        AnalysisResult.ticker == "ALL"
    ).all()
    
    cd_dates = []
    for res in cd_results:
        if res.data and isinstance(res.data, list):
            for item in res.data:
                if isinstance(item, dict) and item.get('ticker') == ticker and 'date' in item:
                    # Normalize date to YYYY-MM-DD string format
                    date_val = item['date']
                    if hasattr(date_val, 'strftime'):
                        date_str = date_val.strftime('%Y-%m-%d')
                    else:
                        date_str = str(date_val)[:10]  # Take first 10 chars (YYYY-MM-DD)
                    cd_dates.append(date_str)
    
    logger.info(f"ticker={ticker} CD 1234 dates: {cd_dates}")
    
    # Fetch MC 1234 results (stored as 'mc_breakout_candidates_summary_1234')
    mc_results = db.query(AnalysisResult).filter(
        AnalysisResult.run_id == run_id,
        AnalysisResult.result_type == "mc_breakout_candidates_summary_1234",
        AnalysisResult.ticker == "ALL"
    ).all()
    
    mc_dates = []
    for res in mc_results:
        if res.data and isinstance(res.data, list):
            for item in res.data:
                if isinstance(item, dict) and item.get('ticker') == ticker and 'date' in item:
                    # Normalize date to YYYY-MM-DD string format
                    date_val = item['date']
                    if hasattr(date_val, 'strftime'):
                        date_str = date_val.strftime('%Y-%m-%d')
                    else:
                        date_str = str(date_val)[:10]  # Take first 10 chars (YYYY-MM-DD)
                    mc_dates.append(date_str)
    
    logger.info(f"ticker={ticker} MC 1234 dates: {mc_dates}")
    
    return {"cd_dates": cd_dates, "mc_dates": mc_dates}


# ─── Scoring Configuration ───────────────────────────────────────────────

@router.get("/config/scoring")
def get_scoring_weights():
    """Return the current scoring weight configuration."""
    return get_scoring_config()


@router.put("/config/scoring")
def update_scoring_weights(config: Dict[str, Any]):
    """Update scoring weight configuration. Changes take effect immediately."""
    updated = save_scoring_config(config)
    return updated


@router.get("/config/scoring/defaults")
def get_scoring_defaults():
    """Return the default scoring weight configuration."""
    return SCORING_DEFAULTS


@router.delete("/cleanup-database")
def cleanup_database(tables: Optional[str] = None, db: Session = Depends(get_db)):
    """Delete data from selected tables to allow a fresh re-run.
    
    Args:
        tables: Comma-separated list of tables to clean. 
                Valid values: analysis_runs, analysis_results, price_history, option_chains.
                If not specified, all tables are cleaned.
    """
    try:
        # Determine which tables to clean
        all_tables = {'analysis_runs', 'analysis_results', 'price_history', 'option_chains'}
        if tables:
            selected = {t.strip() for t in tables.split(',')}
            selected = selected & all_tables  # Only allow valid table names
        else:
            selected = all_tables

        deleted = {}
        # Delete analysis_results before analysis_runs (foreign key dependency)
        if 'analysis_results' in selected:
            deleted['analysis_results'] = db.query(AnalysisResult).delete()
        if 'analysis_runs' in selected:
            deleted['analysis_runs'] = db.query(AnalysisRun).delete()
        if 'price_history' in selected:
            deleted['price_history'] = db.query(PriceBar).delete()
        if 'option_chains' in selected:
            deleted['option_chains'] = db.query(OptionChain).delete()

        db.commit()
        # VACUUM to reclaim disk space (SQLite keeps allocated space after DELETE)
        db.execute(text("VACUUM"))
        logger.info(f"Database cleanup: {deleted}")
        return {
            "status": "success",
            "deleted": deleted
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Database cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
