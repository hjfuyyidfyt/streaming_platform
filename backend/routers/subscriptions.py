from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select, func
from typing import List, Optional
from ..database import get_session
from ..models import Subscription, User, Video, VideoPublic
from .auth import require_user, get_current_user

router = APIRouter(
    prefix="/subscriptions",
    tags=["subscriptions"]
)

@router.post("/channel/{channel_id}")
async def toggle_subscription(
    channel_id: int, 
    user: User = Depends(require_user), 
    session: Session = Depends(get_session)
):
    """Subscribe or unsubscribe from a channel."""
    if channel_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot subscribe to yourself")
    
    # Check if channel exists (optional but good)
    channel = session.get(User, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    # Check existence
    sub = session.exec(
        select(Subscription)
        .where(Subscription.subscriber_id == user.id)
        .where(Subscription.channel_id == channel_id)
    ).first()
    
    if sub:
        # Unsubscribe
        session.delete(sub)
        session.commit()
        return {"subscribed": False}
    else:
        # Subscribe
        new_sub = Subscription(subscriber_id=user.id, channel_id=channel_id)
        session.add(new_sub)
        session.commit()
        return {"subscribed": True}

@router.get("/channel/{channel_id}/status")
async def check_subscription_status(
    channel_id: int, 
    user: Optional[User] = Depends(get_current_user), 
    session: Session = Depends(get_session)
):
    """Check if current user is subscribed."""
    if not user:
        return {"subscribed": False}
        
    sub = session.exec(
        select(Subscription)
        .where(Subscription.subscriber_id == user.id)
        .where(Subscription.channel_id == channel_id)
    ).first()
    return {"subscribed": sub is not None}

@router.get("/channel/{channel_id}/count")
async def get_subscriber_count(
    channel_id: int, 
    session: Session = Depends(get_session)
):
    """Get total subscribers for a channel."""
    # Using len() on list for simplicity with SQLModel where count() can be tricky depending on version
    subs = session.exec(
        select(Subscription)
        .where(Subscription.channel_id == channel_id)
    ).all()
    return {"count": len(subs)}

@router.get("/feed", response_model=List[VideoPublic])
async def subscription_feed(
    skip: int = 0, 
    limit: int = 20, 
    user: User = Depends(require_user), 
    session: Session = Depends(get_session)
):
    """Get videos from subscribed channels."""
    # Get IDs of channels user is subscribed to
    subs = session.exec(
        select(Subscription.channel_id)
        .where(Subscription.subscriber_id == user.id)
    ).all()
    
    if not subs:
        return []
        
    # Lazy imports to avoid circular deps if any, but VideoPublic is imported at top
    from sqlalchemy.orm import joinedload
    
    videos = session.exec(
        select(Video)
        .where(Video.uploader_id.in_(subs))
        .options(joinedload(Video.category), joinedload(Video.uploader)) # Eager load category and uploader
        .order_by(Video.upload_date.desc())
        .offset(skip)
        .limit(limit)
    ).all()
    return videos
