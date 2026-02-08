import sys
import os
# Add the project root directory to the Python path
sys.path.insert(0, os.getcwd())

from backend.database import engine
from sqlalchemy import text

def add_thumbnail_column():
    try:
        with engine.connect() as conn:
            # Check if column exists strictly if possible, but simple approach is catch error
            # Or just run it. Using 'IF NOT EXISTS' if supported by PostgreSQL (it is)
            conn.execute(text("ALTER TABLE telegraminfo ADD COLUMN IF NOT EXISTS thumbnail_file_id VARCHAR"))
            conn.commit()
            print("Column thumbnail_file_id added successfully (or already exists).")
    except Exception as e:
        print(f"Error updating schema: {e}")

if __name__ == "__main__":
    add_thumbnail_column()
