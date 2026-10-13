"""MC (sell) signal evaluation; the implementation is shared with CD in signal_evaluation.py."""
from app.logic.signal_evaluation import MAX_SIGNALS_THRESHOLD, evaluate_interval as _evaluate_interval, calculate_returns as _calculate_returns


def calculate_returns(data, signals=None, periods=None, max_signals=MAX_SIGNALS_THRESHOLD):
    return _calculate_returns(data, 'mc', signals, periods, max_signals)


def evaluate_interval(ticker, interval, data=None):
    return _evaluate_interval(ticker, interval, 'mc', data=data)
