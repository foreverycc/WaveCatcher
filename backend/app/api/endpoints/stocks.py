import os
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data"))

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
