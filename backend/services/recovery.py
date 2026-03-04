import os
import logging
import asyncio
from sqlmodel import Session, select
from ..database import engine
from ..models import Video, VideoSource
from ..routers.upload import transcode_only_task, TEMP_DIR

logger = logging.getLogger(__name__)

async def recover_incomplete_tasks():
    """
    Scans the database for videos that were interrupted during processing
    and restarts the transcoding/upload process if the source file still exists.
    """
    logger.info("[Recovery] Checking for incomplete tasks...")
    
    with Session(engine) as session:
        # Look for videos that are NOT 'completed' and are 'multi' storage
        statement = select(Video).where(
            Video.storage_mode == "multi",
            Video.processing_status.in_(["pending", "processing"])
        )
        incomplete_videos = session.exec(statement).all()
        
        if not incomplete_videos:
            logger.info("[Recovery] No incomplete tasks found.")
            return

        logger.info(f"[Recovery] Found {len(incomplete_videos)} incomplete tasks.")
        
        # Load settings for providers
        from ..routers.admin import load_settings
        settings = load_settings()
        active_providers = [k for k, v in settings.storage_providers.items() if v['enabled']]
        if not active_providers:
            active_providers = ['telegram']

        for video in incomplete_videos:
            if not video.temp_file_path:
                logger.warning(f"[Recovery] Video {video.id} has no temp_file_path, cannot auto-resume.")
                continue
                
            if not os.path.exists(video.temp_file_path):
                logger.error(f"[Recovery] Source file for Video {video.id} NOT FOUND at {video.temp_file_path}. Task failed.")
                video.processing_status = "failed"
                session.add(video)
                continue

            logger.info(f"[Recovery] Resuming task for Video {video.id}: {video.title}")
            # Re-trigger transcoding and upload
            # Note: transcode_only_task runs in a background thread
            transcode_only_task(
                video_id=video.id,
                source_file=video.temp_file_path,
                title=video.title,
                original_resolution=video.original_resolution or "unknown",
                active_providers=active_providers
            )
        
        session.commit()
    logger.info("[Recovery] Task recovery check complete.")
