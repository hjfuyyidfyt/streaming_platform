from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks
from sqlmodel import Session, select
from typing import Optional, List
from ..database import get_session, engine
from ..models import Video, Category, TelegramInfo, VideoResolution, User, VideoPublic
from ..services.telegram_uploader import upload_video_to_telegram, upload_photo_to_telegram
from ..services.crypto import encrypt_stream_to_file
from ..services.transcoder import get_video_info, transcode_video, check_ffmpeg_installed, extract_multi_thumbnails
from ..services.external_storage import upload_to_streamtape, upload_to_doodstream, remotedl_to_streamtape, remotedl_to_doodstream
from ..models import StorageMode
from .auth import get_current_user, require_user
import os
import shutil
import uuid
import logging
import asyncio
import httpx
from pydantic import BaseModel
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

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMP_DIR = os.path.join(BASE_DIR, "temp_uploads")
TRANSCODE_DIR = os.path.join(BASE_DIR, "temp_transcodes")
THUMBNAIL_DIR = os.path.join(BASE_DIR, "thumbnails")
TG_UPLOADS_DIR = os.path.join(BASE_DIR, "temp_tg_uploads")

os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(TRANSCODE_DIR, exist_ok=True)
os.makedirs(THUMBNAIL_DIR, exist_ok=True)
os.makedirs(TG_UPLOADS_DIR, exist_ok=True)


