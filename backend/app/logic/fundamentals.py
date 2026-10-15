"""
Quarterly fundamentals
======================
Revenue, gross profit, net income and EPS per fiscal quarter from yfinance's quarterly income
statement (usually the last 4-6 quarters), stored in the quarterly_financials table and refreshed
at most every REFRESH_DAYS per ticker. Index aggregates sum the figures of a stock list per
calendar quarter.
"""
import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

from app.db.database import SessionLocal
from app.db.models import QuarterlyFinancial

logger = logging.getLogger(__name__)

REFRESH_DAYS = 7

ROWS = {
    'revenue': ['Total Revenue', 'Operating Revenue'],
    'gross_profit': ['Gross Profit'],
    'net_income': ['Net Income', 'Net Income Common Stockholders'],
    'eps': ['Diluted EPS', 'Basic EPS'],
}


def _has_statements(ticker):
    return not (ticker.startswith('^') or ticker.endswith('-USD'))


def fetch_quarterly(ticker):
    """{period_end: {revenue, gross_profit, net_income, eps}} from yfinance (empty when unavailable)."""
    stmt = yf.Ticker(ticker).quarterly_income_stmt
    if stmt is None or stmt.empty:
        return {}
    out = {}
    for col in stmt.columns:
        values = {}
        for field, names in ROWS.items():
            value = None
            for name in names:
                if name in stmt.index and pd.notna(stmt.at[name, col]):
                    value = float(stmt.at[name, col])
                    break
            values[field] = value
        if any(v is not None for v in values.values()):
            out[pd.Timestamp(col).date()] = values
    return out


def refresh_quarterly(ticker, max_age_days=REFRESH_DAYS):
    """Fetch and store a ticker's quarterly figures unless they were fetched within max_age_days."""
    if not _has_statements(ticker):
        return
    db = SessionLocal()
    try:
        last = (db.query(QuarterlyFinancial.fetched_at)
                .filter(QuarterlyFinancial.ticker == ticker)
                .order_by(QuarterlyFinancial.fetched_at.desc()).first())
        if last and last[0] and datetime.utcnow() - last[0] < timedelta(days=max_age_days):
            return
        rows = fetch_quarterly(ticker)
        now = datetime.utcnow()
        for period_end, values in rows.items():
            db.merge(QuarterlyFinancial(ticker=ticker, period_end=period_end, fetched_at=now, **values))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"{ticker}: quarterly financials not updated: {e}")
    finally:
        db.close()


def load_quarterly(tickers):
    """DataFrame of stored quarterly rows for the tickers."""
    db = SessionLocal()
    try:
        rows = db.query(QuarterlyFinancial).filter(QuarterlyFinancial.ticker.in_(list(tickers))).all()
    finally:
        db.close()
    return pd.DataFrame([{
        'ticker': r.ticker, 'period_end': pd.Timestamp(r.period_end), 'revenue': r.revenue,
        'gross_profit': r.gross_profit, 'net_income': r.net_income, 'eps': r.eps,
    } for r in rows])


def _clean(value):
    return None if value is None or pd.isna(value) else float(value)


def ticker_quarterly(ticker):
    """Quarterly rows of one ticker, oldest first."""
    df = load_quarterly([ticker])
    if df.empty:
        return []
    df = df.sort_values('period_end')
    return [{
        'period_end': row.period_end.strftime('%Y-%m-%d'),
        'revenue': _clean(row.revenue), 'gross_profit': _clean(row.gross_profit),
        'net_income': _clean(row.net_income), 'eps': _clean(row.eps),
    } for row in df.itertuples()]


def aggregate_quarterly(tickers, min_coverage=0.8):
    """
    Stock-list totals per calendar quarter (fiscal quarters mapped to the calendar quarter they end in).
    Totals use the same companies in every quarter shown (those reporting all of them), so the series
    is not distorted by companies dropping in and out. eps_up_pct is the share of companies whose EPS
    rose from their previous quarter.
    """
    df = load_quarterly(tickers)
    if df.empty:
        return []
    df['quarter'] = df.period_end.dt.to_period('Q')
    df = df.sort_values('period_end').drop_duplicates(['ticker', 'quarter'], keep='last')
    n_tickers = df.ticker.nunique()
    coverage = df.groupby('quarter').ticker.nunique()
    quarters = sorted(coverage[coverage >= min_coverage * n_tickers].index)
    if not quarters:
        return []
    df = df[df.quarter.isin(quarters)]
    complete = df.groupby('ticker').quarter.nunique()
    common = complete[complete == len(quarters)].index
    base = df[df.ticker.isin(common)]
    eps = df.pivot(index='ticker', columns='quarter', values='eps')
    out = []
    for i, q in enumerate(quarters):
        rows = base[base.quarter == q]
        entry = {
            'period_end': q.end_time.strftime('%Y-%m-%d'),
            'quarter': str(q),
            'companies': int(len(rows)),
            'revenue': _clean(rows.revenue.sum(min_count=1)),
            'gross_profit': _clean(rows.gross_profit.sum(min_count=1)),
            'net_income': _clean(rows.net_income.sum(min_count=1)),
            'eps_up_pct': None,
        }
        if i > 0:
            both = eps[[quarters[i - 1], q]].dropna()
            if len(both):
                entry['eps_up_pct'] = round(float((both[q] > both[quarters[i - 1]]).mean() * 100), 1)
        out.append(entry)
    return out
