"""Offline tests for the quarterly fundamentals store and the stock-list aggregate."""
import os
import sys

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, BACKEND)

from app.db.database import Base  # noqa: E402
from app.logic import fundamentals as F  # noqa: E402


def statement(ends, revenue, eps):
    cols = [pd.Timestamp(e) for e in ends]
    return pd.DataFrame({c: {'Total Revenue': r, 'Gross Profit': r / 2, 'Net Income': r / 10, 'Diluted EPS': e}
                         for c, r, e in zip(cols, revenue, eps)})


@pytest.fixture
def store(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/t.db")
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(F, 'SessionLocal', sessionmaker(bind=engine))
    statements = {
        'AAA': statement(['2026-06-30', '2026-03-31', '2025-12-31'], [300, 200, 100], [3, 2, 1]),
        'BBB': statement(['2026-06-27', '2026-03-28', '2025-12-27'], [30, 20, 10], [1, 2, 3]),  # fiscal quarter ends
        'CCC': statement(['2026-06-30'], [1000], [5]),  # only one quarter: left out of the totals
    }
    calls = []

    class FakeTicker:
        def __init__(self, t):
            calls.append(t)
            self.quarterly_income_stmt = statements.get(t, pd.DataFrame())

    monkeypatch.setattr(F.yf, 'Ticker', FakeTicker, raising=False)
    return calls


def test_refresh_and_aggregate(store):
    for t in ['AAA', 'BBB', 'CCC', '^SPX']:
        F.refresh_quarterly(t)
    assert '^SPX' not in store
    F.refresh_quarterly('AAA')  # fresh: not fetched again
    assert store.count('AAA') == 1

    rows = F.ticker_quarterly('AAA')
    assert [r['period_end'] for r in rows] == ['2025-12-31', '2026-03-31', '2026-06-30']
    assert rows[-1]['revenue'] == 300 and rows[-1]['eps'] == 3

    agg = F.aggregate_quarterly(['AAA', 'BBB', 'CCC'], min_coverage=0.6)
    assert [a['quarter'] for a in agg] == ['2025Q4', '2026Q1', '2026Q2']
    assert [a['revenue'] for a in agg] == [110, 220, 330]  # AAA + BBB; CCC lacks earlier quarters
    assert agg[0]['eps_up_pct'] is None
    assert agg[2]['eps_up_pct'] == 50.0  # AAA up, BBB down (CCC has no previous quarter)
    assert agg[2]['companies'] == 2
