from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from sqlalchemy.orm import joinedload
from typing import List, Optional
from ..database import get_session
from ..models import Video, Category, VideoPublic, CategoryPublic, ViewHistory
from fastapi import Request

router = APIRouter(
    prefix="/videos",
    tags=["videos"]
)

@router.get("/", response_model=List[VideoPublic])
async def read_videos(
    skip: int = 0, 
    limit: int = 20, 
    session: Session = Depends(get_session)
):
    videos = session.exec(
        select(Video)
        .options(joinedload(Video.category), joinedload(Video.uploader))
        .offset(skip).limit(limit)
    ).all()
    return videos

@router.get("/search", response_model=List[VideoPublic])
async def search_videos(
    q: str,
    skip: int = 0,
    limit: int = 20,
    session: Session = Depends(get_session)
):
    statement = select(Video).where(
        (Video.title.contains(q)) | (Video.description.contains(q))
    ).options(joinedload(Video.category), joinedload(Video.uploader)).offset(skip).limit(limit)
    videos = session.exec(statement).all()
    return videos

@router.get("/shorts", response_model=List[VideoPublic])
async def read_shorts(
    skip: int = 0,
    limit: int = 20,
    session: Session = Depends(get_session)
):
    videos = session.exec(
        select(Video)
        .where(Video.is_short == True)
        .options(joinedload(Video.category), joinedload(Video.uploader))
        .offset(skip).limit(limit)
    ).all()
    return videos

@router.get("/categories/all", response_model=List[CategoryPublic])
async def read_categories(session: Session = Depends(get_session)):
    categories = session.exec(select(Category)).all()
    return categories

@router.get("/category/{slug}", response_model=List[VideoPublic])
async def read_videos_by_category(
    slug: str,
    skip: int = 0,
    limit: int = 20,
    session: Session = Depends(get_session)
):
    # First find category by slug
    category = session.exec(select(Category).where(Category.slug == slug)).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    videos = session.exec(
        select(Video)
        .where(Video.category_id == category.id)
        .options(joinedload(Video.category), joinedload(Video.uploader))
        .offset(skip).limit(limit)
    ).all()
    return videos

@router.get("/{video_id}", response_model=VideoPublic)
async def read_video(video_id: int, session: Session = Depends(get_session)):
    video = session.exec(
        select(Video).where(Video.id == video_id).options(joinedload(Video.category), joinedload(Video.uploader), joinedload(Video.sources))
    ).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video

@router.post("/{video_id}/view")
async def increment_view(
    video_id: int, 
    request: Request,
    session: Session = Depends(get_session)
):
    video = session.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Increment counter
    video.views += 1
    session.add(video)
    
    # Log history
    history = ViewHistory(
        video_id=video_id,
        ip_address=request.client.host,
        user_agent=request.headers.get("user-agent")
    )
    session.add(history)
    
    session.commit()
    return {"status": "success", "views": video.views}
