import sys
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Add logic directory to sys.path to ensure legacy imports work
logic_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "logic"))
sys.path.append(logic_path)

# Add parent directory to sys.path to allow imports from app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api.endpoints import analysis, stocks
from app.db.database import engine, Base
from app.db import models

# Create database tables
Base.metadata.create_all(bind=engine)

import logging
from logging.handlers import RotatingFileHandler

# Setup logging
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_file = 'backend_server.log'
file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
file_handler.setFormatter(log_formatter)
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
logger = logging.getLogger(__name__)

# Reduce yfinance logging verbosity
logging.getLogger('yfinance').setLevel(logging.WARNING)

app = FastAPI(
    title="Stock Signal Dashboard API",
    description="API for Stock Signal Analysis Dashboard",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(stocks.router, prefix="/api/stocks", tags=["stocks"])

@app.get("/")
async def root():
    return {"message": "Stock Signal Dashboard API is running"}

if __name__ == "__main__":
    import uvicorn
    # default port 8000
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
