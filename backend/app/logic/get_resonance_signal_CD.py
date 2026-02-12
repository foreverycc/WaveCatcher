import pandas as pd
from indicators import compute_cd_indicator, compute_nx_break_through
from utils import calculate_current_nx_values, get_trading_day_window_end
    
def calculate_score(data, interval, signal_date):
    interval_weights = {
        '1h': 6, 
        '2h': 7,
        '3h': 8,
        '4h': 9,
        '1d': 10
    }
    iw = interval_weights.get(interval, 0)
    
    # 获取信号当天的数据
    row = data.loc[signal_date]
    candle_size = round(float(abs(row['Close'] - row['Open']) / row['Close'] * 100), 2)  # Convert to Python float
    
    # 计算过去20天的平均成交量
    avg_volume = data['Volume'].rolling(20).mean().loc[:signal_date].iloc[-1]
    volume_ratio = row['Volume'] / avg_volume if avg_volume != 0 else 0
    
    score = iw * 0.5 + candle_size * 0.3 + volume_ratio * 0.2
    return round(score, 2)

def process_ticker_1234(ticker, data_ticker=None):
    """
    Process ticker for 1234 breakout analysis
    
    Args:
        ticker: Stock symbol
        data_ticker: pre-downloaded data dictionary, key is interval, value is dataframe
    
    Returns:
        List of results
    """
    intervals = ['1h', '2h', '3h', '4h', '1d']
    
    results = []
    # Use provided data or download if not provided
    if data_ticker is None:
        print (f"data not provided for {ticker}")
        # throw an error
        raise ValueError(f"data not provided for {ticker}") 

    for interval in intervals:
        print(f"ticker: {ticker} interval: {interval}")
        data = data_ticker.get(interval, pd.DataFrame())
        if data.empty:
            print(f"data is empty: {ticker} {interval}")
            continue
        
        try:
            cd = compute_cd_indicator(data)
            breakthrough = compute_nx_break_through(data)
            # Handle NaN values by replacing them with False for boolean operations
            cd_bool = cd.fillna(False).infer_objects(copy=False).astype(bool)
            buy_signals = (cd_bool & breakthrough) | (cd_bool & breakthrough.rolling(10).apply(lambda x: x.iloc[0] if x.any() else False))   
            signal_dates = data.index[buy_signals]
            breakthrough_dates = data.index[breakthrough]
            
            # Filter out NaN values for signal processing
            valid_cd_signals = cd.fillna(False).infer_objects(copy=False)
            for date in data.index[valid_cd_signals]:
                score = calculate_score(data, interval, date)
                signal_price = data.loc[date, 'Close']  # Get the Close price at signal date
                # Find the next breakthrough date after the signal date
                future_breakthroughs = breakthrough_dates[breakthrough_dates >= date]
                next_breakthrough = future_breakthroughs[0] if len(future_breakthroughs) > 0 else None

                results.append({
                    'ticker': ticker,
                    'interval': interval,
                    'score': score,
                    'signal_date': date.strftime('%Y-%m-%d %H:%M:%S'),
                    'signal_price': round(signal_price, 2),
                    'breakthrough_date': next_breakthrough.strftime('%Y-%m-%d %H:%M:%S') if next_breakthrough is not None else None
                })
        except Exception as e:
            print(f"Error processing {ticker} {interval}: {e}")
    
    return results


