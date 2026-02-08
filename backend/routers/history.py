"""
Watch History Router - Track user watch progress and history.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from ..database import get_session
from ..models import WatchHistory, Video, User
from .auth import get_current_user, require_user

router = APIRouter(
    prefix="/history",
    tags=["history"]
)


class ProgressUpdate(BaseModel):
    video_id: int
    progress_seconds: int
    completed: bool = False


@router.post("/")
async def update_watch_progress(
    data: ProgressUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_user)
):
    """Update watch progress for a video."""
    video = session.get(Video, data.video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Find existing history entry
    existing = session.exec(
        select(WatchHistory)
        .where(WatchHistory.video_id == data.video_id)
        .where(WatchHistory.user_id == current_user.id)
    ).first()
    
    if existing:
        # Update existing
        existing.progress_seconds = data.progress_seconds
        existing.watched_at = datetime.utcnow()
        if data.completed:
            existing.completed = True
        existing.duration_watched += 10  # Approximate
        session.add(existing)
    else:
        # Create new
        history = WatchHistory(
            video_id=data.video_id,
            user_id=current_user.id,
            progress_seconds=data.progress_seconds,
            completed=data.completed,
            duration_watched=data.progress_seconds
        )
        session.add(history)
    
    session.commit()
    return {"status": "saved", "progress_seconds": data.progress_seconds}


@router.get("/")
async def get_watch_history(
    limit: int = 50,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_user)
):
    """Get user's watch history."""
    history = session.exec(
        select(WatchHistory)
        .where(WatchHistory.user_id == current_user.id)
        .order_by(WatchHistory.watched_at.desc())
        .limit(limit)
    ).all()
    
    result = []
    for entry in history:
        video = session.get(Video, entry.video_id)
        if video:
            result.append({
                "id": entry.id,
                "video_id": video.id,
                "title": video.title,
                "thumbnail_url": video.thumbnail_url,
                "duration": video.duration,
                "progress_seconds": entry.progress_seconds,
                "completed": entry.completed,
                "watched_at": entry.watched_at.isoformat()
            })
    
    return {"history": result}


@router.get("/continue")
async def get_continue_watching(
    limit: int = 10,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_user)
):
    """Get videos to continue watching (not completed)."""
    history = session.exec(
        select(WatchHistory)
        .where(WatchHistory.user_id == current_user.id)
        .where(WatchHistory.completed == False)
        .where(WatchHistory.progress_seconds > 30)  # At least 30s watched
        .order_by(WatchHistory.watched_at.desc())
        .limit(limit)
    ).all()
    
    result = []
    for entry in history:
        video = session.get(Video, entry.video_id)
        if video:
            result.append({
                "video_id": video.id,
                "title": video.title,
                "thumbnail_url": video.thumbnail_url,
                "duration": video.duration,
                "progress_seconds": entry.progress_seconds,
                "progress_percent": round((entry.progress_seconds / video.duration * 100) if video.duration else 0, 1)
            })
    
    return {"continue_watching": result}


@router.get("/video/{video_id}")
async def get_video_progress(
    video_id: int,
    session: Session = Depends(get_session),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Get progress for a specific video."""
    if not current_user:
        return {"progress_seconds": 0, "completed": False}
    
    entry = session.exec(
        select(WatchHistory)
        .where(WatchHistory.video_id == video_id)
        .where(WatchHistory.user_id == current_user.id)
    ).first()
    
    if entry:
        return {
            "progress_seconds": entry.progress_seconds,
            "completed": entry.completed
        }
    
    return {"progress_seconds": 0, "completed": False}


@router.delete("/{history_id}")
async def delete_history_entry(
    history_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_user)
):
    """Remove a video from watch history."""
    entry = session.get(WatchHistory, history_id)
    if not entry:
        raise HTTPException(status_code=404, detail="History entry not found")
    
    if entry.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    session.delete(entry)
    session.commit()
    return {"message": "Removed from history"}


@router.delete("/")
async def clear_history(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_user)
):
    """Clear all watch history."""
    entries = session.exec(
        select(WatchHistory).where(WatchHistory.user_id == current_user.id)
    ).all()
    
    for entry in entries:
        session.delete(entry)
    
    session.commit()
    return {"message": f"Cleared {len(entries)} entries"}
