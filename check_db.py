from sqlmodel import Session, select, func
from backend.database import engine
from backend.models import Video

def check_videos():
    with Session(engine) as session:
        count = session.exec(select(func.count(Video.id))).one()
        print(f"Total Videos in DB: {count}")
        
        videos = session.exec(select(Video).limit(5)).all()
        for v in videos:
            print(f"ID: {v.id}, Title: {v.title}, Storage: {v.storage_mode}")

if __name__ == "__main__":
    check_videos()
