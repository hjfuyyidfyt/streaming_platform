from sqlmodel import create_engine, Session
from .models import * # Import models to register them with SQLModel
import os
import logging
import time

logger = logging.getLogger(__name__)

# DATABASE_URL is loaded by main.py from .env

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgresql"):
    # Using PostgreSQL (Neon serverless)
    # Use QueuePool to REUSE connections — NullPool was creating a new TCP connection
    # per request, each potentially hitting Neon's 15-30s cold-start.
    from sqlalchemy.pool import QueuePool
    
    logger.info(f"Using PostgreSQL: {DATABASE_URL[:50]}...")
    engine = create_engine(
        DATABASE_URL, 
        echo=False,
        poolclass=QueuePool,
        pool_size=3,          # Keep 3 connections alive
        max_overflow=5,       # Allow up to 8 total during bursts
        pool_timeout=35,      # Wait up to 35s for a connection from pool
        pool_recycle=270,     # Recycle connections every 4.5 min (Neon idles at ~5 min)
        pool_pre_ping=True,   # Verify connection is alive before using it
        connect_args={
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
            "connect_timeout": 30,  # 30s for Neon cold-start (free tier can take 15-25s)
        }
    )
else:
    # Fallback to SQLite
    logger.info("Using SQLite (Local)")
    sqlite_file_name = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.db")
    sqlite_url = f"sqlite:///{sqlite_file_name}"
    engine = create_engine(sqlite_url, echo=False)

def get_session():
    """Yield a database session with retry logic for Neon cold-start."""
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            with Session(engine) as session:
                yield session
                return
        except Exception as e:
            if attempt < max_retries and ("timeout" in str(e).lower() or "closed" in str(e).lower()):
                logger.warning(f"DB connection attempt {attempt+1} failed ({e}), retrying in 1s...")
                time.sleep(1)  # sync sleep OK here — this is a sync generator
            else:
                raise