def background_full_process_task(video_id: int, source_file: str, title: str, original_resolution: str, active_providers: List[str]):
    """
    Consolidated background task:
    Phase 1: Upload Original to FAST providers (StreamTape, DoodStream) in parallel.
    Phase 2: Transcode if needed.
    Phase 3: Upload Transcoded to FAST providers.
    Telegram: Queued separately — uploads one-at-a-time in background queue.
    """
    import threading
    
    def run_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def process_async():
            try:
                logger.info(f"[BG-{video_id}] Starting background process...")
                from sqlmodel import Session as SqlSession
                from ..models import VideoSource, TelegramInfo, Video

                # Update status to processing
                with SqlSession(engine) as session_init:
                    v_init = session_init.get(Video, video_id)
                    if v_init:
                        v_init.processing_status = "processing"
                        session_init.add(v_init)
                        session_init.commit()
                from ..services.telegram_queue import telegram_queue, TelegramUploadJob
                
                # Helper to save source to DB
                def save_source(provider, res=None, file_id=None, embed_url=None):
                    with SqlSession(engine) as session_bg:
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

                # ============================================================
                # PHASE 1: FAST PROVIDERS — Original Upload (parallel)
                # ============================================================
                logger.info(f"[BG-{video_id}] Phase 1: Uploading original to fast providers...")
                
                fast_providers = [p for p in active_providers if p != 'telegram']
                fast_tasks = []
                
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
                            # Fallback Doodstream thumbnail if not set
                            with SqlSession(engine) as session_thumb:
                                v_rec = session_thumb.get(Video, video_id)
                                if v_rec and not v_rec.thumbnail_url and dd_res.get('thumbnail_url'):
                                    v_rec.thumbnail_url = dd_res['thumbnail_url']
                                    session_thumb.add(v_rec)
                                    session_thumb.commit()
                                    logger.info(f"[BG-{video_id}] Used DoodStream splash_img as fallback thumbnail")
                    except Exception as e:
                        logger.error(f"[BG-{video_id}] DoodStream Original Error: {e}")

                if 'streamtape' in fast_providers: fast_tasks.append(st_orig())
                if 'doodstream' in fast_providers: fast_tasks.append(dd_orig())
                
                if fast_tasks:
                    await asyncio.gather(*fast_tasks)
                
                logger.info(f"[BG-{video_id}] Phase 1 complete — fast provider results saved.")

                # ============================================================
                # TELEGRAM QUEUE — Enqueue original (runs separately, no blocking)
                # ============================================================
                if 'telegram' in active_providers:
                    # Copy source file to a safe TG_UPLOADS_DIR (the original temp file will be cleaned up)
                    tg_copy_filename = f"{uuid.uuid4()}_orig_{os.path.basename(source_file)}"
                    tg_copy_path = os.path.join(TG_UPLOADS_DIR, tg_copy_filename)
                    try:
                        shutil.copy2(source_file, tg_copy_path)
                        telegram_queue.enqueue(TelegramUploadJob(
                            video_id=video_id,
                            file_path=tg_copy_path,
                            title=title,
                            resolution=original_resolution,
                            caption=f"{title} [Source]",
                            is_original=True,
                            cleanup_after=True  # Delete copy after upload
                        ))
                        logger.info(f"[BG-{video_id}] Telegram original queued (position: {telegram_queue.pending_count})")
                    except Exception as e:
                        logger.error(f"[BG-{video_id}] Failed to queue Telegram original: {e}")

                # ============================================================
                # PHASE 2: TRANSCODE
                # ============================================================
                ffmpeg_available = check_ffmpeg_installed()
                logger.info(f"[BG-{video_id}] FFmpeg available: {ffmpeg_available}")
                if not ffmpeg_available:
                    logger.warning(f"[BG-{video_id}] FFmpeg NOT FOUND! Skipping transcoding.")
                
                if ffmpeg_available:
                    logger.info(f"[BG-{video_id}] Phase 2: Starting transcoding...")
                    transcode_output_dir = os.path.join(TRANSCODE_DIR, str(video_id))
                    transcoded_files = await loop.run_in_executor(
                        None, lambda: transcode_video(source_file, transcode_output_dir, is_encrypted=False)
                    )
                    
                    if transcoded_files:
                        logger.info(f"[BG-{video_id}] Transcoding SUCCESS! Created: {list(transcoded_files.keys())}")
                        
                        # ============================================================
                        # PHASE 3: Upload transcoded to FAST providers
                        # ============================================================
                        for resolution, file_path in transcoded_files.items():
                            res_tasks = []
                            
                            async def st_res_task(res, path):
                                try:
                                    st_res_data = await asyncio.wait_for(upload_to_streamtape(path, title=f"{title} {res}"), timeout=600)
                                    if st_res_data:
                                        save_source("streamtape", res, st_res_data['file_id'], st_res_data['embed_url'])
                                except Exception as e:
                                    logger.error(f"[BG-{video_id}] StreamTape {res} Error: {e}")

                            async def dd_res_task(res, path):
                                try:
                                    dd_res_data = await asyncio.wait_for(upload_to_doodstream(path, title=f"{title} {res}"), timeout=600)
                                    if dd_res_data:
                                        save_source("doodstream", res, dd_res_data['file_id'], dd_res_data['embed_url'])
                                except Exception as e:
                                    logger.error(f"[BG-{video_id}] DoodStream {res} Error: {e}")

                            if 'streamtape' in fast_providers: res_tasks.append(st_res_task(resolution, file_path))
                            if 'doodstream' in fast_providers: res_tasks.append(dd_res_task(resolution, file_path))
                            
                            if res_tasks:
                                await asyncio.gather(*res_tasks)
                            
                            # Queue transcoded to Telegram too
                            if 'telegram' in active_providers:
                                # Move to safe TG_UPLOADS_DIR instead of copying in-place
                                tg_res_filename = f"{uuid.uuid4()}_{resolution}_{os.path.basename(file_path)}"
                                tg_res_dest = os.path.join(TG_UPLOADS_DIR, tg_res_filename)
                                try:
                                    shutil.copy2(file_path, tg_res_dest)
                                    telegram_queue.enqueue(TelegramUploadJob(
                                        video_id=video_id,
                                        file_path=tg_res_dest,
                                        title=title,
                                        resolution=resolution,
                                        caption=f"{title} [{resolution}]",
                                        is_original=False,
                                        cleanup_after=True
                                    ))
                                except Exception as e:
                                    logger.error(f"[BG-{video_id}] Failed to queue Telegram {resolution}: {e}")
                            
                            cleanup_file(file_path)
                    else:
                        logger.warning(f"[BG-{video_id}] Transcoding returned NO files")
                    
                    if os.path.exists(transcode_output_dir):
                        shutil.rmtree(transcode_output_dir, ignore_errors=True)
                
                logger.info(f"[BG-{video_id}] All fast tasks complete! "
                           f"Telegram queue: {telegram_queue.pending_count} pending")
                
                # Update status to completed
                with SqlSession(engine) as session_final:
                    v_final = session_final.get(Video, video_id)
                    if v_final:
                        v_final.processing_status = "completed"
                        session_final.add(v_final)
                        session_final.commit()
                
            except Exception as e:
                logger.error(f"[BG-{video_id}] Process Error: {e}", exc_info=True)
                with SqlSession(engine) as session_err:
                    v_err = session_err.get(Video, video_id)
                    if v_err:
                        v_err.processing_status = "failed"
                        session_err.add(v_err)
                        session_err.commit()
            finally:
                cleanup_file(source_file)

        try:
            loop.run_until_complete(process_async())
        finally:
            loop.close()
    
    # Start in background thread
    threading.Thread(target=run_in_thread, daemon=True).start()


