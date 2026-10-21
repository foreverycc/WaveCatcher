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

from data_loader import (load_stock_list, download_stock_data, drop_unfinished_bars,
                         fill_missing_bars, validate_intraday_coverage, transform_1h_data)
from app.logic.db_utils import (
    save_price_history,
    load_price_history,
    create_analysis_run,
    update_analysis_run_status,
    save_analysis_result
)
from app.logic.utils import (
    calculate_current_nx_values,
)
from app.logic.scoring_config import get_interval_weights, get_evaluation_config
from app.logic.signal_stats import BEST_PERIOD_GRID, select_best_rows, pooled_stats, pooled_edges, apply_universe_baseline
from app.logic.get_resonance_signal_CD import (
    process_ticker_1234, 
    identify_1234, 
)
from app.logic.get_resonance_signal_MC import (
    process_ticker_mc_1234, 
    identify_mc_1234, 
)
from app.logic.get_best_CD_interval import evaluate_interval
from app.logic.fundamentals import refresh_quarterly
from app.logic.score_distribution import aggregate_score_histograms
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
                          'excess_return', 'baseline_return', 'pooled_excess_return', 'oos_avg_return', 'oos_success_rate', 'oos_count',
                          'nx_1d_signal', 'nx_1h_signal',
                          'nx_1d', 'nx_1h', 'nx_4h',
                          'mc_signals_before_cd', 'mc_at_top_price_count', 'mc_at_top_price_rate',
                          'avg_mc_price_percentile', 'avg_mc_decline_after', 'avg_mc_criteria_met',
                          'latest_mc_date', 'latest_mc_price', 'latest_mc_at_top_price',
                          'latest_mc_price_percentile', 'latest_mc_decline_after', 'latest_mc_criteria_met']

