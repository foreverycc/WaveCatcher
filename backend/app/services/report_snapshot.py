"""Capture inputs while the analysis still owns the downloaded data."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.logic.db_utils import save_analysis_result
from app.logic.scoring_config import get_config


def save_report_snapshot(run_id, indices, ticker_data, end_date, failed_tickers):
    prices = {}
    for index in indices:
        frame = ticker_data.get(index["symbol"], {}).get("1d")
        prices[index["symbol"]] = [] if frame is None else [
            {"date": stamp.strftime("%Y-%m-%d"),
             **{key.lower(): float(row[key]) for key in ["Open", "High", "Low", "Close", "Volume"]}}
            for stamp, row in frame.iterrows()
        ]
    save_analysis_result(run_id, "ALL", "ALL", "report_snapshot", {
        "indices": indices,
        "prices": prices,
        "as_of": end_date or datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat(),
        "scoring": get_config(),
        "failed_tickers": failed_tickers,
    })
