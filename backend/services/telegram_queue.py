"""
Telegram Upload Queue — processes Telegram uploads one-at-a-time in background.

Fast providers (StreamTape, DoodStream) upload immediately.
Telegram uploads are queued here and processed sequentially to avoid
timeouts, rate limits, and resource contention.
"""
import asyncio
import logging
import os
import shutil
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class TelegramUploadJob:
    """A single Telegram upload job."""
    video_id: int
    file_path: str
    title: str
    resolution: str
    caption: str
    is_original: bool = True
    # If True, this file is a temp copy that should be deleted after upload
    cleanup_after: bool = False


class TelegramUploadQueue:
    """
    Background queue that processes Telegram uploads one at a time.
    Runs as an asyncio task in the main event loop.
    """
    
    def __init__(self):
        self._queue: asyncio.Queue[TelegramUploadJob] = asyncio.Queue()
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._current_job: Optional[TelegramUploadJob] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    def start(self):
        """Start the background worker. Call this from the FastAPI startup event."""
        if self._running:
            return
        self._running = True
        self._loop = asyncio.get_running_loop()
        self._worker_task = asyncio.create_task(self._worker())
        logger.info("[TelegramQueue] Worker started")
    
    def stop(self):
        """Stop the background worker."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            logger.info("[TelegramQueue] Worker stopped")
    
    @property
    def pending_count(self) -> int:
        return self._queue.qsize()
    
    @property
    def current_job(self) -> Optional[TelegramUploadJob]:
        return self._current_job
    
    def enqueue(self, job: TelegramUploadJob):
        """Add an upload job to the queue. Thread-safe for calls from background threads."""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
            
        if self._loop and current_loop != self._loop:
            # We are calling from a different thread/loop, use threadsafe
            self._loop.call_soon_threadsafe(self._queue.put_nowait, job)
        else:
            self._queue.put_nowait(job)
            
        logger.info(f"[TelegramQueue] Enqueued via {'threadsafe ' if self._loop and current_loop != self._loop else ''}put: video_id={job.video_id}, "
                    f"res={job.resolution}, queue_size={self._queue.qsize()}")
    
    async def _worker(self):
        """Process jobs one at a time."""
        from .telegram_uploader import upload_video_to_telegram
        from ..database import engine
        from sqlmodel import Session as SqlSession
        from ..models import VideoSource, TelegramInfo, Video
        
        logger.info("[TelegramQueue] Worker loop started, waiting for jobs...")
        
        while self._running:
            try:
                # Wait for next job (blocks until available)
                job = await self._queue.get()
                self._current_job = job
                
                logger.info(f"[TelegramQueue] Processing: video_id={job.video_id}, "
                           f"res={job.resolution}, file={job.file_path}")
                
                if not os.path.exists(job.file_path):
                    logger.error(f"[TelegramQueue] File not found: {job.file_path}")
                    self._queue.task_done()
                    self._current_job = None
                    continue
                
                try:
                    # Upload to Telegram (no timeout — let it run as long as needed)
                    data = await upload_video_to_telegram(
                        job.file_path,
                        caption=job.caption,
                        is_encrypted=False
                    )
                    
                    # Save to database
                    with SqlSession(engine) as session_bg:
                        if job.is_original:
                            # Save TelegramInfo for original uploads
                            tg_info = TelegramInfo(
                                video_id=job.video_id,
                                file_id=data["file_id"],
                                file_unique_id=data["file_unique_id"],
                                file_size=data["file_size"],
                                mime_type=data["mime_type"],
                                channel_message_id=data["channel_message_id"]
                            )
                            session_bg.add(tg_info)
                        
                        # Save to VideoResolution table (this is what the API uses for quality options)
                        res_val = job.resolution
                        if not res_val or res_val == "unknown":
                            v_rec = session_bg.get(Video, job.video_id)
                            res_val = v_rec.original_resolution if v_rec else "Original"
                        
                        # Add/Update VideoResolution entry
                        existing_res = session_bg.exec(
                            select(VideoResolution).where(
                                VideoResolution.video_id == job.video_id,
                                VideoResolution.resolution == res_val
                            )
                        ).first()

                        if not existing_res:
                            new_res = VideoResolution(
                                video_id=job.video_id,
                                resolution=res_val,
                                file_id=data["file_id"],
                                file_unique_id=data["file_unique_id"],
                                file_size=data["file_size"],
                                channel_message_id=data["channel_message_id"]
                            )
                            session_bg.add(new_res)
                        
                        # Also save to VideoSource table for unified access
                        source = VideoSource(
                            video_id=job.video_id,
                            provider="telegram",
                            resolution=res_val,
                            file_id=data["file_id"]
                        )
                        session_bg.add(source)
                        session_bg.commit()
                    
                    logger.info(f"[TelegramQueue] SUCCESS: video_id={job.video_id}, "
                               f"res={job.resolution}, msg_id={data.get('channel_message_id')}")
                
                except Exception as e:
                    logger.error(f"[TelegramQueue] FAILED: video_id={job.video_id}, "
                                f"res={job.resolution}, error={e}")
                
                finally:
                    # Cleanup temp file if needed
                    if job.cleanup_after and os.path.exists(job.file_path):
                        try:
                            os.remove(job.file_path)
                            logger.info(f"[TelegramQueue] Cleaned up: {job.file_path}")
                        except Exception:
                            pass
                    
                    self._queue.task_done()
                    self._current_job = None
                    
                    # Small delay between uploads to avoid rate limits
                    await asyncio.sleep(2)
            
            except asyncio.CancelledError:
                logger.info("[TelegramQueue] Worker cancelled")
                break
            except Exception as e:
                logger.error(f"[TelegramQueue] Worker error: {e}", exc_info=True)
                await asyncio.sleep(5)  # Wait before retrying


# Global singleton
telegram_queue = TelegramUploadQueue()
