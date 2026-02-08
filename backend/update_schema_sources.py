from sqlmodel import SQLModel
from backend.database import engine
from backend.models import VideoSource

print("Creating tables...")
SQLModel.metadata.create_all(engine)
print("Tables created.")
