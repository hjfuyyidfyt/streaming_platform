from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, StreamingResponse, Response
from sqlmodel import Session, select
from ..database import get_session
from ..models import Video, TelegramInfo, VideoResolution
import os
import httpx
from pathlib import Path
from typing import Optional
import logging
import time

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/stream",
    tags=["stream"]
)

# Cache for file URLs to avoid repeated API calls
# Format: {file_id: (url, timestamp)}
file_url_cache = {}
CACHE_EXPIRATION = 3000  # 50 minutes in seconds

# Telethon client singleton for streaming
_stream_client = None

async def _get_stream_client():
    """Get or create a Telethon client for streaming."""
    global _stream_client
    if _stream_client is not None and _stream_client.is_connected():
        return _stream_client
    
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    
    if not token or not api_id or not api_hash:
        raise ValueError("Telegram credentials not fully configured in .env")
    
    from telethon import TelegramClient
    from telethon.sessions import MemorySession
    
    _stream_client = TelegramClient(
        MemorySession(),
        int(api_id),
        api_hash,
        timeout=120,
    )
    await _stream_client.start(bot_token=token)
    logger.info("[Stream] Telethon client connected for streaming (MemorySession)")
    return _stream_client


async def get_telegram_file_url(file_id: str) -> str:
    """
    Get the download URL for a file from Telegram Bot API (with caching).
    Falls back to Bot API for URL generation since Telethon doesn't directly provide URLs.
    """
    current_time = time.time()
    
    if file_id in file_url_cache:
        url, timestamp = file_url_cache[file_id]
        if current_time - timestamp < CACHE_EXPIRATION:
            return url
    
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not set")
    
    # Use Bot API HTTP endpoint directly instead of the library
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.telegram.org/bot{token}/getFile",
            params={"file_id": file_id},
            timeout=30.0
        )
        data = resp.json()
        
        if not data.get("ok"):
            raise ValueError(f"Telegram getFile failed: {data.get('description', 'unknown error')}")
        
        file_path = data["result"]["file_path"]
        file_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
        
        file_url_cache[file_id] = (file_url, current_time)
        return file_url


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
    request: Request,
    resolution: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
    session: Session = Depends(get_session)
):
    """Stream video - supports both Telegram and external providers."""
    video = session.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # First, check for external embed sources (StreamTape, DoodStream)
    from ..models import VideoSource, TelegramInfo
    
    # Check for any available source
    file_id = None
    embed_url = None
    found_provider = None
    
    # If resolution specified, look for it (filter by provider if given)
    if resolution:
        query = select(VideoSource).where(VideoSource.video_id == video_id)
        
        # Filter by provider if specified
        if provider:
            query = query.where(VideoSource.provider == provider)
        
        if resolution.lower() == 'original':
            src_record = session.exec(query.where(
                (VideoSource.resolution == None) | (VideoSource.resolution == "Original")
            )).first()
        else:
            src_record = session.exec(query.where(VideoSource.resolution == resolution)).first()

        if src_record:
            file_id = src_record.file_id
            embed_url = src_record.embed_url
            found_provider = src_record.provider
    
    # If no source found yet and provider is telegram (or no provider specified), fallback to telegram
    if not file_id and (not provider or provider == 'telegram'):
        src_record = session.exec(
            select(VideoSource)
            .where(VideoSource.video_id == video_id)
            .where(VideoSource.provider == "telegram")
        ).first()
        
        if src_record:
            file_id = src_record.file_id
            found_provider = "telegram"
        elif video.telegram_info:  # Legacy fallback
            file_id = video.telegram_info.file_id
            found_provider = "telegram"
    
    if not file_id:
        raise HTTPException(status_code=404, detail="Video source not found")
    
    # For external providers with embed URLs, redirect
    if embed_url and found_provider in ("streamtape", "doodstream"):
        return RedirectResponse(url=embed_url)
    
    # For Telegram sources, try to stream via Telethon
    try:
        if found_provider == "telegram" and os.getenv("TELEGRAM_API_ID") and os.getenv("TELEGRAM_API_HASH"):
            # Use Telethon to download and stream (supports large files)
            client = await _get_stream_client()
            _channel_id_str = os.getenv("TELEGRAM_CHANNEL_ID")
            channel_id = int(_channel_id_str.strip()) if _channel_id_str else None
            
            if channel_id:
                try:
                    # Get the channel_message_id from TelegramInfo (NOT file_id!)
                    # file_id is a Telegram Bot API string like "BAACAgIAA...", NOT a message ID integer
                    tg_info = session.exec(
                        select(TelegramInfo).where(TelegramInfo.video_id == video_id)
                    ).first()
                    
                    if msg_id:
                        message = await client.get_messages(channel_id, ids=msg_id)
                        if message and message.media and hasattr(message.media, "document"):
                            file_size = message.media.document.size
                            
                            range_header = request.headers.get("Range")
                            start = 0
                            end = file_size - 1
                            
                            if range_header:
                                ranges = range_header.replace("bytes=", "").split("-")
                                start = int(ranges[0]) if ranges[0] else 0
                                end = int(ranges[1]) if len(ranges) > 1 and ranges[1] else file_size - 1
                            
                            content_length = (end - start) + 1
                            
                            headers = {
                                "Accept-Ranges": "bytes",
                                "Content-Length": str(content_length),
                                "Content-Type": "video/mp4",
                                "Content-Disposition": f"inline; filename=video_{video_id}.mp4"
                            }
                            
                            status_code = 200
                            if range_header:
                                headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
                                status_code = 206
                                
                            async def telethon_stream():
                                async for chunk in client.iter_download(message.media, offset=start, limit=content_length, chunk_size=65536):
                                    if not chunk:
                                        break
                                    yield chunk
                            
                            return StreamingResponse(
                                telethon_stream(),
                                status_code=status_code,
                                headers=headers,
                                media_type="video/mp4"
                            )
                    else:
                        logger.warning(f"No channel_message_id found for video {video_id}, falling back to Bot API")
                except Exception as e:
                    logger.warning(f"Telethon stream failed, falling back to Bot API: {e}")
        
        # Fallback: use Bot API URL (works for files < 20MB download)
        file_url = await get_telegram_file_url(file_id)
        logger.info(f"Streaming video {video_id} from Bot API URL")
        
        range_header = request.headers.get("Range")
        req_headers = {}
        if range_header:
            req_headers["Range"] = range_header
        
        # Proxy request directly to Telegram API with Range header
        client = httpx.AsyncClient(timeout=300.0)
        bot_api_req = client.build_request("GET", file_url, headers=req_headers)
        bot_api_resp = await client.send(bot_api_req, stream=True)
        
        async def stream_generator():
            async for chunk in bot_api_resp.aiter_bytes(chunk_size=65536):
                yield chunk
            await client.aclose()
            
        proxy_headers = {
            "Accept-Ranges": "bytes",
            "Content-Disposition": f"inline; filename=video_{video_id}.mp4",
            "Content-Type": "video/mp4",
        }
        if "Content-Range" in bot_api_resp.headers:
            proxy_headers["Content-Range"] = bot_api_resp.headers["Content-Range"]
        if "Content-Length" in bot_api_resp.headers:
            proxy_headers["Content-Length"] = bot_api_resp.headers["Content-Length"]
            
        return StreamingResponse(
            stream_generator(),
            status_code=bot_api_resp.status_code,
            headers=proxy_headers,
            media_type="video/mp4"
        )

    except Exception as e:
        logger.error(f"Streaming Error: {e}")
        raise HTTPException(status_code=500, detail=f"Could not stream video: {str(e)}")
