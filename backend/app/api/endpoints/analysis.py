import os
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import logging
import traceback
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.services.engine import job_manager
from app.logic.indicators import compute_cd_indicator, compute_mc_indicator, compute_nx_break_through, compute_cd_score, compute_mc_score
from app.db.database import SessionLocal
from app.db.models import AnalysisRun, AnalysisResult, PriceBar
from app.logic.db_utils import save_price_history
from app.logic.options import get_option_data
from app.logic.scoring_config import get_config as get_scoring_config, save_config as save_scoring_config, DEFAULT_CONFIG as SCORING_DEFAULTS, get_cd_threshold, get_mc_threshold

logger = logging.getLogger(__name__)

router = APIRouter()

import subprocess
import sys

@router.post("/update-indices")
async def update_indices():
    """Run the script to update SP500 and Nasdaq 100 indices."""
    try:
        # Assuming the script is in backend/scripts/fetch_indices.py
        # and we are running from the project root or backend root.
        # Let's use absolute path or relative from where uvicorn runs.
        # Usually uvicorn runs from backend/ or project root.
        # Safest is to find relative to this file? Or just assume standard layout.
        
        # We are in backend/app/api/endpoints/analysis.py
        # script is in backend/scripts/fetch_indices.py
        # cmd: python3 backend/scripts/fetch_indices.py
        
        # Let's try to locate it relative to current working directory of the process
        script_path = os.path.join("backend", "scripts", "fetch_indices.py")
        if not os.path.exists(script_path):
             # Try without 'backend' prefix if running from inside backend
             script_path = os.path.join("scripts", "fetch_indices.py")

        if not os.path.exists(script_path):
            return {"status": "error", "message": f"Script not found at {script_path}"}

        # Use sys.executable to ensure we use the same python environment
        result = subprocess.run([sys.executable, script_path], capture_output=True, text=True)
        
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

@router.get("/indices")
async def get_available_indices():
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
            "stock_list": config["stock_list"], "tickers": tickers
        })
    
    return {"indices": indices}


class IndexConfigEntry(BaseModel):
    symbol: str
    stock_list: str


