import pandas as pd
import yfinance as yf
from datetime import datetime

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
        # If data has timezone, convert end_date to the same timezone
        # First convert to UTC, then to the data's timezone
        end_date = end_date.tz_localize('UTC').tz_convert(data_frame.index.tz)
    
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
    
    # Define base timeframes to download directly (using original periods)
    try:
        # Get 5-minute data for short timeframes
        # data_ticker['5m'] = stock.history(interval='5m', period='1mo')
        data_ticker['5m'] = stock.history(interval='5m', period='60d')
        if not data_ticker['5m'].empty:
            print(f"Downloaded 5m data for {ticker}")
        else:
            print(f"No 5m data available for {ticker}")
    except Exception as e:
        print(f"Error downloading {ticker} 5m data: {e}")
        data_ticker['5m'] = pd.DataFrame()
    
    try:
        # Get 1-hour data for medium timeframes
        # data_ticker['1h'] = stock.history(interval='60m', period='3mo')
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
        # data_ticker['1d'] = stock.history(interval='1d', period='1y')
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
        for interval_key in ['5m', '1h', '1d']:
            if not data_ticker[interval_key].empty:
                original_count = len(data_ticker[interval_key])
                data_ticker[interval_key] = truncate_data_to_date(data_ticker[interval_key], end_date)
                if not data_ticker[interval_key].empty:
                    print(f"Truncated {interval_key} data for {ticker}: {len(data_ticker[interval_key])}/{original_count} records up to {end_date.strftime('%Y-%m-%d')}")
    
    # Generate derived timeframes from base downloads
    # Process 5m to create 10m, 15m, 30m
    if not data_ticker['5m'].empty:
        for interval in ['10m', '15m', '30m']:
            data_ticker[interval] = transform_5m_data(data_ticker['5m'], interval)
            
    # Process 1h to create 2h, 3h, 4h
    if not data_ticker['1h'].empty:
        for interval in ['2h', '3h', '4h']:
            data_ticker[interval] = transform_1h_data(data_ticker['1h'], interval)
    
    # Create weekly data from daily data
    if not data_ticker['1d'].empty:
        data_ticker['1w'] = data_ticker['1d'].resample('W').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        })
    else:
        data_ticker['1w'] = pd.DataFrame()
    
    return data_ticker

def transform_1h_data(df_1h, new_interval = '2h'):
    if df_1h.empty:
        return pd.DataFrame()
    # 确保DatetimeIndex
    df_1h.index = pd.to_datetime(df_1h.index)
    df_1h.sort_index(inplace=True)  # 排序一下，以防万一

    # ============== 2) 只保留日盘 (9:30-16:00) ==============
    #   如果你也想包括盘前/盘后，则可不做这步，或改成更广时间段
    df_1h = df_1h.between_time("09:30", "16:00")

    # ============== 3) 按"每个自然日"分组 ==============
    #   这样做可以保证日内聚合，跨日不拼接。
    grouped = df_1h.groupby(df_1h.index.date)

    # ============== 4) 对单日数据做 "2H" 重采样 ==============
    def resample_xh(daily_df):
        """
        对当日(9:30~16:00)的 1 小时数据做 x 小时的重采样:
        - Bar起点对齐到 9:30
        - 最后不足x小时的也生成单独一根
        """
        # 注意这里 origin="start_day", offset="9h30min" 是关键
        # 使得日内区间从 当日00:00+9h30 => 当日09:30 开始切分
        # 结果区间: 9:30~11:30, 11:30~13:30, 13:30~15:30, 15:30~17:30(只到16:00)
        return daily_df.resample(
            rule=new_interval,
            closed="left",   # 区间左闭右开
            label="left",    # 用区间左端做时间戳
            origin="start_day", 
            offset="9h30min"
        ).agg({
            "Open":  "first",
            "High":  "max",
            "Low":   "min",
            "Close": "last",
            "Volume":"sum"
        })

    # ============== 5) 分日重采样，再拼接回总表 ==============
    df_xh_list = []
    for date_key, daily_data in grouped:
        # 做 xH 重采样
        bar_xh = resample_xh(daily_data)
        
        # 有时遇到完全没数据或NaN的行，可自行选择是否 dropna()
        bar_xh.dropna(subset=["Open","High","Low","Close"], how="any", inplace=True)
        
        df_xh_list.append(bar_xh)

    # 合并成完整的X小时数据表
    df_xh = pd.concat(df_xh_list).sort_index() if df_xh_list else pd.DataFrame()
    return df_xh

def transform_5m_data(df_5m, new_interval = '10m'):
    if df_5m.empty:
        return pd.DataFrame()
    # 确保DatetimeIndex
    df_5m.index = pd.to_datetime(df_5m.index)
    df_5m.sort_index(inplace=True)  # 排序一下，以防万一
    
    # ============== 2) 只保留日盘 (9:30-16:00) ==============
    #   如果你也想包括盘前/盘后，则可不做这步，或改成更广时间段
    df_5m = df_5m.between_time("09:30", "16:00")

    # ============== 3) 按"每个自然日"分组 ==============
    #   这样做可以保证日内聚合，跨日不拼接。
    grouped = df_5m.groupby(df_5m.index.date)

    # ============== 4) 对单日数据做 "10m" 重采样 ==============
    def resample_xh(daily_df):
        """
        对当日(9:30~16:00)的 5 分钟数据做 x 分钟的重采样:
        - Bar起点对齐到 9:30
        - 最后不足x分钟的也生成单独一根
        """
        # 注意这里 origin="start_day", offset="9h30min" 是关键
        # 使得日内区间从 当日00:00+9h30 => 当日09:30 开始切分
        return daily_df.resample(
            rule=new_interval.replace('m', 'min'),
            closed="left",   # 区间左闭右开
            label="left",    # 用区间左端做时间戳
            origin="start_day", 
            offset="9h30min"
        ).agg({
            "Open":  "first",
            "High":  "max",
            "Low":   "min",
            "Close": "last",
            "Volume":"sum"
        })

    # ============== 5) 分日重采样，再拼接回总表 ==============
    df_xh_list = []
    for date_key, daily_data in grouped:
        # 做 xH 重采样
        bar_xh = resample_xh(daily_data)
        
        # 有时遇到完全没数据或NaN的行，可自行选择是否 dropna()
        bar_xh.dropna(subset=["Open","High","Low","Close"], how="any", inplace=True)
        
        df_xh_list.append(bar_xh)

    # 合并成完整的X小时数据表
    df_xh = pd.concat(df_xh_list).sort_index() if df_xh_list else pd.DataFrame()
    return df_xh
