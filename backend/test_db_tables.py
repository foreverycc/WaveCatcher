import sys
import os
from sqlalchemy import inspect

# Add parent directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.database import engine

inspector = inspect(engine)
tables = inspector.get_table_names()
print(f"Tables found: {tables}")
