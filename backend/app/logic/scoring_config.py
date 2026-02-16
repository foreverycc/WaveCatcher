"""
Scoring Configuration Management
=================================
Manages scoring weights for CD/MC signals. Stored as JSON in the data directory.
Allows adjusting weights without re-running analysis.
"""

import json
import os
from pathlib import Path

# Default configuration (backtest-optimized values)
DEFAULT_CONFIG = {
    "cd_component_weights": {
        "divergence": 15,
        "price_position": 70,
        "volume": 15
    },
    "mc_component_weights": {
        "divergence": 30,
        "price_position": 20,
        "volume": 50
    },
    "interval_weights": {
        "1h": 1,
        "2h": 2,
        "3h": 4,
        "4h": 8,
        "1d": 16
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
