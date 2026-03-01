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


@router.get("/download-all/{video_id}")
async def download_all_thumbnails(
    video_id: str
):
    """Admin endpoint to download all extracted thumbnails as a ZIP file."""
    # Clean up video_id
    clean_id_str = video_id.split(".")[0]
    
    try:
        clean_id = int(clean_id_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid video ID format")
        
    zip_path = os.path.join(THUMBNAIL_DIR, f"{clean_id}_thumbs.zip")
    if os.path.exists(zip_path):
        return FileResponse(
            zip_path, 
            media_type="application/zip", 
            filename=f"video_{clean_id}_thumbnails.zip"
        )
    else:
        raise HTTPException(status_code=404, detail="Thumbnails ZIP not found.")

@router.get("/{video_id}")
async def get_thumbnail(
    video_id: str
):
    """Get thumbnail for a video. Returns uploaded image (local) or SVG placeholder."""
    
    # Clean up video_id (remove .jpg if present, it happens due to frontend using the raw URL)
    clean_id_str = video_id.split(".")[0]
    
    try:
        clean_id = int(clean_id_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid video ID format")
    
    # 1. Check for saved thumbnail locally FIRST (no DB needed = instant)
    for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
        thumb_path = os.path.join(THUMBNAIL_DIR, f"{clean_id}{ext}")
        if os.path.exists(thumb_path):
            return FileResponse(thumb_path)
    
    # 2. No local file — need DB for Telegram fallback or placeholder
    from ..database import get_session as _get_session
    try:
        session_gen = _get_session()
        session = next(session_gen)
    except Exception as e:
        logger.error(f"DB connection failed for thumbnail: {e}")
        # Return generic placeholder without video title
        return Response(
            content=create_placeholder_image(f"Video {clean_id}"),
            media_type="image/svg+xml"
        )
    
    try:
        video = session.get(Video, clean_id)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        
        # 3. Check Telegram thumbnail (proxy from TG)
        tg_info = session.exec(select(TelegramInfo).where(TelegramInfo.video_id == clean_id)).first()
        if tg_info and tg_info.thumbnail_file_id:
            try:
                content = await get_telegram_file_bytes(tg_info.thumbnail_file_id)
                if content:
                    return Response(content=bytes(content), media_type="image/jpeg")
            except Exception as e:
                logger.error(f"Failed to fetch thumb from TG: {e}")
        
        # 4. No saved thumbnail - return SVG placeholder
        return Response(
            content=create_placeholder_image(video.title),
            media_type="image/svg+xml"
        )
    finally:
        try:
            session_gen.close()
        except Exception:
            pass


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