def transcode_only_task(video_id: int, source_file: str, title: str, original_resolution: str, active_providers: List[str]):
    """
    Transcode-only background task for reprocessing.
    Only does Phase 2+3: Transcode + Upload transcoded to fast providers.
    Does NOT re-upload original or delete source file.
    """
    import threading
    
    def run_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def process_async():
            try:
                logger.info(f"[REPROCESS-{video_id}] Starting transcode-only reprocess...")
                from sqlmodel import Session as SqlSession
                from ..models import VideoSource, Video

                # Update status to processing
                with SqlSession(engine) as session_init:
                    v_init = session_init.get(Video, video_id)
                    if v_init:
                        v_init.processing_status = "processing"
                        session_init.add(v_init)
                        session_init.commit()
                
                def save_source(provider, res=None, file_id=None, embed_url=None):
                    with SqlSession(engine) as session_bg:
                        if not res or res == "unknown":
                            res = original_resolution if original_resolution != "unknown" else "Original"
                        # Check if this source already exists to avoid duplicates
                        existing = session_bg.exec(
                            select(VideoSource).where(
                                VideoSource.video_id == video_id,
                                VideoSource.provider == provider,
                                VideoSource.resolution == res
                            )
                        ).first()
                        if existing:
                            logger.info(f"[REPROCESS-{video_id}] Source already exists: {provider} - {res}, skipping")
                            return
                        source = VideoSource(
                            video_id=video_id,
                            provider=provider,
                            resolution=res,
                            file_id=file_id,
                            embed_url=embed_url
                        )
                        session_bg.add(source)
                        session_bg.commit()
                        logger.info(f"[REPROCESS-{video_id}] Source saved: {provider} - {res}")
                
                fast_providers = [p for p in active_providers if p != 'telegram']
                
                # Phase 2: Transcode
                ffmpeg_available = check_ffmpeg_installed()
                if not ffmpeg_available:
                    logger.error(f"[REPROCESS-{video_id}] FFmpeg NOT FOUND! Cannot transcode.")
                    return
                
                logger.info(f"[REPROCESS-{video_id}] Starting transcoding...")
                transcode_output_dir = os.path.join(TRANSCODE_DIR, str(video_id))
                transcoded_files = await loop.run_in_executor(
                    None, lambda: transcode_video(source_file, transcode_output_dir, is_encrypted=False)
                )
                
                if not transcoded_files:
                    logger.warning(f"[REPROCESS-{video_id}] Transcoding returned NO files")
                    return
                
                logger.info(f"[REPROCESS-{video_id}] Transcoding SUCCESS! Created: {list(transcoded_files.keys())}")
                
                # Phase 3: Upload transcoded to fast providers
                for resolution, file_path in transcoded_files.items():
                    res_tasks = []
                    
                    async def st_res_task(res, path):
                        try:
                            st_res_data = await asyncio.wait_for(
                                upload_to_streamtape(path, title=f"{title} {res}"), timeout=300
                            )
                            if st_res_data:
                                save_source("streamtape", res, st_res_data['file_id'], st_res_data['embed_url'])
                        except Exception as e:
                            logger.error(f"[REPROCESS-{video_id}] StreamTape {res} Error: {e}")
                    
                    async def dd_res_task(res, path):
                        try:
                            dd_res_data = await asyncio.wait_for(
                                upload_to_doodstream(path, title=f"{title} {res}"), timeout=300
                            )
                            if dd_res_data:
                                save_source("doodstream", res, dd_res_data['file_id'], dd_res_data['embed_url'])
                        except Exception as e:
                            logger.error(f"[REPROCESS-{video_id}] DoodStream {res} Error: {e}")
                    
                    if 'streamtape' in fast_providers: res_tasks.append(st_res_task(resolution, file_path))
                    if 'doodstream' in fast_providers: res_tasks.append(dd_res_task(resolution, file_path))
                    
                    if res_tasks:
                        await asyncio.gather(*res_tasks)
                    
                    cleanup_file(file_path)
                
                if os.path.exists(transcode_output_dir):
                    shutil.rmtree(transcode_output_dir, ignore_errors=True)
                
                logger.info(f"[REPROCESS-{video_id}] Reprocess complete!")
                # Update status to completed
                with SqlSession(engine) as session_final:
                    v_final = session_final.get(Video, video_id)
                    if v_final:
                        v_final.processing_status = "completed"
                        session_final.add(v_final)
                        session_final.commit()
                
            except Exception as e:
                logger.error(f"[REPROCESS-{video_id}] Error: {e}", exc_info=True)
                with SqlSession(engine) as session_err:
                    v_err = session_err.get(Video, video_id)
                    if v_err:
                        v_err.processing_status = "failed"
                        session_err.add(v_err)
                        session_err.commit()
            # NOTE: Do NOT delete source_file — keep for future reprocessing
        
        try:
            loop.run_until_complete(process_async())
        finally:
            loop.close()
    
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
        is_short=is_short,
        temp_file_path=temp_file_path
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
        video.thumbnail_url = f"/thumbnails/{video.id}{thumb_ext}"
        session.add(video)
        session.commit()
    else:
        # Try local extraction if FFmpeg is available
        first_thumb_path, zip_path = extract_multi_thumbnails(temp_file_path, THUMBNAIL_DIR, video.id, is_encrypted=False)
        if first_thumb_path:
            video.thumbnail_url = f"/thumbnails/{video.id}.jpg"
            session.add(video)
            session.commit()
            logger.info(f"Local multi-thumbnail extraction complete. Created ZIP at {zip_path}")
        else:
            logger.info("Local thumbnail extraction skipped/failed. Waiting for fallback in background task.")

    # Invalidate video list cache to show new video on home page
    from ..services.cache import app_cache
    app_cache.invalidate("videos_skip_0")

    # 5. Hand off EVERYTHING to background task
    background_full_process_task(video.id, temp_file_path, title, original_resolution, active_providers)

    return video


