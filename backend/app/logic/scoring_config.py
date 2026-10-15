"""
Scoring Configuration Management
=================================
Manages scoring weights for CD/MC signals. Stored as JSON in the data directory.
Allows adjusting weights without re-running analysis.
"""

import copy
import json
import os
from pathlib import Path

# Default configuration (backtest-optimized across SOXX/SPACE/CRYPTO/QUANTUM/KWEB)
DEFAULT_CONFIG = {
    "cd_component_weights": {
        "divergence": 40,
        "price_position": 40,
        "volume": 20
    },
    "mc_component_weights": {
        "divergence": 40,
        "price_position": 20,
        "volume": 40
    },
    "interval_weights": {
        "1h": 1,
        "2h": 2,
        "3h": 4,
        "4h": 8,
        "1d": 32
    },
    "cd_threshold": 40,
    "mc_threshold": 50,
    "hq_algorithm": "breakthrough",
    "hq_high_return": {
        "lookback_signals": 3,
        "lookback_bars": 20,
        "cd_return_threshold": 5.0,
        "mc_return_threshold": -5.0
    },
    # trend_regime HQ: CD needs a deep decline below the stock's EMA, CD/MC need the market index
    # near or below its EMA (see hq_filters.compute_trend_regime and market_regime.py)
    "hq_trend_regime": {
        "stock_ema": 50,
        "cd_below_ema_pct": {"1h": 4.5, "2h": 6.5, "3h": 8.0, "4h": 10.0, "1d": 14.0},
        "use_market_cd": True,
        "use_market_mc": True,
        "market_symbol": "^SPX",
        "market_ema": 50,
        "market_max_above_ema_pct": 1.0
    },
    # Return evaluation and result-table filters (take effect on the next analysis run;
    # lookback_days also sets how far back the price charts show signals)
    "evaluation": {
        "lookback_days": {"1h": 180, "2h": 180, "3h": 365, "4h": 365, "1d": 730},
        "max_signals": 20,
        "min_samples": 3,
        "min_excess_return": 5.0,
        "min_success_rate": 50.0,
        "min_oos_count": 3,
        "min_prior_signals": 2
    }
}

# Config file location
_CONFIG_DIR = Path(__file__).parent.parent.parent / "data"
_CONFIG_FILE = _CONFIG_DIR / "scoring_config.json"


def get_config() -> dict:
    """Load scoring config from file, falling back to defaults."""
    if _CONFIG_FILE.exists():
        try:
            with open(_CONFIG_FILE, 'r') as f:
                config = json.load(f)
            # Merge with defaults to handle missing keys
            merged = copy.deepcopy(DEFAULT_CONFIG)
            for key in DEFAULT_CONFIG:
                if key in config:
                    if isinstance(DEFAULT_CONFIG[key], dict):
                        merged[key] = {**DEFAULT_CONFIG[key], **config[key]}
                        if key == 'evaluation':
                            merged[key]['lookback_days'] = {**DEFAULT_CONFIG[key]['lookback_days'],
                                                            **config[key].get('lookback_days', {})}
                        if key == 'hq_trend_regime':
                            merged[key]['cd_below_ema_pct'] = {**DEFAULT_CONFIG[key]['cd_below_ema_pct'],
                                                               **config[key].get('cd_below_ema_pct', {})}
                    else:
                        merged[key] = config[key]
            return merged
        except (json.JSONDecodeError, IOError):
            return copy.deepcopy(DEFAULT_CONFIG)
    return copy.deepcopy(DEFAULT_CONFIG)