@router.put("/indices")
async def update_all_indices(config: Dict[str, IndexConfigEntry]):
    """Replace the entire index configuration."""
    try:
        save_index_config({k: v.dict() for k, v in config.items()})
        return {"status": "success", "count": len(config)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/indices/{key}")
async def upsert_index(key: str, entry: IndexConfigEntry):
    """Add or update a single index entry."""
    try:
        config = load_index_config()
        config[key] = entry.dict()
        save_index_config(config)
        return {"status": "success", "key": key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/indices/{key}")
async def delete_index(key: str):
    """Remove an index entry."""
    config = load_index_config()
    if key not in config:
        raise HTTPException(status_code=404, detail=f"Index '{key}' not found")
    del config[key]
    save_index_config(config)
    return {"status": "success", "key": key}

@router.post("/run", response_model=JobStatus)
async def run_analysis(request: AnalysisRequest):
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
async def run_multi_index_analysis(request: MultiIndexRequest):
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
async def get_current_status():
    """Get status of the current or last job."""
    job = job_manager.get_current_job()
    if not job:
        return None
    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress": job.progress,
        "error": job.error,
        "start_time": job.start_time.isoformat() if job.start_time else None,
        "end_time": job.end_time.isoformat() if job.end_time else None
    }

@router.get("/runs")
async def get_analysis_runs(db: Session = Depends(get_db)):
    """List all analysis runs."""
    runs = db.query(AnalysisRun).order_by(desc(AnalysisRun.timestamp)).all()
    return [{
        "id": r.id,
        # Append Z to indicate UTC timezone, as timestamps in DB are naive UTC
        "timestamp": r.timestamp.isoformat() + "Z", 
        "status": r.status,
        "stock_list_name": r.stock_list_name
    } for r in runs]

@router.get("/market_breadth/{stock_list}")
async def get_market_breadth_by_stock_list(
    stock_list: str,
    db: Session = Depends(get_db)
):
    """
    Get market breadth data (CD/MC signal counts per day) for a specific stock list.
    Returns data from the latest completed analysis run for that stock list.
    Also checks multi-index runs where breadth is stored per-index.
    """
    # First, try to find a dedicated run for this stock list
    latest_run = db.query(AnalysisRun).filter(
        AnalysisRun.stock_list_name == stock_list,
        AnalysisRun.status == "completed"
    ).order_by(desc(AnalysisRun.timestamp)).first()
    
    run_id = latest_run.id if latest_run else None
    
    cd_breadth = []
    mc_breadth = []
    
    if run_id:
        # Single stock-list run: breadth stored with ticker="ALL"
        cd_result = db.query(AnalysisResult).filter(
            AnalysisResult.run_id == run_id,
            AnalysisResult.result_type == "cd_market_breadth_1234",
            AnalysisResult.ticker == "ALL"
        ).first()
        cd_breadth = cd_result.data if cd_result and cd_result.data else []
        
        mc_result = db.query(AnalysisResult).filter(
            AnalysisResult.run_id == run_id,
            AnalysisResult.result_type == "mc_market_breadth_1234",
            AnalysisResult.ticker == "ALL"
        ).first()
        mc_breadth = mc_result.data if mc_result and mc_result.data else []
    
    if not cd_breadth and not mc_breadth:
        # Fallback: check multi-index runs where breadth is stored with
        # ticker=stock_list_name (e.g. "stocks_soxx.tab") and interval="ALL"
        multi_run = db.query(AnalysisRun).filter(
            AnalysisRun.stock_list_name == "multi_index",
            AnalysisRun.status == "completed"
        ).order_by(desc(AnalysisRun.timestamp)).first()
        
        if multi_run:
            run_id = multi_run.id
            cd_result = db.query(AnalysisResult).filter(
                AnalysisResult.run_id == run_id,
                AnalysisResult.result_type == "cd_market_breadth_1234",
                AnalysisResult.ticker == stock_list
            ).first()
            cd_breadth = cd_result.data if cd_result and cd_result.data else []
            
            mc_result = db.query(AnalysisResult).filter(
                AnalysisResult.run_id == run_id,
                AnalysisResult.result_type == "mc_market_breadth_1234",
                AnalysisResult.ticker == stock_list
            ).first()
            mc_breadth = mc_result.data if mc_result and mc_result.data else []
    
    # Fetch per-interval signal breadth (CD/MC signal counts by interval per day)
    cd_signal_breadth = []
    mc_signal_breadth = []
    
    # Build list of (run_id, ticker_key) pairs to check
    run_ticker_pairs = []
    if run_id:
        run_ticker_pairs.append((run_id, stock_list))
        run_ticker_pairs.append((run_id, "ALL"))
    
    # Also check multi-index run if it's different from run_id
    multi_run = db.query(AnalysisRun).filter(
        AnalysisRun.stock_list_name == "multi_index",
        AnalysisRun.status == "completed"
    ).order_by(desc(AnalysisRun.timestamp)).first()
    if multi_run and multi_run.id != run_id:
        run_ticker_pairs.append((multi_run.id, stock_list))
        run_ticker_pairs.append((multi_run.id, "ALL"))
    
    for rid, ticker_key in run_ticker_pairs:
        if not cd_signal_breadth:
            cd_sig_result = db.query(AnalysisResult).filter(
                AnalysisResult.run_id == rid,
                AnalysisResult.result_type == "cd_signal_breadth_by_interval",
                AnalysisResult.ticker == ticker_key
            ).first()
            cd_signal_breadth = cd_sig_result.data if cd_sig_result and cd_sig_result.data else []
        
        if not mc_signal_breadth:
            mc_sig_result = db.query(AnalysisResult).filter(
                AnalysisResult.run_id == rid,
                AnalysisResult.result_type == "mc_signal_breadth_by_interval",
                AnalysisResult.ticker == ticker_key
            ).first()
            mc_signal_breadth = mc_sig_result.data if mc_sig_result and mc_sig_result.data else []
    # Fetch per-interval score breadth (CD/MC indicator scores weighted by interval)
    cd_score_breadth = []
    mc_score_breadth = []
    for rid, ticker_key in run_ticker_pairs:
        if not cd_score_breadth:
            cd_sc_result = db.query(AnalysisResult).filter(
                AnalysisResult.run_id == rid,
                AnalysisResult.result_type == "cd_score_breadth_by_interval",
                AnalysisResult.ticker == ticker_key
            ).first()
            cd_score_breadth = cd_sc_result.data if cd_sc_result and cd_sc_result.data else []
        
        if not mc_score_breadth:
            mc_sc_result = db.query(AnalysisResult).filter(
                AnalysisResult.run_id == rid,
                AnalysisResult.result_type == "mc_score_breadth_by_interval",
                AnalysisResult.ticker == ticker_key
            ).first()
            mc_score_breadth = mc_sc_result.data if mc_sc_result and mc_sc_result.data else []
    
    return {
        "cd_breadth": cd_breadth,
        "mc_breadth": mc_breadth,
        "cd_signal_breadth": cd_signal_breadth,
        "mc_signal_breadth": mc_signal_breadth,
        "cd_score_breadth": cd_score_breadth,
        "mc_score_breadth": mc_score_breadth,
        "run_id": run_id
    }

@router.get("/runs/{run_id}/results/{result_type}")
async def get_analysis_result(
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

@router.get("/price_history/{ticker}/{interval}")
async def get_price_history(
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

    if interval in ['1d', '1w', '1wk']:
        cutoff_date = now - timedelta(days=730) # 2 years
    elif interval in ['3h', '4h']:
        cutoff_date = now - timedelta(days=365) # 1 year
    elif interval in ['1h', '60m', '2h']:
        cutoff_date = now - timedelta(days=180) # 6 months
    elif interval in ['15m', '30m']:
        cutoff_date = now - timedelta(days=60)
    elif interval in ['5m', '10m']:
        cutoff_date = now - timedelta(days=30)
    
    # Base query
    query = db.query(PriceBar).filter(
        PriceBar.ticker == ticker,
        PriceBar.interval == interval
    )

    # Apply date filter if cutoff is determined
    if cutoff_date:
        query = query.filter(PriceBar.timestamp >= cutoff_date)

    prices = query.order_by(PriceBar.timestamp).all()
    
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
    } for p in prices]
    
    df = pd.DataFrame(data)
    if df.empty:
        return []
        
    df.set_index("timestamp", inplace=True)
    
    # Compute Indicators
    try:
        cd_signals = compute_cd_indicator(df)
        mc_signals = compute_mc_indicator(df)
        breakthrough = compute_nx_break_through(df)
        cd_scores = compute_cd_score(df)
        mc_scores = compute_mc_score(df)
        
        # Fill NaNs with False
        cd_signals = cd_signals.fillna(False).astype(bool)
        mc_signals = mc_signals.fillna(False).astype(bool)
        breakthrough = breakthrough.fillna(False).astype(bool)

        # Apply score threshold filtering
        cd_thresh = get_cd_threshold()
        mc_thresh = get_mc_threshold()
        for ts in cd_signals.index:
            if cd_signals[ts]:
                sc = cd_scores.get(ts, np.nan)
                if pd.isna(sc) or sc < cd_thresh:
                    cd_signals[ts] = False
        for ts in mc_signals.index:
            if mc_signals[ts]:
                sc = mc_scores.get(ts, np.nan)
                if pd.isna(sc) or sc < mc_thresh:
                    mc_signals[ts] = False

        # 1234 Logic: (Signal & Breakthrough) | (Signal & Recent Breakthrough)
        # Recent Breakthrough: occurred between 5 and 15 bars ago (inclusive)
        # We use a rolling window of 11 bars (covering t-5 to t-15) shifted by 5
        recent_breakthrough = breakthrough.rolling(window=11, min_periods=1).max().shift(5).fillna(False).astype(bool)
        
        cd_1234 = (cd_signals & breakthrough) | (cd_signals & recent_breakthrough)
        mc_1234 = (mc_signals & breakthrough) | (mc_signals & recent_breakthrough)

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
        cd_signals = pd.Series(False, index=df.index)
        mc_signals = pd.Series(False, index=df.index)

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
async def get_ticker_signals(ticker: str, db: Session = Depends(get_db)):
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
        prices = db.query(PriceBar).filter(
            PriceBar.ticker == ticker,
            PriceBar.interval == interval,
            PriceBar.timestamp >= cutoff
        ).order_by(PriceBar.timestamp).all()

        if not prices or len(prices) < 50:
            continue

        df = pd.DataFrame([{
            "timestamp": p.timestamp,
            "Open": p.open, "High": p.high, "Low": p.low,
            "Close": p.close, "Volume": p.volume
        } for p in prices])
        df.set_index("timestamp", inplace=True)

        try:
            cd_sig = compute_cd_indicator(df).fillna(False).astype(bool)
            mc_sig = compute_mc_indicator(df).fillna(False).astype(bool)
            cd_sc = compute_cd_score(df)
            mc_sc = compute_mc_score(df)

            # Apply score threshold filtering
            cd_thresh = get_cd_threshold()
            mc_thresh = get_mc_threshold()
            for ts in cd_sig.index:
                if cd_sig[ts]:
                    sc = cd_sc.get(ts, np.nan)
                    if pd.isna(sc) or sc < cd_thresh:
                        cd_sig[ts] = False
            for ts in mc_sig.index:
                if mc_sig[ts]:
                    sc = mc_sc.get(ts, np.nan)
                    if pd.isna(sc) or sc < mc_thresh:
                        mc_sig[ts] = False

            # 1234 logic (same as price_history endpoint)
            bt = compute_nx_break_through(df).fillna(False).astype(bool)
            # Recent Breakthrough: occurred between 1 and 10 bars ago (inclusive)
            recent_bt = bt.rolling(window=10, min_periods=1).max().shift(1).fillna(False).astype(bool)
            
            cd_1234 = (cd_sig & bt) | (cd_sig & recent_bt)
            mc_1234 = (mc_sig & bt) | (mc_sig & recent_bt)
        except Exception as e:
            logger.warning(f"Error computing signals for {ticker}/{interval}: {e}")
            continue

        # Aggregate into per-date buckets
        for ts in df.index:
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

    return {
        "cd_signal_breadth": cd_signal_breadth,
        "mc_signal_breadth": mc_signal_breadth,
        "cd_score_breadth": cd_score_breadth,
        "mc_score_breadth": mc_score_breadth,
        "cd_breadth": cd_breadth,
        "mc_breadth": mc_breadth,
    }


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
async def get_signals_1234(ticker: str, db: Session = Depends(get_db)):
    """Get 1234 CD/MC signal dates for a specific ticker from the latest analysis run."""
    # Get latest analysis run
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
async def get_scoring_weights():
    """Return the current scoring weight configuration."""
    return get_scoring_config()


@router.put("/config/scoring")
async def update_scoring_weights(config: Dict[str, Any]):
    """Update scoring weight configuration. Changes take effect immediately."""
    updated = save_scoring_config(config)
    return updated


@router.get("/config/scoring/defaults")
async def get_scoring_defaults():
    """Return the default scoring weight configuration."""
    return SCORING_DEFAULTS
