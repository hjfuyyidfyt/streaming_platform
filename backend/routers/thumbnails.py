from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, FileResponse, StreamingResponse
from sqlmodel import Session
from ..database import get_session
from ..models import Video, TelegramInfo
from ..services.telegram_uploader import get_telegram_file_bytes
from ..services.crypto import decrypt_file_generator
from sqlmodel import select
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/thumbnails",
    tags=["thumbnails"]
)

THUMBNAIL_DIR = "backend/thumbnails"
os.makedirs(THUMBNAIL_DIR, exist_ok=True)


@router.get("/{video_id}")
async def get_thumbnail(
    video_id: int,
    session: Session = Depends(get_session)
):
    """Get thumbnail for a video. Returns uploaded image (local or telegram) or generated SVG placeholder."""
    video = session.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # 1. Check for saved thumbnail locally (Backup/Cache)
    for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
        thumb_path = os.path.join(THUMBNAIL_DIR, f"{video_id}{ext}")
        if os.path.exists(thumb_path):
            return FileResponse(thumb_path)
            
    # 2. Check Telegram Proxy
    tg_info = session.exec(select(TelegramInfo).where(TelegramInfo.video_id == video_id)).first()
    if tg_info and tg_info.thumbnail_file_id:
        try:
            content = await get_telegram_file_bytes(tg_info.thumbnail_file_id)
            if content:
                # Assuming JPEG for now, or detect from bytes
                return Response(content=bytes(content), media_type="image/jpeg")
        except Exception as e:
            logger.error(f"Failed to fetch thumb from TG: {e}")
    
    # 3. No saved thumbnail - return SVG placeholder
    return Response(
        content=create_placeholder_image(video.title),
        media_type="image/svg+xml"
    )


def create_placeholder_image(title: str) -> bytes:
    """Create a simple SVG placeholder with video title."""
    # Truncate title
    display_title = title[:35] + "..." if len(title) > 35 else title
    # Escape HTML entities
    display_title = display_title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360">
    <defs>
        <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" style="stop-color:#1a1a2e"/>
            <stop offset="100%" style="stop-color:#16213e"/>
        </linearGradient>
    </defs>
    <rect width="100%" height="100%" fill="url(#bg)"/>
    <circle cx="320" cy="160" r="40" fill="rgba(255,255,255,0.1)"/>
    <polygon points="310,140 310,180 345,160" fill="rgba(255,255,255,0.8)"/>
    <text x="320" y="240" text-anchor="middle" fill="#888" font-family="Arial, sans-serif" font-size="16">{display_title}</text>
</svg>'''
    return svg.encode('utf-8')
