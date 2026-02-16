import sqlite3
import os

DB_PATH = "backend/database.db"

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        print("Adding 'is_short' column to 'video' table...")
        cursor.execute("ALTER TABLE video ADD COLUMN is_short BOOLEAN DEFAULT 0")
        conn.commit()
        print("Migration successful: 'is_short' column added.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("Migration skipped: 'is_short' column already exists.")
        else:
            print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
