import os
from fastapi import APIRouter, HTTPException, Body, Depends
from pydantic import BaseModel
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import distinct

from app.db.database import SessionLocal
from app.db.models import PriceBar
from app.services.stock_weights import load_weights, save_weights, fetch_market_caps

router = APIRouter()

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class StockListCreate(BaseModel):
    name: str
    content: str
    extension: str = ".tab"

class StockListUpdate(BaseModel):
    content: str

class StockListResponse(BaseModel):
    filename: str
    count: int
    preview: List[str]
    content: Optional[str] = None

@router.get("/", response_model=List[str])
async def list_stock_files():
    """List all available stock list files."""
    if not os.path.exists(DATA_DIR):
        return []
    return [f for f in os.listdir(DATA_DIR) if f.endswith('.tab') or f.endswith('.txt')]

@router.get("/{filename}", response_model=StockListResponse)
async def get_stock_list(filename: str):
    """Get content of a specific stock list file."""
    file_path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        with open(file_path, 'r') as f:
            content = f.read().strip()
            
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        return {
            "filename": filename,
            "count": len(lines),
            "preview": lines[:5],
            "content": content # We might want to return full content for editing
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{filename}/content")
async def get_stock_list_content(filename: str):
    """Get full raw content of a stock list file."""
    file_path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        with open(file_path, 'r') as f:
            return {"content": f.read()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class StockWeightsUpdate(BaseModel):
    weights: Dict[str, float]


def _list_tickers(filename):
    file_path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    with open(file_path) as f:
        return list(dict.fromkeys(line.strip().upper() for line in f if line.strip()))


@router.get("/{filename}/weights")
async def get_stock_weights(filename: str):
    """Per-ticker weights of a stock list (empty when none are set)."""
    _list_tickers(filename)
    return {"weights": load_weights(filename)}


@router.put("/{filename}/weights")
async def update_stock_weights(filename: str, update: StockWeightsUpdate):
    _list_tickers(filename)
    return {"weights": save_weights(filename, update.weights)}


@router.post("/{filename}/weights/market_cap")
def fill_weights_from_market_cap(filename: str):
    """Set every ticker's weight to its current market cap from yfinance."""
    tickers = _list_tickers(filename)
    caps, missing = fetch_market_caps(tickers)
    return {"weights": save_weights(filename, caps), "missing": missing}


@router.post("/")
async def create_stock_list(stock_list: StockListCreate):
    """Create a new stock list file."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        
    filename = f"{stock_list.name}{stock_list.extension}"
    file_path = os.path.join(DATA_DIR, filename)
    
    if os.path.exists(file_path):
        raise HTTPException(status_code=400, detail="File already exists")
    
    try:
        with open(file_path, 'w') as f:
            f.write(stock_list.content.strip())
        return {"message": "File created successfully", "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{filename}")
async def update_stock_list(filename: str, update: StockListUpdate):
    """Update an existing stock list file."""
    file_path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        with open(file_path, 'w') as f:
            f.write(update.content.strip())
        return {"message": "File updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{filename}")
async def delete_stock_list(filename: str):
    """Delete a stock list file."""
    file_path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        os.remove(file_path)
        return {"message": "File deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ValidateTickersRequest(BaseModel):
    tickers: List[str]


@router.post("/validate")
async def validate_tickers(request: ValidateTickersRequest, db: Session = Depends(get_db)):
    """Validate tickers by checking if they have price data in the database."""
    if not request.tickers:
        return {"bad_tickers": [], "good_tickers": []}

    # Get all tickers that have at least one row in the price_history table
    existing_tickers = set(
        row[0] for row in db.query(distinct(PriceBar.ticker))
        .filter(PriceBar.ticker.in_(request.tickers))
        .all()
    )

    good_tickers = [t for t in request.tickers if t in existing_tickers]
    bad_tickers = [t for t in request.tickers if t not in existing_tickers]

    return {"bad_tickers": bad_tickers, "good_tickers": good_tickers}
