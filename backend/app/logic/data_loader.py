import numpy as np
import pandas as pd
import yfinance as yf
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

MARKET_TZ = 'America/New_York'
MARKET_CLOSE = pd.Timedelta(hours=16)
INTRADAY_BAR_LENGTH = {'1h': pd.Timedelta(hours=1), '2h': pd.Timedelta(hours=2),
                       '3h': pd.Timedelta(hours=3), '4h': pd.Timedelta(hours=4)}

def unfinished_bars(index, interval, now=None):
    """
    Boolean array: True for bars that have not closed yet at `now`.
    Bars are labelled by their start time; an intraday bar ends after its length or at the 16:00 close,
    a daily bar at the 16:00 close. Naive timestamps are taken as US/Eastern (how the database stores them).
    """
    idx = pd.DatetimeIndex(index)
    if len(idx) == 0 or (interval != '1d' and interval not in INTRADAY_BAR_LENGTH):
        return np.zeros(len(idx), dtype=bool)
    local = idx.tz_convert(MARKET_TZ) if idx.tz is not None else idx.tz_localize(MARKET_TZ)
    now = pd.Timestamp.now(tz=MARKET_TZ) if now is None else pd.Timestamp(now)
    now = now.tz_convert(MARKET_TZ) if now.tzinfo is not None else now.tz_localize(MARKET_TZ)
    session_close = local.normalize() + MARKET_CLOSE
    if interval == '1d':
        ends = session_close
    else:
        ends = local + INTRADAY_BAR_LENGTH[interval]
        ends = ends.where(ends < session_close, session_close)
    return np.asarray(ends > now)

def drop_unfinished_bars(data_ticker, now=None):
    """Copy of data_ticker without bars that are still forming, so signals only come from closed bars."""
    result = dict(data_ticker)
    for interval, df in data_ticker.items():
        if isinstance(df, pd.DataFrame) and not df.empty:
            result[interval] = df[~unfinished_bars(df.index, interval, now)]
    return result

def load_stock_list(file_path):
    return pd.read_csv(file_path, sep='\t', header=None, names=['ticker'])['ticker'].tolist()

def truncate_data_to_date(data_frame, end_date):
    """
    Truncate DataFrame to only include data up to the specified end_date.
    
    Args:
        data_frame: pandas DataFrame with datetime index
        end_date: end date (string 'YYYY-MM-DD' or datetime object)
    
    Returns:
        Truncated DataFrame
    """
    if data_frame.empty:
        return data_frame
        
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, '%Y-%m-%d')
    
    # Convert end_date to pandas Timestamp and handle timezone
    end_date = pd.Timestamp(end_date)
    
    # Handle timezone-aware datetime indexes
    if data_frame.index.tz is not None:
        # end_date is a calendar date in the data's own timezone; converting from UTC would shift it back a day
        end_date = end_date.tz_localize(data_frame.index.tz)
    
    return data_frame[data_frame.index.date <= end_date.date()]

