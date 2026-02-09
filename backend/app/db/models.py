from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, BigInteger, Text
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

