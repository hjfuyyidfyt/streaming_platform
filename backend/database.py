from sqlmodel import create_engine, Session
from .models import * # Import models to register them with SQLModel
import os
from dotenv import load_dotenv

# Load environment variables from .env file in the same directory
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(env_path)

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgresql"):
    # Using PostgreSQL (Neon)
    print(f"Using PostgreSQL: {DATABASE_URL[:50]}...")
    # Robust connection settings for cloud DB
    engine = create_engine(
        DATABASE_URL, 
        echo=False,
        pool_pre_ping=True,
        pool_recycle=300, # Recycle connections every 5 minutes
        connect_args={
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5
        }
    )
else:
    # Fallback to SQLite (Forcing SQLite for now due to connection issues)
    print("Using SQLite (Local)")
    sqlite_file_name = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.db")
    sqlite_url = f"sqlite:///{sqlite_file_name}"
    engine = create_engine(sqlite_url, echo=True)

def get_session():
    with Session(engine) as session:
        yield session