def identify_1234(data, all_ticker_data):
    """
    Identify potential breakout stocks based on breakout signals across the 1h, 2h, 3h, and 4h intervals.
    
    Parameters:
        data (pd.DataFrame or list): DataFrame or list of dictionaries containing breakout signals.
        all_ticker_data (dict): Dictionary with pre-downloaded ticker data.

    Returns:
        DataFrame: A DataFrame of ticker symbols that are potential breakout stocks.
    """
    try:
        if isinstance(data, list):
            df = pd.DataFrame(data)
        elif isinstance(data, pd.DataFrame):
            df = data.copy()
        else:
            print("Invalid data format for identify_1234")
            return pd.DataFrame()
            
        if df.empty:
            return pd.DataFrame()

    except Exception as e:
        print(f"Error processing data in identify_1234: {e}")
        return pd.DataFrame()

    # Ensure signal_date is parsed as datetime
    if "signal_date" in df.columns:
        df["signal_date"] = pd.to_datetime(df["signal_date"], errors="coerce")

    # Define the required intervals
    required_intervals = {"1h", "2h", "3h", "4h"}
    # Filter for rows whose interval is in our required set
    df = df[df["interval"].isin(required_intervals)]

    breakout_candidates = []
    processed_combinations = set()  # Track (ticker, date) combinations to avoid duplicates

    # Group data by ticker
    # Convert signal_date to date only (removing time component)
    df['date'] = df['signal_date'].dt.date

    # Use sorted unique dates to ensure proper time window calculation
    unique_dates = sorted(df['date'].unique())
    # Get unique dates to iterate through
    for i in range(len(unique_dates)):
        date = unique_dates[i]
        # Get data within BROAD window (e.g. 10 days) to assume coverage
        window_end_broad = date + pd.Timedelta(days=10)
        window_data_broad = df[(df['date'] >= date) & 
                        (df['date'] < window_end_broad)]
        
        # Check each ticker in this window
        for ticker in window_data_broad['ticker'].unique():
            # Apply precise trading day window
            precise_end_date = get_trading_day_window_end(date, ticker, all_ticker_data, days=3)
            
            ticker_data = window_data_broad[(window_data_broad['ticker'] == ticker) & 
                                            (window_data_broad['date'] < precise_end_date + pd.Timedelta(days=1))] # precise_end is inclusive day
            
            unique_intervals = set(ticker_data['interval'])

            if len(unique_intervals.intersection(required_intervals)) >= 3:
                # Get the most recent signal date within this window for this ticker
                most_recent_signal_date = ticker_data['signal_date'].max().date()
                # Check if we've already processed this combination
                combination = (ticker, most_recent_signal_date)
                if combination not in processed_combinations:
                    processed_combinations.add(combination)
                    # Get the latest signal price for this ticker/date combination (most recent signal)
                    latest_signal_price = ticker_data.loc[ticker_data['signal_date'].idxmax(), 'signal_price'] if 'signal_price' in ticker_data.columns and not ticker_data.empty else None
                    resonating_intervals_set = unique_intervals.intersection(required_intervals)
                    intervals_str = ",".join(map(str, sorted([int(s.replace('h', '')) for s in resonating_intervals_set])))
                    breakout_candidates.append([ticker, most_recent_signal_date, intervals_str, latest_signal_price])
    
    # Include signal_price column if available
    columns = ['ticker', 'date', 'intervals']
    if any(len(candidate) > 3 for candidate in breakout_candidates):
        columns.append('signal_price')
        
    df_breakout_candidates = pd.DataFrame(breakout_candidates, columns=columns).sort_values(by=['date', 'ticker'], ascending=[False, True])

    current_data = df_breakout_candidates['ticker'].apply(lambda ticker: 
        (
            round(all_ticker_data[ticker]['1d'].iloc[-1]['Close'], 2),
            all_ticker_data[ticker]['1d'].iloc[-1].name.strftime('%Y-%m-%d %H:%M:%S')
        ) if ticker in all_ticker_data and '1d' in all_ticker_data[ticker] and not all_ticker_data[ticker]['1d'].empty else (None, None)
    )
    df_breakout_candidates[['current_price', 'current_time']] = pd.DataFrame(current_data.tolist(), index=df_breakout_candidates.index)

    dict_nx_1d = {}

    for ticker in df_breakout_candidates['ticker'].unique():
        # Calculate nx_1d
        if ticker not in all_ticker_data or '1d' not in all_ticker_data[ticker] or all_ticker_data[ticker]['1d'].empty:
            print(f"No 1d data found for {ticker} in pre-downloaded data, skipping nx_1d calculation.")
            continue
            
        df_stock = all_ticker_data[ticker]['1d']
        
        close = df_stock['Close']
        short_close = close.ewm(span = 24, adjust=False).mean()
        long_close = close.ewm(span = 89, adjust=False).mean()
        nx_1d = (short_close > long_close) 

        nx_1d.index = nx_1d.index.date
        dict_nx_1d[ticker] = nx_1d.to_dict()
    
    # remove tickers that failed to get data
    df_breakout_candidates = df_breakout_candidates[df_breakout_candidates['ticker'].isin(dict_nx_1d.keys())]
    
    # Check if DataFrame is empty after filtering
    if df_breakout_candidates.empty:
        print("No breakout candidates found after filtering")
        return df_breakout_candidates  # Return empty DataFrame
    
    # add nx_1d to df_breakout_candidates according to ticker and date
    df_breakout_candidates['nx_1d_signal'] = df_breakout_candidates.apply(lambda row: dict_nx_1d[row['ticker']].get(row['date'], None), axis=1)
    
    # Add current nx values
    current_nx_data = df_breakout_candidates['ticker'].apply(
        lambda ticker: calculate_current_nx_values(
            ticker,
            all_ticker_data,
            precomputed_series={
                '1d': dict_nx_1d.get(ticker),
            }
        )
    )
    # Assign columns individually to avoid duplicate column issues
    current_nx_df = pd.DataFrame(current_nx_data.tolist(), index=df_breakout_candidates.index)
    df_breakout_candidates['nx_1d'] = current_nx_df['nx_1d']
    df_breakout_candidates['nx_1h'] = current_nx_df['nx_1h']
   
    df_breakout_candidates_sel = df_breakout_candidates
    
    return df_breakout_candidates_sel

