"""
Playlists Router - User playlists including Watch Later.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from ..database import get_session
from ..models import Playlist, PlaylistItem, Video, User
from .auth import get_current_user, require_user

router = APIRouter(
    prefix="/playlists",
    tags=["playlists"]
)


class PlaylistCreate(BaseModel):
    name: str
    description: Optional[str] = None
    is_public: bool = True


class PlaylistUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None


class AddVideoRequest(BaseModel):
    video_id: int


@router.get("/")
async def get_user_playlists(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_user)
):
    """Get all playlists of current user."""
    playlists = session.exec(
        select(Playlist)
        .where(Playlist.user_id == current_user.id)
        .order_by(Playlist.is_watch_later.desc())  # Watch Later first
        .order_by(Playlist.created_at.desc())
    ).all()
    
    result = []
    for pl in playlists:
        # Count videos
        count = len(session.exec(
            select(PlaylistItem).where(PlaylistItem.playlist_id == pl.id)
        ).all())
        
        result.append({
            "id": pl.id,
            "name": pl.name,
            "description": pl.description,
            "is_public": pl.is_public,
            "is_watch_later": pl.is_watch_later,
            "video_count": count,
            "created_at": pl.created_at.isoformat()
        })
    
    return {"playlists": result}


@router.post("/", status_code=201)
async def create_playlist(
    data: PlaylistCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_user)
):
    """Create a new playlist."""
    playlist = Playlist(
        user_id=current_user.id,
        name=data.name,
        description=data.description,
        is_public=data.is_public
    )
    session.add(playlist)
    session.commit()
    session.refresh(playlist)
    
    return {
        "id": playlist.id,
        "name": playlist.name,
        "description": playlist.description,
        "is_public": playlist.is_public,
        "video_count": 0
    }


@router.get("/{playlist_id}")
async def get_playlist(
    playlist_id: int,
    session: Session = Depends(get_session),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Get playlist details with videos."""
    playlist = session.get(Playlist, playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    # Check access
    if not playlist.is_public:
        if not current_user or current_user.id != playlist.user_id:
            raise HTTPException(status_code=403, detail="Playlist is private")
    
    # Get videos
    items = session.exec(
        select(PlaylistItem)
        .where(PlaylistItem.playlist_id == playlist_id)
        .order_by(PlaylistItem.position)
    ).all()
    
    videos = []
    for item in items:
        video = session.get(Video, item.video_id)
        if video:
            videos.append({
                "item_id": item.id,
                "position": item.position,
                "video_id": video.id,
                "title": video.title,
                "thumbnail_url": video.thumbnail_url,
                "duration": video.duration,
                "views": video.views,
                "added_at": item.added_at.isoformat()
            })
    
    return {
        "id": playlist.id,
        "name": playlist.name,
        "description": playlist.description,
        "is_public": playlist.is_public,
        "is_watch_later": playlist.is_watch_later,
        "videos": videos,
        "video_count": len(videos)
    }


@router.put("/{playlist_id}")
async def update_playlist(
    playlist_id: int,
    data: PlaylistUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_user)
):
    """Update playlist details."""
    playlist = session.get(Playlist, playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    if playlist.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if playlist.is_watch_later:
        raise HTTPException(status_code=400, detail="Cannot modify Watch Later playlist")
    
    if data.name is not None:
        playlist.name = data.name
    if data.description is not None:
        playlist.description = data.description
    if data.is_public is not None:
        playlist.is_public = data.is_public
    
    session.add(playlist)
    session.commit()
    session.refresh(playlist)
    
    return {"message": "Playlist updated", "id": playlist.id}


@router.delete("/{playlist_id}")
async def delete_playlist(
    playlist_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_user)
):
    """Delete a playlist."""
    playlist = session.get(Playlist, playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    if playlist.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if playlist.is_watch_later:
        raise HTTPException(status_code=400, detail="Cannot delete Watch Later playlist")
    
    # Delete items
    items = session.exec(
        select(PlaylistItem).where(PlaylistItem.playlist_id == playlist_id)
    ).all()
    for item in items:
        session.delete(item)
    
    session.delete(playlist)
    session.commit()
    
    return {"message": "Playlist deleted"}


@router.post("/{playlist_id}/add")
async def add_video_to_playlist(
    playlist_id: int,
    data: AddVideoRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_user)
):
    """Add a video to playlist."""
    playlist = session.get(Playlist, playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    if playlist.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    video = session.get(Video, data.video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Check if already in playlist
    existing = session.exec(
        select(PlaylistItem)
        .where(PlaylistItem.playlist_id == playlist_id)
        .where(PlaylistItem.video_id == data.video_id)
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Video already in playlist")
    
    # Get next position
    items = session.exec(
        select(PlaylistItem).where(PlaylistItem.playlist_id == playlist_id)
    ).all()
    next_pos = len(items)
    
    item = PlaylistItem(
        playlist_id=playlist_id,
        video_id=data.video_id,
        position=next_pos
    )
    session.add(item)
    session.commit()
    
    return {"message": "Video added to playlist", "position": next_pos}


@router.delete("/{playlist_id}/remove/{video_id}")
async def remove_video_from_playlist(
    playlist_id: int,
    video_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_user)
):
    """Remove a video from playlist."""
    playlist = session.get(Playlist, playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    if playlist.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    item = session.exec(
        select(PlaylistItem)
        .where(PlaylistItem.playlist_id == playlist_id)
        .where(PlaylistItem.video_id == video_id)
    ).first()
    
    if not item:
        raise HTTPException(status_code=404, detail="Video not in playlist")
    
    session.delete(item)
    session.commit()
    
    return {"message": "Video removed from playlist"}


@router.get("/watch-later/videos")
async def get_watch_later(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_user)
):
    """Get Watch Later playlist videos."""
    playlist = session.exec(
        select(Playlist)
        .where(Playlist.user_id == current_user.id)
        .where(Playlist.is_watch_later == True)
    ).first()
    
    if not playlist:
        return {"videos": [], "playlist_id": None}
    
    items = session.exec(
        select(PlaylistItem)
        .where(PlaylistItem.playlist_id == playlist.id)
        .order_by(PlaylistItem.added_at.desc())
    ).all()
    
    videos = []
    for item in items:
        video = session.get(Video, item.video_id)
        if video:
            videos.append({
                "video_id": video.id,
                "title": video.title,
                "thumbnail_url": video.thumbnail_url,
                "duration": video.duration,
                "added_at": item.added_at.isoformat()
            })
    
    return {"videos": videos, "playlist_id": playlist.id}


@router.post("/watch-later/add/{video_id}")
async def add_to_watch_later(
    video_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_user)
):
    """Quick add to Watch Later."""
    # Get or create Watch Later playlist
    playlist = session.exec(
        select(Playlist)
        .where(Playlist.user_id == current_user.id)
        .where(Playlist.is_watch_later == True)
    ).first()
    
    if not playlist:
        playlist = Playlist(
            user_id=current_user.id,
            name="Watch Later",
            is_watch_later=True,
            is_public=False
        )
        session.add(playlist)
        session.commit()
        session.refresh(playlist)
    
    video = session.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Check if exists
    existing = session.exec(
        select(PlaylistItem)
        .where(PlaylistItem.playlist_id == playlist.id)
        .where(PlaylistItem.video_id == video_id)
    ).first()
    
    if existing:
        # Remove from Watch Later (toggle)
        session.delete(existing)
        session.commit()
        return {"action": "removed", "video_id": video_id}
    
    item = PlaylistItem(
        playlist_id=playlist.id,
        video_id=video_id,
        position=0
    )
    session.add(item)
    session.commit()
    
    return {"action": "added", "video_id": video_id}
