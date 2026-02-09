from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.db.models import PriceBar, AnalysisRun, AnalysisResult
from datetime import datetime, date
import pandas as pd
import json

def get_db_session():
    """Helper to get a new session, useful for worker processes."""
    return SessionLocal()

def save_price_history(ticker: str, interval: str, df: pd.DataFrame):
    """
    Save OHLCV data to the database.
    Replaces existing data for the same ticker/interval/timestamp.
    """
    if df.empty:
        return

    db = SessionLocal()
    try:
        # Convert DataFrame to list of dictionaries
        # Ensure timestamp is standard datetime
        records = []
        for index, row in df.iterrows():
            # index is 'timestamp' usually
            # Ensure index is datetime
            ts = pd.to_datetime(index)
            # If naive, perfect (market time). If aware, strip or convert?
            # Backend logic earlier enforced naive ET.
            if ts.tzinfo is not None:
                ts = ts.tz_convert('America/New_York').tz_localize(None)
                
            record = {
                "ticker": ticker,
                "interval": interval,
                "timestamp": ts,
                "open": row.get('Open'),
                "high": row.get('High'),
                "low": row.get('Low'),
                "close": row.get('Close'),
                "volume": int(row.get('Volume', 0))
            }
            records.append(record)
            
        # Bulk Insert / Upsert
        # SQLite doesn't support "ON CONFLICT UPDATE" in standard INSERT easily with ORM bulk_save_objects
        # unless we use core insert().
        # For simplicity and robustness, we can delete existing for this ticker/interval range or just merge.
        # Merging one by one is slow.
        # SQLite 3.24+ supports UPSERT. SQLAlchemy 1.2+ supports it via dialects.
        
        # Strategy: Delete existing for this ticker+interval (full replace) or merge.
        # Since we usually download the full history required, full replace for the ticker/interval is safer/easier.
        # BUT be careful not to delete mostly everything if we only downloaded a partial update?
        # Usually we download 'max' or specific period. 
        # Let's use merge for now or iterate.
        # Optimization: Use core implementation for bulk upsert if speed is needed. 
        
        # Simple cleanup first (optional, maybe too aggressive if we want to append?)
        # db.query(PriceBar).filter(PriceBar.ticker == ticker, PriceBar.interval == interval).delete()
        
        # Let's try bulk_save_objects used as upsert? No, it inserts.
        # Let's use merge efficiently?
        for r in records:
            # merge checks PK
            db.merge(PriceBar(**r))
            
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error saving price history for {ticker}: {e}")
    finally:
        db.close()

def create_analysis_run(stock_list_name: str) -> int:
    """
    Create a new analysis run record and return its ID.
    Enforces 'Keep Latest' policy by deleting all previous runs for this stock list.
    """
    db = SessionLocal()
    try:
        # Cleanup previous runs for this stock list
        try:
            db.query(AnalysisRun).filter(AnalysisRun.stock_list_name == stock_list_name).delete()
            db.commit()
            print(f"Cleaned up previous runs for {stock_list_name}")
        except Exception as e:
            db.rollback()
            print(f"Error cleaning up previous runs: {e}")

        # Create new run
        run = AnalysisRun(stock_list_name=stock_list_name, status="running")
        db.add(run)
        db.commit()
        db.refresh(run)
        return run.id
    finally:
        db.close()

def update_analysis_run_status(run_id: int, status: str):
    """Update the status of an analysis run."""
    db = SessionLocal()
    try:
        run = db.query(AnalysisRun).filter(AnalysisRun.id == run_id).first()
        if run:
            run.status = status
            db.commit()
    finally:
        db.close()

def save_analysis_result(run_id: int, ticker: str, interval: str, result_type: str, data: dict):
    """Save a generic analysis result."""
    db = SessionLocal()
    try:
        # Sanitize data for JSON (handle primitives, remove NaNs)
        def clean_nans(d):
            if isinstance(d, float) and (d != d or d == float('inf') or d == float('-inf')):
                return None
            if isinstance(d, dict):
                return {k: clean_nans(v) for k, v in d.items()}
            if isinstance(d, list):
                return [clean_nans(v) for v in d]
            if isinstance(d, (datetime, pd.Timestamp)):
                return d.isoformat()
            if hasattr(d, 'isoformat'): # Handle datetime.date
                return d.isoformat()
            return d

        clean_data = clean_nans(data)

        # Delete existing result for this run/ticker/type to prevent duplicates
        db.query(AnalysisResult).filter(
            AnalysisResult.run_id == run_id,
            AnalysisResult.ticker == ticker,
            AnalysisResult.interval == interval,
            AnalysisResult.result_type == result_type
        ).delete()

        result = AnalysisResult(
            run_id=run_id,
            ticker=ticker,
            interval=interval,
            result_type=result_type,
            data=clean_data
        )
        db.add(result)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error saving analysis result {result_type} for {ticker}: {e}")
    finally:
        db.close()
