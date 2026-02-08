"""
Video Likes Router - Like/Dislike videos.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import Optional
from datetime import datetime

from ..database import get_session
from ..models import VideoLike, Video, User
from .auth import get_current_user, require_user

router = APIRouter(
    prefix="/likes",
    tags=["likes"]
)


@router.post("/video/{video_id}")
async def like_video(
    video_id: int,
    is_like: bool = True,  # True=like, False=dislike
    session: Session = Depends(get_session),
    current_user: User = Depends(require_user)
):
    """Like or dislike a video. Toggle if already liked/disliked."""
    video = session.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Check if already liked/disliked
    existing = session.exec(
        select(VideoLike)
        .where(VideoLike.video_id == video_id)
        .where(VideoLike.user_id == current_user.id)
    ).first()
    
    if existing:
        if existing.is_like == is_like:
            # Same action - remove like/dislike (toggle off)
            session.delete(existing)
            session.commit()
            return {"action": "removed", "video_id": video_id}
        else:
            # Different action - switch from like to dislike or vice versa
            existing.is_like = is_like
            session.add(existing)
            session.commit()
            return {
                "action": "switched",
                "is_like": is_like,
                "video_id": video_id
            }
    else:
        # New like/dislike
        video_like = VideoLike(
            video_id=video_id,
            user_id=current_user.id,
            is_like=is_like
        )
        session.add(video_like)
        session.commit()
        return {
            "action": "added",
            "is_like": is_like,
            "video_id": video_id
        }


@router.get("/video/{video_id}/status")
async def get_like_status(
    video_id: int,
    session: Session = Depends(get_session),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Get like/dislike status and counts for a video."""
    video = session.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Count likes and dislikes
    likes = len(session.exec(
        select(VideoLike)
        .where(VideoLike.video_id == video_id)
        .where(VideoLike.is_like == True)
    ).all())
    
    dislikes = len(session.exec(
        select(VideoLike)
        .where(VideoLike.video_id == video_id)
        .where(VideoLike.is_like == False)
    ).all())
    
    # Check user's status
    user_liked = None
    if current_user:
        user_vote = session.exec(
            select(VideoLike)
            .where(VideoLike.video_id == video_id)
            .where(VideoLike.user_id == current_user.id)
        ).first()
        if user_vote:
            user_liked = user_vote.is_like
    
    return {
        "video_id": video_id,
        "likes": likes,
        "dislikes": dislikes,
        "user_liked": user_liked  # True=liked, False=disliked, None=no vote
    }


@router.get("/user/liked")
async def get_user_liked_videos(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_user)
):
    """Get all videos liked by the current user."""
    likes = session.exec(
        select(VideoLike)
        .where(VideoLike.user_id == current_user.id)
        .where(VideoLike.is_like == True)
        .order_by(VideoLike.created_at.desc())
    ).all()
    
    video_ids = [like.video_id for like in likes]
    
    videos = []
    for vid_id in video_ids:
        video = session.get(Video, vid_id)
        if video:
            videos.append({
                "id": video.id,
                "title": video.title,
                "thumbnail_url": video.thumbnail_url,
                "duration": video.duration,
                "views": video.views
            })
    
    return {"liked_videos": videos, "count": len(videos)}
