import pandas as pd
import numpy as np
import yfinance as yf
import os
import time
from datetime import datetime, timedelta
import multiprocessing
import logging

# Setup logger
logger = logging.getLogger(__name__)

from data_loader import load_stock_list, download_stock_data
from app.logic.db_utils import (
    save_price_history,
    create_analysis_run,
    update_analysis_run_status,
    save_analysis_result
)
from app.logic.utils import (
    calculate_current_nx_values,
)
from app.logic.get_resonance_signal_CD import (
    process_ticker_1234, 
    process_ticker_5230, 
    identify_1234, 
    identify_5230
)
from app.logic.get_resonance_signal_MC import (
    process_ticker_mc_1234, 
    process_ticker_mc_5230, 
    identify_mc_1234, 
    identify_mc_5230
)
from app.logic.get_best_CD_interval import evaluate_interval
from app.logic.get_best_MC_interval import evaluate_interval as evaluate_mc_interval
from multiprocessing import Pool, cpu_count
import functools

# Suppress pandas FutureWarnings about downcasting
pd.set_option('future.no_silent_downcasting', True)

# Define column configurations at module level for reusability
best_intervals_columns = ['ticker', 'interval', 'hold_time',  
                          'avg_return', 'latest_signal', 'latest_signal_price', 
                          'current_time', 'current_price', 'current_period',
                          'test_count', 'success_rate', 'best_period', 'signal_count',
                          'nx_1d_signal', 'nx_30m_signal', 'nx_1h_signal', 'nx_5m_signal',
                          'nx_1d', 'nx_30m', 'nx_1h', 'nx_5m', 'nx_4h',
                          'mc_signals_before_cd', 'mc_at_top_price_count', 'mc_at_top_price_rate',
                          'avg_mc_price_percentile', 'avg_mc_decline_after', 'avg_mc_criteria_met',
                          'latest_mc_date', 'latest_mc_price', 'latest_mc_at_top_price',
                          'latest_mc_price_percentile', 'latest_mc_decline_after', 'latest_mc_criteria_met']

# Define MC column configurations with CD analysis columns (needed for symmetry with CD analysis)
mc_best_intervals_columns = ['ticker', 'interval', 'hold_time',  
                             'avg_return', 'latest_signal', 'latest_signal_price', 
                             'current_time', 'current_price', 'current_period',
                             'test_count', 'success_rate', 'best_period', 'signal_count',
                             'nx_1d_signal', 'nx_30m_signal', 'nx_1h_signal', 'nx_5m_signal',
                             'nx_1d', 'nx_30m', 'nx_1h', 'nx_5m', 'nx_4h',
                             'cd_signals_before_mc', 'cd_at_bottom_price_count', 'cd_at_bottom_price_rate',
                             'avg_cd_price_percentile', 'avg_cd_increase_after', 'avg_cd_criteria_met',
                             'latest_cd_date', 'latest_cd_price', 'latest_cd_at_bottom_price',
                             'latest_cd_price_percentile', 'latest_cd_increase_after', 'latest_cd_criteria_met']

# Define all periods for dynamic handling
periods = [0] + list(range(1, 101))  # Full range from 0 to 100

# Define period ranges for different best intervals tables
period_ranges = {
    '20': list(range(20)),
    '50': list(range(50)),
    '100': list(range(100))
}

# Build good_signals_columns dynamically
good_signals_columns = ['ticker', 'interval', 'hold_time', 
                        'exp_return', 'latest_signal', 'latest_signal_price',
                        'current_time', 'current_price', 'current_period',
                        'test_count', 'success_rate', 'best_period', 'signal_count',
                        'nx_1d_signal', 'nx_30m_signal', 'nx_1h_signal', 'nx_5m_signal',
                        'nx_1d', 'nx_30m', 'nx_1h', 'nx_5m', 'nx_4h',
                        'mc_signals_before_cd', 'mc_at_top_price_count', 'mc_at_top_price_rate',
                        'avg_mc_price_percentile', 'avg_mc_decline_after', 'avg_mc_criteria_met',
                        'latest_mc_date', 'latest_mc_price', 'latest_mc_at_top_price',
                        'latest_mc_price_percentile', 'latest_mc_decline_after', 'latest_mc_criteria_met']

# Add all period-specific columns to good_signals_columns
for period in periods:
    good_signals_columns.extend([f'test_count_{period}', f'success_rate_{period}', f'avg_return_{period}'])
good_signals_columns.extend(['max_return', 'min_return'])

# Build MC good_signals_columns dynamically with CD analysis columns (needed for symmetry with CD analysis)
mc_good_signals_columns = ['ticker', 'interval', 'hold_time', 
                           'exp_return', 'latest_signal', 'latest_signal_price',
                           'current_time', 'current_price', 'current_period',
                           'test_count', 'success_rate', 'best_period', 'signal_count',
                           'cd_signals_before_mc', 'cd_at_bottom_price_count', 'cd_at_bottom_price_rate',
                           'avg_cd_price_percentile', 'avg_cd_increase_after', 'avg_cd_criteria_met',
                           'latest_cd_date', 'latest_cd_price', 'latest_cd_at_bottom_price',
                           'latest_cd_price_percentile', 'latest_cd_increase_after', 'latest_cd_criteria_met']

# Add all period-specific columns to MC good_signals_columns
for period in periods:
    mc_good_signals_columns.extend([f'test_count_{period}', f'success_rate_{period}', f'avg_return_{period}'])
mc_good_signals_columns.extend(['max_return', 'min_return'])

def parse_interval_to_minutes(interval_str):
    """
    Parse interval string to minutes.
    Examples: '5m' -> 5, '1h' -> 60, '1d' -> 480 (8 hours), '1w' -> 2400 (5 trading days * 8 hours)
    """
    if interval_str.endswith('m'):
        return int(interval_str[:-1])
    elif interval_str.endswith('h'):
        return int(interval_str[:-1]) * 60
    elif interval_str.endswith('d'):
        return int(interval_str[:-1]) * 8 * 60  # 8 trading hours per day
    elif interval_str.endswith('w'):
        return int(interval_str[:-1]) * 5 * 8 * 60  # 5 trading days * 8 hours per day
    else:
        return 0

