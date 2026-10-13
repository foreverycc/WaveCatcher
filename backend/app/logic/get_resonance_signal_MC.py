"""MC (sell) 1234 resonance; the implementation is shared with CD in resonance.py."""
from app.logic.resonance import calculate_score as calculate_mc_score, process_ticker_1234 as _process, identify_1234 as _identify


def process_ticker_mc_1234(ticker, data_ticker=None):
    return _process(ticker, data_ticker, side='mc')


def identify_mc_1234(data, all_ticker_data):
    return _identify(data, all_ticker_data, side='mc')
