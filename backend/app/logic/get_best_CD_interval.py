import pandas as pd
import numpy as np
from data_loader import download_stock_data
from indicators import compute_cd_indicator, compute_mc_indicator
import yfinance as yf

# EMA warmup period - should match the value in indicators.py
EMA_WARMUP_PERIOD = 0

# Maximum number of latest signals to process (to reduce noise from older signals)
MAX_SIGNALS_THRESHOLD = 7

def find_latest_mc_signal_before_cd(data, cd_date, mc_signals):
    """
    Find the latest MC signal that occurred before a given CD signal date.
    
    Args:
        data: DataFrame with price data
        cd_date: Date of the CD signal
        mc_signals: Series with MC signals (boolean)
    
    Returns:
        Tuple of (mc_signal_date, mc_signal_price) or (None, None) if no MC signal found
    """
    # Get all MC signal dates before the CD signal date
    # Handle NaN values by replacing them with False for boolean indexing
    mc_signals_bool = mc_signals.fillna(False).infer_objects(copy=False)
    mc_signal_dates = data.index[mc_signals_bool]
    previous_mc_signals = mc_signal_dates[mc_signal_dates < cd_date]
    
    if len(previous_mc_signals) == 0:
        return None, None
    
    # Get the latest MC signal before the CD signal
    latest_mc_date = previous_mc_signals.max()
    latest_mc_price = data.loc[latest_mc_date, 'Close']
    
    return latest_mc_date, latest_mc_price

