from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlmodel import Session, select
from ..database import get_session
from ..models import Video, TelegramInfo, VideoResolution
import os
import httpx
from telegram import Bot
from dotenv import load_dotenv
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Load .env from backend directory
env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

router = APIRouter(
    prefix="/stream",
    tags=["stream"]
)

# Cache for file URLs to avoid repeated API calls
# Format: {file_id: (url, timestamp)}
file_url_cache = {}
import time
CACHE_EXPIRATION = 3000 # 50 minutes in seconds

async def get_telegram_file_url(file_id: str) -> str:
    """Get the download URL for a file from Telegram (with caching)."""
    current_time = time.time()
    
    if file_id in file_url_cache:
        url, timestamp = file_url_cache[file_id]
        if current_time - timestamp < CACHE_EXPIRATION:
            return url
    
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not set")
    
    bot = Bot(token=TOKEN)
    file = await bot.get_file(file_id)
    # Cache with timestamp
    file_url_cache[file_id] = (file.file_path, current_time)
    return file.file_path


@router.get("/{video_id}/resolutions")
async def get_video_resolutions(
    video_id: int,
    session: Session = Depends(get_session)
):
    """Get all available resolutions for a video."""
    video = session.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    resolutions = session.exec(
        select(VideoResolution)
        .where(VideoResolution.video_id == video_id)
        .order_by(VideoResolution.resolution.desc())
    ).all()
    
    available = []
    for res in resolutions:
        available.append({
            "resolution": res.resolution,
            "label": res.resolution,
            "file_size": res.file_size
        })
    
    if not available and video.telegram_info:
        available.append({
            "resolution": video.original_resolution or "original",
            "label": video.original_resolution or "Original",
            "file_size": video.telegram_info.file_size
        })
    
    return {
        "video_id": video_id,
        "original_resolution": video.original_resolution,
        "available_resolutions": available
    }


@router.get("/{video_id}")
async def stream_video(
    video_id: int,
    resolution: Optional[str] = Query(None),
    session: Session = Depends(get_session)
):
    """Stream video with proxy to avoid CORS/redirect issues."""
    video = session.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    file_id = None
    
    # If resolution specified, look for it in VideoSource
    if resolution:
        from ..models import VideoSource
        query = select(VideoSource).where(VideoSource.video_id == video_id).where(VideoSource.provider == "telegram")
        
        if resolution.lower() == 'original':
             # Check for None or 'Original' explicitly
             src_record = session.exec(query.where(
                 (VideoSource.resolution == None) | (VideoSource.resolution == "Original")
             )).first()
        else:
             src_record = session.exec(query.where(VideoSource.resolution == resolution)).first()

        if src_record:
            file_id = src_record.file_id
    
    # Fallback to original
    if not file_id:
        # Try finding ANY telegram source
        from ..models import VideoSource
        src_record = session.exec(
            select(VideoSource)
            .where(VideoSource.video_id == video_id)
            .where(VideoSource.provider == "telegram")
        ).first()
        
        if src_record:
            file_id = src_record.file_id
        elif video.telegram_info: # Legacy fallback
             file_id = video.telegram_info.file_id
        else:
             raise HTTPException(status_code=404, detail="Video source not found")
    
    try:
        # Get Telegram file URL
        file_url = await get_telegram_file_url(file_id)
        logger.info(f"Streaming video {video_id} from: {file_url[:50]}...")
        
        # Proxy stream the video
        async def stream_generator():
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream("GET", file_url) as response:
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        yield chunk
        
        return StreamingResponse(
            stream_generator(),
            media_type="video/mp4",
            headers={
                "Accept-Ranges": "bytes",
                "Content-Disposition": f"inline; filename=video_{video_id}.mp4"
            }
        )

    except Exception as e:
        logger.error(f"Streaming Error: {e}")
        raise HTTPException(status_code=500, detail=f"Could not stream video: {str(e)}")
