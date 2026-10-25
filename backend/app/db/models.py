from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, JSON, BigInteger, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    stock_list_name = Column(String, index=True)
    status = Column(String, default="pending")  # pending, completed, failed
    
    results = relationship("AnalysisResult", back_populates="run", cascade="all, delete-orphan")

class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("analysis_runs.id"), index=True)
    ticker = Column(String, index=True)
    interval = Column(String, index=True)
    result_type = Column(String, index=True) # e.g., 'cd_eval_detailed', 'best_intervals_50', 'breakout_1234'
    
    # Store dynamic metrics (test_count_0..100, etc.) in a JSON column
    # This avoids creating a table with 300+ columns
    data = Column(JSON)
    
    run = relationship("AnalysisRun", back_populates="results")

class SavedReport(Base):
    __tablename__ = "saved_reports"

    id = Column(String, primary_key=True)
    run_id = Column(Integer, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="generating")
    path = Column(Text, nullable=True)
    error = Column(Text, nullable=True)


class PriceBar(Base):
    __tablename__ = "price_history"

    ticker = Column(String, primary_key=True, index=True)
    interval = Column(String, primary_key=True, index=True)
    timestamp = Column(DateTime, primary_key=True, index=True) # Naive market time preferably
    
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(BigInteger)
    
    # Optional: Store computed signals if we want to cache them persistently?
    # For now, keep signals computed on-the-fly or in cache, 
    # but storing raw OHLCV here is the main goal.

class OptionChain(Base):
    __tablename__ = "option_chains"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, index=True)
    expiration = Column(String, index=True) # YYYY-MM-DD
    scrape_date = Column(DateTime, default=datetime.utcnow, index=True)
    
    data = Column(JSON) # List of {strike, calls, puts}
    current_price = Column(Float)
    max_pain = Column(Float, nullable=True)


class QuarterlyFinancial(Base):
    """Quarterly income statement figures per ticker (from yfinance quarterly_income_stmt)."""
    __tablename__ = "quarterly_financials"

    ticker = Column(String, primary_key=True, index=True)
    period_end = Column(Date, primary_key=True)  # fiscal quarter end date
    revenue = Column(Float, nullable=True)
    gross_profit = Column(Float, nullable=True)
    net_income = Column(Float, nullable=True)
    eps = Column(Float, nullable=True)  # diluted EPS
    fetched_at = Column(DateTime, default=datetime.utcnow)


class QuarterlyCashFlow(Base):
    """Quarterly cash flow figures per ticker (from yfinance quarterly_cashflow).
    A row dated CASHFLOW_NONE_DATE marks a ticker without a cash flow statement, so it is not
    refetched before the next refresh."""
    __tablename__ = "quarterly_cashflow"

    ticker = Column(String, primary_key=True, index=True)
    period_end = Column(Date, primary_key=True)  # fiscal quarter end date
    operating_cash_flow = Column(Float, nullable=True)
    free_cash_flow = Column(Float, nullable=True)  # operating cash flow - capital expenditure
    capital_expenditure = Column(Float, nullable=True)  # negative = cash spent
    fetched_at = Column(DateTime, default=datetime.utcnow)