def format_hold_time(total_minutes):
    """
    Format total minutes into readable format.
    Examples: 150 -> '2hr30min', 600 -> '1day2hr', 250 -> '4hr10min'
    """
    if total_minutes < 60:
        return f"{total_minutes}min"
    
    # Convert to trading time (8 hours per day)
    trading_hours_per_day = 8
    
    days = total_minutes // (trading_hours_per_day * 60)
    remaining_minutes = total_minutes % (trading_hours_per_day * 60)
    hours = remaining_minutes // 60
    minutes = remaining_minutes % 60
    
    result = []
    if days > 0:
        result.append(f"{days}day{'s' if days > 1 else ''}")
    if hours > 0:
        result.append(f"{hours}hr")
    if minutes > 0:
        result.append(f"{minutes}min")
    
    result = "".join(result) if result else "0min"
    return result

# Move this function outside the analyze_stocks function so it can be pickled
def process_ticker_all(ticker, end_date=None):
    """Process a single ticker for all analysis types"""
    try:
        print(f"Processing {ticker}")
        # Download data once for all analyses
        data = download_stock_data(ticker, end_date=end_date)
        
        # Skip if no data available
        if all(df.empty for df in data.values()):
            print(f"No data available for {ticker}")
            return ticker, None, None, [], [], [], [], None
            
        # Save downloaded data to database (replacing cache files)
        for interval, df in data.items():
            if not df.empty:
                save_price_history(ticker, interval, df)
        
        # Process for 1234 breakout (CD signals)
        results_1234 = process_ticker_1234(ticker, data)
        
        # Process for 5230 breakout (CD signals)
        results_5230 = process_ticker_5230(ticker, data)
        
        # Process for MC 1234 breakout (MC signals)
        mc_results_1234 = process_ticker_mc_1234(ticker, data)
        
        # Process for MC 5230 breakout (MC signals)
        mc_results_5230 = process_ticker_mc_5230(ticker, data)
        
        # Process for CD signal evaluation
        cd_results = []
        intervals = ['5m', '10m', '15m', '30m', '1h', '2h', '3h', '4h', '1d', '1w']
        for interval in intervals:
            result = evaluate_interval(ticker, interval, data=data)
            if result:
                cd_results.append(result)
        
        # Process for MC signal evaluation
        mc_results = []
        for interval in intervals:
            result = evaluate_mc_interval(ticker, interval, data=data)
            if result:
                mc_results.append(result)
        
        return ticker, results_1234, results_5230, mc_results_1234, mc_results_5230, cd_results, mc_results, data
        
    except Exception as e:
        print(f"Error processing {ticker}: {e}")
        return ticker, None, None, [], [], [], [], None

