"""The Summary tab and exported report consume these exact, run-scoped figures."""
import pandas as pd

from app.logic.indicators import (
    compute_cd_indicator, compute_mc_indicator, compute_cd_score, compute_mc_score,
    compute_cd_break_through, compute_mc_break_through,
)
from app.logic.hq_filters import compute_high_return_cd, compute_high_return_mc
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
        **{key: row.get(key.lower(), row.get('close', 0)) for key in ['Open', 'High', 'Low', 'Close', 'Volume']},
    } for row in rows])
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.set_index('timestamp').sort_index()
    for side, indicator, score_fn, breakthrough_fn, hq_fn in [
        ('cd', compute_cd_indicator, compute_cd_score, compute_cd_break_through, compute_high_return_cd),
        ('mc', compute_mc_indicator, compute_mc_score, compute_mc_break_through, compute_high_return_mc),
    ]:
        weights = config[f'{side}_component_weights']
        score = score_fn(df, weights=tuple(weights[key] for key in ['divergence', 'price_position', 'volume']))
        signal = indicator(df).fillna(False).astype(bool) & score.ge(config[f'{side}_threshold'])
        if config['hq_algorithm'] == 'high_return':
            hq = signal & hq_fn(df, signal, **config['hq_high_return'])
        else:
            breakthrough = breakthrough_fn(df).fillna(False).astype(bool)
            recent = breakthrough.rolling(10, min_periods=1).max().shift(1).fillna(False).astype(bool)
            hq = signal & (breakthrough | recent)
        df[f'{side}_signal'] = signal
        df[f'{side}_1234_signal'] = hq
        df[f'{side}_score'] = score
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