def evaluate_mc_at_top_price(data, mc_date, mc_price, cd_date):
    """
    Evaluate if an MC signal was at a "top price" by checking if it was near a local maximum.
    
    Args:
        data: DataFrame with price data
        mc_date: Date of the MC signal
        mc_price: Price at the MC signal
        cd_date: Date of the latest CD signal (used for range calculations)
    
    Returns:
        Dictionary with evaluation metrics
    """
    try:
        mc_idx = data.index.get_loc(mc_date)
        cd_idx = data.index.get_loc(cd_date)
        
        # 1. Calculate lookback range: from EMA warmup period to latest CD time point
        # Exclude unreliable early periods before EMA convergence
        warmup_start = min(EMA_WARMUP_PERIOD, len(data) - 1)
        lookback_data = data.iloc[warmup_start:cd_idx+1]  # Start from warmup period, include CD signal date
        
        # 2. Calculate lookahead range: from MC signal to latest CD time point
        lookahead_data = data.iloc[mc_idx:cd_idx+1]  # Include CD signal date
        
        # Calculate metrics
        metrics = {}
        
        # 1. Check if MC price is near the highest price in the full historical range
        if not lookback_data.empty:
            lookback_max = lookback_data['High'].max()
            lookback_min = lookback_data['Low'].min()
            lookback_range = lookback_max - lookback_min
            
            # Calculate percentile position of MC price in full historical range
            if lookback_range > 0:
                price_percentile = (mc_price - lookback_min) / lookback_range
                metrics['lookback_price_percentile'] = price_percentile
                metrics['is_near_lookback_high'] = price_percentile >= 0.8  # Top 20% of full range
            else:
                metrics['lookback_price_percentile'] = 0.5
                metrics['is_near_lookback_high'] = False
        else:
            metrics['lookback_price_percentile'] = 0.5
            metrics['is_near_lookback_high'] = False
        
        # 2. Check if price declined after MC signal until CD signal (more stringent threshold)
        if len(lookahead_data) > 1:
            lookahead_min = lookahead_data['Low'].min()
            price_decline_pct = round((mc_price - lookahead_min) / mc_price * 100, 2)
            metrics['price_decline_after_mc'] = price_decline_pct
            metrics['is_followed_by_decline'] = price_decline_pct >= 5.0  # At least 5% decline (increased from 2%)
        else:
            metrics['price_decline_after_mc'] = 0
            metrics['is_followed_by_decline'] = False
        
        # 3. Check if MC signal is at local maximum using relative method
        # Use dynamic window size based on data availability and relative price position
        # Calculate window size as a percentage of total data length (more robust across timeframes)
        total_length = len(data)
        window_size = max(3, min(10, total_length // 20))  # 5% of data length, but between 3-10 periods
        
        window_start = max(0, mc_idx - window_size)
        window_end = min(len(data), mc_idx + window_size + 1)
        window_data = data.iloc[window_start:window_end]
        
        if not window_data.empty and len(window_data) > 1:
            # Use relative ranking instead of fixed percentage
            window_highs = window_data['High'].values
            mc_rank = sum(mc_price >= h for h in window_highs) / len(window_highs)
            
            # MC signal is local max if it's in top 30% of surrounding prices
            is_local_max = mc_rank >= 0.7
            metrics['is_local_maximum'] = is_local_max
        else:
            metrics['is_local_maximum'] = False
        
        # 4. Overall evaluation - MC signal is at "top price" if it meets multiple criteria
        criteria_met = sum([
            metrics['is_near_lookback_high'],
            metrics['is_followed_by_decline'],
            metrics['is_local_maximum']
        ])
        
        metrics['criteria_met'] = criteria_met
        metrics['is_at_top_price'] = criteria_met >= 2  # At least 2 out of 3 criteria
        
        return metrics
        
    except Exception as e:
        print(f"Error evaluating MC signal at {mc_date}: {e}")
        return {
            'lookback_price_percentile': 0.5,
            'is_near_lookback_high': False,
            'price_decline_after_mc': 0,
            'is_followed_by_decline': False,
            'is_local_maximum': False,
            'criteria_met': 0,
            'is_at_top_price': False
        }

def calculate_returns(data, cd_signals, periods=None, max_signals=MAX_SIGNALS_THRESHOLD):
    """
    Calculate returns after CD signals for specified periods.
    
    Args:
        data: DataFrame with price data
        cd_signals: Series with CD signals (boolean)
        periods: List of periods to calculate returns for (default: 0 to 100)
        max_signals: Maximum number of latest signals to process (default: MAX_SIGNALS_THRESHOLD)
    
    Returns:
        DataFrame with signal dates, returns, and volume data for each period
    """
    if periods is None:
        periods = [0] + list(range(1, 101))  # Full range from 0 to 100
    results = []
    # Handle NaN values by replacing them with False for boolean indexing
    cd_signals_bool = cd_signals.fillna(False).infer_objects(copy=False)
    signal_dates = data.index[cd_signals_bool]
    
    # Limit to the latest N signals to reduce noise from older signals
    if len(signal_dates) > max_signals:
        signal_dates = signal_dates[-max_signals:]
    
    # Also compute MC signals for analysis
    mc_signals = compute_mc_indicator(data)
    
    for date in signal_dates:
        idx = data.index.get_loc(date)
        
        # Skip signals that are too close to the end of the data
        if idx + max(periods) >= len(data):
            continue
            
        entry_price = data.loc[date, 'Close']
        entry_volume = data.loc[date, 'Volume']
        returns = {}
        volumes = {}
        
        for period in periods:
            if idx + period < len(data):
                exit_price = data.iloc[idx + period]['Close']
                exit_volume = data.iloc[idx + period]['Volume']
                returns[f'return_{period}'] = round(float((exit_price - entry_price) / entry_price * 100), 2)  # Convert to Python float
                volumes[f'volume_{period}'] = round(int(exit_volume), 0)  # Convert to Python int
            else:
                returns[f'return_{period}'] = np.nan
                volumes[f'volume_{period}'] = np.nan
        
        # Find the latest MC signal before this CD signal
        latest_mc_date, latest_mc_price = find_latest_mc_signal_before_cd(data, date, mc_signals)
        
        # Evaluate if the MC signal was at top price
        mc_evaluation = {}
        if latest_mc_date is not None:
            mc_evaluation = evaluate_mc_at_top_price(data, latest_mc_date, latest_mc_price, date)
            
        # Add MC signal analysis to the results
        mc_info = {
            'prev_mc_date': latest_mc_date.strftime('%Y-%m-%d %H:%M:%S') if latest_mc_date else None,
            'prev_mc_price': round(latest_mc_price, 2) if latest_mc_price else None,
            'mc_at_top_price': mc_evaluation.get('is_at_top_price', False),
            'mc_price_percentile': round(mc_evaluation.get('lookback_price_percentile', 0), 2),
            'mc_decline_after': round(mc_evaluation.get('price_decline_after_mc', 0), 2),
            'mc_criteria_met': mc_evaluation.get('criteria_met', 0)
        }
                
        results.append({
            'date': date,
            'entry_volume': entry_volume,
            **returns,
            **volumes,
            **mc_info
        })
    
    return pd.DataFrame(results)

def evaluate_interval(ticker, interval, data=None):
    """
    Evaluate CD signals for a specific ticker and interval.
    
    Args:
        ticker: Stock ticker symbol
        interval: Time interval to evaluate
        data: Optional pre-downloaded data dictionary
    
    Returns:
        Dictionary with evaluation metrics and individual returns
    """
    print(f"Evaluating {ticker} at {interval} interval")
    
    try:
        # If data dictionary is provided, use it
        if data and interval in data and not data[interval].empty:
            data_frame = data[interval]
        else:
            # Handle weekly interval separately
            if interval == '1w':
                # Try to use daily data from the provided dictionary
                if data and '1d' in data and not data['1d'].empty:
                    daily_data = data['1d']
                else:
                    stock = yf.Ticker(ticker)
                    daily_data = stock.history(interval='1d', period='1y')
                    
                if daily_data.empty:
                    return None
                    
                # Resample daily data to weekly
                data_frame = daily_data.resample('W').agg({
                    'Open': 'first',
                    'High': 'max',
                    'Low': 'min',
                    'Close': 'last',
                    'Volume': 'sum'
                })
            # Get data based on interval type
            elif interval in ['5m', '10m', '15m', '30m', '1h', '2h', '3h', '4h']:
                data_ticker = download_stock_data(ticker, end_date=None)
                data_frame = data_ticker[interval]
            elif interval == '1d':
                stock = yf.Ticker(ticker)
                data_frame = stock.history(interval='1d', period='1y')
            else:
                return None
                
        if data_frame.empty:
            return None
            
        # Compute CD signals
        cd_signals = compute_cd_indicator(data_frame)
        # Handle NaN values for signal count calculation
        signal_count = cd_signals.fillna(False).infer_objects(copy=False).sum()
        
        # Get the latest signal date
        # Handle NaN values by replacing them with False for boolean indexing
        cd_signals_bool = cd_signals.fillna(False).infer_objects(copy=False)
        latest_signal_date = data_frame.index[cd_signals_bool].max() if signal_count > 0 else None
        latest_signal_str = latest_signal_date.strftime('%Y-%m-%d %H:%M:%S') if latest_signal_date else None
        latest_signal_price = round(float(data_frame.loc[latest_signal_date, 'Close']), 2) if latest_signal_date is not None else None  # Convert to Python float
        
        # Get current time and price
        current_time = data_frame.index[-1]
        current_time_str = current_time.strftime('%Y-%m-%d %H:%M:%S')
        current_price = round(float(data_frame.iloc[-1]['Close']), 2)  # Convert to Python float
        
        if signal_count == 0:
            result = {
                'ticker': ticker,
                'interval': interval,
                'signal_count': 0,
                'latest_signal': None,
                'latest_signal_price': None,
                'current_time': current_time_str,
                'current_price': current_price,
                'current_period': 0,
                'max_return': 0,
                'min_return': 0,
                'price_history': {},
                'volume_history': {}
            }
            # Add zero values for all periods
            periods = [0] + list(range(1, 101))  # Full range from 0 to 100
            for period in periods:
                result[f'test_count_{period}'] = 0
                result[f'success_rate_{period}'] = 0
                result[f'avg_return_{period}'] = 0
                result[f'returns_{period}'] = []  # Store empty list for individual returns
                result[f'volumes_{period}'] = [] # Store empty list for individual volumes
            
            # Add MC signal analysis fields
            result['mc_signals_before_cd'] = 0
            result['mc_at_top_price_count'] = 0
            result['mc_at_top_price_rate'] = 0
            result['avg_mc_price_percentile'] = 0
            result['avg_mc_decline_after'] = 0
            result['avg_mc_criteria_met'] = 0
            
            # Add latest MC signal data (all None/False when no data)
            result['latest_mc_date'] = None
            result['latest_mc_price'] = None
            result['latest_mc_at_top_price'] = False
            result['latest_mc_price_percentile'] = 0
            result['latest_mc_decline_after'] = 0
            result['latest_mc_criteria_met'] = 0
            
            # Add NX values (both signal and current values)
            result['nx_1d_signal'] = None
            result['nx_30m_signal'] = None  
            result['nx_1h_signal'] = None
            result['nx_5m_signal'] = None
            result['nx_1d'] = None
            result['nx_30m'] = None
            result['nx_1h'] = None
            result['nx_5m'] = None
            result['nx_4h'] = None
            
            # Calculate current NX values using pre-downloaded data
            if data:
                for timeframe in ['1d', '30m', '1h', '5m', '4h']:
                    if timeframe in data and not data[timeframe].empty:
                        df_nx = data[timeframe]
                        if len(df_nx) >= 89:  # Need at least 89 periods for long EMA
                            close = df_nx['Close']
                            short_close = close.ewm(span=24, adjust=False).mean()
                            long_close = close.ewm(span=89, adjust=False).mean()
                            current_nx = short_close.iloc[-1] > long_close.iloc[-1]
                            result[f'nx_{timeframe}'] = bool(current_nx)
            
            return result
            
        # Calculate returns for each signal (limit to latest signals to reduce noise)
        returns_df = calculate_returns(data_frame, cd_signals, max_signals=MAX_SIGNALS_THRESHOLD)
        
        if returns_df.empty:
            result = {
                'ticker': ticker,
                'interval': interval,
                'signal_count': signal_count,
                'latest_signal': latest_signal_str,
                'latest_signal_price': latest_signal_price,
                'current_time': current_time_str,
                'current_price': current_price,
                'current_period': 0,
                'max_return': 0,
                'min_return': 0,
                'price_history': {},
                'volume_history': {}
            }
            # Add zero values for all periods
            periods = [0] + list(range(1, 101))  # Full range from 0 to 100
            for period in periods:
                result[f'test_count_{period}'] = 0
                result[f'success_rate_{period}'] = 0
                result[f'avg_return_{period}'] = 0
                result[f'returns_{period}'] = []  # Store empty list for individual returns
                result[f'volumes_{period}'] = [] # Store empty list for individual volumes
            
            # Add MC signal analysis fields
            result['mc_signals_before_cd'] = 0
            result['mc_at_top_price_count'] = 0
            result['mc_at_top_price_rate'] = 0
            result['avg_mc_price_percentile'] = 0
            result['avg_mc_decline_after'] = 0
            result['avg_mc_criteria_met'] = 0
            
            # Add latest MC signal data (all None/False when no data)
            result['latest_mc_date'] = None
            result['latest_mc_price'] = None
            result['latest_mc_at_top_price'] = False
            result['latest_mc_price_percentile'] = 0
            result['latest_mc_decline_after'] = 0
            result['latest_mc_criteria_met'] = 0
            return result
        
        # Define all periods
        periods = [0] + list(range(1, 101))  # Full range from 0 to 100
        
        # Initialize result dictionary with basic info
        result = {
            'ticker': ticker,
            'interval': interval,
            'signal_count': signal_count,
            'latest_signal': latest_signal_str,
            'latest_signal_price': latest_signal_price,
            'current_time': current_time_str,
            'current_price': current_price
        }
        
        # Calculate current period if there's a latest signal
        if latest_signal_date:
            # Find the index of the latest signal and current time
            signal_idx = data_frame.index.get_loc(latest_signal_date)
            current_idx = len(data_frame) - 1
            # Calculate current period as the number of data points between signal and current time
            current_period = current_idx - signal_idx
            
            # Calculate actual price history and volume history for the latest signal
            price_history = {}
            volume_history = {}
            entry_price = data_frame.loc[latest_signal_date, 'Close']
            entry_volume = data_frame.loc[latest_signal_date, 'Volume']
            price_history[0] = round(float(entry_price), 2)  # Entry price at period 0, convert to Python float
            volume_history[0] = round(int(entry_volume), 0)  # Entry volume at period 0, convert to Python int
            
            for period in periods:
                if signal_idx + period < len(data_frame):
                    actual_price = data_frame.iloc[signal_idx + period]['Close']
                    actual_volume = data_frame.iloc[signal_idx + period]['Volume']
                    price_history[period] = round(float(actual_price), 2)  # Convert to Python float
                    volume_history[period] = round(int(actual_volume), 0)  # Convert to Python int
                else:
                    price_history[period] = None
                    volume_history[period] = None
                    
            # Add current price and volume if we're beyond the latest period
            if current_period > max(periods):
                price_history[current_period] = round(float(current_price), 2)  # Convert to Python float
                volume_history[current_period] = round(int(data_frame.iloc[-1]['Volume']), 0)  # Convert to Python int
        else:
            current_period = 0
            price_history = {}
            volume_history = {}
            
        result['current_period'] = current_period
        result['price_history'] = price_history
        result['volume_history'] = volume_history
        
        # Calculate metrics for each period dynamically
        for period in periods:
            return_col = f'return_{period}'
            volume_col = f'volume_{period}'
            if return_col in returns_df:
                # Get individual returns and volumes (excluding NaN values)
                individual_returns = [round(float(x), 2) for x in returns_df[return_col].dropna().tolist()]  # Convert to Python float
                individual_volumes = [round(int(x), 0) for x in returns_df[volume_col].dropna().tolist()] if volume_col in returns_df else []  # Convert to Python int
                test_count = len(individual_returns)
                success_rate = round(float((pd.Series(returns_df[return_col].dropna()) > 0).mean() * 100), 2)  # Convert to Python float
                avg_return = round(float(pd.Series(returns_df[return_col].dropna()).mean()), 2) if test_count > 0 else 0  # Convert to Python float
                avg_volume = round(int(pd.Series(returns_df[volume_col].dropna()).mean()), 0) if volume_col in returns_df and len(returns_df[volume_col].dropna()) > 0 else 0  # Convert to Python int
            else:
                individual_returns = []
                individual_volumes = []
                test_count = 0
                success_rate = 0
                avg_return = 0
                avg_volume = 0
            
            result[f'test_count_{period}'] = test_count
            result[f'success_rate_{period}'] = success_rate
            result[f'avg_return_{period}'] = avg_return
            result[f'avg_volume_{period}'] = avg_volume
            result[f'returns_{period}'] = individual_returns  # Store individual returns for boxplot
            result[f'volumes_{period}'] = individual_volumes  # Store individual volumes for volume chart
        
        # Add MC signal analysis summary to the result
        if not returns_df.empty:
            # Calculate MC signal statistics
            mc_at_top_count = returns_df['mc_at_top_price'].sum() if 'mc_at_top_price' in returns_df else 0
            mc_total_count = len(returns_df[returns_df['prev_mc_date'].notna()]) if 'prev_mc_date' in returns_df else 0
            mc_at_top_rate = round((mc_at_top_count / mc_total_count * 100), 2) if mc_total_count > 0 else 0
            
            # Average MC evaluation metrics
            avg_mc_percentile = round(float(returns_df['mc_price_percentile'].mean()), 2) if 'mc_price_percentile' in returns_df else 0  # Convert to Python float
            avg_mc_decline = round(float(returns_df['mc_decline_after'].mean()), 2) if 'mc_decline_after' in returns_df else 0  # Convert to Python float
            avg_mc_criteria = round(float(returns_df['mc_criteria_met'].mean()), 2) if 'mc_criteria_met' in returns_df else 0  # Convert to Python float
            
            # Latest MC signal data (from the most recent CD signal)
            latest_cd_signal = returns_df[returns_df['prev_mc_date'].notna()].sort_values('date', ascending=False)
            if not latest_cd_signal.empty:
                latest_mc_data = latest_cd_signal.iloc[0]
                latest_mc_price = latest_mc_data['prev_mc_price'] if 'prev_mc_price' in latest_mc_data else None
                latest_mc_date = latest_mc_data['prev_mc_date'] if 'prev_mc_date' in latest_mc_data else None
                latest_mc_at_top_price = latest_mc_data['mc_at_top_price'] if 'mc_at_top_price' in latest_mc_data else False
                latest_mc_price_percentile = latest_mc_data['mc_price_percentile'] if 'mc_price_percentile' in latest_mc_data else 0
                latest_mc_decline_after = latest_mc_data['mc_decline_after'] if 'mc_decline_after' in latest_mc_data else 0
                latest_mc_criteria_met = latest_mc_data['mc_criteria_met'] if 'mc_criteria_met' in latest_mc_data else 0
            else:
                latest_mc_price = None
                latest_mc_date = None
                latest_mc_at_top_price = False
                latest_mc_price_percentile = 0
                latest_mc_decline_after = 0
                latest_mc_criteria_met = 0
            
            # Add MC analysis to result
            result['mc_signals_before_cd'] = mc_total_count
            result['mc_at_top_price_count'] = mc_at_top_count
            result['mc_at_top_price_rate'] = round(float(mc_at_top_rate), 2)  # Convert to Python float
            result['avg_mc_price_percentile'] = round(float(avg_mc_percentile), 2)  # Convert to Python float
            result['avg_mc_decline_after'] = round(float(avg_mc_decline), 2)  # Convert to Python float
            result['avg_mc_criteria_met'] = round(float(avg_mc_criteria), 2)  # Convert to Python float
            
            # Add latest MC signal data
            result['latest_mc_date'] = latest_mc_date
            result['latest_mc_price'] = round(float(latest_mc_price), 2) if latest_mc_price else None  # Convert to Python float
            result['latest_mc_at_top_price'] = latest_mc_at_top_price
            result['latest_mc_price_percentile'] = round(float(latest_mc_price_percentile), 2)  # Convert to Python float
            result['latest_mc_decline_after'] = round(float(latest_mc_decline_after), 2)  # Convert to Python float
            result['latest_mc_criteria_met'] = latest_mc_criteria_met
        else:
            result['mc_signals_before_cd'] = 0
            result['mc_at_top_price_count'] = 0
            result['mc_at_top_price_rate'] = 0
            result['avg_mc_price_percentile'] = 0
            result['avg_mc_decline_after'] = 0
            result['avg_mc_criteria_met'] = 0
            
            # Add latest MC signal data (all None/False when no data)
            result['latest_mc_date'] = None
            result['latest_mc_price'] = None
            result['latest_mc_at_top_price'] = False
            result['latest_mc_price_percentile'] = 0
            result['latest_mc_decline_after'] = 0
            result['latest_mc_criteria_met'] = 0
        
        # Calculate max and min returns across all periods
        all_returns = []
        for col in returns_df.columns:
            if col.startswith('return_'):
                all_returns.extend(returns_df[col].dropna().tolist())
                
        result['max_return'] = round(float(max(all_returns)), 2) if all_returns else 0  # Convert to Python float
        result['min_return'] = round(float(min(all_returns)), 2) if all_returns else 0  # Convert to Python float
        
        # Add NX values (both signal and current values)
        # Signal NX values (at signal dates) - using the latest signal date if available
        result['nx_1d_signal'] = None
        result['nx_30m_signal'] = None  
        result['nx_1h_signal'] = None
        result['nx_5m_signal'] = None
        
        if latest_signal_date and data:
             for timeframe in ['1d', '30m', '1h', '5m']:
                if timeframe in data and not data[timeframe].empty:
                    df_nx = data[timeframe]
                    if len(df_nx) >= 89:
                        # Calculate EMAs
                        close = df_nx['Close']
                        short_close = close.ewm(span=24, adjust=False).mean()
                        long_close = close.ewm(span=89, adjust=False).mean()
                        nx_series = short_close > long_close
                        
                        # Find value at signal date
                        # Use asof to find the latest valid index up to signal_date
                        try:
                            # Note: yfinance 1d data is usually indexed at 00:00:00 (start of day)
                            # If signal is 14:30:00, asof(14:30) might match today's 00:00 if present.
                            # However, today's 1d bar is only complete at close. 
                            # If we are "backtesting", we theoretically shouldn't know Close of today at 14:30.
                            # But often for 1d trend we check "Yesterday's Close" or "Current Live".
                            # Here we use simplest approach: lookup nearest past/present timestamp.
                            
                            idx_loc = df_nx.index.get_indexer([latest_signal_date], method='pad')[0]
                            if idx_loc != -1:
                                val = bool(nx_series.iloc[idx_loc])
                                result[f'nx_{timeframe}_signal'] = val
                        except Exception as e:
                            print(f"Error calculating nx_{timeframe}_signal for {ticker}: {e}")

        # Current NX values (at current time)
        result['nx_1d'] = None
        result['nx_30m'] = None
        result['nx_1h'] = None
        result['nx_5m'] = None
        result['nx_4h'] = None
        
        # Calculate current NX values using pre-downloaded data
        if data:
            # Calculate NX for different timeframes
            for timeframe in ['1d', '30m', '1h', '5m', '4h']:
                if timeframe in data and not data[timeframe].empty:
                    df_nx = data[timeframe]
                    if len(df_nx) >= 89:  # Need at least 89 periods for long EMA
                        close = df_nx['Close']
                        short_close = close.ewm(span=24, adjust=False).mean()
                        long_close = close.ewm(span=89, adjust=False).mean()
                        current_nx = short_close.iloc[-1] > long_close.iloc[-1]
                        result[f'nx_{timeframe}'] = bool(current_nx)
        
        # For signal NX values, we would need the signal date to calculate NX at that time
        # This is more complex and would require storing historical NX calculations
        # Logic implemented above using EMA calculation and index lookup
        
        return result
        
    except Exception as e:
        print(f"Error evaluating {ticker} at {interval} interval: {e}")
        return None
