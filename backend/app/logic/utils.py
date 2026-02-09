import pandas as pd
import os
import numpy as np

def get_trading_day_window_end(start_date, ticker, all_ticker_data, days=3):
    """
    Calculate the end date of a trading day window.
    
    Args:
        start_date (datetime.date): The starting date.
        ticker (str): Ticker symbol.
        all_ticker_data (dict): Dictionary of ticker data.
        days (int): Number of trading days in the window suitable for the cluster.
                    Current logic usually implies 3-day window inclusive (Start, +1, +2).
    
    Returns:
        datetime.date: The end date of the window.
    """
    # Default fallback: 5 calendar days (covers weekend)
    fallback_date = start_date + pd.Timedelta(days=3)
    
    if ticker not in all_ticker_data or '1d' not in all_ticker_data[ticker]:
        return fallback_date
        
    df_daily = all_ticker_data[ticker]['1d']
    if df_daily.empty:
        return fallback_date
        
    # Get sorted trading dates as pd.Timestamp list
    trading_dates = df_daily.index
    
    # Find insertion point for start_date
    # Normalize start_date to timestamp for comparison (assume 00:00 or match index)
    # Trading index is usually DatetimeIndex.
    try:
        ts_start = pd.Timestamp(start_date)
        
        # Use searchsorted to find position
        # If match, returns index. If not, returns index where it would be inserted.
        idx = trading_dates.searchsorted(ts_start)
        
        # If idx is past end, return fallback
        if idx >= len(trading_dates):
            return fallback_date
            
        # Target index: inclusive of start day?
        # If start_date is present (idx points to it), we want start + 2 more days.
        # So target = idx + (days - 1).
        
        target_idx = idx + (days - 1)
        
        if target_idx < len(trading_dates):
            return trading_dates[target_idx].date()
        else:
            # If window extends beyond available data, just take the last available date
            # But maybe add buffer if we are at edge?
            # Safe to return last date available.
            return trading_dates[-1].date()
            
    except Exception as e:
        # print(f"Error calculating trading window: {e}")
        return fallback_date

def save_results(results, output_file):
    df = pd.DataFrame(results)
    if df.empty:
        print("No results to save")
        return
    df = df.sort_values(by=['signal_date', 'breakthrough_date', 'score', 'interval'], ascending=[False, False, False, False])
    
    # Include signal_price in the saved columns if it exists
    columns_to_save = ['ticker', 'interval', 'score', 'signal_date']
    if 'signal_price' in df.columns:
        columns_to_save.append('signal_price')
    columns_to_save.append('breakthrough_date')
    
    df.to_csv(output_file, sep='\t', index=False, columns=columns_to_save)

def save_breakout_candidates_1234(df, file_path):
    # Extract base name and directory from the input file path
    directory = os.path.dirname(file_path)
    base_name = os.path.basename(file_path)
    output_path = os.path.join(directory, base_name).replace("details", "summary")
    
    # Handle case where df might be a list (convert to empty DataFrame)
    if isinstance(df, list):
        df = pd.DataFrame()
    
    # Handle empty DataFrame
    if df.empty:
        print("No 1234 breakout candidates to save")
        # Create empty file with headers
        empty_df = pd.DataFrame(columns=['ticker', 'date', 'intervals', 'signal_price', 'current_price', 'current_time', 'nx_1d_signal', 'nx_30m_signal', 'nx_1d', 'nx_1h', 'nx_30m'])
        empty_df.to_csv(output_path, sep='\t', index=False)
        return
    
    # Check which columns exist and save accordingly
    available_columns = ['ticker', 'date', 'intervals']
    if 'signal_price' in df.columns:
        available_columns.append('signal_price')
    if 'current_price' in df.columns:
        available_columns.append('current_price')
    if 'current_time' in df.columns:
        available_columns.append('current_time')
    if 'nx_1d_signal' in df.columns:
        available_columns.append('nx_1d_signal')
    if 'nx_30m_signal' in df.columns:
        available_columns.append('nx_30m_signal')
    if 'nx_1d' in df.columns:
        available_columns.append('nx_1d')
    if 'nx_1h' in df.columns:
        available_columns.append('nx_1h')
    if 'nx_30m' in df.columns:
        available_columns.append('nx_30m')
    
    df.to_csv(output_path, sep='\t', index=False, columns=available_columns)

def save_breakout_candidates_5230(df, file_path):
    # Extract base name and directory from the input file path
    directory = os.path.dirname(file_path)
    base_name = os.path.basename(file_path)
    output_path = os.path.join(directory, base_name).replace("details", "summary")
    
    # Handle case where df might be a list (convert to empty DataFrame)
    if isinstance(df, list):
        df = pd.DataFrame()
    
    # Handle empty DataFrame
    if df.empty:
        print("No 5230 breakout candidates to save")
        # Create empty file with headers
        empty_df = pd.DataFrame(columns=['ticker', 'date', 'intervals', 'signal_price', 'current_price', 'current_time', 'nx_1h_signal', 'nx_5m_signal', 'nx_1d', 'nx_1h', 'nx_30m'])
        empty_df.to_csv(output_path, sep='\t', index=False)
        return
    
    # Check which columns exist and save accordingly
    available_columns = ['ticker', 'date', 'intervals']
    if 'signal_price' in df.columns:
        available_columns.append('signal_price')
    if 'current_price' in df.columns:
        available_columns.append('current_price')
    if 'current_time' in df.columns:
        available_columns.append('current_time')
    if 'nx_1h_signal' in df.columns:
        available_columns.append('nx_1h_signal')
    if 'nx_5m_signal' in df.columns:
        available_columns.append('nx_5m_signal')
    if 'nx_1d' in df.columns:
        available_columns.append('nx_1d')
    if 'nx_1h' in df.columns:
        available_columns.append('nx_1h')
    if 'nx_30m' in df.columns:
        available_columns.append('nx_30m')
    
    df.to_csv(output_path, sep='\t', index=False, columns=available_columns)

