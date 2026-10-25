"""
Quarterly fundamentals
======================
Revenue, gross profit, net income and EPS per fiscal quarter from yfinance's quarterly income
statement, and operating / free cash flow from its quarterly cash flow statement (usually the last
4-6 quarters), stored in the quarterly_financials and quarterly_cashflow tables and refreshed at
most every REFRESH_DAYS per ticker. Index aggregates sum the figures of a stock list per
calendar quarter.
"""
import logging
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

from app.db.database import SessionLocal, engine
from app.logic.data_loader import call_with_rate_limit_retry
from app.db.models import QuarterlyFinancial, QuarterlyCashFlow

logger = logging.getLogger(__name__)

REFRESH_DAYS = 7

ROWS = {
    'revenue': ['Total Revenue', 'Operating Revenue'],
    'gross_profit': ['Gross Profit'],
    'net_income': ['Net Income', 'Net Income Common Stockholders'],
    'eps': ['Diluted EPS', 'Basic EPS'],
}


CASHFLOW_NONE_DATE = date(1900, 1, 1)  # marker row: no cash flow statement available
# cash flow fetched before this lacks capital expenditure: refetch it once
CAPEX_ADDED = datetime(2026, 10, 25, 15, 0)


def _ensure_capex_column():
    """Add capital_expenditure to a quarterly_cashflow table created before it existed."""
    try:
        with engine.begin() as conn:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(quarterly_cashflow)")]
            if cols and 'capital_expenditure' not in cols:
                conn.exec_driver_sql("ALTER TABLE quarterly_cashflow ADD COLUMN capital_expenditure FLOAT")
    except Exception as e:
        logger.warning(f"Could not add capital_expenditure column: {e}")


_ensure_capex_column()


def _has_statements(ticker):
    return not (ticker.startswith('^') or ticker.endswith('-USD'))


def fetch_quarterly(ticker):
    """{period_end: {revenue, gross_profit, net_income, eps}} from yfinance (empty when unavailable)."""
    stmt = call_with_rate_limit_retry(lambda: yf.Ticker(ticker).quarterly_income_stmt, label=f'{ticker} financials')
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


def _stmt_value(stmt, names, col):
    for name in names:
        if name in stmt.index and pd.notna(stmt.at[name, col]):
            return float(stmt.at[name, col])
    return None


def fetch_cashflow(ticker):
    """{period_end: {operating_cash_flow, free_cash_flow, capital_expenditure}} from yfinance (empty when unavailable).
    Free cash flow = operating cash flow - capital expenditure (yfinance's row, or computed)."""
    stmt = call_with_rate_limit_retry(lambda: yf.Ticker(ticker).quarterly_cashflow, label=f'{ticker} cash flow')
    if stmt is None or stmt.empty:
        return {}
    out = {}
    for col in stmt.columns:
        ocf = _stmt_value(stmt, ['Operating Cash Flow', 'Cash Flow From Continuing Operating Activities'], col)
        fcf = _stmt_value(stmt, ['Free Cash Flow'], col)
        capex = _stmt_value(stmt, ['Capital Expenditure'], col)
        if fcf is None and ocf is not None and capex is not None:
            fcf = ocf + capex  # capex is reported as a negative number
        if ocf is not None or fcf is not None:
            if capex is None and ocf is not None and fcf is not None:
                capex = fcf - ocf
            out[pd.Timestamp(col).date()] = {'operating_cash_flow': ocf, 'free_cash_flow': fcf,
                                             'capital_expenditure': capex}
    return out


def refresh_cashflow(ticker, max_age_days=REFRESH_DAYS):
    """Fetch and store a ticker's quarterly cash flow unless fetched within max_age_days."""
    if not _has_statements(ticker):
        return
    db = SessionLocal()
    try:
        last = (db.query(QuarterlyCashFlow.fetched_at)
                .filter(QuarterlyCashFlow.ticker == ticker)
                .order_by(QuarterlyCashFlow.fetched_at.desc()).first())
        if last and last[0] and last[0] >= CAPEX_ADDED and datetime.utcnow() - last[0] < timedelta(days=max_age_days):
            return
        rows = fetch_cashflow(ticker)
        now = datetime.utcnow()
        if not rows:
            rows = {CASHFLOW_NONE_DATE: {'operating_cash_flow': None, 'free_cash_flow': None, 'capital_expenditure': None}}
        for period_end, values in rows.items():
            db.merge(QuarterlyCashFlow(ticker=ticker, period_end=period_end, fetched_at=now, **values))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"{ticker}: quarterly cash flow not updated: {e}")
    finally:
        db.close()


