import pandas as pd
import numpy as np
from data_loader import download_stock_data
from indicators import compute_mc_indicator, compute_cd_indicator
import yfinance as yf

# EMA warmup period - should match the value in indicators.py
EMA_WARMUP_PERIOD = 0

# Maximum number of latest signals to process (to reduce noise from older signals)
MAX_SIGNALS_THRESHOLD = 7

def find_latest_cd_signal_before_mc(data, mc_date, cd_signals):
    """
    Find the latest CD signal that occurred before a given MC signal date.
    
    Args:
        data: DataFrame with price data
        mc_date: Date of the MC signal
        cd_signals: Series with CD signals (boolean)
    
    Returns:
        Tuple of (cd_signal_date, cd_signal_price) or (None, None) if no CD signal found
    """
    # Get all CD signal dates before the MC signal date
    # Handle NaN values by replacing them with False for boolean indexing
    cd_signals_bool = cd_signals.fillna(False).infer_objects(copy=False)
    cd_signal_dates = data.index[cd_signals_bool]
    previous_cd_signals = cd_signal_dates[cd_signal_dates < mc_date]
    
    if len(previous_cd_signals) == 0:
        return None, None
    
    # Get the latest CD signal before the MC signal
    latest_cd_date = previous_cd_signals.max()
    latest_cd_price = data.loc[latest_cd_date, 'Close']
    
    return latest_cd_date, latest_cd_price

