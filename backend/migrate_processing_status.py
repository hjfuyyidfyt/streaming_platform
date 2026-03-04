import os
import logging
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migration")

def migrate():
    # Load environment variables FIRST
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path, override=True)
        logger.info(f"Loaded .env from {env_path}")
    else:
        logger.warning(f".env not found at {env_path}")

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not found in environment!")
        return

    logger.info(f"Target Database: {database_url[:30]}...")
    
    # Create a fresh engine to avoid any cached configuration
    engine = create_engine(database_url)
    
    with engine.connect() as conn:
        try:
            # 1. Add processing_status
            logger.info("Attempting to add 'processing_status'...")
            try:
                conn.execute(text("ALTER TABLE video ADD COLUMN processing_status VARCHAR DEFAULT 'pending';"))
                conn.commit()
                logger.info("Column 'processing_status' added successfully.")
            except Exception as e:
                # Handle "already exists" error gracefully
                if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                    logger.info("Column 'processing_status' already exists.")
                    conn.rollback()
                else:
                    logger.error(f"Failed to add 'processing_status': {e}")
                    conn.rollback()

            # 2. Update existing entries to 'completed'
            try:
                conn.execute(text("UPDATE video SET processing_status = 'completed' WHERE processing_status IS NULL OR processing_status = 'pending';"))
                conn.commit()
                logger.info("Updated existing videos to 'completed'.")
            except Exception as e:
                logger.error(f"Failed to update existing videos: {e}")
                conn.rollback()

            # 3. Add temp_file_path
            logger.info("Attempting to add 'temp_file_path'...")
            try:
                conn.execute(text("ALTER TABLE video ADD COLUMN temp_file_path VARCHAR;"))
                conn.commit()
                logger.info("Column 'temp_file_path' added successfully.")
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                    logger.info("Column 'temp_file_path' already exists.")
                    conn.rollback()
                else:
                    logger.error(f"Failed to add 'temp_file_path': {e}")
                    conn.rollback()

            logger.info("Migration process finished.")
        except Exception as e:
            logger.error(f"Critical Migration error: {e}")
            conn.rollback()

if __name__ == "__main__":
    migrate()
