"""Shared index configuration loader — reads from data/index_config.json."""
import os
import json
import logging

logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/index_config.json"))

# Fallback if file doesn't exist yet
_FALLBACK = {
    "SPX": {"symbol": "^SPX", "stock_list": "stocks_sp500.tab", "whitelist": []},
    "QQQ": {"symbol": "QQQ", "stock_list": "stocks_nasdaq100.tab", "whitelist": []},
    "DJI": {"symbol": "^DJI", "stock_list": "stocks_dowjones.tab", "whitelist": []},
    "IWM": {"symbol": "IWM", "stock_list": "stocks_russell2000.tab", "whitelist": []},
}


def load_index_config() -> dict:
    """Load index configuration from JSON file (re-reads each call)."""
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        else:
            logger.warning(f"Index config not found at {CONFIG_PATH}, using fallback")
            return dict(_FALLBACK)
    except Exception as e:
        logger.error(f"Error loading index config: {e}")
        return dict(_FALLBACK)


def save_index_config(config: dict) -> None:
    """Save index configuration to JSON file."""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
