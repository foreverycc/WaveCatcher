"""
Per-interval evaluation of CD (buy) and MC (sell) signals
=========================================================
One implementation for both sides; get_best_CD_interval / get_best_MC_interval are thin wrappers.

For each signal: the return from the next bar's open to the close 0-100 bars later, plus how the
latest opposite signal before it looked (an MC before a CD: was it at a top; a CD before an MC:
was it at a bottom).
"""

import pandas as pd
import numpy as np
import yfinance as yf

from app.logic.data_loader import download_stock_data
from app.logic.indicators import compute_cd_indicator, compute_mc_indicator
from app.logic.signal_stats import add_signal_stats
from app.logic.signals import compute_signals, opposite, signal_lookback_days, DEFAULT_SIGNAL_LOOKBACK_DAYS
from app.logic.scoring_config import get_config

# Start of the lookback range used to judge the opposite signal's price position
EMA_WARMUP_PERIOD = 0

# Maximum number of latest signals to process (to reduce noise from older signals)
MAX_SIGNALS_THRESHOLD = 20  # default; the analysis uses evaluation.max_signals from the configuration

PERIODS = [0] + list(range(1, 101))  # Full range from 0 to 100

RAW_INDICATORS = {'cd': compute_cd_indicator, 'mc': compute_mc_indicator}

# How the opposite signal before a signal is judged: an MC at a top followed by a decline,
# a CD at a bottom followed by an increase. Names are used in the result keys.
EXTREME = {'mc': 'top', 'cd': 'bottom'}
MOVE = {'mc': 'decline', 'cd': 'increase'}


def find_latest_signal_before(data, date, signals):
    """
    Latest signal in `signals` (boolean Series) strictly before `date`.

    Returns (signal_date, close at that date) or (None, None).
    """
    signals_bool = signals.fillna(False).infer_objects(copy=False)
    signal_dates = data.index[signals_bool]
    previous = signal_dates[signal_dates < date]
    if len(previous) == 0:
        return None, None
    latest_date = previous.max()
    return latest_date, data.loc[latest_date, 'Close']


