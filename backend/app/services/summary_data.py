"""The Summary tab and exported report consume these exact, run-scoped figures."""
import pandas as pd

from app.logic.signals import compute_signals
from app.logic.scoring_config import DEFAULT_CONFIG

BREADTH_FIELDS = {
    'Breadth': 'market_breadth_1234',
    'SignalBreadth': 'signal_breadth_by_interval',
    'ScoreBreadth': 'score_breadth_by_interval',
    'BreakthroughScoreBreadth': 'breakthrough_score_by_interval',
}


def price_history(rows, scoring):
    if not rows:
        return []
    config = {**DEFAULT_CONFIG, **scoring}
    df = pd.DataFrame([{
        'timestamp': row.get('time', row.get('date')),
        **{key: row.get(key.lower(), row.get('close', 0)) for key in ['Open', 'High', 'Low', 'Close']},
        'Volume': row.get('volume', 0),
    } for row in rows])
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.set_index('timestamp').sort_index()
    for side in ['cd', 'mc']:
        signals = compute_signals(df, side, config)
        df[f'{side}_signal'] = signals['signal']
        df[f'{side}_1234_signal'] = signals['hq']
        df[f'{side}_score'] = signals['score']
    for span in [13, 21, 144, 169, 20]:
        df[f'ema_{span}'] = df.Close.ewm(span=span, adjust=False).mean()
    for span in [50, 100, 200]:
        df[f'sma_{span}'] = df.Close.rolling(span).mean()
    output = []
    for timestamp, row in df.iterrows():
        result = {'time': timestamp.isoformat()}
        for key, value in row.items():
            result[key.lower()] = None if pd.isna(value) else (bool(value) if 'signal' in key else float(value))
        output.append(result)
    return output


def summary_figures(results):
    snapshot = results.get(('report_snapshot', 'ALL'))
    if not snapshot:
        raise ValueError('This older run has no report snapshot. Run analysis again to generate a report.')
    figures = []
    for index in snapshot['indices']:
        symbol = index['symbol']
        figure = {
            'title': index['key'], 'indexTicker': symbol,
            'tickers': list(dict.fromkeys(index['tickers'])),
            'spxData': price_history(snapshot['prices'].get(symbol, []), snapshot['scoring']),
            'intervalWeights': snapshot['scoring'].get('interval_weights', DEFAULT_CONFIG['interval_weights']),
            'signals1234': {
                f'{side}_dates': [str(row['date'])[:10] for row in results.get((f'{side}_breakout_candidates_summary_1234', 'ALL'), []) if row.get('ticker') == symbol]
                for side in ['cd', 'mc']
            },
        }
        for side in ['cd', 'mc']:
            for field, suffix in BREADTH_FIELDS.items():
                figure[side + field] = results.get((f'{side}_{suffix}', index['breadth_key']), [])
        figures.append(figure)
    return {'figures': figures, 'as_of': snapshot['as_of']}
