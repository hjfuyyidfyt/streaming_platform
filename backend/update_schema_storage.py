from sqlmodel import Session, create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

def update_schema():
    with Session(engine) as session:
        print("Adding storage_mode column...")
        try:
            session.exec(text("ALTER TABLE video ADD COLUMN storage_mode VARCHAR DEFAULT 'local'"))
            session.commit()
            print("Added storage_mode.")
        except Exception as e:
            print(f"storage_mode might exist: {e}")
            session.rollback()

        print("Adding external_id column...")
        try:
            session.exec(text("ALTER TABLE video ADD COLUMN external_id VARCHAR"))
            session.commit()
            print("Added external_id.")
        except Exception as e:
            print(f"external_id might exist: {e}")
            session.rollback()

        print("Adding embed_url column...")
        try:
            session.exec(text("ALTER TABLE video ADD COLUMN embed_url VARCHAR"))
            session.commit()
            print("Added embed_url.")
        except Exception as e:
            print(f"embed_url might exist: {e}")
            session.rollback()

if __name__ == "__main__":
    update_schema()