def download_stock_data(ticker, end_date=None):
    """
    Download stock data for all required intervals in a single function
    
    Args:
        ticker: Stock ticker symbol
        end_date: Optional end date for backtesting (format: 'YYYY-MM-DD' or datetime)
                 If None, uses current date (no truncation)
    
    Returns:
        Dictionary with data for all intervals needed
    """
    print(f"Downloading data for {ticker}...")
    
    # Process end_date parameter for truncation
    truncate_data = False
    if end_date is not None:
        truncate_data = True
        if isinstance(end_date, str):
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d')
            except ValueError:
                print(f"Invalid end_date format: {end_date}. No truncation will be applied.")
                truncate_data = False
    
    data_ticker = {}
    stock = yf.Ticker(ticker)
    
    try:
        # Get 1-hour data for medium timeframes
        data_ticker['1h'] = stock.history(interval='60m', period='2y')
        if not data_ticker['1h'].empty:
            print(f"Downloaded 1h data for {ticker}")
        else:
            print(f"No 1h data available for {ticker}")
    except Exception as e:
        print(f"Error downloading {ticker} 1h data: {e}")
        data_ticker['1h'] = pd.DataFrame()
    
    try:
        # Get daily data for long timeframes
        data_ticker['1d'] = stock.history(interval='1d', period='2y')
        if not data_ticker['1d'].empty:
            print(f"Downloaded 1d data for {ticker}")
        else:
            print(f"No 1d data available for {ticker}")
    except Exception as e:
        print(f"Error downloading {ticker} 1d data: {e}")
        data_ticker['1d'] = pd.DataFrame()
    
    # Truncate data to end_date if backtesting mode is enabled
    if truncate_data:
        print(f"Truncating data to {end_date.strftime('%Y-%m-%d')} for backtesting")
        for interval_key in ['1h', '1d']:
            if not data_ticker[interval_key].empty:
                original_count = len(data_ticker[interval_key])
                data_ticker[interval_key] = truncate_data_to_date(data_ticker[interval_key], end_date)
                if not data_ticker[interval_key].empty:
                    print(f"Truncated {interval_key} data for {ticker}: {len(data_ticker[interval_key])}/{original_count} records up to {end_date.strftime('%Y-%m-%d')}")
    
    # Validate: check that 1h data covers all trading days in 1d data
    warnings = validate_intraday_coverage(ticker, data_ticker)
    data_ticker['_warnings'] = warnings
    
    # Generate derived timeframes from base downloads
    # Process 1h to create 2h, 3h, 4h
    if not data_ticker['1h'].empty:
        for interval in ['2h', '3h', '4h']:
            data_ticker[interval] = transform_1h_data(data_ticker['1h'], interval)
    
    return data_ticker


def validate_intraday_coverage(ticker, data_ticker):
    """Check that 1h data covers all trading days present in 1d data.
    Returns a list of warning strings for any missing dates."""
    warnings = []
    df_1h = data_ticker.get('1h', pd.DataFrame())
    df_1d = data_ticker.get('1d', pd.DataFrame())
    
    if df_1h.empty or df_1d.empty:
        return warnings
    
    # Get unique trading dates from each
    dates_1h = set(str(d) for d in df_1h.index.date)
    dates_1d = set(str(d) for d in df_1d.index.date)
    
    # Only check dates within the 1h data range (1h may have shorter history than 1d)
    if df_1h.index.tz is not None:
        first_1h_date = df_1h.index[0].date()
    else:
        first_1h_date = df_1h.index[0].date()
    
    # Filter 1d dates to only those on or after the first 1h date
    dates_1d_in_range = set(d for d in dates_1d if d >= str(first_1h_date))
    
    # Find dates in 1d but missing from 1h
    missing_dates = sorted(dates_1d_in_range - dates_1h)
    
    if missing_dates:
        msg = f"⚠️ {ticker}: Missing 1h data for {len(missing_dates)} trading day(s): {', '.join(missing_dates)}"
        logger.warning(msg)
        print(msg)
        warnings.append(msg)
    
    return warnings

def transform_1h_data(df_1h, new_interval = '2h'):
    if df_1h.empty:
        return pd.DataFrame()
    df_1h.index = pd.to_datetime(df_1h.index)
    df_1h.sort_index(inplace=True)

    df_1h = df_1h.between_time("09:30", "16:00")

    grouped = df_1h.groupby(df_1h.index.date)

    def resample_xh(daily_df):
        return daily_df.resample(
            rule=new_interval,
            closed="left",
            label="left",
            origin="start_day", 
            offset="9h30min"
        ).agg({
            "Open":  "first",
            "High":  "max",
            "Low":   "min",
            "Close": "last",
            "Volume":"sum"
        })

    df_xh_list = []
    for date_key, daily_data in grouped:
        bar_xh = resample_xh(daily_data)
        bar_xh.dropna(subset=["Open","High","Low","Close"], how="any", inplace=True)
        df_xh_list.append(bar_xh)

    df_xh = pd.concat(df_xh_list).sort_index() if df_xh_list else pd.DataFrame()
    return df_xh
