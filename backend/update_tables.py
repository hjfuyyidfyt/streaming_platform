from sqlmodel import SQLModel
from backend.database import engine
from backend.models import *

def update_db():
    print("Updating database tables...")
    SQLModel.metadata.create_all(engine)
    print("Database tables updated.")

if __name__ == "__main__":
    update_db()
