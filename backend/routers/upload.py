from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks
from sqlmodel import Session, select
from typing import Optional, List
from ..database import get_session, engine
from ..models import Video, Category, TelegramInfo, VideoResolution, User, VideoPublic
from ..services.telegram_uploader import upload_video_to_telegram, upload_photo_to_telegram
from ..services.crypto import encrypt_stream_to_file
from ..services.transcoder import get_video_info, transcode_video, check_ffmpeg_installed
from ..services.external_storage import upload_to_streamtape, upload_to_doodstream
from ..models import StorageMode
from .auth import get_current_user, require_user
import os
import shutil
import uuid
import logging
import asyncio

# Configure logger
logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.setLevel(logging.INFO)
    f_handler = logging.FileHandler('backend/upload_debug.log')
    f_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    f_handler.setFormatter(formatter)
    logger.addHandler(f_handler)
    
    # Also add a stream handler for console output
    s_handler = logging.StreamHandler()
    s_handler.setFormatter(formatter)
    logger.addHandler(s_handler)

router = APIRouter(
    prefix="/upload",
    tags=["upload"]
)

TEMP_DIR = "backend/temp_uploads"
TRANSCODE_DIR = "backend/temp_transcodes"
THUMBNAIL_DIR = "backend/thumbnails"
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(TRANSCODE_DIR, exist_ok=True)
os.makedirs(THUMBNAIL_DIR, exist_ok=True)