# Define MC column configurations with CD analysis columns (needed for symmetry with CD analysis)
mc_best_intervals_columns = ['ticker', 'interval', 'hold_time',  
                             'avg_return', 'latest_signal', 'latest_signal_price', 
                             'current_time', 'current_price', 'current_period',
                             'test_count', 'success_rate', 'best_period', 'signal_count',
                             'excess_return', 'baseline_return', 'pooled_excess_return', 'oos_avg_return', 'oos_success_rate', 'oos_count',
                             'nx_1d_signal', 'nx_1h_signal',
                             'nx_1d', 'nx_1h', 'nx_4h',
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
                        'nx_1d_signal', 'nx_1h_signal',
                        'nx_1d', 'nx_1h', 'nx_4h',
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

# Bars per US regular session for each interval (1h data has 7 bars: 9:30 ... 15:30)
BARS_PER_DAY = {'1h': 7, '2h': 4, '3h': 3, '4h': 2, '1d': 1}

def format_hold_time_bars(interval, bars):
    """
    Format a holding period given in bars of `interval` as trading days plus remaining hours.
    Examples: ('1h', 14) -> '2days', ('3h', 4) -> '1day3hr', ('1d', 5) -> '5days'
    """
    bars = int(bars)
    bars_per_day = BARS_PER_DAY.get(interval)
    if not bars_per_day:
        return format_hold_time(parse_interval_to_minutes(interval) * bars)
    days, rem_bars = divmod(bars, bars_per_day)
    result = []
    if days > 0:
        result.append(f"{days}day{'s' if days > 1 else ''}")
    if rem_bars > 0:
        result.append(f"{rem_bars * parse_interval_to_minutes(interval) // 60}hr")
    return "".join(result) if result else "0min"

# Move this function outside the analyze_stocks function so it can be pickled
def fill_gaps_from_history(ticker, data):
    """Fill bars missing from the 1h / 1d download with stored bars and rebuild 2h-4h from the filled 1h."""
    for interval in ['1h', '1d']:
        df = data.get(interval)
        if df is None or df.empty:
            continue
        filled = fill_missing_bars(df, load_price_history(ticker, interval))
        if len(filled) == len(df):
            continue
        logger.info(f"{ticker}: filled {len(filled) - len(df)} missing {interval} bars from stored history")
        data[interval] = filled
        if interval == '1h':
            for derived in ['2h', '3h', '4h']:
                data[derived] = transform_1h_data(filled, derived)
    data['_warnings'] = validate_intraday_coverage(ticker, data)
    return data


def process_ticker_all(ticker, end_date=None):
    """Process a single ticker for all analysis types"""
    try:
        print(f"Processing {ticker}")
        # Download data once for all analyses
        data = download_stock_data(ticker, end_date=end_date)
        data = fill_gaps_from_history(ticker, data)
        refresh_quarterly(ticker)  # quarterly financials, refetched at most weekly
        
        # Skip if no data available
        if all(df.empty for key, df in data.items() if isinstance(df, pd.DataFrame)):
            print(f"No data available for {ticker}")
            return ticker, None, None, [], [], None
            
        # Log any data quality warnings
        data_warnings = data.get('_warnings', [])
        if data_warnings:
            for w in data_warnings:
                logger.warning(w)
            
        # Save downloaded data to database (replacing cache files)
        for interval, df in data.items():
            if interval.startswith('_'):
                continue
            if not df.empty:
                save_price_history(ticker, interval, df)
        
        # Charts keep the live bar, but signals only come from bars that have closed
        # (a signal on a still-forming bar can disappear by the time the bar closes)
        data = drop_unfinished_bars(data)
        
        # Process for 1234 breakout (CD signals); score_hist collects the scores of every
        # indicator firing (before the threshold) for the score distribution chart
        score_hist = {'cd': {}, 'mc': {}}
        results_1234 = process_ticker_1234(ticker, data, score_hist=score_hist['cd'])
        
        # Process for MC 1234 breakout (MC signals)
        mc_results_1234 = process_ticker_mc_1234(ticker, data, score_hist=score_hist['mc'])
        data['_score_hist'] = score_hist
        
        # Process for CD signal evaluation
        cd_results = []
        intervals = ['1h', '2h', '3h', '4h', '1d']
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
        
        return ticker, results_1234, mc_results_1234, cd_results, mc_results, data
        
    except Exception as e:
        print(f"Error processing {ticker}: {e}")
        return ticker, None, None, [], [], None

def save_eval_results(run_id, eval_results, side, all_ticker_data):
    """
    Save CD ('cd') or MC ('mc') evaluation tables: detailed rows, returns distribution,
    best intervals for each period range, good signals and per-interval summary.

    Best periods come from the fixed BEST_PERIOD_GRID, must have at least min_samples signals
    and beat the rest of the stock list by min_excess_return (configuration evaluation.*); with REQUIRE_POOLED_EDGE the
    interval/period must also show an edge pooled over all stocks (see signal_stats.py).
    """
    if not eval_results:
        return
    logger.info(f"Saving {side.upper()} evaluation results...")
    bullish = side == 'cd'
    columns = best_intervals_columns if bullish else mc_best_intervals_columns

    def round_floats(frame):
        for col in frame.columns:
            if frame[col].dtype in ['float64', 'float32']:
                frame[col] = frame[col].round(3)
        return frame

    # Excess return of every signal over the other stocks in the list over the same bars
    settings = get_evaluation_config()
    apply_universe_baseline(eval_results, all_ticker_data, bullish, settings['min_samples'])
    df_eval = round_floats(pd.DataFrame(eval_results))
    save_analysis_result(run_id, "ALL", "ALL", f'{side}_eval_custom_detailed', df_eval.to_dict(orient='records'))

    # Returns distribution
    returns_data = []
    for result in eval_results:
        for period in periods:
            individual_returns = result.get(f'returns_{period}') or []
            individual_volumes = result.get(f'volumes_{period}', [])
            for i, return_value in enumerate(individual_returns):
                returns_data.append({
                    'ticker': result['ticker'],
                    'interval': result['interval'],
                    'period': period,
                    'return': return_value,
                    'volume': individual_volumes[i] if i < len(individual_volumes) else None
                })
    if returns_data:
        df_returns = pd.DataFrame(returns_data)
        df_returns['return'] = df_returns['return'].round(3)
        df_returns['volume'] = df_returns['volume'].round(0)
        save_analysis_result(run_id, "ALL", "ALL", f'{side}_eval_returns_distribution', df_returns.to_dict(orient='records'))
    else:
        save_analysis_result(run_id, "ALL", "ALL", f'{side}_eval_returns_distribution', [])

    def finish(frame):
        frame = frame.copy()
        frame['hold_time'] = frame.apply(lambda row: format_hold_time_bars(row['interval'], row['best_period']), axis=1)
        frame = frame[[col for col in columns if col in frame.columns]]
        return round_floats(frame.sort_values('latest_signal', ascending=False))

    # Pooled edge per interval x period over the whole stock list
    pooled = pooled_stats(df_eval, BEST_PERIOD_GRID, bullish)
    for row in pooled:
        row['hold_time'] = format_hold_time_bars(row['interval'], row['period'])
    save_analysis_result(run_id, "ALL", "ALL", f'{side}_eval_pooled_stats', pooled)
    edges = pooled_edges(pooled)

    # Best intervals per period range (one row per ticker, signal still inside its best holding window)
    for range_name, range_periods in period_ranges.items():
        grid = [p for p in BEST_PERIOD_GRID if p in range_periods]
        best_intervals = select_best_rows(df_eval, grid, bullish, one_per_ticker=True, edges=edges, settings=settings)
        if not best_intervals.empty:
            best_intervals = best_intervals[best_intervals['current_period'] <= best_intervals['best_period']]
        records = finish(best_intervals).to_dict(orient='records') if not best_intervals.empty else []
        save_analysis_result(run_id, "ALL", "ALL", f'{side}_eval_best_intervals_{range_name}', records)

    # Good signals (every ticker/interval that passes, over the full grid)
    good_signals = select_best_rows(df_eval, BEST_PERIOD_GRID, bullish, one_per_ticker=False, edges=edges, settings=settings)
    records = finish(good_signals).to_dict(orient='records') if not good_signals.empty else []
    save_analysis_result(run_id, "ALL", "ALL", f'{side}_eval_good_signals', records)

    # Interval summary
    agg_dict = {'signal_count': 'sum'}
    for period in periods:
        if f'test_count_{period}' in df_eval.columns: agg_dict[f'test_count_{period}'] = 'sum'
        if f'success_rate_{period}' in df_eval.columns: agg_dict[f'success_rate_{period}'] = 'mean'
        if f'avg_return_{period}' in df_eval.columns: agg_dict[f'avg_return_{period}'] = 'mean'
    interval_summary = df_eval.groupby('interval').agg(agg_dict).reset_index()
    save_analysis_result(run_id, "ALL", "ALL", f'{side}_eval_interval_summary', interval_summary.to_dict(orient='records'))


def analyze_stocks(file_path, end_date=None, progress_callback=None):
    """
    Comprehensive stock analysis function that performs all analysis types:
    - 1234 Breakout candidates (CD & MC)
    - CD/MC Signal Evaluation
    
    Args:
        file_path: Path to the file containing stock ticker symbols
        end_date: Optional end date for backtesting (format: 'YYYY-MM-DD')
        progress_callback: Optional callable that accepts integer progress (0-100)
    
    Returns:
        int: ID of the completed database run
    """
    stock_list_name = os.path.basename(file_path)
    logger.info(f"Starting analysis for {stock_list_name}")
    
    # Create Analysis Run in DB
    try:
        run_id = create_analysis_run(stock_list_name)
    except Exception as e:
        logger.error(f"Failed to create analysis run: {e}")
        raise

    # Load stock list
    try:
        tickers = []
        with open(file_path, 'r') as f:
            raw_tickers = [line.strip() for line in f if line.strip()]
            # Deduplicate while preserving order
            tickers = list(dict.fromkeys(raw_tickers))
        
        # Prepend Index tickers so they are included in 1234 analysis
        index_tickers = ["^SPX", "^DJI", "QQQ", "IWM"]
        from app.services.index_config import load_index_config
        index_tickers = list(dict.fromkeys(index_tickers + [
            config['symbol'] for config in load_index_config().values()
            if config['stock_list'] == stock_list_name
        ]))
        tickers = index_tickers + [t for t in tickers if t not in index_tickers]
        
        logger.info(f"Loaded {len(tickers)} tickers from {file_path} (including indices)")
    except Exception as e:
        logger.error(f"Failed to load stock list: {e}")
        update_analysis_run_status(run_id, "failed")
        raise

    if not tickers:
        logger.warning("No tickers found in file")
        update_analysis_run_status(run_id, "failed")
        raise ValueError("No tickers found")

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
        mc_results_1234 = []
        cd_results_1234 = []
        cd_eval_results = []
        mc_eval_results = []
        all_ticker_data = {}
        failed_tickers = []

        for res in results:
            if res is None:
                continue
                
            ticker, r_1234, mc_r_1234, cd_res, mc_res, data = res
            
            if r_1234 is None and not cd_res and not mc_res:
                 failed_tickers.append(ticker)
                 continue
                 
            if r_1234: cd_results_1234.extend(r_1234)
            if mc_r_1234: mc_results_1234.extend(mc_r_1234)
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
                
                df_work = df.copy()
                
                # If 'intervals' column exists (from identify_1234, e.g. "1,2,3"),
                # explode it into individual interval rows
                if 'intervals' in df_work.columns and 'interval' not in df_work.columns:
                    df_work['interval_list'] = df_work['intervals'].apply(
                        lambda x: [f'{v}h' if v != '1d' else '1d' for v in str(x).split(',')] if pd.notna(x) else []
                    )
                    df_work = df_work.explode('interval_list').rename(columns={'interval_list': 'interval'})
                
                # If interval column exists, break down by interval
                if 'interval' in df_work.columns:
                    counts = df_work.groupby(['date', 'interval'])['ticker'].nunique().reset_index()
                    counts.columns = ['date', 'interval', 'count']
                    pivot = counts.pivot_table(index='date', columns='interval', values='count', fill_value=0).reset_index()
                    result = []
                    for _, row in pivot.iterrows():
                        # Ensure date is YYYY-MM-DD string
                        date_val = row['date']
                        if hasattr(date_val, 'strftime'):
                            date_str = date_val.strftime('%Y-%m-%d')
                        else:
                            date_str = str(date_val).split(' ')[0]
                        entry = {'date': date_str}
                        for intv in ['1h', '2h', '3h', '4h', '1d']:
                            entry[f'count_{intv}'] = int(row.get(intv, 0))
                        result.append(entry)
                    return sorted(result, key=lambda x: x['date'])
                else:
                    # Fallback: count unique tickers per day (no interval info)
                    daily_counts = df_work.groupby('date')['ticker'].nunique().reset_index()
                    daily_counts.columns = ['date', 'count']
                    daily_counts = daily_counts.sort_values('date')
                    daily_counts['date'] = daily_counts['date'].astype(str)
                    return [{'date': r['date'], 'count_1h': 0, 'count_2h': 0, 'count_3h': 0, 'count_4h': 0, 'count_1d': int(r['count'])} for r in daily_counts.to_dict(orient='records')]
            except Exception as e:
                logger.error(f"Error aggregating {metric_name}: {e}")
                return []

        # Helper: aggregate raw signal details by date and interval
        def aggregate_signals_by_interval(raw_details, metric_name, ticker_list=None):
            """Aggregate raw signal details by date and interval.
            Returns list of {date, count_1h, count_2h, count_3h, count_4h, count_1d}."""
            if not raw_details:
                return []
            try:
                df = pd.DataFrame(raw_details)
                if df.empty or 'signal_date' not in df.columns or 'interval' not in df.columns:
                    return []
                # Filter to specific tickers if provided
                if ticker_list is not None:
                    ticker_set = set(ticker_list)
                    df = df[df['ticker'].isin(ticker_set)]
                    if df.empty:
                        return []
                df['date'] = pd.to_datetime(df['signal_date']).dt.strftime('%Y-%m-%d')
                # Count unique tickers per (date, interval)
                counts = df.groupby(['date', 'interval'])['ticker'].nunique().reset_index()
                counts.columns = ['date', 'interval', 'count']
                # Pivot to get one column per interval
                pivot = counts.pivot_table(index='date', columns='interval', values='count', fill_value=0).reset_index()
                # Standardize column names
                result = []
                for _, row in pivot.iterrows():
                    entry = {'date': str(row['date'])}
                    for intv in ['1h', '2h', '3h', '4h', '1d']:
                        entry[f'count_{intv}'] = int(row.get(intv, 0))
                    result.append(entry)
                return sorted(result, key=lambda x: x['date'])
            except Exception as e:
                logger.error(f"Error aggregating {metric_name} by interval: {e}")
                return []

        # Helper: aggregate indicator scores by date and interval
        SCORE_INTERVAL_WEIGHTS = get_interval_weights()

        def aggregate_scores_by_interval(raw_details, metric_name, ticker_list=None):
            """Aggregate indicator_score * interval_weight by date.
            Returns list of {date, score_1h, score_2h, ..., score_1d, total_score}."""
            if not raw_details:
                return []
            try:
                df = pd.DataFrame(raw_details)
                if df.empty or 'signal_date' not in df.columns or 'interval' not in df.columns:
                    return []
                if 'indicator_score' not in df.columns:
                    return []
                # Filter to specific tickers if provided
                if ticker_list is not None:
                    ticker_set = set(ticker_list)
                    df = df[df['ticker'].isin(ticker_set)]
                    if df.empty:
                        return []
                df['date'] = pd.to_datetime(df['signal_date']).dt.strftime('%Y-%m-%d')
                # Drop rows without valid score
                df = df.dropna(subset=['indicator_score'])
                if df.empty:
                    return []
                # Sum indicator_score per (date, interval)
                score_sums = df.groupby(['date', 'interval'])['indicator_score'].sum().reset_index()
                score_sums.columns = ['date', 'interval', 'score_sum']
                pivot = score_sums.pivot_table(index='date', columns='interval', values='score_sum', fill_value=0).reset_index()
                result = []
                for _, row in pivot.iterrows():
                    entry = {'date': str(row['date'])}
                    total = 0
                    for intv in ['1h', '2h', '3h', '4h', '1d']:
                        s = float(row.get(intv, 0))
                        entry[f'score_{intv}'] = round(s, 1)
                        total += s * SCORE_INTERVAL_WEIGHTS[intv]
                    entry['total_score'] = round(total, 1)
                    result.append(entry)
                return sorted(result, key=lambda x: x['date'])
            except Exception as e:
                logger.error(f"Error aggregating scores for {metric_name}: {e}")
                return []

        # 1. Save 1234 results and identify breakout candidates
        print("Saving 1234 breakout results...")
        save_analysis_result(run_id, "ALL", "ALL", 'cd_breakout_candidates_details_1234', cd_results_1234)
        df_breakout_1234 = identify_1234(cd_results_1234, all_ticker_data)
        if not df_breakout_1234.empty:
            save_analysis_result(run_id, "ALL", "ALL", 'cd_breakout_candidates_summary_1234', df_breakout_1234.to_dict(orient='records'))
        
        # Aggregate HQ breadth using is_hq flag (respects configured HQ algorithm)
        cd_hq_results = [r for r in cd_results_1234 if r.get('is_hq', False)]
        cd_hq_breadth = aggregate_signals_by_interval(cd_hq_results, 'CD HQ')
        if cd_hq_breadth:
            save_analysis_result(run_id, "ALL", "ALL", 'cd_market_breadth_1234', cd_hq_breadth)
        
        # Aggregate CD signals by interval (from ALL raw details — not HQ filtered)
        cd_signal_by_interval = aggregate_signals_by_interval(cd_results_1234, 'CD signals')
        if cd_signal_by_interval:
            save_analysis_result(run_id, "ALL", "ALL", 'cd_signal_breadth_by_interval', cd_signal_by_interval)

        # 2. Save MC 1234 results and identify breakout candidates
        logger.info("Saving MC 1234 breakout results...")
        save_analysis_result(run_id, "ALL", "ALL", 'mc_breakout_candidates_details_1234', mc_results_1234)
        df_mc_breakout_1234 = identify_mc_1234(mc_results_1234, all_ticker_data)
        if not df_mc_breakout_1234.empty:
            save_analysis_result(run_id, "ALL", "ALL", 'mc_breakout_candidates_summary_1234', df_mc_breakout_1234.to_dict(orient='records'))

        # Aggregate HQ breadth using is_hq flag
        mc_hq_results = [r for r in mc_results_1234 if r.get('is_hq', False)]
        mc_hq_breadth = aggregate_signals_by_interval(mc_hq_results, 'MC HQ')
        if mc_hq_breadth:
            save_analysis_result(run_id, "ALL", "ALL", 'mc_market_breadth_1234', mc_hq_breadth)

        # Aggregate MC signals by interval (from ALL raw details — not HQ filtered)
        mc_signal_by_interval = aggregate_signals_by_interval(mc_results_1234, 'MC signals')
        if mc_signal_by_interval:
            save_analysis_result(run_id, "ALL", "ALL", 'mc_signal_breadth_by_interval', mc_signal_by_interval)

        # Aggregate CD/MC indicator scores by interval (from ALL raw details)
        cd_score_by_interval = aggregate_scores_by_interval(cd_results_1234, 'CD scores')
        if cd_score_by_interval:
            save_analysis_result(run_id, "ALL", "ALL", 'cd_score_breadth_by_interval', cd_score_by_interval)

        mc_score_by_interval = aggregate_scores_by_interval(mc_results_1234, 'MC scores')
        if mc_score_by_interval:
            save_analysis_result(run_id, "ALL", "ALL", 'mc_score_breadth_by_interval', mc_score_by_interval)

        # Aggregate HQ Scores (scores only for HQ signals)
        cd_hq_score = aggregate_scores_by_interval(cd_hq_results, 'CD HQ scores')
        if cd_hq_score:
            save_analysis_result(run_id, "ALL", "ALL", 'cd_breakthrough_score_by_interval', cd_hq_score)

        mc_hq_score = aggregate_scores_by_interval(mc_hq_results, 'MC HQ scores')
        if mc_hq_score:
            save_analysis_result(run_id, "ALL", "ALL", 'mc_breakthrough_score_by_interval', mc_hq_score)

        save_analysis_result(run_id, "ALL", "ALL", 'score_distribution', aggregate_score_histograms(all_ticker_data))

        # 5-6. Save CD / MC evaluation results
        save_eval_results(run_id, cd_eval_results, 'cd', all_ticker_data)
        save_eval_results(run_id, mc_eval_results, 'mc', all_ticker_data)
        
        from app.services.report_snapshot import save_report_snapshot
        from app.services.index_config import load_index_config
        matched = [(k, v) for k, v in load_index_config().items() if v['stock_list'] == stock_list_name]
        report_indices = [{"key": k, "symbol": v["symbol"], "stock_list": stock_list_name,
                           "tickers": raw_tickers, "breadth_key": "ALL"} for k, v in matched]
        if not report_indices:
            report_indices = [{"key": stock_list_name, "symbol": "", "stock_list": stock_list_name,
                               "tickers": raw_tickers, "breadth_key": "ALL"}]
        save_report_snapshot(run_id, report_indices, all_ticker_data, end_date, failed_tickers)
        print("All analyses completed successfully!")
        update_analysis_run_status(run_id, "completed")

        if failed_tickers:
            print("\n----------------------")
            print("Failed to process the following tickers:")
            print(", ".join(failed_tickers))
            print("----------------------\n")

        return run_id

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
            raise ValueError("No tickers found for selected indices")
        
        # 2. Run the analysis on combined set (same as analyze_stocks)
        total = len(tickers)
        cd_results_1234 = []
        mc_results_1234 = []
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
                ticker, cd_1234, mc_1234, cd_eval, mc_eval, ticker_data = result
                
                if ticker_data is not None:
                    all_ticker_data[ticker] = ticker_data
                    if cd_1234:
                        cd_results_1234.extend(cd_1234)
                    if mc_1234:
                        mc_results_1234.extend(mc_1234)
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
        
        # Helper: aggregate raw signal details by date and interval
        def aggregate_signals_by_interval(raw_details, metric_name, ticker_list=None):
            """Aggregate raw signal details by date and interval.
            Returns list of {date, count_1h, count_2h, count_3h, count_4h, count_1d}."""
            if not raw_details:
                return []
            try:
                df = pd.DataFrame(raw_details)
                if df.empty or 'signal_date' not in df.columns or 'interval' not in df.columns:
                    return []
                if ticker_list is not None:
                    df = df[df['ticker'].isin(ticker_list)]
                    if df.empty:
                        return []
                df['date'] = pd.to_datetime(df['signal_date']).dt.strftime('%Y-%m-%d')
                counts = df.groupby(['date', 'interval'])['ticker'].nunique().reset_index()
                counts.columns = ['date', 'interval', 'count']
                pivot = counts.pivot_table(index='date', columns='interval', values='count', fill_value=0).reset_index()
                result = []
                for _, row in pivot.iterrows():
                    entry = {'date': str(row['date'])}
                    for intv in ['1h', '2h', '3h', '4h', '1d']:
                        entry[f'count_{intv}'] = int(row.get(intv, 0))
                    result.append(entry)
                return sorted(result, key=lambda x: x['date'])
            except Exception as e:
                logger.error(f"Error aggregating {metric_name} by interval: {e}")
                return []

        # Helper: aggregate indicator scores by date and interval
        SCORE_INTERVAL_WEIGHTS = get_interval_weights()

        def aggregate_scores_by_interval(raw_details, metric_name, ticker_list=None):
            """Aggregate indicator_score * interval_weight by date.
            Returns list of {date, score_1h, score_2h, ..., score_1d, total_score}."""
            if not raw_details:
                return []
            try:
                df = pd.DataFrame(raw_details)
                if df.empty or 'signal_date' not in df.columns or 'interval' not in df.columns:
                    return []
                if 'indicator_score' not in df.columns:
                    return []
                if ticker_list is not None:
                    df = df[df['ticker'].isin(ticker_list)]
                    if df.empty:
                        return []
                df['date'] = pd.to_datetime(df['signal_date']).dt.strftime('%Y-%m-%d')
                df = df.dropna(subset=['indicator_score'])
                if df.empty:
                    return []
                score_sums = df.groupby(['date', 'interval'])['indicator_score'].sum().reset_index()
                score_sums.columns = ['date', 'interval', 'score_sum']
                pivot = score_sums.pivot_table(index='date', columns='interval', values='score_sum', fill_value=0).reset_index()
                result = []
                for _, row in pivot.iterrows():
                    entry = {'date': str(row['date'])}
                    total = 0
                    for intv in ['1h', '2h', '3h', '4h', '1d']:
                        s = float(row.get(intv, 0))
                        entry[f'score_{intv}'] = round(s, 1)
                        total += s * SCORE_INTERVAL_WEIGHTS[intv]
                    entry['total_score'] = round(total, 1)
                    result.append(entry)
                return sorted(result, key=lambda x: x['date'])
            except Exception as e:
                logger.error(f"Error aggregating scores for {metric_name}: {e}")
                return []

        # 3. Identify breakouts and save results
        df_breakout_1234 = identify_1234(cd_results_1234, all_ticker_data)
        df_mc_breakout_1234 = identify_mc_1234(mc_results_1234, all_ticker_data)
        
        # Save combined results for reference
        save_analysis_result(run_id, "ALL", "ALL", 'cd_breakout_candidates_summary_1234', 
                           df_breakout_1234.to_dict(orient='records') if not df_breakout_1234.empty else [])
        save_analysis_result(run_id, "ALL", "ALL", 'mc_breakout_candidates_summary_1234',
                           df_mc_breakout_1234.to_dict(orient='records') if not df_mc_breakout_1234.empty else [])
        
        # 3b-3d. Save CD / MC evaluation results
        save_eval_results(run_id, cd_eval_results, 'cd', all_ticker_data)
        save_eval_results(run_id, mc_eval_results, 'mc', all_ticker_data)
        
        # 4. Compute per-index breadth (KEY CHANGE)
        def aggregate_signals_for_tickers(df, ticker_list, metric_name):
            """Aggregate signals for a specific set of tickers, broken down by interval."""
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
                
                # If 'intervals' column exists (from identify_1234, e.g. "1,2,3"),
                # explode it into individual interval rows
                if 'intervals' in df_filtered.columns and 'interval' not in df_filtered.columns:
                    df_filtered['interval_list'] = df_filtered['intervals'].apply(
                        lambda x: [f'{v}h' if v != '1d' else '1d' for v in str(x).split(',')] if pd.notna(x) else []
                    )
                    df_filtered = df_filtered.explode('interval_list').rename(columns={'interval_list': 'interval'})
                
                if 'interval' in df_filtered.columns:
                    counts = df_filtered.groupby(['date', 'interval'])['ticker'].nunique().reset_index()
                    counts.columns = ['date', 'interval', 'count']
                    pivot = counts.pivot_table(index='date', columns='interval', values='count', fill_value=0).reset_index()
                    result = []
                    for _, row in pivot.iterrows():
                        # Ensure date is YYYY-MM-DD string
                        date_val = row['date']
                        if hasattr(date_val, 'strftime'):
                            date_str = date_val.strftime('%Y-%m-%d')
                        else:
                            date_str = str(date_val).split(' ')[0]
                        entry = {'date': date_str}
                        for intv in ['1h', '2h', '3h', '4h', '1d']:
                            entry[f'count_{intv}'] = int(row.get(intv, 0))
                        result.append(entry)
                    return sorted(result, key=lambda x: x['date'])
                else:
                    daily_counts = df_filtered.groupby('date')['ticker'].nunique().reset_index()
                    daily_counts.columns = ['date', 'count']
                    daily_counts = daily_counts.sort_values('date')
                    daily_counts['date'] = daily_counts['date'].astype(str)
                    return [{'date': r['date'], 'count_1h': 0, 'count_2h': 0, 'count_3h': 0, 'count_4h': 0, 'count_1d': int(r['count'])} for r in daily_counts.to_dict(orient='records')]
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
            
            # CD HQ breadth for this index (using is_hq flag)
            cd_hq_for_idx = [r for r in cd_results_1234 if r.get('is_hq', False) and r.get('ticker', '') in set(idx_tickers)]
            cd_hq_breadth = aggregate_signals_by_interval(cd_hq_for_idx, f'CD HQ {idx_key}')
            if cd_hq_breadth:
                save_analysis_result(run_id, stock_list_name, "ALL", 'cd_market_breadth_1234', cd_hq_breadth)
                logger.info(f"Saved CD HQ breadth for {idx_key}: {len(cd_hq_breadth)} days")
            
            # MC HQ breadth for this index (using is_hq flag)
            mc_hq_for_idx = [r for r in mc_results_1234 if r.get('is_hq', False) and r.get('ticker', '') in set(idx_tickers)]
            mc_hq_breadth = aggregate_signals_by_interval(mc_hq_for_idx, f'MC HQ {idx_key}')
            if mc_hq_breadth:
                save_analysis_result(run_id, stock_list_name, "ALL", 'mc_market_breadth_1234', mc_hq_breadth)
                logger.info(f"Saved MC HQ breadth for {idx_key}: {len(mc_hq_breadth)} days")
            
            # CD signal breadth by interval for this index
            cd_sig_by_intv = aggregate_signals_by_interval(cd_results_1234, f'CD signals {idx_key}', ticker_list=idx_tickers)
            if cd_sig_by_intv:
                save_analysis_result(run_id, stock_list_name, "ALL", 'cd_signal_breadth_by_interval', cd_sig_by_intv)
                logger.info(f"Saved CD signal breadth by interval for {idx_key}: {len(cd_sig_by_intv)} days")
            
            # MC signal breadth by interval for this index
            mc_sig_by_intv = aggregate_signals_by_interval(mc_results_1234, f'MC signals {idx_key}', ticker_list=idx_tickers)
            if mc_sig_by_intv:
                save_analysis_result(run_id, stock_list_name, "ALL", 'mc_signal_breadth_by_interval', mc_sig_by_intv)
                logger.info(f"Saved MC signal breadth by interval for {idx_key}: {len(mc_sig_by_intv)} days")
            
            # CD score breadth by interval for this index
            cd_score_by_intv = aggregate_scores_by_interval(cd_results_1234, f'CD scores {idx_key}', ticker_list=idx_tickers)
            if cd_score_by_intv:
                save_analysis_result(run_id, stock_list_name, "ALL", 'cd_score_breadth_by_interval', cd_score_by_intv)
                logger.info(f"Saved CD score breadth by interval for {idx_key}: {len(cd_score_by_intv)} days")
            
            # MC score breadth by interval for this index
            mc_score_by_intv = aggregate_scores_by_interval(mc_results_1234, f'MC scores {idx_key}', ticker_list=idx_tickers)
            if mc_score_by_intv:
                save_analysis_result(run_id, stock_list_name, "ALL", 'mc_score_breadth_by_interval', mc_score_by_intv)
                logger.info(f"Saved MC score breadth by interval for {idx_key}: {len(mc_score_by_intv)} days")
            
            # CD HQ score by interval for this index
            cd_hq_score = aggregate_scores_by_interval(cd_hq_for_idx, f'CD HQ scores {idx_key}')
            if cd_hq_score:
                save_analysis_result(run_id, stock_list_name, "ALL", 'cd_breakthrough_score_by_interval', cd_hq_score)
                logger.info(f"Saved CD HQ score by interval for {idx_key}: {len(cd_hq_score)} days")

            # MC HQ score by interval for this index
            mc_hq_score = aggregate_scores_by_interval(mc_hq_for_idx, f'MC HQ scores {idx_key}')
            if mc_hq_score:
                save_analysis_result(run_id, stock_list_name, "ALL", 'mc_breakthrough_score_by_interval', mc_hq_score)
                logger.info(f"Saved MC HQ score by interval for {idx_key}: {len(mc_hq_score)} days")
        
        if progress_callback:
            progress_callback(100)
        
        # Collect and save data quality warnings
        all_warnings = []
        for t, t_data in all_ticker_data.items():
            if isinstance(t_data, dict):
                t_warnings = t_data.get('_warnings', [])
                all_warnings.extend(t_warnings)
        
        quality_report = {
            'warnings': all_warnings,
            'failed_tickers': failed_tickers,
            'total_tickers': len(tickers),
            'successful_tickers': len(all_ticker_data),
        }
        save_analysis_result(run_id, "ALL", "ALL", 'data_quality_warnings', quality_report)
        save_analysis_result(run_id, "ALL", "ALL", 'score_distribution', aggregate_score_histograms(all_ticker_data))
        
        if all_warnings:
            logger.warning(f"Data quality: {len(all_warnings)} warning(s) across tickers")
        if failed_tickers:
            logger.warning(f"Failed tickers ({len(failed_tickers)}): {', '.join(failed_tickers)}")
        
        from app.services.report_snapshot import save_report_snapshot
        report_indices = [{"key": info["key"], "symbol": info["symbol"],
                           "stock_list": info["stock_list_name"], "breadth_key": info["stock_list_name"],
                           "tickers": index_ticker_map[info["key"]]} for info in index_info_list]
        save_report_snapshot(run_id, report_indices, all_ticker_data, end_date, failed_tickers)
        update_analysis_run_status(run_id, "completed")
        logger.info(f"Multi-index analysis completed. Run ID: {run_id}")
        return run_id
        
    except Exception as e:
        logger.error(f"Multi-index analysis failed: {e}")
        update_analysis_run_status(run_id, "failed")
        raise e