# ============== New Upload Methods ==============

class UrlUploadRequest(BaseModel):
    title: str
    description: Optional[str] = None
    category_id: int
    url: str
    is_short: bool = False
    thumbnail_url: Optional[str] = None

class EmbedUploadRequest(BaseModel):
    title: str
    description: Optional[str] = None
    category_id: int
    embed_code: str
    is_short: bool = False
    thumbnail_url: Optional[str] = None

class RemoteUploadRequest(BaseModel):
    title: str
    description: Optional[str] = None
    category_id: int
    url: str
    is_short: bool = False


def background_remote_upload_task(video_id: int, url: str, title: str, active_providers: List[str]):
    import threading
    def run_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def process_async():
            try:
                logger.info(f"[BG-REMOTE-{video_id}] Starting remote download from {url}")
                from sqlmodel import Session as SqlSession
                from ..models import Video
                
                with SqlSession(engine) as session_init:
                    v_init = session_init.get(Video, video_id)
                    if v_init:
                        v_init.processing_status = "processing"
                        session_init.add(v_init)
                        session_init.commit()

                # Generate a temp file path
                file_extension = ".mp4"
                unique_filename = f"{uuid.uuid4()}{file_extension}"
                temp_file_path = os.path.join(TEMP_DIR, unique_filename)

                # ═══ Use yt-dlp to download HIGH QUALITY video ═══
                # This ensures we get 1080p+ and merged audio/video for YouTube/etc.
                downloaded_via_ytdlp = False
                try:
                    import yt_dlp
                    logger.info(f"[BG-REMOTE-{video_id}] Attempting high-quality download via yt-dlp...")
                    
                    ydl_opts = {
                        'quiet': True,
                        'no_warnings': True,
                        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                        'outtmpl': temp_file_path,
                        'nocheckcertificate': True,
                        'merge_output_format': 'mp4',
                        'socket_timeout': 60,
                    }
                    
                    # Run yt-dlp in a thread-safe way within the loop
                    def ytdl_download():
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            return ydl.extract_info(url, download=True)
                    
                    loop_ytdl = asyncio.get_event_loop()
                    info = await loop_ytdl.run_in_executor(None, ytdl_download)
                    
                    if os.path.exists(temp_file_path) and os.path.getsize(temp_file_path) > 1000:
                        downloaded_via_ytdlp = True
                        logger.info(f"[BG-REMOTE-{video_id}] yt-dlp download success.")
                        
                        # Extract duration if available
                        video_duration = int(info.get('duration', 0) or 0)
                        if video_duration > 0:
                            with SqlSession(engine) as s_dur:
                                v_dur = s_dur.get(Video, video_id)
                                if v_dur and v_dur.duration == 0:
                                    v_dur.duration = video_duration
                                    s_dur.add(v_dur)
                                    s_dur.commit()
                    else:
                        logger.warning(f"[BG-REMOTE-{video_id}] yt-dlp completed but output file missing or empty.")
                                
                except Exception as yt_err:
                    logger.warning(f"[BG-REMOTE-{video_id}] yt-dlp download failed, falling back to direct URL: {str(yt_err)[:200]}")

                # ═══ Fallback: Direct Download with httpx ═══
                if not downloaded_via_ytdlp:
                    logger.info(f"[BG-REMOTE-{video_id}] Downloading via httpx (fallback)...")
                    async with httpx.AsyncClient(timeout=600, follow_redirects=True, verify=False) as client:
                        async with client.stream("GET", url, headers={
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                        }) as response:
                            response.raise_for_status()
                            with open(temp_file_path, "wb") as f:
                                async for chunk in response.aiter_bytes(chunk_size=1024*1024):
                                    f.write(chunk)
                                    
                logger.info(f"[BG-REMOTE-{video_id}] Download complete. Detecting resolution...")
                
                # Detect resolution of downloaded file to ensure transcoding works correctly
                detected_resolution = "unknown"
                if check_ffmpeg_installed():
                    loop_sync = asyncio.get_event_loop()
                    try:
                        info = await loop_sync.run_in_executor(None, lambda: get_video_info(temp_file_path, is_encrypted=False))
                        if info:
                            detected_resolution = info.get("resolution", "unknown")
                            logger.info(f"[BG-REMOTE-{video_id}] Detected resolution: {detected_resolution}")
                    except Exception as e:
                        logger.warning(f"[BG-REMOTE-{video_id}] Failed to detect resolution: {e}")

                # Hand off to the regular background task
                background_full_process_task(video_id, temp_file_path, title, detected_resolution, active_providers)

            except Exception as e:
                logger.error(f"[BG-REMOTE-{video_id}] Error: {e}")
                from sqlmodel import Session as SqlSession
                from ..models import Video
                with SqlSession(engine) as session_err:
                    v_err = session_err.get(Video, video_id)
                    if v_err:
                        v_err.processing_status = "failed"
                        session_err.add(v_err)
                        session_err.commit()

        try:
            loop.run_until_complete(process_async())
        finally:
            loop.close()
    
    threading.Thread(target=run_in_thread, daemon=True).start()


