import yfinance as yf
import pandas as pd
import os
import sys

def test_fetch(ticker, interval):
    print(f"Testing fetch for {ticker} {interval}")
    
    # Logic from analysis.py
    yf_interval_map = {
        '5m': '5m', '15m': '15m', '30m': '30m', '60m': '60m', '1h': '1h',
        '1d': '1d', '1wk': '1wk', '1mo': '1mo'
    }
    
    target_yf_interval = yf_interval_map.get(interval, '1d') 
    print(f"Target YF Interval: {target_yf_interval}")
    
    period = '60d' if interval.endswith('m') else '2y'
    print(f"Period: {period}")
    
    stock = yf.Ticker(ticker)
    df = stock.history(interval=target_yf_interval, period=period)
    
    print(f"Result Shape: {df.shape}")
    if not df.empty:
        print(df.head())
        print(df.tail())
    else:
        print("Empty DataFrame returned")

if __name__ == "__main__":
    test_fetch("SOUN", "2h")
    test_fetch("OPR", "1d")
