"""
Earnings dates
==============
Past and upcoming earnings report dates of a ticker with the time of day (before the open /
after the close), EPS estimate, reported EPS and surprise, from yfinance get_earnings_dates.
Stored in the earnings_events table and refreshed at most every REFRESH_HOURS per ticker.
"""
import logging
import math
from datetime import date, datetime, timedelta

import yfinance as yf

from app.db.database import SessionLocal
from app.db.models import EarningsEvent
from app.logic.data_loader import call_with_rate_limit_retry

logger = logging.getLogger(__name__)

REFRESH_HOURS = 24
LIMIT = 40  # about the next 4 and the last 36 reports
NONE_DATE = date(1900, 1, 1)  # marker row: no earnings dates available


def _session(ts):
    """Report time of day in exchange local time."""
    minutes = ts.hour * 60 + ts.minute
    if minutes == 0:
        return 'tbd'
    if minutes < 9 * 60 + 30:
        return 'bmo'
    if minutes >= 16 * 60:
        return 'amc'
    return 'dmh'


def _num(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def fetch_earnings(ticker):
    df = call_with_rate_limit_retry(lambda: yf.Ticker(ticker).get_earnings_dates(limit=LIMIT))
    rows = {}
    if df is None or df.empty:
        return rows
    for ts, r in df.iterrows():
        d = ts.date()
        rows[d] = {
            'event_time': ts.strftime('%H:%M'),
            'session': _session(ts),
            'eps_estimate': _num(r.get('EPS Estimate')),
            'eps_actual': _num(r.get('Reported EPS')),
            'surprise_pct': _num(r.get('Surprise(%)')),
        }
    return rows


def refresh_earnings(ticker, max_age_hours=REFRESH_HOURS):
    """Fetch and store a ticker's earnings dates unless fetched within max_age_hours."""
    if ticker.startswith('^'):
        return
    db = SessionLocal()
    try:
        last = (db.query(EarningsEvent.fetched_at)
                .filter(EarningsEvent.ticker == ticker)
                .order_by(EarningsEvent.fetched_at.desc()).first())
        if last and last[0] and datetime.utcnow() - last[0] < timedelta(hours=max_age_hours):
            return
        rows = fetch_earnings(ticker)
        now = datetime.utcnow()
        if not rows:
            rows = {NONE_DATE: {'event_time': None, 'session': None, 'eps_estimate': None, 'eps_actual': None, 'surprise_pct': None}}
        for d, values in rows.items():
            db.merge(EarningsEvent(ticker=ticker, event_date=d, fetched_at=now, **values))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"{ticker}: earnings dates not updated: {e}")
    finally:
        db.close()


def ticker_earnings(ticker):
    """Earnings events of one ticker, oldest first."""
    db = SessionLocal()
    try:
        rows = (db.query(EarningsEvent)
                .filter(EarningsEvent.ticker == ticker, EarningsEvent.event_date > NONE_DATE)
                .order_by(EarningsEvent.event_date).all())
        return [{
            'date': r.event_date.strftime('%Y-%m-%d'), 'time': r.event_time, 'session': r.session,
            'eps_estimate': r.eps_estimate, 'eps_actual': r.eps_actual, 'surprise_pct': r.surprise_pct,
        } for r in rows]
    finally:
        db.close()