@router.post("/url")
async def upload_by_url(
    title: str = Form(...),
    url: str = Form(...),
    description: Optional[str] = Form(None),
    category_id: int = Form(...),
    is_short: bool = Form(False),
    duration: int = Form(0),
    thumbnail_url: Optional[str] = Form(None),
    thumbnail: UploadFile = File(None),
    current_user: User = Depends(require_user),
    session: Session = Depends(get_session)
):
    video = Video(
        title=title,
        description=description,
        category_id=category_id,
        uploader_id=current_user.id,
        storage_mode="direct_url",
        duration=duration,
        original_resolution="unknown",
        is_short=is_short,
        direct_url=url,
        thumbnail_url=thumbnail_url,
        processing_status="completed" # No processing needed
    )
    session.add(video)
    session.commit()
    session.refresh(video)
    
    if thumbnail:
        thumb_ext = os.path.splitext(thumbnail.filename)[1] or ".jpg"
        thumb_path = os.path.join(THUMBNAIL_DIR, f"{video.id}{thumb_ext}")
        with open(thumb_path, "wb") as buffer:
            shutil.copyfileobj(thumbnail.file, buffer)
        video.thumbnail_url = f"/thumbnails/{video.id}{thumb_ext}"
        session.add(video)
        session.commit()
    
    from ..services.cache import app_cache
    app_cache.invalidate("videos_skip_0")
    return video

@router.post("/embed")
async def upload_by_embed(
    title: str = Form(...),
    embed_code: str = Form(...),
    description: Optional[str] = Form(None),
    category_id: int = Form(...),
    is_short: bool = Form(False),
    duration: int = Form(0),
    thumbnail_url: Optional[str] = Form(None),
    thumbnail: UploadFile = File(None),
    current_user: User = Depends(require_user),
    session: Session = Depends(get_session)
):
    video = Video(
        title=title,
        description=description,
        category_id=category_id,
        uploader_id=current_user.id,
        storage_mode="embed_code",
        duration=duration,
        original_resolution="unknown",
        is_short=is_short,
        embed_code=embed_code,
        thumbnail_url=thumbnail_url,
        processing_status="completed"
    )
    session.add(video)
    session.commit()
    session.refresh(video)
    
    if thumbnail:
        thumb_ext = os.path.splitext(thumbnail.filename)[1] or ".jpg"
        thumb_path = os.path.join(THUMBNAIL_DIR, f"{video.id}{thumb_ext}")
        with open(thumb_path, "wb") as buffer:
            shutil.copyfileobj(thumbnail.file, buffer)
        video.thumbnail_url = f"/thumbnails/{video.id}{thumb_ext}"
        session.add(video)
        session.commit()
    
    from ..services.cache import app_cache
    app_cache.invalidate("videos_skip_0")
    return video

