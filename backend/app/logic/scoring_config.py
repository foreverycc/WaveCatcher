"""
Scoring Configuration Management
=================================
Manages scoring weights for CD/MC signals. Stored as JSON in the data directory.
Allows adjusting weights without re-running analysis.
"""

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
            merged = DEFAULT_CONFIG.copy()
            for key in DEFAULT_CONFIG:
                if key in config:
                    if isinstance(DEFAULT_CONFIG[key], dict):
                        merged[key] = {**DEFAULT_CONFIG[key], **config[key]}
                    else:
                        merged[key] = config[key]
            return merged
        except (json.JSONDecodeError, IOError):
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> dict:
    """Save scoring config to file. Returns the saved config."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    # Validate structure
    validated = DEFAULT_CONFIG.copy()
    
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
        if algo in ('breakthrough', 'high_return'):
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
    """Return the HQ algorithm: 'breakthrough' or 'high_return'."""
    config = get_config()
    algo = config.get('hq_algorithm', 'breakthrough')
    if algo not in ('breakthrough', 'high_return'):
        return 'breakthrough'
    return algo


def get_hq_high_return_config() -> dict:
    """Return the high-return HQ configuration parameters."""
    config = get_config()
    return config.get('hq_high_return', DEFAULT_CONFIG['hq_high_return'])
