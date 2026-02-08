"""
Comments Router - Handles video comments with Super Chat support.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from ..database import get_session
from ..models import Comment, CommentLike, Video, User
from .auth import get_current_user, require_user

router = APIRouter(
    prefix="/comments",
    tags=["comments"]
)


# Pydantic schemas
class CommentCreate(BaseModel):
    video_id: int
    content: str
    parent_id: Optional[int] = None
    is_super_chat: bool = False
    super_chat_amount: Optional[float] = None
    super_chat_color: Optional[str] = None


class CommentUpdate(BaseModel):
    content: str


class CommentResponse(BaseModel):
    id: int
    video_id: int
    user_id: int
    parent_id: Optional[int]
    content: str
    is_super_chat: bool
    super_chat_amount: Optional[float]
    super_chat_color: Optional[str]
    likes_count: int
    is_edited: bool
    created_at: datetime
    user: Optional[dict] = None
    replies: List["CommentResponse"] = []


# Endpoints
@router.get("/video/{video_id}")
async def get_video_comments(
    video_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=100),
    session: Session = Depends(get_session),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Get all comments for a video with replies."""
    # Check video exists
    video = session.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Get top-level comments (parent_id is None)
    comments = session.exec(
        select(Comment)
        .where(Comment.video_id == video_id)
        .where(Comment.parent_id == None)
        .order_by(Comment.is_super_chat.desc())  # Super chats first
        .order_by(Comment.created_at.desc())
        .offset(skip)
        .limit(limit)
    ).all()
    
    # Build response with user info and replies
    result = []
    for comment in comments:
        comment_data = build_comment_response(comment, session, current_user)
        result.append(comment_data)
    
    # Get total count
    total = len(session.exec(
        select(Comment)
        .where(Comment.video_id == video_id)
        .where(Comment.parent_id == None)
    ).all())
    
    return {
        "comments": result,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.post("/", status_code=201)
async def create_comment(
    comment_data: CommentCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_user)
):
    """Create a new comment. Requires authentication."""
    # Check video exists
    video = session.get(Video, comment_data.video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Check parent comment exists if replying
    if comment_data.parent_id:
        parent = session.get(Comment, comment_data.parent_id)
        if not parent or parent.video_id != comment_data.video_id:
            raise HTTPException(status_code=400, detail="Invalid parent comment")
    
    # Validate Super Chat
    if comment_data.is_super_chat:
        if not comment_data.super_chat_amount or comment_data.super_chat_amount <= 0:
            raise HTTPException(status_code=400, detail="Super Chat requires a valid amount")
        # Set default color if not provided
        if not comment_data.super_chat_color:
            if comment_data.super_chat_amount >= 100:
                comment_data.super_chat_color = "#ff0000"  # Red for $100+
            elif comment_data.super_chat_amount >= 50:
                comment_data.super_chat_color = "#ff6600"  # Orange for $50+
            elif comment_data.super_chat_amount >= 20:
                comment_data.super_chat_color = "#ffcc00"  # Yellow for $20+
            else:
                comment_data.super_chat_color = "#00cc00"  # Green for others
    
    # Create comment
    comment = Comment(
        video_id=comment_data.video_id,
        user_id=current_user.id,
        parent_id=comment_data.parent_id,
        content=comment_data.content,
        is_super_chat=comment_data.is_super_chat,
        super_chat_amount=comment_data.super_chat_amount,
        super_chat_color=comment_data.super_chat_color
    )
    session.add(comment)
    session.commit()
    session.refresh(comment)
    
    return build_comment_response(comment, session, current_user)


@router.put("/{comment_id}")
async def update_comment(
    comment_id: int,
    update_data: CommentUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_user)
):
    """Update a comment. Only owner can update."""
    comment = session.get(Comment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    
    if comment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to edit this comment")
    
    comment.content = update_data.content
    comment.is_edited = True
    session.add(comment)
    session.commit()
    session.refresh(comment)
    
    return build_comment_response(comment, session, current_user)


@router.delete("/{comment_id}")
async def delete_comment(
    comment_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_user)
):
    """Delete a comment. Only owner can delete."""
    comment = session.get(Comment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    
    if comment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this comment")
    
    # Delete replies first
    replies = session.exec(
        select(Comment).where(Comment.parent_id == comment_id)
    ).all()
    for reply in replies:
        session.delete(reply)
    
    # Delete comment likes
    likes = session.exec(
        select(CommentLike).where(CommentLike.comment_id == comment_id)
    ).all()
    for like in likes:
        session.delete(like)
    
    session.delete(comment)
    session.commit()
    
    return {"message": "Comment deleted"}


@router.post("/{comment_id}/like")
async def like_comment(
    comment_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_user)
):
    """Like/unlike a comment (toggle)."""
    comment = session.get(Comment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    
    # Check if already liked
    existing = session.exec(
        select(CommentLike)
        .where(CommentLike.comment_id == comment_id)
        .where(CommentLike.user_id == current_user.id)
    ).first()
    
    if existing:
        # Unlike
        session.delete(existing)
        comment.likes_count = max(0, comment.likes_count - 1)
        action = "unliked"
    else:
        # Like
        like = CommentLike(
            comment_id=comment_id,
            user_id=current_user.id
        )
        session.add(like)
        comment.likes_count += 1
        action = "liked"
    
    session.add(comment)
    session.commit()
    
    return {"action": action, "likes_count": comment.likes_count}


# Helper functions
def build_comment_response(comment: Comment, session: Session, current_user: Optional[User] = None) -> dict:
    """Build comment response with user info and replies."""
    # Get user info
    user = session.get(User, comment.user_id)
    user_data = None
    if user:
        user_data = {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "avatar_url": user.avatar_url
        }
    
    # Get replies (first level only)
    replies = session.exec(
        select(Comment)
        .where(Comment.parent_id == comment.id)
        .order_by(Comment.created_at.asc())
        .limit(10)
    ).all()
    
    reply_data = []
    for reply in replies:
        reply_user = session.get(User, reply.user_id)
        reply_user_data = None
        if reply_user:
            reply_user_data = {
                "id": reply_user.id,
                "username": reply_user.username,
                "display_name": reply_user.display_name,
                "avatar_url": reply_user.avatar_url
            }
        reply_data.append({
            "id": reply.id,
            "video_id": reply.video_id,
            "user_id": reply.user_id,
            "parent_id": reply.parent_id,
            "content": reply.content,
            "is_super_chat": reply.is_super_chat,
            "super_chat_amount": reply.super_chat_amount,
            "super_chat_color": reply.super_chat_color,
            "likes_count": reply.likes_count,
            "is_edited": reply.is_edited,
            "created_at": reply.created_at.isoformat(),
            "user": reply_user_data,
            "replies": []
        })
    
    return {
        "id": comment.id,
        "video_id": comment.video_id,
        "user_id": comment.user_id,
        "parent_id": comment.parent_id,
        "content": comment.content,
        "is_super_chat": comment.is_super_chat,
        "super_chat_amount": comment.super_chat_amount,
        "super_chat_color": comment.super_chat_color,
        "likes_count": comment.likes_count,
        "is_edited": comment.is_edited,
        "created_at": comment.created_at.isoformat(),
        "user": user_data,
        "replies": reply_data
    }