@router.post("/remote")
async def upload_remote(
    title: str = Form(...),
    url: str = Form(...),
    description: Optional[str] = Form(None),
    category_id: int = Form(...),
    is_short: bool = Form(False),
    duration: int = Form(0),
    thumbnail_url: Optional[str] = Form(None),
    thumbnail: UploadFile = File(None),
    current_user: User = Depends(require_user),
    session: Session = Depends(get_session)
):
    from .admin import load_settings
    settings = load_settings()
    active_providers = [k for k, v in settings.storage_providers.items() if v['enabled']]
    if not active_providers:
        active_providers = ['telegram']

    video = Video(
        title=title,
        description=description,
        category_id=category_id,
        uploader_id=current_user.id,
        storage_mode="multi",
        duration=duration,
        original_resolution="unknown",
        is_short=is_short,
        thumbnail_url=thumbnail_url,
        processing_status="pending"
    )
    session.add(video)
    session.commit()
    session.refresh(video)
    
    if thumbnail:
        thumb_ext = os.path.splitext(thumbnail.filename)[1] or ".jpg"
        thumb_path = os.path.join(THUMBNAIL_DIR, f"{video.id}{thumb_ext}")
        with open(thumb_path, "wb") as buffer:
            shutil.copyfileobj(thumbnail.file, buffer)
        video.thumbnail_url = f"/thumbnails/{video.id}{thumb_ext}"
        session.add(video)
        session.commit()
    
    from ..services.cache import app_cache
    app_cache.invalidate("videos_skip_0")
    
    background_remote_upload_task(video.id, url, title, active_providers)
    
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