def refresh_quarterly(ticker, max_age_days=REFRESH_DAYS):
    """Refresh both the income statement and the cash flow figures of a ticker."""
    refresh_income(ticker, max_age_days)
    refresh_cashflow(ticker, max_age_days)


def refresh_income(ticker, max_age_days=REFRESH_DAYS):
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
    """DataFrame of stored quarterly rows for the tickers (income statement plus cash flow)."""
    db = SessionLocal()
    try:
        rows = db.query(QuarterlyFinancial).filter(QuarterlyFinancial.ticker.in_(list(tickers))).all()
        cf_rows = db.query(QuarterlyCashFlow).filter(
            QuarterlyCashFlow.ticker.in_(list(tickers)), QuarterlyCashFlow.period_end > CASHFLOW_NONE_DATE).all()
    finally:
        db.close()
    df = pd.DataFrame([{
        'ticker': r.ticker, 'period_end': pd.Timestamp(r.period_end), 'revenue': r.revenue,
        'gross_profit': r.gross_profit, 'net_income': r.net_income, 'eps': r.eps,
    } for r in rows])
    cf = pd.DataFrame([{
        'ticker': r.ticker, 'period_end': pd.Timestamp(r.period_end),
        'operating_cash_flow': r.operating_cash_flow, 'free_cash_flow': r.free_cash_flow,
        'capital_expenditure': r.capital_expenditure,
    } for r in cf_rows], columns=['ticker', 'period_end', 'operating_cash_flow', 'free_cash_flow', 'capital_expenditure'])
    if df.empty:
        return df
    return df.merge(cf, on=['ticker', 'period_end'], how='left')


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
        'operating_cash_flow': _clean(row.operating_cash_flow), 'free_cash_flow': _clean(row.free_cash_flow),
        'capital_expenditure': _clean(row.capital_expenditure),
    } for row in df.itertuples()]


def aggregate_quarterly(tickers, min_coverage=0.8):
    """
    Stock-list totals per calendar quarter (fiscal quarters mapped to the calendar quarter they end in).
    Totals use the same companies in every quarter shown (those reporting all of them), so the series
    is not distorted by companies dropping in and out. eps_up_pct is the share of companies whose EPS
    rose from their previous quarter. Cash flow: totals over the same companies that report it,
    fcf_margin = their free cash flow / their revenue (%), fcf_conversion = their free cash flow /
    their net income (%, only when that net income is positive), fcf_positive_pct = share of
    companies reporting free cash flow that quarter whose free cash flow is positive.
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
            'operating_cash_flow': None, 'free_cash_flow': None, 'capital_expenditure': None,
            'fcf_margin': None, 'fcf_conversion': None, 'fcf_positive_pct': None,
        }
        with_fcf = rows[rows.free_cash_flow.notna()]
        if len(with_fcf):
            entry['operating_cash_flow'] = _clean(with_fcf.operating_cash_flow.sum(min_count=1))
            entry['free_cash_flow'] = _clean(with_fcf.free_cash_flow.sum())
            entry['capital_expenditure'] = _clean(with_fcf.capital_expenditure.sum(min_count=1))
            rev = with_fcf.revenue.sum(min_count=1)
            if pd.notna(rev) and rev > 0:
                entry['fcf_margin'] = round(float(with_fcf.free_cash_flow.sum() / rev * 100), 1)
            ni = with_fcf[with_fcf.net_income.notna()]
            ni_sum = ni.net_income.sum()
            if len(ni) and ni_sum > 0:
                entry['fcf_conversion'] = round(float(ni.free_cash_flow.sum() / ni_sum * 100), 1)
        all_fcf = df[(df.quarter == q) & df.free_cash_flow.notna()]
        if len(all_fcf):
            entry['fcf_positive_pct'] = round(float((all_fcf.free_cash_flow > 0).mean() * 100), 1)
        if i > 0:
            both = eps[[quarters[i - 1], q]].dropna()
            if len(both):
                entry['eps_up_pct'] = round(float((both[q] > both[quarters[i - 1]]).mean() * 100), 1)
        out.append(entry)
    return out
