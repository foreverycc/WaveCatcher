from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import AnalysisRun, AnalysisResult
from app.api.endpoints.analysis import _latest_run_for_stock_list


def test_latest_run_per_stock_list_survives_other_runs():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    t0 = datetime(2026, 10, 24, 12)

    def run(i, name, keys, minutes, status="completed"):
        r = AnalysisRun(id=i, stock_list_name=name, status=status, timestamp=t0 + timedelta(minutes=minutes))
        db.add(r)
        for k in keys:
            db.add(AnalysisResult(run_id=i, ticker=k, interval="ALL", result_type="cd_company_breadth", data=[]))

    run(1, "multi_index", ["stocks_spx.tab"], 0)                          # SPX
    run(2, "multi_index", ["stocks_dji.tab", "stocks_soxx.tab"], 10)      # DJI + SOXX afterwards
    run(3, "stocks_dji.tab", ["ALL"], 20, status="failed")                # failed runs are ignored
    db.commit()

    assert _latest_run_for_stock_list(db, "stocks_spx.tab") == (1, "stocks_spx.tab")
    assert _latest_run_for_stock_list(db, "stocks_dji.tab") == (2, "stocks_dji.tab")
    assert _latest_run_for_stock_list(db, "stocks_qqq.tab") == (None, None)

    run(4, "stocks_spx.tab", ["ALL"], 30)                                 # single-list run of SPX
    db.commit()
    assert _latest_run_for_stock_list(db, "stocks_spx.tab") == (4, "ALL")
