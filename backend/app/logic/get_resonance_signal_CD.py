"""CD (buy) 1234 resonance; the implementation is shared with MC in resonance.py."""
from app.logic.resonance import calculate_score, process_ticker_1234 as _process, identify_1234 as _identify


def process_ticker_1234(ticker, data_ticker=None, score_hist=None):
    return _process(ticker, data_ticker, side='cd', score_hist=score_hist)


def identify_1234(data, all_ticker_data):
    return _identify(data, all_ticker_data, side='cd')