def evaluate_at_extreme(data, side, date, price, until_date):
    """
    Judge whether a `side` signal was at an extreme: a top for MC, a bottom for CD.

    Criteria (at least 2 of 3):
      1. price in the top (MC) / bottom (CD) 20% of the range up to `until_date`
      2. a move of at least 5% in the expected direction between the signal and `until_date`
      3. in the top (MC) / bottom (CD) 30% of the surrounding bars

    Returns dict with lookback_price_percentile, move_after, criteria_met, is_at_extreme.
    """
    top = side == 'mc'
    try:
        idx = data.index.get_loc(date)
        until_idx = data.index.get_loc(until_date)

        # Lookback range: from the warmup period to until_date; lookahead: from the signal to until_date
        warmup_start = min(EMA_WARMUP_PERIOD, len(data) - 1)
        lookback_data = data.iloc[warmup_start:until_idx + 1]
        lookahead_data = data.iloc[idx:until_idx + 1]

        metrics = {}

        # 1. Position of the price in the full historical range
        near_extreme = False
        metrics['lookback_price_percentile'] = 0.5
        if not lookback_data.empty:
            lookback_max = lookback_data['High'].max()
            lookback_min = lookback_data['Low'].min()
            lookback_range = lookback_max - lookback_min
            if lookback_range > 0:
                percentile = (price - lookback_min) / lookback_range
                metrics['lookback_price_percentile'] = percentile
                near_extreme = percentile >= 0.8 if top else percentile <= 0.2

        # 2. Move after the signal (decline after a top, increase after a bottom)
        if len(lookahead_data) > 1:
            if top:
                move = round(float((price - lookahead_data['Low'].min()) / price * 100), 2)
            else:
                move = round(float((lookahead_data['High'].max() - price) / price * 100), 2)
            metrics['move_after'] = move
            followed_by_move = move >= 5.0
        else:
            metrics['move_after'] = 0
            followed_by_move = False

        # 3. Local extreme relative to the surrounding bars (window: 5% of the data, 3-10 bars)
        window_size = max(3, min(10, len(data) // 20))
        window_data = data.iloc[max(0, idx - window_size):min(len(data), idx + window_size + 1)]
        if len(window_data) > 1:
            if top:
                rank = sum(price >= h for h in window_data['High'].values) / len(window_data)
            else:
                rank = sum(price <= l for l in window_data['Low'].values) / len(window_data)
            local_extreme = rank >= 0.7
        else:
            local_extreme = False

        criteria_met = sum([near_extreme, followed_by_move, local_extreme])
        metrics['criteria_met'] = criteria_met
        metrics['is_at_extreme'] = criteria_met >= 2
        return metrics

    except Exception as e:
        print(f"Error evaluating {side.upper()} signal at {date}: {e}")
        return {'lookback_price_percentile': 0.5, 'move_after': 0, 'criteria_met': 0, 'is_at_extreme': False}


def calculate_returns(data, side, signals=None, periods=None, max_signals=MAX_SIGNALS_THRESHOLD,
                      lookback_days=DEFAULT_SIGNAL_LOOKBACK_DAYS):
    """
    Returns after each signal for the given periods.

    Args:
        data: DataFrame with price data
        side: 'cd' or 'mc'
        signals: compute_signals(data, side) result (computed when not given)
        periods: periods to calculate returns for (default: 0 to 100)
        max_signals: maximum number of latest signals to process
        lookback_days: only signals within this many calendar days before the last bar

    Returns:
        DataFrame with signal dates, returns and volumes per period and the opposite-signal analysis
    """
    if periods is None:
        periods = PERIODS
    if signals is None:
        signals = compute_signals(data, side)

    signal_dates = data.index[signals['signal'].values]
    signal_dates = signal_dates[signal_dates >= data.index[-1] - pd.Timedelta(days=lookback_days)]
    # Limit to the latest N signals to reduce noise from older signals
    if len(signal_dates) > max_signals:
        signal_dates = signal_dates[-max_signals:]

    other = opposite(side)
    other_signals = RAW_INDICATORS[other](data)
    extreme, move = EXTREME[other], MOVE[other]
    scores = signals['score']

    results = []
    for date in signal_dates:
        idx = data.index.get_loc(date)

        # The signal is only known once its bar has closed, so enter at the next bar's open
        entry_price = data.iloc[idx + 1]['Open'] if idx + 1 < len(data) else np.nan
        entry_volume = data.loc[date, 'Volume']
        returns = {}
        volumes = {}

        for period in periods:
            if idx + period < len(data) and pd.notna(entry_price) and entry_price > 0:
                exit_price = entry_price if period == 0 else data.iloc[idx + period]['Close']
                exit_volume = data.iloc[idx + period]['Volume']
                returns[f'return_{period}'] = round(float((exit_price - entry_price) / entry_price * 100), 2)
                volumes[f'volume_{period}'] = round(int(exit_volume), 0)
            elif idx + period < len(data):
                returns[f'return_{period}'] = np.nan
                volumes[f'volume_{period}'] = round(int(data.iloc[idx + period]['Volume']), 0)
            else:
                returns[f'return_{period}'] = np.nan
                volumes[f'volume_{period}'] = np.nan

        # Latest opposite signal before this one, and whether it was at an extreme
        other_date, other_price = find_latest_signal_before(data, date, other_signals)
        evaluation = evaluate_at_extreme(data, other, other_date, other_price, date) if other_date is not None else {}

        score = scores.get(date, np.nan)
        results.append({
            'date': date,
            'entry_volume': entry_volume,
            'signal_score': float(score) if pd.notna(score) else None,
            **returns,
            **volumes,
            f'prev_{other}_date': other_date.strftime('%Y-%m-%d %H:%M:%S') if other_date else None,
            f'prev_{other}_price': round(float(other_price), 2) if other_price else None,
            f'{other}_at_{extreme}_price': evaluation.get('is_at_extreme', False),
            f'{other}_price_percentile': round(float(evaluation.get('lookback_price_percentile', 0)), 2),
            f'{other}_{move}_after': round(float(evaluation.get('move_after', 0)), 2),
            f'{other}_criteria_met': evaluation.get('criteria_met', 0),
        })

    return pd.DataFrame(results)


def _empty_other_summary(side):
    other = opposite(side)
    extreme, move = EXTREME[other], MOVE[other]
    return {
        f'{other}_signals_before_{side}': 0,
        f'{other}_at_{extreme}_price_count': 0,
        f'{other}_at_{extreme}_price_rate': 0,
        f'avg_{other}_price_percentile': 0,
        f'avg_{other}_{move}_after': 0,
        f'avg_{other}_criteria_met': 0,
        f'latest_{other}_date': None,
        f'latest_{other}_price': None,
        f'latest_{other}_at_{extreme}_price': False,
        f'latest_{other}_price_percentile': 0,
        f'latest_{other}_{move}_after': 0,
        f'latest_{other}_criteria_met': 0,
    }


def _other_summary(side, returns_df):
    """Summary of the opposite signals found before this side's signals."""
    other = opposite(side)
    extreme, move = EXTREME[other], MOVE[other]
    date_col, price_col = f'prev_{other}_date', f'prev_{other}_price'
    at_col, pct_col = f'{other}_at_{extreme}_price', f'{other}_price_percentile'
    move_col, crit_col = f'{other}_{move}_after', f'{other}_criteria_met'

    at_count = returns_df[at_col].sum() if at_col in returns_df else 0
    total = len(returns_df[returns_df[date_col].notna()]) if date_col in returns_df else 0
    at_rate = round(float(at_count / total * 100), 2) if total > 0 else 0

    summary = {
        f'{other}_signals_before_{side}': total,
        f'{other}_at_{extreme}_price_count': at_count,
        f'{other}_at_{extreme}_price_rate': round(float(at_rate), 2),
        f'avg_{other}_price_percentile': round(float(returns_df[pct_col].mean()), 2) if pct_col in returns_df else 0,
        f'avg_{other}_{move}_after': round(float(returns_df[move_col].mean()), 2) if move_col in returns_df else 0,
        f'avg_{other}_criteria_met': round(float(returns_df[crit_col].mean()), 2) if crit_col in returns_df else 0,
    }

    # Opposite signal before the most recent signal
    with_other = returns_df[returns_df[date_col].notna()].sort_values('date', ascending=False)
    if with_other.empty:
        latest = _empty_other_summary(side)
        summary.update({k: v for k, v in latest.items() if k.startswith('latest_')})
        return summary
    row = with_other.iloc[0]
    price = row[price_col] if price_col in row else None
    summary.update({
        f'latest_{other}_date': row[date_col] if date_col in row else None,
        f'latest_{other}_price': round(float(price), 2) if price else None,
        f'latest_{other}_at_{extreme}_price': row[at_col] if at_col in row else False,
        f'latest_{other}_price_percentile': round(float(row[pct_col] if pct_col in row else 0), 2),
        f'latest_{other}_{move}_after': round(float(row[move_col] if move_col in row else 0), 2),
        f'latest_{other}_criteria_met': row[crit_col] if crit_col in row else 0,
    })
    return summary


def _nx(df_nx):
    """NX trend per bar: EMA24 of the close above EMA89, or None with too little data."""
    if df_nx is None or df_nx.empty or len(df_nx) < 89:  # Need at least 89 periods for long EMA
        return None
    close = df_nx['Close']
    return close.ewm(span=24, adjust=False).mean() > close.ewm(span=89, adjust=False).mean()


def _current_nx(result, data):
    """Current NX values (at the last bar) for 1d, 1h and 4h."""
    for timeframe in ['1d', '1h', '4h']:
        result[f'nx_{timeframe}'] = None
        nx = _nx(data.get(timeframe)) if data else None
        if nx is not None:
            result[f'nx_{timeframe}'] = bool(nx.iloc[-1])


def _signal_nx(result, data, ticker, interval, latest_signal_date):
    """NX values at the latest signal for 1d and 1h."""
    for timeframe in ['1d', '1h']:
        result[f'nx_{timeframe}_signal'] = None
        if not (latest_signal_date and data):
            continue
        df_nx = data.get(timeframe)
        nx = _nx(df_nx)
        if nx is None:
            continue
        try:
            if timeframe == '1d' and interval != '1d':
                # The daily bar for the signal's own day is not complete yet; use the previous day
                prior = df_nx.index[df_nx.index.date < latest_signal_date.date()]
                idx_loc = df_nx.index.get_loc(prior[-1]) if len(prior) else -1
            else:
                idx_loc = df_nx.index.get_indexer([latest_signal_date], method='pad')[0]
            if idx_loc != -1:
                result[f'nx_{timeframe}_signal'] = bool(nx.iloc[idx_loc])
        except Exception as e:
            print(f"Error calculating nx_{timeframe}_signal for {ticker}: {e}")


def _load_frame(ticker, interval, data):
    """Data for the interval from the pre-downloaded dict, or downloaded when not given."""
    if data and interval in data and not data[interval].empty:
        return data[interval]
    if interval == '1w':
        if data and '1d' in data and not data['1d'].empty:
            daily_data = data['1d']
        else:
            daily_data = yf.Ticker(ticker).history(interval='1d', period='1y')
        if daily_data.empty:
            return daily_data
        return daily_data.resample('W').agg({
            'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
        })
    if interval in ['5m', '10m', '15m', '30m', '1h', '2h', '3h', '4h']:
        return download_stock_data(ticker, end_date=None)[interval]
    if interval == '1d':
        return yf.Ticker(ticker).history(interval='1d', period='1y')
    return None


def evaluate_interval(ticker, interval, side, data=None):
    """
    Evaluate `side` ('cd' or 'mc') signals for a ticker and interval.

    Args:
        ticker: Stock ticker symbol
        interval: Time interval to evaluate
        side: 'cd' or 'mc'
        data: Optional pre-downloaded data dictionary

    Returns:
        Dictionary with evaluation metrics and individual returns
    """
    bullish = side == 'cd'
    print(f"Evaluating {ticker} at {interval} interval for {side.upper()} signals")

    try:
        data_frame = _load_frame(ticker, interval, data)
        if data_frame is None or data_frame.empty:
            return None

        config = get_config()
        signals = compute_signals(data_frame, side, config, interval)
        signal_mask = signals['signal'].values
        signal_count = int(signal_mask.sum())

        latest_signal_date = data_frame.index[signal_mask].max() if signal_count > 0 else None
        current_price = round(float(data_frame.iloc[-1]['Close']), 2)

        result = {
            'ticker': ticker,
            'interval': interval,
            'signal_count': signal_count,
            'latest_signal': latest_signal_date.strftime('%Y-%m-%d %H:%M:%S') if latest_signal_date else None,
            'latest_signal_price': round(float(data_frame.loc[latest_signal_date, 'Close']), 2) if latest_signal_date is not None else None,
            'current_time': data_frame.index[-1].strftime('%Y-%m-%d %H:%M:%S'),
            'current_price': current_price,
        }

        returns_df = (calculate_returns(data_frame, side, signals,
                                        max_signals=config['evaluation']['max_signals'],
                                        lookback_days=signal_lookback_days(interval, config))
                      if signal_count > 0 else pd.DataFrame())
        # Signals actually evaluated: within the lookback window, at most max_signals
        result['signal_count'] = len(returns_df)

        if returns_df.empty:
            result.update({'current_period': 0, 'max_return': 0, 'min_return': 0,
                           'price_history': {}, 'volume_history': {}})
            for period in PERIODS:
                result[f'test_count_{period}'] = 0
                result[f'success_rate_{period}'] = 0
                result[f'avg_return_{period}'] = 0
                result[f'avg_volume_{period}'] = 0
                result[f'returns_{period}'] = []
                result[f'volumes_{period}'] = []
            result.update(_empty_other_summary(side))
            _signal_nx(result, data, ticker, interval, None)
            _current_nx(result, data)
            return result

        # Price and volume path of the latest signal up to now
        signal_idx = data_frame.index.get_loc(latest_signal_date)
        current_period = len(data_frame) - 1 - signal_idx
        if signal_idx + 1 < len(data_frame):
            # Returns are measured from the next bar's open (see calculate_returns)
            result['entry_price'] = round(float(data_frame.iloc[signal_idx + 1]['Open']), 2)
        price_history = {0: round(float(data_frame.loc[latest_signal_date, 'Close']), 2)}
        volume_history = {0: round(int(data_frame.loc[latest_signal_date, 'Volume']), 0)}
        for period in PERIODS:
            if signal_idx + period < len(data_frame):
                price_history[period] = round(float(data_frame.iloc[signal_idx + period]['Close']), 2)
                volume_history[period] = round(int(data_frame.iloc[signal_idx + period]['Volume']), 0)
            else:
                price_history[period] = None
                volume_history[period] = None
        if current_period > max(PERIODS):
            price_history[current_period] = current_price
            volume_history[current_period] = round(int(data_frame.iloc[-1]['Volume']), 0)
        result['current_period'] = current_period
        result['price_history'] = price_history
        result['volume_history'] = volume_history

        # Metrics per period (a period only counts signals that have that many bars after them)
        all_returns = []
        for period in PERIODS:
            period_returns = returns_df[f'return_{period}'].dropna()
            volume_col = f'volume_{period}'
            period_volumes = returns_df[volume_col].dropna() if volume_col in returns_df else pd.Series([], dtype='float64')
            test_count = len(period_returns)
            # A buy works when the price rises, a sell when it falls
            wins = period_returns > 0 if bullish else period_returns < 0
            result[f'test_count_{period}'] = test_count
            result[f'success_rate_{period}'] = round(float(wins.mean() * 100), 2) if test_count > 0 else 0
            result[f'avg_return_{period}'] = round(float(period_returns.mean()), 2) if test_count > 0 else 0
            result[f'avg_volume_{period}'] = round(int(period_volumes.mean()), 0) if len(period_volumes) > 0 else 0
            result[f'returns_{period}'] = [round(float(x), 2) for x in period_returns.tolist()]
            result[f'volumes_{period}'] = [round(int(x), 0) for x in period_volumes.tolist()]
            all_returns.extend(period_returns.tolist())

        result.update(_other_summary(side, returns_df))

        result['max_return'] = round(float(max(all_returns)), 2) if all_returns else 0
        result['min_return'] = round(float(min(all_returns)), 2) if all_returns else 0

        # Baseline / excess return, best period from the fixed grid and walk-forward out-of-sample stats
        add_signal_stats(result, returns_df, data_frame, bullish=bullish,
                         min_prior=config['evaluation']['min_prior_signals'])

        _signal_nx(result, data, ticker, interval, latest_signal_date)
        _current_nx(result, data)
        return result

    except Exception as e:
        print(f"Error evaluating {ticker} at {interval} interval: {e}")
        return None
