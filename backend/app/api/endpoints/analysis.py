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
from app.logic.indicators import compute_cd_indicator, compute_mc_indicator, compute_nx_break_through
from app.db.database import SessionLocal
from app.db.models import AnalysisRun, AnalysisResult, PriceBar
from app.logic.db_utils import save_price_history
from app.logic.options import get_option_data

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

class AnalysisRequest(BaseModel):
    stock_list_file: str
    end_date: Optional[str] = None

class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: int
    error: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None

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
    """
    # Find the latest completed run for this stock list
    latest_run = db.query(AnalysisRun).filter(
        AnalysisRun.stock_list_name == stock_list,
        AnalysisRun.status == "completed"
    ).order_by(desc(AnalysisRun.timestamp)).first()
    
    if not latest_run:
        logger.info(f"No completed analysis run found for stock list: {stock_list}")
        return {"cd_breadth": [], "mc_breadth": [], "run_id": None}
    
    run_id = latest_run.id
    
    # Fetch CD market breadth 1234
    cd_result = db.query(AnalysisResult).filter(
        AnalysisResult.run_id == run_id,
        AnalysisResult.result_type == "cd_market_breadth_1234",
        AnalysisResult.ticker == "ALL"
    ).first()
    
    cd_breadth = cd_result.data if cd_result and cd_result.data else []
    
    # Fetch MC market breadth 1234
    mc_result = db.query(AnalysisResult).filter(
        AnalysisResult.run_id == run_id,
        AnalysisResult.result_type == "mc_market_breadth_1234",
        AnalysisResult.ticker == "ALL"
    ).first()
    
    mc_breadth = mc_result.data if mc_result and mc_result.data else []
    
    return {
        "cd_breadth": cd_breadth,
        "mc_breadth": mc_breadth,
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
        
        # Fill NaNs with False
        cd_signals = cd_signals.fillna(False).astype(bool)
        mc_signals = mc_signals.fillna(False).astype(bool)
        breakthrough = breakthrough.fillna(False).astype(bool)

        # 1234 Logic: (Signal & Breakthrough) | (Signal & Breakthrough[t-9])
        # Logic analysis: `breakthrough.rolling(10).apply(lambda x: x.iloc[0] if x.any() else False)`
        # If x.iloc[0] (t-9) is True, then x.any() is True, so it returns True.
        # If x.iloc[0] is False, it returns False regardless of x.any().
        # Thus, it simplifies to breakthrough.shift(9).
        oldest_breakthrough = breakthrough.shift(9).fillna(False)
        
        cd_1234 = (cd_signals & breakthrough) | (cd_signals & oldest_breakthrough)
        mc_1234 = (mc_signals & breakthrough) | (mc_signals & oldest_breakthrough)

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

        response.append({
            "time": p.timestamp.isoformat(),
            "open": p.open,
            "high": p.high,
            "low": p.low,
            "close": p.close,
            "volume": p.volume,
            "cd_signal": is_cd,
            "mc_signal": is_mc,
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