def background_full_process_task(video_id: int, source_file: str, title: str, original_resolution: str, active_providers: List[str]):
    """
    Consolidated background task to:
    1. Upload Original to all providers.
    2. Transcode if needed.
    3. Upload Transcoded to all providers.
    4. Update DB as we go.
    """
    import threading
    
    def run_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def process_async():
            try:
                logger.info(f"[BG-{video_id}] Starting full background process (Async)...")
                from sqlmodel import Session as SqlSession
                from ..models import VideoSource, TelegramInfo, Video
                
                # Helper to save source
                def save_source(provider, res=None, file_id=None, embed_url=None):
                    with SqlSession(engine) as session_bg:
                        # Fallback for resolution
                        if not res or res == "unknown":
                            v_rec = session_bg.get(Video, video_id)
                            res = v_rec.original_resolution if v_rec and v_rec.original_resolution != "unknown" else "Original"

                        source = VideoSource(
                            video_id=video_id,
                            provider=provider,
                            resolution=res,
                            file_id=file_id,
                            embed_url=embed_url
                        )
                        session_bg.add(source)
                        session_bg.commit()
                        logger.info(f"[BG-{video_id}] Source saved: {provider} - {res}")

                # --- 1. UPLOAD ORIGINAL (PARALLEL) ---
                logger.info(f"[BG-{video_id}] Starting parallel Original uploads...")
                
                async def tg_orig():
                    try:
                        data = await asyncio.wait_for(
                            upload_video_to_telegram(source_file, caption=f"{title} [Source]", is_encrypted=False),
                            timeout=600 # 10 mins
                        )
                        with SqlSession(engine) as session_bg:
                            tg_info = TelegramInfo(
                                video_id=video_id,
                                file_id=data["file_id"],
                                file_unique_id=data["file_unique_id"],
                                file_size=data["file_size"],
                                mime_type=data["mime_type"],
                                channel_message_id=data["channel_message_id"]
                            )
                            session_bg.add(tg_info)
                            # Get resolution if unknown
                            res_val = original_resolution
                            if not res_val or res_val == "unknown":
                                v_rec = session_bg.get(Video, video_id)
                                res_val = v_rec.original_resolution if v_rec else "Original"
                            
                            source = VideoSource(
                                video_id=video_id,
                                provider="telegram",
                                resolution=res_val,
                                file_id=data["file_id"]
                            )
                            session_bg.add(source)
                            session_bg.commit()
                            logger.info(f"[BG-{video_id}] Telegram Original saved.")
                    except Exception as e:
                        logger.error(f"[BG-{video_id}] Telegram Original Error: {e}")

                async def st_orig():
                    try:
                        st_res = await asyncio.wait_for(upload_to_streamtape(source_file, title=title), timeout=600)
                        if st_res:
                            save_source("streamtape", original_resolution, st_res['file_id'], st_res['embed_url'])
                    except Exception as e:
                        logger.error(f"[BG-{video_id}] StreamTape Original Error: {e}")

                async def dd_orig():
                    try:
                        dd_res = await asyncio.wait_for(upload_to_doodstream(source_file, title=title), timeout=600)
                        if dd_res:
                            save_source("doodstream", original_resolution, dd_res['file_id'], dd_res['embed_url'])
                    except Exception as e:
                        logger.error(f"[BG-{video_id}] DoodStream Original Error: {e}")

                upload_tasks = []
                if 'telegram' in active_providers: upload_tasks.append(tg_orig())
                if 'streamtape' in active_providers: upload_tasks.append(st_orig())
                if 'doodstream' in active_providers: upload_tasks.append(dd_orig())
                
                if upload_tasks:
                    await asyncio.gather(*upload_tasks)

                # --- 2. TRANSCODE ---
                if check_ffmpeg_installed():
                    logger.info(f"[BG-{video_id}] Starting transcoding...")
                    transcode_output_dir = os.path.join(TRANSCODE_DIR, str(video_id))
                    # Transcoding is CPU intensive, we do it synchronously in this thread
                    transcoded_files = await loop.run_in_executor(None, lambda: transcode_video(source_file, transcode_output_dir, is_encrypted=False))
                    
                    if transcoded_files:
                        logger.info(f"[BG-{video_id}] Transcoded: {list(transcoded_files.keys())}")
                        
                        for resolution, file_path in transcoded_files.items():
                            # For each resolution, upload to all providers in parallel
                            res_tasks = []
                            
                            async def tg_res(res, path):
                                try:
                                    tg_data = await asyncio.wait_for(upload_video_to_telegram(path, caption=f"[{res}]", is_encrypted=False), timeout=300)
                                    save_source("telegram", res, tg_data["file_id"])
                                except Exception as e:
                                    logger.error(f"[BG-{video_id}] Telegram {res} Error: {e}")

                            async def st_res_task(res, path):
                                try:
                                    st_res_data = await asyncio.wait_for(upload_to_streamtape(path, title=f"{title} {res}"), timeout=300)
                                    if st_res_data:
                                        save_source("streamtape", res, st_res_data['file_id'], st_res_data['embed_url'])
                                except Exception as e:
                                    logger.error(f"[BG-{video_id}] StreamTape {res} Error: {e}")

                            async def dd_res_task(res, path):
                                try:
                                    dd_res_data = await asyncio.wait_for(upload_to_doodstream(path, title=f"{title} {res}"), timeout=300)
                                    if dd_res_data:
                                        save_source("doodstream", res, dd_res_data['file_id'], dd_res_data['embed_url'])
                                except Exception as e:
                                    logger.error(f"[BG-{video_id}] DoodStream {res} Error: {e}")

                            if 'telegram' in active_providers: res_tasks.append(tg_res(resolution, file_path))
                            if 'streamtape' in active_providers: res_tasks.append(st_res_task(resolution, file_path))
                            if 'doodstream' in active_providers: res_tasks.append(dd_res_task(resolution, file_path))
                            
                            if res_tasks:
                                await asyncio.gather(*res_tasks)
                            
                            cleanup_file(file_path)
                    
                    if os.path.exists(transcode_output_dir):
                        shutil.rmtree(transcode_output_dir, ignore_errors=True)
                
                logger.info(f"[BG-{video_id}] All tasks complete!")
                
            except Exception as e:
                logger.error(f"[BG-{video_id}] Process Error: {e}", exc_info=True)
            finally:
                cleanup_file(source_file)

        try:
            loop.run_until_complete(process_async())
        finally:
            loop.close()
    
    # Start in background thread
    threading.Thread(target=run_in_thread, daemon=True).start()


