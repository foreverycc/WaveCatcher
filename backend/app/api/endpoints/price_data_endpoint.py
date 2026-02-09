from fastapi import HTTPException
from typing import Optional
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

@router.get("/price_data/{ticker}")
async def get_price_data(
    ticker: str,
    interval: str = "1d",
    days: int = 60
):
    """Get OHLCV price data for a ticker."""
    try:
        # Map interval to yfinance format
        interval_map = {
            '5m': '5m',
            '10m': '10m',
            '15m': '15m',
            '30m': '30m',
            '1h': '1h',
            '2h': '2h',
            '3h': '3h',
            '4h': '4h',
            '1d': '1d',
            '1w': '1wk'
        }
        yf_interval = interval_map.get(interval, '1d')
        
        # Calculate period
        period = f"{days}d" if days <= 730 else "2y"
        
        # Fetch data
        stock = yf.Ticker(ticker)
        df = stock.history(period=period, interval=yf_interval)
        
        if df.empty:
            return []
        
        # Convert to list of dicts
        df = df.reset_index()
        df = df.rename(columns={'index': 'Date'}) if 'index' in df.columns else df
        
        # Replace NaN/Inf with None
        df = df.replace({pd.np.nan: None, pd.np.inf: None, -pd.np.inf: None})
        
        records = []
        for _, row in df.iterrows():
            record = {
                'date': row['Date'].isoformat() if pd.notna(row['Date']) else None,
                'open': float(row['Open']) if pd.notna(row['Open']) else None,
                'high': float(row['High']) if pd.notna(row['High']) else None,
                'low': float(row['Low']) if pd.notna(row['Low']) else None,
                'close': float(row['Close']) if pd.notna(row['Close']) else None,
                'volume': int(row['Volume']) if pd.notna(row['Volume']) else 0
            }
            records.append(record)
        
        return records
        
    except Exception as e:
        logger.error(f"Error fetching price data for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching price data: {str(e)}")
