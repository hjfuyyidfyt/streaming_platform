from backend.database import engine
from sqlmodel import text

with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE videosource ADD COLUMN resolution VARCHAR"))
        conn.commit()
        print("Column 'resolution' added.")
    except Exception as e:
        print(f"Error (maybe already exists): {e}")