def save_mc_breakout_candidates_1234(df, file_path):
    """Save MC 1234 breakout candidates summary"""
    # Extract base name and directory from the input file path
    directory = os.path.dirname(file_path)
    base_name = os.path.basename(file_path)
    output_path = os.path.join(directory, base_name).replace("details", "summary")
    
    # Handle case where df might be a list (convert to empty DataFrame)
    if isinstance(df, list):
        df = pd.DataFrame()
    
    # Handle empty DataFrame
    if df.empty:
        print("No MC 1234 breakout candidates to save")
        # Create empty file with headers
        empty_df = pd.DataFrame(columns=['ticker', 'date', 'intervals', 'signal_price', 'current_price', 'current_time', 'nx_1d_signal', 'nx_30m_signal', 'nx_1d', 'nx_1h', 'nx_30m'])
        empty_df.to_csv(output_path, sep='\t', index=False)
        return
    
    # Check which columns exist and save accordingly
    available_columns = ['ticker', 'date', 'intervals']
    if 'signal_price' in df.columns:
        available_columns.append('signal_price')
    if 'current_price' in df.columns:
        available_columns.append('current_price')
    if 'current_time' in df.columns:
        available_columns.append('current_time')
    if 'nx_1d_signal' in df.columns:
        available_columns.append('nx_1d_signal')
    if 'nx_30m_signal' in df.columns:
        available_columns.append('nx_30m_signal')
    if 'nx_1d' in df.columns:
        available_columns.append('nx_1d')
    if 'nx_1h' in df.columns:
        available_columns.append('nx_1h')
    if 'nx_30m' in df.columns:
        available_columns.append('nx_30m')
    
    df.to_csv(output_path, sep='\t', index=False, columns=available_columns)

def save_mc_breakout_candidates_5230(df, file_path):
    """Save MC 5230 breakout candidates summary"""
    # Extract base name and directory from the input file path
    directory = os.path.dirname(file_path)
    base_name = os.path.basename(file_path)
    output_path = os.path.join(directory, base_name).replace("details", "summary")
    
    # Handle case where df might be a list (convert to empty DataFrame)
    if isinstance(df, list):
        df = pd.DataFrame()
    
    # Handle empty DataFrame
    if df.empty:
        print("No MC 5230 breakout candidates to save")
        # Create empty file with headers
        empty_df = pd.DataFrame(columns=['ticker', 'date', 'intervals', 'signal_price', 'current_price', 'current_time', 'nx_1h_signal', 'nx_5m_signal', 'nx_1d', 'nx_1h', 'nx_30m'])
        empty_df.to_csv(output_path, sep='\t', index=False)
        return
    
    # Check which columns exist and save accordingly
    available_columns = ['ticker', 'date', 'intervals']
    if 'signal_price' in df.columns:
        available_columns.append('signal_price')
    if 'current_price' in df.columns:
        available_columns.append('current_price')
    if 'current_time' in df.columns:
        available_columns.append('current_time')
    if 'nx_1h_signal' in df.columns:
        available_columns.append('nx_1h_signal')
    if 'nx_5m_signal' in df.columns:
        available_columns.append('nx_5m_signal')
    if 'nx_1d' in df.columns:
        available_columns.append('nx_1d')
    if 'nx_1h' in df.columns:
        available_columns.append('nx_1h')
    if 'nx_30m' in df.columns:
        available_columns.append('nx_30m')
    
    df.to_csv(output_path, sep='\t', index=False, columns=available_columns)

def calculate_current_nx_values(ticker, all_ticker_data, precomputed_series=None):
    """
    Calculate current NX values for a ticker across different timeframes.
    
    Args:
        ticker: Stock symbol
        all_ticker_data: Dictionary containing ticker data
        precomputed_series: Optional dictionary of precomputed boolean series to avoiding recalculation
                           Format: {'1d': series, '1h': series, ...}
    
    Returns:
        dict: Dictionary with 'nx_1d', 'nx_1h', 'nx_30m', 'nx_5m' boolean values
    """
    results = {
        'nx_1d': None,
        'nx_1h': None,
        'nx_30m': None,
        'nx_5m': None
    }
    
    if ticker not in all_ticker_data:
        return results
        
    precomputed = precomputed_series or {}
    
    # Helper to calculate or reuse NX value
    def get_nx_value(interval, key):
        # Try to use precomputed series logic
        if key in precomputed and precomputed[key] is not None:
            # precomputed[key] is a dict {date: bool} or Series
            # We want current status (latest available)
            # This is tricky because precomputed used date keys.
            # So fallback to recalculation is safer for "current status" unless dates align perfectly.
            pass
            
        if interval in all_ticker_data[ticker] and not all_ticker_data[ticker][interval].empty:
            df = all_ticker_data[ticker][interval]
            close = df['Close']
            short = close.ewm(span=24, adjust=False).mean()
            long = close.ewm(span=89, adjust=False).mean()
            return bool((short > long).iloc[-1])
        return None

    results['nx_1d'] = get_nx_value('1d', '1d')
    results['nx_1h'] = get_nx_value('1h', '1h')
    results['nx_30m'] = get_nx_value('30m', '30m')
    results['nx_5m'] = get_nx_value('5m', '5m')
    
    return results