def analyze_stocks(file_path, end_date=None, progress_callback=None):
    """
    Comprehensive stock analysis function that performs all three types of analysis:
    - 1234 Breakout candidates
    - 5230 Breakout candidates
    - CD Signal Evaluation
    
    Args:
        file_path: Path to the file containing stock ticker symbols
        end_date: Optional end date for backtesting (format: 'YYYY-MM-DD')
        progress_callback: Optional callable that accepts integer progress (0-100)
    
    Returns:
        None: Results are saved to database
    """
    stock_list_name = os.path.basename(file_path)
    logger.info(f"Starting analysis for {stock_list_name}")
    
    # Create Analysis Run in DB
    try:
        run_id = create_analysis_run(stock_list_name)
    except Exception as e:
        logger.error(f"Failed to create analysis run: {e}")
        return

    # Load stock list
    try:
        tickers = []
        with open(file_path, 'r') as f:
            raw_tickers = [line.strip() for line in f if line.strip()]
            # Deduplicate while preserving order
            tickers = list(dict.fromkeys(raw_tickers))
        
        # Prepend Index tickers so they are included in 1234 analysis
        index_tickers = ["^SPX", "^DJI", "QQQ", "IWM"]
        tickers = index_tickers + [t for t in tickers if t not in index_tickers]
        
        logger.info(f"Loaded {len(tickers)} tickers from {file_path} (including indices)")
    except Exception as e:
        logger.error(f"Failed to load stock list: {e}")
        update_analysis_run_status(run_id, "failed")
        return

    if not tickers:
        logger.warning("No tickers found in file")
        update_analysis_run_status(run_id, "failed")
        return

    # Process tickers
    results = []
    
    # Use multiprocessing
    num_processes = max(1, cpu_count() - 1)
    logger.info(f"Using {num_processes} processes for analysis")
    
    try:
        with Pool(num_processes) as pool:
            # Create a partial function with fixed arguments
            process_func = functools.partial(process_ticker_all, end_date=end_date)
            
            # Map the function to the tickers using imap for progress tracking
            total_tickers = len(tickers)
            processed_count = 0
            
            if progress_callback:
                progress_callback(0)
            
            # Use chunks for better performance but iterate one by one for progress
            # chunksize heuristic
            chunk_size = max(1, total_tickers // (num_processes * 4))
            
            for result in pool.imap(process_func, tickers, chunksize=chunk_size):
                results.append(result)
                processed_count += 1
                
                if processed_count % 5 == 0 or processed_count == total_tickers:
                    logger.info(f"Processed {processed_count}/{total_tickers} tickers")
                    
                if progress_callback:
                    # Scale progress 1-99% (engine sets 100% on completion)
                    progress = max(1, int((processed_count / total_tickers) * 99))
                    progress_callback(progress)
                
        logger.info("All tickers processed. Aggregating results...")
        
        # Separate results
        cd_results = []
        mc_results = []
        mc_results_1234 = []
        mc_results_5230 = []
        cd_results_1234 = []
        cd_results_5230 = []
        cd_eval_results = []
        mc_eval_results = []
        all_ticker_data = {}
        failed_tickers = []

        for res in results:
            if res is None:
                continue
                
            ticker, r_1234, r_5230, mc_r_1234, mc_r_5230, cd_res, mc_res, data = res
            
            if r_1234 is None and r_5230 is None and not cd_res and not mc_res:
                 failed_tickers.append(ticker)
                 continue
                 
            if r_1234: cd_results_1234.extend(r_1234)
            if r_5230: cd_results_5230.extend(r_5230)
            if mc_r_1234: mc_results_1234.extend(mc_r_1234)
            if mc_r_5230: mc_results_5230.extend(mc_r_5230)
            if cd_res: cd_eval_results.extend(cd_res)
            if mc_res: mc_eval_results.extend(mc_res)
            if data: all_ticker_data[ticker] = data

        logger.info(f"Aggregated {len(cd_eval_results)} CD evaluation results and {len(mc_eval_results)} MC evaluation results")
        
        # Note: Index tickers (^SPX, QQQ, IWM) are now processed as part of the regular stock list above.

        # --- NEW: Aggregate Market Breadth (Signal Counts) ---
        def aggregate_signals(df, metric_name):
            if df is None or df.empty:
                return []
            
            try:
                # Ensure date column exists
                if 'date' not in df.columns:
                    return []
                
                # Count unique tickers per day
                # df['date'] is already date object or string? identify_... returns date objects
                daily_counts = df.groupby('date')['ticker'].nunique().reset_index()
                daily_counts.columns = ['date', 'count']
                
                # Sort by date
                daily_counts = daily_counts.sort_values('date')
                
                # Convert date to string for JSON serialization
                daily_counts['date'] = daily_counts['date'].astype(str)
                
                return daily_counts.to_dict(orient='records')
            except Exception as e:
                logger.error(f"Error aggregating {metric_name}: {e}")
                return []

        # 1. Save 1234 results and identify breakout candidates
        print("Saving 1234 breakout results...")
        save_analysis_result(run_id, "ALL", "ALL", 'cd_breakout_candidates_details_1234', cd_results_1234)
        df_breakout_1234 = identify_1234(cd_results_1234, all_ticker_data)
        if not df_breakout_1234.empty:
            save_analysis_result(run_id, "ALL", "ALL", 'cd_breakout_candidates_summary_1234', df_breakout_1234.to_dict(orient='records'))
            
            # Aggregate Breadth for CD 1234
            breadth_cd_1234 = aggregate_signals(df_breakout_1234, 'CD 1234')
            if breadth_cd_1234:
                save_analysis_result(run_id, "ALL", "ALL", 'cd_market_breadth_1234', breadth_cd_1234)
        
        # 2. Save 5230 results and identify breakout candidates
        print("Saving 5230 breakout results...")
        save_analysis_result(run_id, "ALL", "ALL", 'cd_breakout_candidates_details_5230', cd_results_5230)
        df_breakout_5230 = identify_5230(cd_results_5230, all_ticker_data)
        if not df_breakout_5230.empty:
            save_analysis_result(run_id, "ALL", "ALL", 'cd_breakout_candidates_summary_5230', df_breakout_5230.to_dict(orient='records'))

            # Aggregate Breadth for CD 5230
            breadth_cd_5230 = aggregate_signals(df_breakout_5230, 'CD 5230')
            if breadth_cd_5230:
                save_analysis_result(run_id, "ALL", "ALL", 'cd_market_breadth_5230', breadth_cd_5230)

        # 3. Save MC 1234 results and identify breakout candidates
        logger.info("Saving MC 1234 breakout results...")
        save_analysis_result(run_id, "ALL", "ALL", 'mc_breakout_candidates_details_1234', mc_results_1234)
        df_mc_breakout_1234 = identify_mc_1234(mc_results_1234, all_ticker_data)
        if not df_mc_breakout_1234.empty:
            save_analysis_result(run_id, "ALL", "ALL", 'mc_breakout_candidates_summary_1234', df_mc_breakout_1234.to_dict(orient='records'))

            # Aggregate Breadth for MC 1234
            breadth_mc_1234 = aggregate_signals(df_mc_breakout_1234, 'MC 1234')
            if breadth_mc_1234:
                save_analysis_result(run_id, "ALL", "ALL", 'mc_market_breadth_1234', breadth_mc_1234)
        
        # 4. Save MC 5230 results and identify breakout candidates
        logger.info("Saving MC 5230 breakout results...")
        save_analysis_result(run_id, "ALL", "ALL", 'mc_breakout_candidates_details_5230', mc_results_5230)
        df_mc_breakout_5230 = identify_mc_5230(mc_results_5230, all_ticker_data)
        if not df_mc_breakout_5230.empty:
            save_analysis_result(run_id, "ALL", "ALL", 'mc_breakout_candidates_summary_5230', df_mc_breakout_5230.to_dict(orient='records'))

            # Aggregate Breadth for MC 5230
            breadth_mc_5230 = aggregate_signals(df_mc_breakout_5230, 'MC 5230')
            if breadth_mc_5230:
                save_analysis_result(run_id, "ALL", "ALL", 'mc_market_breadth_5230', breadth_mc_5230)

        # 5. Save CD evaluation results
        logger.info("Saving CD evaluation results...")
        if cd_eval_results:
            df_cd_eval = pd.DataFrame(cd_eval_results)
            
            # Round numeric columns
            for col in df_cd_eval.columns:
                if df_cd_eval[col].dtype in ['float64', 'float32']:
                    df_cd_eval[col] = df_cd_eval[col].round(3)
            
            save_analysis_result(run_id, "ALL", "ALL", 'cd_eval_custom_detailed', df_cd_eval.to_dict(orient='records'))
            
            # Returns distribution
            returns_data = []
            for result in cd_eval_results:
                ticker = result['ticker']
                interval = result['interval']
                for period in periods:
                    returns_key = f'returns_{period}'
                    volumes_key = f'volumes_{period}'
                    if returns_key in result and result[returns_key]:
                        individual_returns = result[returns_key]
                        individual_volumes = result.get(volumes_key, [])
                        if len(individual_volumes) < len(individual_returns):
                            individual_volumes.extend([None] * (len(individual_returns) - len(individual_volumes)))
                        for i, return_value in enumerate(individual_returns):
                            volume_value = individual_volumes[i] if i < len(individual_volumes) else None
                            returns_data.append({
                                'ticker': ticker,
                                'interval': interval,
                                'period': period,
                                'return': return_value,
                                'volume': volume_value
                            })
            
            if returns_data:
                df_returns = pd.DataFrame(returns_data)
                if 'return' in df_returns.columns: df_returns['return'] = df_returns['return'].round(3)
                if 'volume' in df_returns.columns: df_returns['volume'] = df_returns['volume'].round(0)
                save_analysis_result(run_id, "ALL", "ALL", 'cd_eval_returns_distribution', df_returns.to_dict(orient='records'))
            else:
                save_analysis_result(run_id, "ALL", "ALL", 'cd_eval_returns_distribution', [])

            # Best Intervals Logic
            valid_df = df_cd_eval[df_cd_eval['test_count_10'] >= 2]
            filter_conditions = []
            for period in periods:
                if f'avg_return_{period}' in df_cd_eval.columns:
                    filter_conditions.append(valid_df[f'avg_return_{period}'] >= 5)
            
            if filter_conditions:
                combined_filter = filter_conditions[0]
                for condition in filter_conditions[1:]:
                    combined_filter = combined_filter | condition
                valid_df = valid_df[combined_filter]
            
            if not valid_df.empty:
                for range_name, range_periods in period_ranges.items():
                    avg_return_cols = [f'avg_return_{period}' for period in range_periods if f'avg_return_{period}' in valid_df.columns]
                    range_df = valid_df.copy()
                    range_df['max_return'] = range_df[avg_return_cols].max(axis=1)
                    range_df['best_period'] = range_df[avg_return_cols].idxmax(axis=1).str.extract('(\d+)').astype(int)
                    
                    best_intervals = range_df.loc[range_df.groupby('ticker')['max_return'].idxmax()]
                    best_intervals = best_intervals.assign(
                        test_count=best_intervals.apply(lambda x: x[f'test_count_{int(x.best_period)}'], axis=1),
                        success_rate=best_intervals.apply(lambda x: x[f'success_rate_{int(x.best_period)}'], axis=1),
                        avg_return=best_intervals['max_return']
                    )
                    available_columns = [col for col in best_intervals_columns if col in best_intervals.columns]
                    best_intervals = best_intervals[available_columns].sort_values('latest_signal', ascending=False)
                    best_intervals['hold_time'] = best_intervals.apply(
                        lambda row: format_hold_time(parse_interval_to_minutes(row['interval']) * row['best_period']), axis=1
                    )
                    final_columns = [col for col in best_intervals_columns if col in best_intervals.columns]
                    best_intervals = best_intervals[final_columns]
                    best_intervals = best_intervals[best_intervals['avg_return'] >= 5]
                    best_intervals = best_intervals[best_intervals['success_rate'] >= 50]
                    best_intervals = best_intervals[best_intervals['current_period'] <= best_intervals['best_period']]
                    
                    for col in best_intervals.columns:
                        if best_intervals[col].dtype in ['float64', 'float32']:
                            best_intervals[col] = best_intervals[col].round(3)
                            
                    save_analysis_result(run_id, "ALL", "ALL", f'cd_eval_best_intervals_{range_name}', best_intervals.to_dict(orient='records'))

                # Good Signals
                good_signals = valid_df.sort_values('latest_signal', ascending=False)
                avg_return_cols = [f'avg_return_{period}' for period in periods if f'avg_return_{period}' in good_signals.columns]
                good_signals['max_return'] = good_signals[avg_return_cols].max(axis=1)
                good_signals['best_period'] = good_signals[avg_return_cols].idxmax(axis=1).str.extract('(\d+)').astype(int)
                good_signals['hold_time'] = good_signals.apply(
                    lambda row: format_hold_time(parse_interval_to_minutes(row['interval']) * row['best_period']), axis=1
                )
                good_signals['exp_return'] = good_signals.apply(lambda row: row[f'avg_return_{int(row.best_period)}'], axis=1)
                good_signals['avg_return'] = good_signals['exp_return']
                good_signals['test_count'] = good_signals.apply(lambda row: row[f'test_count_{int(row.best_period)}'], axis=1)
                good_signals['success_rate'] = good_signals.apply(lambda row: row[f'success_rate_{int(row.best_period)}'], axis=1)
                available_good_columns = [col for col in best_intervals_columns if col in good_signals.columns]
                good_signals = good_signals[available_good_columns]
                good_signals = good_signals[good_signals['success_rate'] >= 50]
                
                for col in good_signals.columns:
                    if good_signals[col].dtype in ['float64', 'float32']:
                        good_signals[col] = good_signals[col].round(3)
                
                save_analysis_result(run_id, "ALL", "ALL", 'cd_eval_good_signals', good_signals.to_dict(orient='records'))
            else:
                 # No best intervals
                 pass

            # Interval Summary
            agg_dict = {'signal_count': 'sum'}
            for period in periods:
                if f'test_count_{period}' in df_cd_eval.columns: agg_dict[f'test_count_{period}'] = 'sum'
                if f'success_rate_{period}' in df_cd_eval.columns: agg_dict[f'success_rate_{period}'] = 'mean'
                if f'avg_return_{period}' in df_cd_eval.columns: agg_dict[f'avg_return_{period}'] = 'mean'
            interval_summary = df_cd_eval.groupby('interval').agg(agg_dict).reset_index()
            save_analysis_result(run_id, "ALL", "ALL", 'cd_eval_interval_summary', interval_summary.to_dict(orient='records'))

        # 6. Save MC evaluation results
        logger.info("Saving MC evaluation results...")
        if mc_eval_results:
            df_mc_eval = pd.DataFrame(mc_eval_results)
            for col in df_mc_eval.columns:
                if df_mc_eval[col].dtype in ['float64', 'float32']:
                    df_mc_eval[col] = df_mc_eval[col].round(3)
            save_analysis_result(run_id, "ALL", "ALL", 'mc_eval_custom_detailed', df_mc_eval.to_dict(orient='records'))
            
            # MC Returns distribution
            returns_data = []
            for result in mc_eval_results:
                ticker = result['ticker']
                interval = result['interval']
                for period in periods:
                    returns_key = f'returns_{period}'
                    volumes_key = f'volumes_{period}'
                    if returns_key in result and result[returns_key]:
                        individual_returns = result[returns_key]
                        individual_volumes = result.get(volumes_key, [])
                        if len(individual_volumes) < len(individual_returns):
                            individual_volumes.extend([None] * (len(individual_returns) - len(individual_volumes)))
                        for i, return_value in enumerate(individual_returns):
                            volume_value = individual_volumes[i] if i < len(individual_volumes) else None
                            returns_data.append({
                                'ticker': ticker,
                                'interval': interval,
                                'period': period,
                                'return': return_value,
                                'volume': volume_value
                            })
            if returns_data:
                df_returns = pd.DataFrame(returns_data)
                if 'return' in df_returns.columns: df_returns['return'] = df_returns['return'].round(3)
                if 'volume' in df_returns.columns: df_returns['volume'] = df_returns['volume'].round(0)
                save_analysis_result(run_id, "ALL", "ALL", 'mc_eval_returns_distribution', df_returns.to_dict(orient='records'))
            else:
                save_analysis_result(run_id, "ALL", "ALL", 'mc_eval_returns_distribution', [])

            # MC Best Intervals logic
            valid_df = df_mc_eval[df_mc_eval['test_count_10'] >= 2]
            filter_conditions = []
            for period in periods:
                if f'avg_return_{period}' in df_mc_eval.columns:
                    filter_conditions.append(valid_df[f'avg_return_{period}'] <= -5)
            
            if filter_conditions:
                combined_filter = filter_conditions[0]
                for condition in filter_conditions[1:]:
                    combined_filter = combined_filter | condition
                valid_df = valid_df[combined_filter]
            
            if not valid_df.empty:
                for range_name, range_periods in period_ranges.items():
                    avg_return_cols = [f'avg_return_{period}' for period in range_periods if f'avg_return_{period}' in valid_df.columns]
                    range_df = valid_df.copy()
                    range_df['min_return'] = range_df[avg_return_cols].min(axis=1)
                    range_df['best_period'] = range_df[avg_return_cols].idxmin(axis=1).str.extract('(\d+)').astype(int)
                    best_intervals = range_df.loc[range_df.groupby('ticker')['min_return'].idxmin()]
                    best_intervals = best_intervals.assign(
                        test_count=best_intervals.apply(lambda x: x[f'test_count_{int(x.best_period)}'], axis=1),
                        success_rate=best_intervals.apply(lambda x: x[f'success_rate_{int(x.best_period)}'], axis=1),
                        avg_return=best_intervals['min_return']
                    )
                    available_columns = [col for col in mc_best_intervals_columns if col in best_intervals.columns]
                    best_intervals = best_intervals[available_columns].sort_values('latest_signal', ascending=False)
                    best_intervals['hold_time'] = best_intervals.apply(
                        lambda row: format_hold_time(parse_interval_to_minutes(row['interval']) * row['best_period']), axis=1
                    )
                    final_columns = [col for col in mc_best_intervals_columns if col in best_intervals.columns]
                    best_intervals = best_intervals[final_columns]
                    best_intervals = best_intervals[best_intervals['avg_return'] <= -5]
                    best_intervals = best_intervals[best_intervals['success_rate'] >= 50]
                    best_intervals = best_intervals[best_intervals['current_period'] <= best_intervals['best_period']]
                    for col in best_intervals.columns:
                        if best_intervals[col].dtype in ['float64', 'float32']:
                            best_intervals[col] = best_intervals[col].round(3)
                    save_analysis_result(run_id, "ALL", "ALL", f'mc_eval_best_intervals_{range_name}', best_intervals.to_dict(orient='records'))

                # MC Good Signals
                good_signals = valid_df.sort_values('latest_signal', ascending=False)
                avg_return_cols = [f'avg_return_{period}' for period in periods if f'avg_return_{period}' in good_signals.columns]
                good_signals['min_return'] = good_signals[avg_return_cols].min(axis=1)
                good_signals['best_period'] = good_signals[avg_return_cols].idxmin(axis=1).str.extract('(\d+)').astype(int)
                good_signals['hold_time'] = good_signals.apply(
                    lambda row: format_hold_time(parse_interval_to_minutes(row['interval']) * row['best_period']), axis=1
                )
                good_signals['exp_return'] = good_signals.apply(lambda row: row[f'avg_return_{int(row.best_period)}'], axis=1)
                good_signals['avg_return'] = good_signals['exp_return']
                good_signals['test_count'] = good_signals.apply(lambda row: row[f'test_count_{int(row.best_period)}'], axis=1)
                good_signals['success_rate'] = good_signals.apply(lambda row: row[f'success_rate_{int(row.best_period)}'], axis=1)
                available_good_columns = [col for col in mc_best_intervals_columns if col in good_signals.columns]
                good_signals = good_signals[available_good_columns]
                good_signals = good_signals[good_signals['success_rate'] >= 50]
                for col in good_signals.columns:
                    if good_signals[col].dtype in ['float64', 'float32']:
                        good_signals[col] = good_signals[col].round(3)
                save_analysis_result(run_id, "ALL", "ALL", 'mc_eval_good_signals', good_signals.to_dict(orient='records'))
            
            # MC Interval Summary
            agg_dict = {'signal_count': 'sum'}
            for period in periods:
                if f'test_count_{period}' in df_mc_eval.columns: agg_dict[f'test_count_{period}'] = 'sum'
                if f'success_rate_{period}' in df_mc_eval.columns: agg_dict[f'success_rate_{period}'] = 'mean'
                if f'avg_return_{period}' in df_mc_eval.columns: agg_dict[f'avg_return_{period}'] = 'mean'
            interval_summary = df_mc_eval.groupby('interval').agg(agg_dict).reset_index()
            save_analysis_result(run_id, "ALL", "ALL", 'mc_eval_interval_summary', interval_summary.to_dict(orient='records'))
        
        print("All analyses completed successfully!")
        update_analysis_run_status(run_id, "completed")

        if failed_tickers:
            print("\n----------------------")
            print("Failed to process the following tickers:")
            print(", ".join(failed_tickers))
            print("----------------------\n")

    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        update_analysis_run_status(run_id, "failed")
        raise e


def analyze_multi_index(index_info_list, end_date=None, progress_callback=None):
    """
    Analyze multiple indices in a single run.
    
    Args:
        index_info_list: List of dicts with keys: key, symbol, stock_list_path, stock_list_name
        end_date: Optional end date for backtesting
        progress_callback: Optional callable for progress updates
    """
    run_id = create_analysis_run("multi_index")
    logger.info(f"Starting multi-index analysis for {[i['key'] for i in index_info_list]}")
    
    try:
        # 1. Collect all unique tickers from all indices
        all_tickers = set()
        index_ticker_map = {}  # Maps index key -> list of tickers
        
        for idx_info in index_info_list:
            try:
                with open(idx_info['stock_list_path'], 'r') as f:
                    tickers = [line.strip() for line in f if line.strip()]
                    tickers = list(dict.fromkeys(tickers))  # Deduplicate
                    index_ticker_map[idx_info['key']] = tickers
                    all_tickers.update(tickers)
                    # Also add the index symbol itself
                    all_tickers.add(idx_info['symbol'])
                    logger.info(f"Loaded {len(tickers)} tickers for {idx_info['key']}")
            except FileNotFoundError:
                logger.warning(f"Stock list not found: {idx_info['stock_list_path']}")
                index_ticker_map[idx_info['key']] = []
        
        # Convert to list and add standard index symbols
        index_symbols = [i['symbol'] for i in index_info_list]
        tickers = list(all_tickers)
        logger.info(f"Combined unique tickers: {len(tickers)}")
        
        if not tickers:
            logger.warning("No tickers found")
            update_analysis_run_status(run_id, "failed")
            return
        
        # 2. Run the analysis on combined set (same as analyze_stocks)
        total = len(tickers)
        cd_results_1234 = []
        mc_results_1234 = []
        cd_results_5230 = []
        mc_results_5230 = []
        cd_eval_results = []
        mc_eval_results = []
        all_ticker_data = {}
        failed_tickers = []
        
        logger.info(f"Processing {total} combined tickers...")
        
        num_processes = max(1, cpu_count() - 1)
        logger.info(f"Using {num_processes} processes for analysis")
        
        with Pool(num_processes) as pool:
            # Create a partial function with fixed arguments
            process_func = functools.partial(process_ticker_all, end_date=end_date)
            
            # Map the function to the tickers using imap for progress tracking
            processed_count = 0
            
            # Use chunks for better performance
            chunk_size = max(1, total // (num_processes * 4))
            
            if progress_callback:
                progress_callback(0)
            
            for result in pool.imap(process_func, tickers, chunksize=chunk_size):
                ticker, cd_1234, cd_5230, mc_1234, mc_5230, cd_eval, mc_eval, ticker_data = result
                
                if ticker_data is not None:
                    all_ticker_data[ticker] = ticker_data
                    if cd_1234:
                        cd_results_1234.extend(cd_1234)
                    if mc_1234:
                        mc_results_1234.extend(mc_1234)
                    if cd_5230:
                        cd_results_5230.extend(cd_5230)
                    if mc_5230:
                        mc_results_5230.extend(mc_5230)
                    if cd_eval:
                        cd_eval_results.extend(cd_eval)
                    if mc_eval:
                        mc_eval_results.extend(mc_eval)
                else:
                    failed_tickers.append(ticker)
                
                processed_count += 1
                if processed_count % 10 == 0 or processed_count == total:
                    logger.info(f"Processed {processed_count}/{total} tickers")
                    
                if progress_callback:
                    progress_callback(int((processed_count / total) * 90))
        
        logger.info(f"Processed {len(all_ticker_data)} tickers successfully")
        
        # 3. Identify breakouts and save results
        df_breakout_1234 = identify_1234(cd_results_1234, all_ticker_data)
        df_mc_breakout_1234 = identify_mc_1234(mc_results_1234, all_ticker_data)
        
        # Save combined results for reference
        save_analysis_result(run_id, "ALL", "ALL", 'cd_breakout_candidates_summary_1234', 
                           df_breakout_1234.to_dict(orient='records') if not df_breakout_1234.empty else [])
        save_analysis_result(run_id, "ALL", "ALL", 'mc_breakout_candidates_summary_1234',
                           df_mc_breakout_1234.to_dict(orient='records') if not df_mc_breakout_1234.empty else [])
        
        # 3b. Save MC 5230 results and identify breakout candidates
        logger.info("Saving MC 5230 breakout results...")
        save_analysis_result(run_id, "ALL", "ALL", 'mc_breakout_candidates_details_5230', mc_results_5230)
        df_mc_breakout_5230 = identify_mc_5230(mc_results_5230, all_ticker_data)
        if not df_mc_breakout_5230.empty:
            save_analysis_result(run_id, "ALL", "ALL", 'mc_breakout_candidates_summary_5230', df_mc_breakout_5230.to_dict(orient='records'))

            # Aggregate Breadth for MC 5230
            def aggregate_signals_simple(df, metric_name):
                if df.empty: return []
                try:
                    df = df.copy()
                    if 'date' not in df.columns: return []
                    df['date'] = pd.to_datetime(df['date'])
                    daily_counts = df.groupby('date')['ticker'].nunique().reset_index()
                    daily_counts.columns = ['date', 'count']
                    daily_counts = daily_counts.sort_values('date')
                    daily_counts['date'] = daily_counts['date'].astype(str)
                    return daily_counts.to_dict(orient='records')
                except Exception: return []

            breadth_mc_5230 = aggregate_signals_simple(df_mc_breakout_5230, 'MC 5230')
            if breadth_mc_5230:
                save_analysis_result(run_id, "ALL", "ALL", 'mc_market_breadth_5230', breadth_mc_5230)

        # 3c. Save CD evaluation results
        logger.info("Saving CD evaluation results...")
        if cd_eval_results:
            df_cd_eval = pd.DataFrame(cd_eval_results)
            
            # Round numeric columns
            for col in df_cd_eval.columns:
                if df_cd_eval[col].dtype in ['float64', 'float32']:
                    df_cd_eval[col] = df_cd_eval[col].round(3)
            
            save_analysis_result(run_id, "ALL", "ALL", 'cd_eval_custom_detailed', df_cd_eval.to_dict(orient='records'))
            
            # Returns distribution
            returns_data = []
            for result in cd_eval_results:
                ticker = result['ticker']
                interval = result['interval']
                for period in periods:
                    returns_key = f'returns_{period}'
                    volumes_key = f'volumes_{period}'
                    if returns_key in result and result[returns_key]:
                        individual_returns = result[returns_key]
                        individual_volumes = result.get(volumes_key, [])
                        if len(individual_volumes) < len(individual_returns):
                            individual_volumes.extend([None] * (len(individual_returns) - len(individual_volumes)))
                        for i, return_value in enumerate(individual_returns):
                            volume_value = individual_volumes[i] if i < len(individual_volumes) else None
                            returns_data.append({
                                'ticker': ticker,
                                'interval': interval,
                                'period': period,
                                'return': return_value,
                                'volume': volume_value
                            })
            
            if returns_data:
                df_returns = pd.DataFrame(returns_data)
                if 'return' in df_returns.columns: df_returns['return'] = df_returns['return'].round(3)
                if 'volume' in df_returns.columns: df_returns['volume'] = df_returns['volume'].round(0)
                save_analysis_result(run_id, "ALL", "ALL", 'cd_eval_returns_distribution', df_returns.to_dict(orient='records'))
            else:
                save_analysis_result(run_id, "ALL", "ALL", 'cd_eval_returns_distribution', [])

            # Best Intervals Logic
            valid_df = df_cd_eval[df_cd_eval['test_count_10'] >= 2]
            filter_conditions = []
            for period in periods:
                if f'avg_return_{period}' in df_cd_eval.columns:
                    filter_conditions.append(valid_df[f'avg_return_{period}'] >= 5)
            
            if filter_conditions:
                combined_filter = filter_conditions[0]
                for condition in filter_conditions[1:]:
                    combined_filter = combined_filter | condition
                valid_df = valid_df[combined_filter]
            
            if not valid_df.empty:
                for range_name, range_periods in period_ranges.items():
                    avg_return_cols = [f'avg_return_{period}' for period in range_periods if f'avg_return_{period}' in valid_df.columns]
                    range_df = valid_df.copy()
                    range_df['max_return'] = range_df[avg_return_cols].max(axis=1)
                    range_df['best_period'] = range_df[avg_return_cols].idxmax(axis=1).str.extract('(\d+)').astype(int)
                    
                    best_intervals = range_df.loc[range_df.groupby('ticker')['max_return'].idxmax()]
                    best_intervals = best_intervals.assign(
                        test_count=best_intervals.apply(lambda x: x[f'test_count_{int(x.best_period)}'], axis=1),
                        success_rate=best_intervals.apply(lambda x: x[f'success_rate_{int(x.best_period)}'], axis=1),
                        avg_return=best_intervals['max_return']
                    )
                    available_columns = [col for col in best_intervals_columns if col in best_intervals.columns]
                    best_intervals = best_intervals[available_columns].sort_values('latest_signal', ascending=False)
                    best_intervals['hold_time'] = best_intervals.apply(
                        lambda row: format_hold_time(parse_interval_to_minutes(row['interval']) * row['best_period']), axis=1
                    )
                    final_columns = [col for col in best_intervals_columns if col in best_intervals.columns]
                    best_intervals = best_intervals[final_columns]
                    best_intervals = best_intervals[best_intervals['avg_return'] >= 5]
                    best_intervals = best_intervals[best_intervals['success_rate'] >= 50]
                    best_intervals = best_intervals[best_intervals['current_period'] <= best_intervals['best_period']]
                    
                    for col in best_intervals.columns:
                        if best_intervals[col].dtype in ['float64', 'float32']:
                            best_intervals[col] = best_intervals[col].round(3)
                            
                    save_analysis_result(run_id, "ALL", "ALL", f'cd_eval_best_intervals_{range_name}', best_intervals.to_dict(orient='records'))

                # Good Signals
                good_signals = valid_df.sort_values('latest_signal', ascending=False)
                avg_return_cols = [f'avg_return_{period}' for period in periods if f'avg_return_{period}' in good_signals.columns]
                good_signals['max_return'] = good_signals[avg_return_cols].max(axis=1)
                good_signals['best_period'] = good_signals[avg_return_cols].idxmax(axis=1).str.extract('(\d+)').astype(int)
                good_signals['hold_time'] = good_signals.apply(
                    lambda row: format_hold_time(parse_interval_to_minutes(row['interval']) * row['best_period']), axis=1
                )
                good_signals['exp_return'] = good_signals.apply(lambda row: row[f'avg_return_{int(row.best_period)}'], axis=1)
                good_signals['avg_return'] = good_signals['exp_return']
                good_signals['test_count'] = good_signals.apply(lambda row: row[f'test_count_{int(row.best_period)}'], axis=1)
                good_signals['success_rate'] = good_signals.apply(lambda row: row[f'success_rate_{int(row.best_period)}'], axis=1)
                available_good_columns = [col for col in best_intervals_columns if col in good_signals.columns]
                good_signals = good_signals[available_good_columns]
                good_signals = good_signals[good_signals['success_rate'] >= 50]
                
                for col in good_signals.columns:
                    if good_signals[col].dtype in ['float64', 'float32']:
                        good_signals[col] = good_signals[col].round(3)
                
                save_analysis_result(run_id, "ALL", "ALL", 'cd_eval_good_signals', good_signals.to_dict(orient='records'))
            else:
                 pass

            # Interval Summary
            agg_dict = {'signal_count': 'sum'}
            for period in periods:
                if f'test_count_{period}' in df_cd_eval.columns: agg_dict[f'test_count_{period}'] = 'sum'
                if f'success_rate_{period}' in df_cd_eval.columns: agg_dict[f'success_rate_{period}'] = 'mean'
                if f'avg_return_{period}' in df_cd_eval.columns: agg_dict[f'avg_return_{period}'] = 'mean'
            interval_summary = df_cd_eval.groupby('interval').agg(agg_dict).reset_index()
            save_analysis_result(run_id, "ALL", "ALL", 'cd_eval_interval_summary', interval_summary.to_dict(orient='records'))

        # 3d. Save MC evaluation results
        logger.info("Saving MC evaluation results...")
        if mc_eval_results:
            df_mc_eval = pd.DataFrame(mc_eval_results)
            for col in df_mc_eval.columns:
                if df_mc_eval[col].dtype in ['float64', 'float32']:
                    df_mc_eval[col] = df_mc_eval[col].round(3)
            save_analysis_result(run_id, "ALL", "ALL", 'mc_eval_custom_detailed', df_mc_eval.to_dict(orient='records'))
            
            # MC Returns distribution
            returns_data = []
            for result in mc_eval_results:
                ticker = result['ticker']
                interval = result['interval']
                for period in periods:
                    returns_key = f'returns_{period}'
                    volumes_key = f'volumes_{period}'
                    if returns_key in result and result[returns_key]:
                        individual_returns = result[returns_key]
                        individual_volumes = result.get(volumes_key, [])
                        if len(individual_volumes) < len(individual_returns):
                            individual_volumes.extend([None] * (len(individual_returns) - len(individual_volumes)))
                        for i, return_value in enumerate(individual_returns):
                            volume_value = individual_volumes[i] if i < len(individual_volumes) else None
                            returns_data.append({
                                'ticker': ticker,
                                'interval': interval,
                                'period': period,
                                'return': return_value,
                                'volume': volume_value
                            })
            if returns_data:
                df_returns = pd.DataFrame(returns_data)
                if 'return' in df_returns.columns: df_returns['return'] = df_returns['return'].round(3)
                if 'volume' in df_returns.columns: df_returns['volume'] = df_returns['volume'].round(0)
                save_analysis_result(run_id, "ALL", "ALL", 'mc_eval_returns_distribution', df_returns.to_dict(orient='records'))
            else:
                save_analysis_result(run_id, "ALL", "ALL", 'mc_eval_returns_distribution', [])

            # MC Best Intervals logic
            valid_df = df_mc_eval[df_mc_eval['test_count_10'] >= 2]
            filter_conditions = []
            for period in periods:
                if f'avg_return_{period}' in df_mc_eval.columns:
                    filter_conditions.append(valid_df[f'avg_return_{period}'] <= -5)
            
            if filter_conditions:
                combined_filter = filter_conditions[0]
                for condition in filter_conditions[1:]:
                    combined_filter = combined_filter | condition
                valid_df = valid_df[combined_filter]
            
            if not valid_df.empty:
                for range_name, range_periods in period_ranges.items():
                    avg_return_cols = [f'avg_return_{period}' for period in range_periods if f'avg_return_{period}' in valid_df.columns]
                    range_df = valid_df.copy()
                    range_df['min_return'] = range_df[avg_return_cols].min(axis=1)
                    range_df['best_period'] = range_df[avg_return_cols].idxmin(axis=1).str.extract('(\d+)').astype(int)
                    best_intervals = range_df.loc[range_df.groupby('ticker')['min_return'].idxmin()]
                    best_intervals = best_intervals.assign(
                        test_count=best_intervals.apply(lambda x: x[f'test_count_{int(x.best_period)}'], axis=1),
                        success_rate=best_intervals.apply(lambda x: x[f'success_rate_{int(x.best_period)}'], axis=1),
                        avg_return=best_intervals['min_return']
                    )
                    available_columns = [col for col in mc_best_intervals_columns if col in best_intervals.columns]
                    best_intervals = best_intervals[available_columns].sort_values('latest_signal', ascending=False)
                    best_intervals['hold_time'] = best_intervals.apply(
                        lambda row: format_hold_time(parse_interval_to_minutes(row['interval']) * row['best_period']), axis=1
                    )
                    final_columns = [col for col in mc_best_intervals_columns if col in best_intervals.columns]
                    best_intervals = best_intervals[final_columns]
                    best_intervals = best_intervals[best_intervals['avg_return'] <= -5]
                    best_intervals = best_intervals[best_intervals['success_rate'] >= 50]
                    best_intervals = best_intervals[best_intervals['current_period'] <= best_intervals['best_period']]
                    for col in best_intervals.columns:
                        if best_intervals[col].dtype in ['float64', 'float32']:
                            best_intervals[col] = best_intervals[col].round(3)
                    save_analysis_result(run_id, "ALL", "ALL", f'mc_eval_best_intervals_{range_name}', best_intervals.to_dict(orient='records'))

                # MC Good Signals
                good_signals = valid_df.sort_values('latest_signal', ascending=False)
                avg_return_cols = [f'avg_return_{period}' for period in periods if f'avg_return_{period}' in good_signals.columns]
                good_signals['min_return'] = good_signals[avg_return_cols].min(axis=1)
                good_signals['best_period'] = good_signals[avg_return_cols].idxmin(axis=1).str.extract('(\d+)').astype(int)
                good_signals['hold_time'] = good_signals.apply(
                    lambda row: format_hold_time(parse_interval_to_minutes(row['interval']) * row['best_period']), axis=1
                )
                good_signals['exp_return'] = good_signals.apply(lambda row: row[f'avg_return_{int(row.best_period)}'], axis=1)
                good_signals['avg_return'] = good_signals['exp_return']
                good_signals['test_count'] = good_signals.apply(lambda row: row[f'test_count_{int(row.best_period)}'], axis=1)
                good_signals['success_rate'] = good_signals.apply(lambda row: row[f'success_rate_{int(row.best_period)}'], axis=1)
                available_good_columns = [col for col in mc_best_intervals_columns if col in good_signals.columns]
                good_signals = good_signals[available_good_columns]
                good_signals = good_signals[good_signals['success_rate'] >= 50]
                for col in good_signals.columns:
                    if good_signals[col].dtype in ['float64', 'float32']:
                        good_signals[col] = good_signals[col].round(3)
                save_analysis_result(run_id, "ALL", "ALL", 'mc_eval_good_signals', good_signals.to_dict(orient='records'))
            
            # MC Interval Summary
            agg_dict = {'signal_count': 'sum'}
            for period in periods:
                if f'test_count_{period}' in df_mc_eval.columns: agg_dict[f'test_count_{period}'] = 'sum'
                if f'success_rate_{period}' in df_mc_eval.columns: agg_dict[f'success_rate_{period}'] = 'mean'
                if f'avg_return_{period}' in df_mc_eval.columns: agg_dict[f'avg_return_{period}'] = 'mean'
            interval_summary = df_mc_eval.groupby('interval').agg(agg_dict).reset_index()
            save_analysis_result(run_id, "ALL", "ALL", 'mc_eval_interval_summary', interval_summary.to_dict(orient='records'))
        
        # 4. Compute per-index breadth (KEY CHANGE)
        def aggregate_signals_for_tickers(df, ticker_list, metric_name):
            """Aggregate signals for a specific set of tickers."""
            if df.empty:
                return []
            try:
                # Filter to only the tickers in this index
                df_filtered = df[df['ticker'].isin(ticker_list)]
                if df_filtered.empty:
                    return []
                
                df_filtered = df_filtered.copy()
                if 'date' not in df_filtered.columns:
                    return []
                
                df_filtered['date'] = pd.to_datetime(df_filtered['date'])
                daily_counts = df_filtered.groupby('date')['ticker'].nunique().reset_index()
                daily_counts.columns = ['date', 'count']
                daily_counts = daily_counts.sort_values('date')
                daily_counts['date'] = daily_counts['date'].astype(str)
                return daily_counts.to_dict(orient='records')
            except Exception as e:
                logger.error(f"Error aggregating {metric_name}: {e}")
                return []
        
        if progress_callback:
            progress_callback(92)
        
        # Compute and save breadth for each index
        for idx_info in index_info_list:
            idx_key = idx_info['key']
            idx_tickers = index_ticker_map.get(idx_key, [])
            stock_list_name = idx_info['stock_list_name']
            
            logger.info(f"Computing breadth for {idx_key} with {len(idx_tickers)} tickers")
            
            # CD 1234 breadth for this index
            cd_breadth = aggregate_signals_for_tickers(df_breakout_1234, idx_tickers, f'CD 1234 {idx_key}')
            if cd_breadth:
                save_analysis_result(run_id, stock_list_name, "ALL", 'cd_market_breadth_1234', cd_breadth)
                logger.info(f"Saved CD breadth for {idx_key}: {len(cd_breadth)} days")
            
            # MC 1234 breadth for this index
            mc_breadth = aggregate_signals_for_tickers(df_mc_breakout_1234, idx_tickers, f'MC 1234 {idx_key}')
            if mc_breadth:
                save_analysis_result(run_id, stock_list_name, "ALL", 'mc_market_breadth_1234', mc_breadth)
                logger.info(f"Saved MC breadth for {idx_key}: {len(mc_breadth)} days")
        
        if progress_callback:
            progress_callback(100)
        
        update_analysis_run_status(run_id, "completed")
        logger.info(f"Multi-index analysis completed. Run ID: {run_id}")
        
        if failed_tickers:
            logger.warning(f"Failed tickers: {', '.join(failed_tickers)}")
        
    except Exception as e:
        logger.error(f"Multi-index analysis failed: {e}")
        update_analysis_run_status(run_id, "failed")
        raise e