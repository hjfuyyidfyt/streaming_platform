import sys
import os
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load the exact same .env file main.py does
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend', '.env')
load_dotenv(dotenv_path=env_path, override=True)

from sqlalchemy import text
from backend.database import engine

def apply_migration():
    print(f"Starting DB migration for missing columns on engine: {engine.url}")
    
    with engine.begin() as conn:
        try:
            print("Adding direct_url column to video table...")
            conn.execute(text("ALTER TABLE video ADD COLUMN direct_url VARCHAR;"))
            print("Added direct_url successfully.")
        except Exception as e:
            print(f"Error adding direct_url (may already exist): {e}")
                
        try:
            print("Adding embed_code column to video table...")
            conn.execute(text("ALTER TABLE video ADD COLUMN embed_code VARCHAR;"))
            print("Added embed_code successfully.")
        except Exception as e:
            print(f"Error adding embed_code (may already exist): {e}")
                
    print("Migration finished!")

if __name__ == "__main__":
    apply_migration()