def cleanup_file(path: str):
    """Safely remove file."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except:
        pass


@router.post("/video")
async def upload_video(
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    description: str = Form(None),
    category_id: int = Form(...),
    file: UploadFile = File(...),
    thumbnail: UploadFile = File(None),
    is_short: bool = Form(False),
    current_user: User = Depends(require_user),
    session: Session = Depends(get_session)
):
    from .admin import load_settings
    
    settings = load_settings()
    active_providers = [k for k, v in settings.storage_providers.items() if v['enabled']]
    logger.info(f"UPLOAD START: Active Providers: {active_providers}")

    if not active_providers:
        active_providers = ['telegram']

    # 1. Save file to temp
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    temp_file_path = os.path.join(TEMP_DIR, unique_filename)
    
    try:
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Failed to save temp file: {e}")
        raise HTTPException(status_code=500, detail="Failed to save upload")

    # 2. Get Video Info
    original_resolution = "unknown"
    duration = 0
    if check_ffmpeg_installed():
        # Run synchronous FFprobe in a thread to avoid blocking the main event loop
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: get_video_info(temp_file_path, is_encrypted=False))
        if info:
            original_resolution = info.get("resolution", "unknown")
            duration = int(info.get("duration", 0))

    # 3. Create Video Record
    video = Video(
        title=title,
        description=description,
        category_id=category_id,
        uploader_id=current_user.id,
        storage_mode="multi",
        duration=duration,
        original_resolution=original_resolution,
        is_short=is_short
    )
    session.add(video)
    session.commit()
    session.refresh(video)

    # 4. Handle Thumbnail
    if thumbnail:
        thumb_ext = os.path.splitext(thumbnail.filename)[1] or ".jpg"
        thumb_path = os.path.join(THUMBNAIL_DIR, f"{video.id}{thumb_ext}")
        with open(thumb_path, "wb") as buffer:
            shutil.copyfileobj(thumbnail.file, buffer)
        video.thumbnail_url = f"/thumbnails/{video.id}"
        session.add(video)
        session.commit()

    # 5. Hand off EVERYTHING to background task
    background_full_process_task(video.id, temp_file_path, title, original_resolution, active_providers)

    return video


# ============== User Video Endpoints ==============

@router.get("/my-videos", response_model=List[VideoPublic])
async def get_my_videos(
    skip: int = 0,
    limit: int = 50,
    session: Session = Depends(get_session),
    current_user: Optional[User] = Depends(get_current_user)
):
    """
    Get all videos uploaded by the current user.
    Requires authentication.
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    from sqlalchemy.orm import joinedload
    videos = session.exec(
        select(Video)
        .where(Video.uploader_id == current_user.id)
        .options(joinedload(Video.category))
        .order_by(Video.upload_date.desc())
        .offset(skip)
        .limit(limit)
    ).all()
    
    return videos


@router.get("/user/{user_id}/videos", response_model=List[VideoPublic])
async def get_user_videos(
    user_id: int,
    skip: int = 0,
    limit: int = 50,
    session: Session = Depends(get_session)
):
    """
    Get all videos uploaded by a specific user (public).
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    from sqlalchemy.orm import joinedload
    videos = session.exec(
        select(Video)
        .where(Video.uploader_id == user_id)
        .options(joinedload(Video.category))
        .order_by(Video.upload_date.desc())
        .offset(skip)
        .limit(limit)
    ).all()
    
    return videos


@router.delete("/video/{video_id}")
async def delete_my_video(
    video_id: int,
    session: Session = Depends(get_session),
    current_user: Optional[User] = Depends(get_current_user)
):
    """
    Delete a video. Only the uploader can delete their own video.
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    video = session.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    if video.uploader_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this video")
    
    # Delete associated records
    if video.telegram_info:
        session.delete(video.telegram_info)
    for resolution in video.resolutions:
        session.delete(resolution)
    
    session.delete(video)
    session.commit()
    
    return {"status": "success", "message": "Video deleted"}