@router.post("/generate-thumbnail")
async def generate_thumbnail_from_url(
    url: str = Form(...),
    current_user: Optional[User] = Depends(get_current_user)
):
    """
    Generate a thumbnail from ANY video URL using a tiered approach:
    1. yt-dlp: Extracts thumbnail from 1000+ supported sites (YouTube, PornHub, XVideos, etc.)
    2. FFmpeg: Falls back to frame extraction for direct video file URLs (.mp4, .webm)
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Validate URL
    if not url.startswith(('http://', 'https://')):
        raise HTTPException(status_code=400, detail="Invalid URL. Must start with http:// or https://")
    
    temp_thumb_path = os.path.join(THUMBNAIL_DIR, f"temp_thumb_{uuid.uuid4().hex}.jpg")
    video_title = ""  # Will be populated by yt-dlp if available
    video_duration = 0  # Will be populated by yt-dlp if available
    
    try:
        import subprocess
        from urllib.parse import quote
        
        logger.info(f"Generating thumbnail from URL: {url}")
        
        # ═══ Strategy 1: yt-dlp (supports 1000+ websites) ═══
        # Works with: YouTube, Facebook, Instagram, Twitter/X, PornHub, XVideos,
        # XHamster, Hanime, Pixeldrain, Dailymotion, Vimeo, and many more
        try:
            import yt_dlp
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,        # Don't download the video
                'writesubtitles': False,
                'writethumbnail': False,       # We'll download manually
                'socket_timeout': 10,
                'extract_flat': False,
                'nocheckcertificate': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if info:
                    # Extract title and duration
                    video_title = info.get('title', '') or info.get('fulltitle', '') or ''
                    video_duration = int(info.get('duration', 0) or 0)
                    logger.info(f"yt-dlp found title: {video_title}, duration: {video_duration}s")
                    
                    thumb_url = info.get('thumbnail')
                    
                    # If no single thumbnail, try thumbnails list
                    if not thumb_url and info.get('thumbnails'):
                        # Get highest quality thumbnail
                        thumbs = sorted(
                            info['thumbnails'],
                            key=lambda t: (t.get('preference', 0), t.get('width', 0)),
                            reverse=True
                        )
                        if thumbs:
                            thumb_url = thumbs[0].get('url')
                    
                    if thumb_url:
                        logger.info(f"yt-dlp found thumbnail: {thumb_url}")
                        
                        # Download the thumbnail image
                        async with httpx.AsyncClient(timeout=10, follow_redirects=True, verify=False) as client:
                            resp = await client.get(thumb_url, headers={
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                            })
                            
                            if resp.status_code == 200 and len(resp.content) > 1000:
                                # Save raw thumbnail
                                raw_thumb = temp_thumb_path + ".raw"
                                with open(raw_thumb, 'wb') as f:
                                    f.write(resp.content)
                                
                                # Convert/resize to standard JPEG using FFmpeg
                                if check_ffmpeg_installed():
                                    resize_cmd = [
                                        "ffmpeg", "-i", raw_thumb,
                                        "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
                                        "-q:v", "2", "-y", temp_thumb_path
                                    ]
                                    resize_result = subprocess.run(resize_cmd, capture_output=True, text=True, timeout=10)
                                    if os.path.exists(raw_thumb):
                                        os.remove(raw_thumb)
                                    
                                    if resize_result.returncode == 0 and os.path.exists(temp_thumb_path) and os.path.getsize(temp_thumb_path) > 0:
                                        logger.info("yt-dlp thumbnail resized successfully")
                                        from fastapi.responses import FileResponse
                                        resp = FileResponse(temp_thumb_path, media_type="image/jpeg", filename="auto_thumbnail.jpg")
                                        if video_title:
                                            resp.headers["X-Video-Title"] = quote(video_title, safe='')
                                        if video_duration:
                                            resp.headers["X-Video-Duration"] = str(video_duration)
                                        return resp
                                
                                # If FFmpeg resize fails, just use the raw thumbnail
                                if os.path.exists(raw_thumb) and os.path.getsize(raw_thumb) > 0:
                                    os.rename(raw_thumb, temp_thumb_path)
                                    from fastapi.responses import FileResponse
                                    resp = FileResponse(temp_thumb_path, media_type="image/jpeg", filename="auto_thumbnail.jpg")
                                    if video_title:
                                        resp.headers["X-Video-Title"] = quote(video_title, safe='')
                                    if video_duration:
                                        resp.headers["X-Video-Duration"] = str(video_duration)
                                    return resp
                        
                        logger.warning(f"yt-dlp thumbnail URL download failed for: {thumb_url}")
                    else:
                        logger.warning("yt-dlp extracted info but no thumbnail URL found")
                        
        except ImportError:
            logger.warning("yt-dlp not installed, skipping...")
        except Exception as yt_err:
            logger.warning(f"yt-dlp extraction failed (will try FFmpeg): {str(yt_err)[:200]}")
        
        # ═══ Strategy 2: FFmpeg direct frame extraction ═══
        # Works with direct video file URLs (.mp4, .webm, .m3u8, etc.)
        if check_ffmpeg_installed():
            logger.info("Trying FFmpeg direct frame extraction...")
            cmd = [
                "ffmpeg",
                "-ss", "1",
                "-i", url,
                "-vframes", "1",
                "-q:v", "2",
                "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
                "-y",
                temp_thumb_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            
            if result.returncode == 0 and os.path.exists(temp_thumb_path) and os.path.getsize(temp_thumb_path) > 0:
                logger.info("FFmpeg thumbnail generated successfully")
                from fastapi.responses import FileResponse
                return FileResponse(temp_thumb_path, media_type="image/jpeg", filename="auto_thumbnail.jpg")
                # Note: FFmpeg can't extract titles from raw video files
            else:
                logger.warning(f"FFmpeg also failed: {result.stderr[:200] if result.stderr else 'unknown error'}")
        
        # Both strategies failed
        raise HTTPException(
            status_code=422,
            detail="Could not extract thumbnail. The URL may be unsupported or inaccessible."
        )
        
    except subprocess.TimeoutExpired:
        if os.path.exists(temp_thumb_path):
            os.remove(temp_thumb_path)
        raise HTTPException(status_code=408, detail="Thumbnail generation timed out.")
    
    except HTTPException:
        if os.path.exists(temp_thumb_path):
            os.remove(temp_thumb_path)
        raise
    
    except Exception as e:
        logger.error(f"Unexpected error generating thumbnail: {e}")
        if os.path.exists(temp_thumb_path):
            os.remove(temp_thumb_path)
        raise HTTPException(status_code=500, detail=f"Failed to generate thumbnail: {str(e)}")

@router.post("/cloud-link")
async def upload_cloud_link(
    url: str = Form(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    category_id: int = Form(...),
    is_short: bool = Form(False),
    thumbnail_url: Optional[str] = Form(None),
    duration: int = Form(0),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Zero-resource upload: Triggers Remote Download on StreamTape and DoodStream.
    No local bandwidth or disk used for the video itself.
    """
    logger.info(f"Cloud-link upload request: {url}")
    
    # 1. Resolve URL and Metadata via yt-dlp
    download_url = url
    extracted_title = title
    extracted_duration = duration
    extracted_thumbnail = thumbnail_url

    try:
        import yt_dlp
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'socket_timeout': 15,
            'nocheckcertificate': True,
            'format': 'best[ext=mp4]/best',
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                # Resolve best stream URL
                resolved = info.get('url')
                if not resolved and info.get('formats'):
                    mp4_formats = [f for f in info['formats'] if f.get('ext') == 'mp4' and f.get('url')]
                    if mp4_formats:
                        mp4_formats.sort(key=lambda f: (f.get('filesize') or 0, f.get('tbr') or 0), reverse=True)
                        resolved = mp4_formats[0]['url']
                
                if resolved:
                    download_url = resolved
                    
                if not extracted_title:
                    extracted_title = info.get('title')
                if extracted_duration == 0:
                    extracted_duration = int(info.get('duration', 0) or 0)
                if not extracted_thumbnail:
                    extracted_thumbnail = info.get('thumbnail')
                    
    except Exception as e:
        logger.warning(f"Metadata extraction failed: {e}")

    # 2. Add to Database
    video = Video(
        title=extracted_title or "Untitled Cloud Video",
        description=description,
        category_id=category_id,
        storage_mode="cloud",
        processing_status="processing",
        thumbnail_url=extracted_thumbnail,
        duration=extracted_duration,
        is_short=is_short,
        views=0,
        direct_url=None,
        embed_code=None
    )
    session.add(video)
    session.commit()
    session.refresh(video)

    # 3. Trigger Remote DLs
    async def trigger_remotes(vid_id: int, d_url: str):
        st_success = False
        dd_success = False
        
        try:
            # Parallel trigger
            logger.info(f"[CLOUD-{vid_id}] Triggering StreamTape and DoodStream Remote DL...")
            
            async def st_task():
                nonlocal st_success
                try:
                    st_res = await remotedl_to_streamtape(d_url, extracted_title)
                    with Session(engine) as s1:
                        from ..models import VideoSource
                        source = VideoSource(
                            video_id=vid_id,
                            provider="streamtape",
                            file_id=st_res['remote_id'],
                            external_id=st_res['remote_id'],
                            embed_url=f"https://streamtape.com/e/{st_res['remote_id']}/",
                            resolution="original"
                        )
                        s1.add(source)
                        s1.commit()
                    st_success = True
                    logger.info(f"[CLOUD-{vid_id}] StreamTape Remote DL triggered: {st_res['remote_id']}")
                except Exception as e:
                    logger.error(f"[CLOUD-{vid_id}] StreamTape Cloud Error: {e}")

            async def dd_task():
                nonlocal dd_success
                try:
                    dd_res = await remotedl_to_doodstream(d_url, extracted_title)
                    with Session(engine) as s1:
                        from ..models import VideoSource
                        source = VideoSource(
                            video_id=vid_id,
                            provider="doodstream",
                            file_id=dd_res['remote_id'],
                            external_id=dd_res['remote_id'],
                            embed_url=f"https://dood.li/e/{dd_res['remote_id']}",
                            resolution="original"
                        )
                        s1.add(source)
                        s1.commit()
                    dd_success = True
                    logger.info(f"[CLOUD-{vid_id}] DoodStream Remote DL triggered: {dd_res['remote_id']}")
                except Exception as e:
                    logger.error(f"[CLOUD-{vid_id}] DoodStream Cloud Error: {e}")

            await asyncio.gather(st_task(), dd_task())

            # Update overall status
            with Session(engine) as s_final:
                v = s_final.get(Video, vid_id)
                if v:
                    if st_success or dd_success:
                        v.processing_status = "completed"
                    else:
                        v.processing_status = "failed"
                    s_final.add(v)
                    s_final.commit()
                    
        except Exception as e:
            logger.error(f"Cloud-link remote trigger task error for video {vid_id}: {e}")
            with Session(engine) as s_err:
                v = s_err.get(Video, vid_id)
                if v:
                    v.processing_status = "failed"
                    s_err.add(v)
                    s_err.commit()

    asyncio.create_task(trigger_remotes(video.id, download_url))

    return {"status": "success", "video_id": video.id, "message": "Remote upload triggered"}
