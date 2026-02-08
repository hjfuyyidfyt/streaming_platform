from sqlmodel import SQLModel
from .database import engine, sqlite_file_name
from .models import Category

def init_db():
    print(f"Creating database tables in {sqlite_file_name}...")
    SQLModel.metadata.create_all(engine)
    print("Database tables created.")

if __name__ == "__main__":
    init_db()