def evaluate_cd_at_bottom_price(data, cd_date, cd_price, mc_date):
    """
    Evaluate if a CD signal was at a "bottom price" by checking if it was near a local minimum.
    
    Args:
        data: DataFrame with price data
        cd_date: Date of the CD signal
        cd_price: Price at the CD signal
        mc_date: Date of the latest MC signal (used for range calculations)
    
    Returns:
        Dictionary with evaluation metrics
    """
    try:
        cd_idx = data.index.get_loc(cd_date)
        mc_idx = data.index.get_loc(mc_date)
        
        # 1. Calculate lookback range: from EMA warmup period to latest MC time point
        # Exclude unreliable early periods before EMA convergence
        warmup_start = min(EMA_WARMUP_PERIOD, len(data) - 1)
        lookback_data = data.iloc[warmup_start:mc_idx+1]  # Start from warmup period, include MC signal date
        
        # 2. Calculate lookahead range: from CD signal to latest MC time point
        lookahead_data = data.iloc[cd_idx:mc_idx+1]  # Include MC signal date
        
        # Calculate metrics
        metrics = {}
        
        # 1. Check if CD price is near the lowest price in the full historical range
        if not lookback_data.empty:
            lookback_max = lookback_data['High'].max()
            lookback_min = lookback_data['Low'].min()
            lookback_range = lookback_max - lookback_min
            
            # Calculate percentile position of CD price in full historical range (inverse for bottom)
            if lookback_range > 0:
                price_percentile = (cd_price - lookback_min) / lookback_range
                metrics['lookback_price_percentile'] = price_percentile
                metrics['is_near_lookback_low'] = price_percentile <= 0.2  # Bottom 20% of full range
            else:
                metrics['lookback_price_percentile'] = 0.5
                metrics['is_near_lookback_low'] = False
        else:
            metrics['lookback_price_percentile'] = 0.5
            metrics['is_near_lookback_low'] = False
        
        # 2. Check if price increased after CD signal until MC signal
        if len(lookahead_data) > 1:
            lookahead_max = lookahead_data['High'].max()
            price_increase_pct = round(float((lookahead_max - cd_price) / cd_price * 100), 2)
            metrics['price_increase_after_cd'] = price_increase_pct
            metrics['is_followed_by_increase'] = price_increase_pct >= 5.0  # At least 5% increase
        else:
            metrics['price_increase_after_cd'] = 0
            metrics['is_followed_by_increase'] = False
        
        # 3. Check if CD signal is at local minimum using relative method
        # Use dynamic window size based on data availability and relative price position
        total_length = len(data)
        window_size = max(3, min(10, total_length // 20))  # 5% of data length, but between 3-10 periods
        
        window_start = max(0, cd_idx - window_size)
        window_end = min(len(data), cd_idx + window_size + 1)
        window_data = data.iloc[window_start:window_end]
        
        if not window_data.empty and len(window_data) > 1:
            # Use relative ranking for local minimum (inverse logic from MC)
            window_lows = window_data['Low'].values
            cd_rank = sum(cd_price <= l for l in window_lows) / len(window_lows)
            
            # CD signal is local min if it's in bottom 30% of surrounding prices
            is_local_min = cd_rank >= 0.7
            metrics['is_local_minimum'] = is_local_min
        else:
            metrics['is_local_minimum'] = False
        
        # 4. Overall evaluation - CD signal is at "bottom price" if it meets multiple criteria
        criteria_met = sum([
            metrics['is_near_lookback_low'],
            metrics['is_followed_by_increase'],
            metrics['is_local_minimum']
        ])
        
        metrics['criteria_met'] = criteria_met
        metrics['is_at_bottom_price'] = criteria_met >= 2  # At least 2 out of 3 criteria
        
        return metrics
        
    except Exception as e:
        print(f"Error evaluating CD signal at {cd_date}: {e}")
        return {
            'lookback_price_percentile': 0.5,
            'is_near_lookback_low': False,
            'price_increase_after_cd': 0,
            'is_followed_by_increase': False,
            'is_local_minimum': False,
            'criteria_met': 0,
            'is_at_bottom_price': False
        }

def calculate_returns(data, mc_signals, periods=None, max_signals=MAX_SIGNALS_THRESHOLD):
    """
    Calculate returns after MC signals for specified periods.
    
    Args:
        data: DataFrame with price data
        mc_signals: Series with MC signals (boolean)
        periods: List of periods to calculate returns for (default: 0 to 100)
        max_signals: Maximum number of latest signals to process (default: MAX_SIGNALS_THRESHOLD)
    
    Returns:
        DataFrame with signal dates, returns, and volume data for each period
    """
    if periods is None:
        periods = [0] + list(range(1, 101))  # Full range from 0 to 100
    results = []
    # Handle NaN values by replacing them with False for boolean indexing
    mc_signals_bool = mc_signals.fillna(False).infer_objects(copy=False)
    signal_dates = data.index[mc_signals_bool]
    
    # Limit to the latest N signals to reduce noise from older signals
    if len(signal_dates) > max_signals:
        signal_dates = signal_dates[-max_signals:]
    
    # Also compute CD signals for analysis
    cd_signals = compute_cd_indicator(data)
    
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
                # For MC signals, we're looking at returns from selling (negative returns indicate profit)
                returns[f'return_{period}'] = round(float((exit_price - entry_price) / entry_price * 100), 2)  # Convert to Python float
                volumes[f'volume_{period}'] = round(int(exit_volume), 0)  # Convert to Python int
            else:
                returns[f'return_{period}'] = np.nan
                volumes[f'volume_{period}'] = np.nan
        
        # Find the latest CD signal before this MC signal
        latest_cd_date, latest_cd_price = find_latest_cd_signal_before_mc(data, date, cd_signals)
        
        # Evaluate if the CD signal was at bottom price
        cd_evaluation = {}
        if latest_cd_date is not None:
            cd_evaluation = evaluate_cd_at_bottom_price(data, latest_cd_date, latest_cd_price, date)
            
        # Add CD signal analysis to the results
        cd_info = {
            'prev_cd_date': latest_cd_date.strftime('%Y-%m-%d %H:%M:%S') if latest_cd_date else None,
            'prev_cd_price': round(float(latest_cd_price), 2) if latest_cd_price else None,
            'cd_at_bottom_price': cd_evaluation.get('is_at_bottom_price', False),
            'cd_price_percentile': round(float(cd_evaluation.get('lookback_price_percentile', 0)), 2),
            'cd_increase_after': round(float(cd_evaluation.get('price_increase_after_cd', 0)), 2),
            'cd_criteria_met': cd_evaluation.get('criteria_met', 0)
        }
                
        results.append({
            'date': date,
            'entry_volume': entry_volume,
            **returns,
            **volumes,
            **cd_info
        })
    
    return pd.DataFrame(results)

def evaluate_interval(ticker, interval, data=None):
    """
    Evaluate MC signals for a specific ticker and interval.
    
    Args:
        ticker: Stock ticker symbol
        interval: Time interval to evaluate
        data: Optional pre-downloaded data dictionary
    
    Returns:
        Dictionary with evaluation metrics and individual returns
    """
    print(f"Evaluating {ticker} at {interval} interval for MC signals")
    
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
            
        # Compute MC signals
        mc_signals = compute_mc_indicator(data_frame)
        # Handle NaN values for signal count calculation
        signal_count = mc_signals.fillna(False).infer_objects(copy=False).sum()
        
        # Get the latest signal date
        # Handle NaN values by replacing them with False for boolean indexing
        mc_signals_bool = mc_signals.fillna(False).infer_objects(copy=False)
        latest_signal_date = data_frame.index[mc_signals_bool].max() if signal_count > 0 else None
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
                result[f'avg_volume_{period}'] = 0
                result[f'returns_{period}'] = []  # Store empty list for individual returns
                result[f'volumes_{period}'] = []  # Store empty list for individual volumes
            
            # Add CD signal analysis fields
            result['cd_signals_before_mc'] = 0
            result['cd_at_bottom_price_count'] = 0
            result['cd_at_bottom_price_rate'] = 0
            result['avg_cd_price_percentile'] = 0
            result['avg_cd_increase_after'] = 0
            result['avg_cd_criteria_met'] = 0
            
            # Add latest CD signal data (all None/False when no data)
            result['latest_cd_date'] = None
            result['latest_cd_price'] = None
            result['latest_cd_at_bottom_price'] = False
            result['latest_cd_price_percentile'] = 0
            result['latest_cd_increase_after'] = 0
            result['latest_cd_criteria_met'] = 0
            
            # Add NX values (both signal and current values)
            result['nx_1d_signal'] = None
            result['nx_1h_signal'] = None
            result['nx_1d'] = None
            result['nx_1h'] = None
            result['nx_4h'] = None
            
            # Calculate current NX values using pre-downloaded data
            if data:
                for timeframe in ['1d', '1h', '4h']:
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
        returns_df = calculate_returns(data_frame, mc_signals, max_signals=MAX_SIGNALS_THRESHOLD)
        
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
                result[f'avg_volume_{period}'] = 0
                result[f'returns_{period}'] = []  # Store empty list for individual returns
                result[f'volumes_{period}'] = []  # Store empty list for individual volumes
            
            # Add CD signal analysis fields
            result['cd_signals_before_mc'] = 0
            result['cd_at_bottom_price_count'] = 0
            result['cd_at_bottom_price_rate'] = 0
            result['avg_cd_price_percentile'] = 0
            result['avg_cd_increase_after'] = 0
            result['avg_cd_criteria_met'] = 0
            
            # Add latest CD signal data (all None/False when no data)
            result['latest_cd_date'] = None
            result['latest_cd_price'] = None
            result['latest_cd_at_bottom_price'] = False
            result['latest_cd_price_percentile'] = 0
            result['latest_cd_increase_after'] = 0
            result['latest_cd_criteria_met'] = 0
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
        
        # Calculate aggregated statistics for each period
        all_returns = []
        for period in periods:
            period_returns = returns_df[f'return_{period}'].dropna()
            period_volumes = returns_df[f'volume_{period}'].dropna() if f'volume_{period}' in returns_df else pd.Series([], dtype='float64')
            
            if len(period_returns) > 0:
                # For MC signals, negative returns indicate profit (price decline after sell signal)
                # So we calculate success rate as percentage of negative returns
                success_rate = round(float((period_returns < 0).mean() * 100), 2)  # Convert to Python float
                avg_return = round(float(period_returns.mean()), 2)  # Convert to Python float
                avg_volume = round(int(period_volumes.mean()), 0) if len(period_volumes) > 0 else 0  # Convert to Python int
                
                # Store aggregated metrics
                result[f'test_count_{period}'] = len(period_returns)
                result[f'success_rate_{period}'] = success_rate
                result[f'avg_return_{period}'] = avg_return
                result[f'avg_volume_{period}'] = avg_volume
                result[f'returns_{period}'] = [round(float(x), 2) for x in period_returns.tolist()]  # Convert to Python float
                result[f'volumes_{period}'] = [round(int(x), 0) for x in period_volumes.tolist()]  # Convert to Python int
                
                all_returns.extend(period_returns.tolist())
            else:
                result[f'test_count_{period}'] = 0
                result[f'success_rate_{period}'] = 0
                result[f'avg_return_{period}'] = 0
                result[f'avg_volume_{period}'] = 0
                result[f'returns_{period}'] = []
                result[f'volumes_{period}'] = []
        
        # Add CD signal analysis summary to the result
        if not returns_df.empty:
            # Calculate CD signal statistics
            cd_at_bottom_count = returns_df['cd_at_bottom_price'].sum() if 'cd_at_bottom_price' in returns_df else 0
            cd_total_count = len(returns_df[returns_df['prev_cd_date'].notna()]) if 'prev_cd_date' in returns_df else 0
            cd_at_bottom_rate = round(float((cd_at_bottom_count / cd_total_count * 100)), 2) if cd_total_count > 0 else 0
            
            # Average CD evaluation metrics
            avg_cd_percentile = round(float(returns_df['cd_price_percentile'].mean()), 2) if 'cd_price_percentile' in returns_df else 0  # Convert to Python float
            avg_cd_increase = round(float(returns_df['cd_increase_after'].mean()), 2) if 'cd_increase_after' in returns_df else 0  # Convert to Python float
            avg_cd_criteria = round(float(returns_df['cd_criteria_met'].mean()), 2) if 'cd_criteria_met' in returns_df else 0  # Convert to Python float
            
            # Latest CD signal data (from the most recent MC signal)
            latest_mc_signal = returns_df[returns_df['prev_cd_date'].notna()].sort_values('date', ascending=False)
            if not latest_mc_signal.empty:
                latest_cd_data = latest_mc_signal.iloc[0]
                latest_cd_price = latest_cd_data['prev_cd_price'] if 'prev_cd_price' in latest_cd_data else None
                latest_cd_date = latest_cd_data['prev_cd_date'] if 'prev_cd_date' in latest_cd_data else None
                latest_cd_at_bottom_price = latest_cd_data['cd_at_bottom_price'] if 'cd_at_bottom_price' in latest_cd_data else False
                latest_cd_price_percentile = latest_cd_data['cd_price_percentile'] if 'cd_price_percentile' in latest_cd_data else 0
                latest_cd_increase_after = latest_cd_data['cd_increase_after'] if 'cd_increase_after' in latest_cd_data else 0
                latest_cd_criteria_met = latest_cd_data['cd_criteria_met'] if 'cd_criteria_met' in latest_cd_data else 0
            else:
                latest_cd_price = None
                latest_cd_date = None
                latest_cd_at_bottom_price = False
                latest_cd_price_percentile = 0
                latest_cd_increase_after = 0
                latest_cd_criteria_met = 0
            
            # Add CD analysis to result
            result['cd_signals_before_mc'] = cd_total_count
            result['cd_at_bottom_price_count'] = cd_at_bottom_count
            result['cd_at_bottom_price_rate'] = round(float(cd_at_bottom_rate), 2)  # Convert to Python float
            result['avg_cd_price_percentile'] = round(float(avg_cd_percentile), 2)  # Convert to Python float
            result['avg_cd_increase_after'] = round(float(avg_cd_increase), 2)  # Convert to Python float
            result['avg_cd_criteria_met'] = round(float(avg_cd_criteria), 2)  # Convert to Python float
            
            # Add latest CD signal data
            result['latest_cd_date'] = latest_cd_date
            result['latest_cd_price'] = round(float(latest_cd_price), 2) if latest_cd_price else None  # Convert to Python float
            result['latest_cd_at_bottom_price'] = latest_cd_at_bottom_price
            result['latest_cd_price_percentile'] = round(float(latest_cd_price_percentile), 2)  # Convert to Python float
            result['latest_cd_increase_after'] = round(float(latest_cd_increase_after), 2)  # Convert to Python float
            result['latest_cd_criteria_met'] = latest_cd_criteria_met
        else:
            result['cd_signals_before_mc'] = 0
            result['cd_at_bottom_price_count'] = 0
            result['cd_at_bottom_price_rate'] = 0
            result['avg_cd_price_percentile'] = 0
            result['avg_cd_increase_after'] = 0
            result['avg_cd_criteria_met'] = 0
            
            # Add latest CD signal data (all None/False when no data)
            result['latest_cd_date'] = None
            result['latest_cd_price'] = None
            result['latest_cd_at_bottom_price'] = False
            result['latest_cd_price_percentile'] = 0
            result['latest_cd_increase_after'] = 0
            result['latest_cd_criteria_met'] = 0
        
        # Calculate overall min/max returns
        if all_returns:
            result['max_return'] = round(float(max(all_returns)), 2)  # Convert to Python float
            result['min_return'] = round(float(min(all_returns)), 2)  # Convert to Python float
        else:
            result['max_return'] = 0
            result['min_return'] = 0
        
        # Add NX values (both signal and current values)
        # Signal NX values (at signal dates) - using the latest signal date if available
        result['nx_1d_signal'] = None
        result['nx_1h_signal'] = None

        if latest_signal_date and data:
             for timeframe in ['1d', '1h']:
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
        result['nx_1h'] = None
        result['nx_4h'] = None
        
        # Calculate current NX values using pre-downloaded data
        if data:
            # Calculate NX for different timeframes
            for timeframe in ['1d', '1h', '4h']:
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
        print(f"Error evaluating {ticker} at {interval}: {e}")
        return None
