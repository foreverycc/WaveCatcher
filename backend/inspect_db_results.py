import sys
import os
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add parent directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.database import engine, Base
from app.db.models import AnalysisResult, AnalysisRun

SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

print("Checking Analysis Runs...")
runs = db.query(AnalysisRun).order_by(AnalysisRun.timestamp.desc()).limit(5).all()
for run in runs:
    print(f"Run ID: {run.id}, Date: {run.timestamp}, Status: {run.status}, StockList: {run.stock_list_name}")

if runs:
    latest_run_id = runs[0].id
    print(f"\nChecking Results for Run ID {latest_run_id}...")
    
    # Check CD Breadth
    cd_res = db.query(AnalysisResult).filter(
        AnalysisResult.run_id == latest_run_id,
        AnalysisResult.result_type == "cd_market_breadth_1234"
    ).first()
    
    if cd_res:
        print(f"Found CD Breadth 1234 for ticker '{cd_res.ticker}':")
        data = cd_res.data
        if isinstance(data, list) and len(data) > 0:
            print(f"  Count: {len(data)}")
            print(f"  First item: {data[0]}")
            print(f"  Available keys: {list(data[0].keys())}")
        else:
            print(f"  Data is empty or not a list: {data}")
    else:
        print("No CD Breadth 1234 found.")
        
    # Check detailed signal breadth
    cd_sig_res = db.query(AnalysisResult).filter(
        AnalysisResult.run_id == latest_run_id,
        AnalysisResult.result_type == "cd_signal_breadth_by_interval"
    ).first()
    
    if cd_sig_res:
         print(f"Found CD Signal Breadth By Interval for ticker '{cd_sig_res.ticker}':")
         data = cd_sig_res.data
         if isinstance(data, list) and len(data) > 0:
            print(f"  First item: {data[0]}")
    else:
        print("No CD Signal Breadth By Interval found.")

db.close()
