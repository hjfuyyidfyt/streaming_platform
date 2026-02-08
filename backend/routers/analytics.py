from fastapi import APIRouter, Depends
from sqlmodel import Session, select, func
from ..database import get_session
from ..models import Video, ViewHistory, Category

router = APIRouter(
    prefix="/analytics",
    tags=["analytics"]
)

@router.get("/summary")
async def get_summary(session: Session = Depends(get_session)):
    total_videos = session.exec(select(func.count(Video.id))).one()
    total_views = session.exec(select(func.sum(Video.views))).one() or 0
    total_categories = session.exec(select(func.count(Category.id))).one()
    
    # Simple recent views count (e.g. last 24h) - skipping time filter for MVP simplicity
    # just counting all history rows
    total_history_entries = session.exec(select(func.count(ViewHistory.id))).one()

    return {
        "total_videos": total_videos,
        "total_views": total_views,
        "total_categories": total_categories,
        "total_view_events": total_history_entries
    }

@router.get("/popular")
async def get_popular_videos(session: Session = Depends(get_session)):
    videos = session.exec(select(Video).order_by(Video.views.desc()).limit(5)).all()
    return videos