def save_config(config: dict) -> dict:
    """Save scoring config to file. Returns the saved config."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    # Validate structure
    validated = copy.deepcopy(DEFAULT_CONFIG)
    
    for key in ['cd_component_weights', 'mc_component_weights']:
        if key in config and isinstance(config[key], dict):
            weights = config[key]
            # Ensure all 3 components present
            for comp in ['divergence', 'price_position', 'volume']:
                if comp in weights:
                    validated[key][comp] = max(0, min(100, float(weights[comp])))
    
    if 'interval_weights' in config and isinstance(config['interval_weights'], dict):
        for intv in ['1h', '2h', '3h', '4h', '1d']:
            if intv in config['interval_weights']:
                validated['interval_weights'][intv] = max(0, float(config['interval_weights'][intv]))
    
    # Validate thresholds (0-100)
    for key in ['cd_threshold', 'mc_threshold']:
        if key in config:
            validated[key] = max(0, min(100, float(config[key])))
    
    # Validate HQ algorithm
    if 'hq_algorithm' in config:
        algo = config['hq_algorithm']
        if algo in ('breakthrough', 'high_return', 'trend_regime'):
            validated['hq_algorithm'] = algo
    
    # Validate HQ high-return params
    if 'hq_high_return' in config and isinstance(config['hq_high_return'], dict):
        hr = config['hq_high_return']
        hr_validated = validated['hq_high_return'].copy()
        if 'lookback_signals' in hr:
            hr_validated['lookback_signals'] = max(1, min(10, int(hr['lookback_signals'])))
        if 'lookback_bars' in hr:
            hr_validated['lookback_bars'] = max(1, min(100, int(hr['lookback_bars'])))
        if 'cd_return_threshold' in hr:
            hr_validated['cd_return_threshold'] = max(0, min(50, float(hr['cd_return_threshold'])))
        if 'mc_return_threshold' in hr:
            hr_validated['mc_return_threshold'] = max(-50, min(0, float(hr['mc_return_threshold'])))
        validated['hq_high_return'] = hr_validated
    
    # Validate trend_regime HQ params
    if 'hq_trend_regime' in config and isinstance(config['hq_trend_regime'], dict):
        tr = config['hq_trend_regime']
        tr_validated = validated['hq_trend_regime']
        if 'stock_ema' in tr:
            tr_validated['stock_ema'] = max(5, min(400, int(tr['stock_ema'])))
        if isinstance(tr.get('cd_below_ema_pct'), dict):
            for intv in ['1h', '2h', '3h', '4h', '1d']:
                if intv in tr['cd_below_ema_pct']:
                    tr_validated['cd_below_ema_pct'][intv] = max(0, min(80, float(tr['cd_below_ema_pct'][intv])))
        for key in ['use_market_cd', 'use_market_mc']:
            if key in tr:
                tr_validated[key] = bool(tr[key])
        if isinstance(tr.get('market_symbol'), str) and tr['market_symbol'].strip():
            tr_validated['market_symbol'] = tr['market_symbol'].strip()[:20]
        if 'market_ema' in tr:
            tr_validated['market_ema'] = max(5, min(400, int(tr['market_ema'])))
        if 'market_max_above_ema_pct' in tr:
            tr_validated['market_max_above_ema_pct'] = max(-50, min(50, float(tr['market_max_above_ema_pct'])))

    # Validate evaluation params
    if 'evaluation' in config and isinstance(config['evaluation'], dict):
        ev = config['evaluation']
        ev_validated = validated['evaluation']
        if isinstance(ev.get('lookback_days'), dict):
            for intv in ['1h', '2h', '3h', '4h', '1d']:
                if intv in ev['lookback_days']:
                    ev_validated['lookback_days'][intv] = max(30, min(3650, int(ev['lookback_days'][intv])))
        limits = {
            'max_signals': (1, 200, int),
            'min_samples': (1, 50, int),
            'min_excess_return': (0, 100, float),
            'min_success_rate': (0, 100, float),
            'min_oos_count': (0, 50, int),
            'min_prior_signals': (1, 20, int),
        }
        for key, (lo, hi, cast) in limits.items():
            if key in ev:
                ev_validated[key] = max(lo, min(hi, cast(ev[key])))

    with open(_CONFIG_FILE, 'w') as f:
        json.dump(validated, f, indent=2)
    
    return validated


def get_cd_weights() -> tuple:
    """Return CD component weights as (divergence, price_position, volume) tuple."""
    config = get_config()
    w = config['cd_component_weights']
    return (w['divergence'], w['price_position'], w['volume'])


def get_mc_weights() -> tuple:
    """Return MC component weights as (divergence, price_position, volume) tuple."""
    config = get_config()
    w = config['mc_component_weights']
    return (w['divergence'], w['price_position'], w['volume'])


def get_interval_weights() -> dict:
    """Return interval weights as dict."""
    config = get_config()
    return config['interval_weights']


def get_cd_threshold() -> float:
    """Return CD score threshold. Signals below this are ignored."""
    config = get_config()
    return config.get('cd_threshold', DEFAULT_CONFIG['cd_threshold'])


def get_mc_threshold() -> float:
    """Return MC score threshold. Signals below this are ignored."""
    config = get_config()
    return config.get('mc_threshold', DEFAULT_CONFIG['mc_threshold'])


def get_hq_algorithm() -> str:
    """Return the HQ algorithm: 'breakthrough', 'high_return' or 'trend_regime'."""
    config = get_config()
    algo = config.get('hq_algorithm', 'breakthrough')
    if algo not in ('breakthrough', 'high_return', 'trend_regime'):
        return 'breakthrough'
    return algo


def get_hq_high_return_config() -> dict:
    """Return the high-return HQ configuration parameters."""
    config = get_config()
    return config.get('hq_high_return', DEFAULT_CONFIG['hq_high_return'])


def get_evaluation_config() -> dict:
    """Return the return-evaluation / result-table filter parameters."""
    return get_config()['evaluation']
