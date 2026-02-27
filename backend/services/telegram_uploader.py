"""
Telegram Uploader Service using Telethon (MTProto).
Supports uploading files up to 2GB via Telegram's MTProto API.
Uses bot token authentication with API ID/Hash for large file support.
Credentials are read dynamically from environment variables.
"""
import os
import asyncio
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.setLevel(logging.INFO)
    f_handler = logging.FileHandler('backend/upload_debug.log')
    f_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    f_handler.setFormatter(formatter)
    logger.addHandler(f_handler)
    s_handler = logging.StreamHandler()
    s_handler.setFormatter(formatter)
    logger.addHandler(s_handler)

# --- Telethon Client (Lazy Singleton) ---
_client = None
_client_lock = asyncio.Lock()
_channel_entity = None  # Cached resolved channel entity
_current_token = None   # Track which token the client was created with

async def _get_client():
    """Get or create a Telethon client. Reads credentials from env at call time."""
    global _client, _channel_entity, _current_token
    
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    channel_id_str = os.getenv("TELEGRAM_CHANNEL_ID")
    
    logger.info(f"[TelegramUploader] Credentials: TOKEN={'Yes' if token else 'No'}, "
                f"API_ID={'Yes' if api_id else 'No'}, "
                f"API_HASH={'Yes' if api_hash else 'No'}, "
                f"CHANNEL_ID={channel_id_str}")
    
    # Fast path without lock
    if _client is not None and _client.is_connected() and _current_token == token:
        return _client
    
    async with _client_lock:
        # Double-check after acquiring lock
        if _client is not None and _client.is_connected() and _current_token == token:
            return _client
        
        # If token changed, disconnect old client
        if _client is not None and _current_token != token:
            logger.info("[TelegramUploader] Token changed, reconnecting...")
            try:
                await _client.disconnect()
            except Exception:
                pass
            _client = None
            _channel_entity = None
        
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN is not set")
        if not api_id:
            raise ValueError("TELEGRAM_API_ID is not set (required for large file uploads)")
        if not api_hash:
            raise ValueError("TELEGRAM_API_HASH is not set (required for large file uploads)")
        
        from telethon import TelegramClient
        
        # Session file stored in backend directory
        session_path = str(Path(__file__).resolve().parent.parent / 'bot_session')
        
        _client = TelegramClient(
            session_path,
            int(api_id),
            api_hash,
            timeout=120,
            request_retries=3,
            connection_retries=3,
            retry_delay=2,
            flood_sleep_threshold=60,  # Auto-sleep on rate limits up to 60s
            use_ipv6=False,            # Avoid IPv6 fallback delays
        )
        
        await _client.start(bot_token=token)
        _current_token = token
        logger.info("[TelegramUploader] Telethon client connected successfully!")
        
        # Pre-resolve the channel entity so send_file works
        if channel_id_str:
            try:
                channel_id = _parse_channel_id(channel_id_str)
                _channel_entity = await _client.get_entity(channel_id)
                logger.info(f"[TelegramUploader] Channel entity resolved: {getattr(_channel_entity, 'title', channel_id)}")
            except Exception as e:
                logger.error(f"[TelegramUploader] Failed to resolve channel entity: {e}")
                _channel_entity = None
        
        return _client


async def _get_channel_entity():
    """Get the resolved channel entity, resolving it if needed."""
    global _channel_entity
    
    if _channel_entity is not None:
        return _channel_entity
    
    client = await _get_client()
    channel_id_str = os.getenv("TELEGRAM_CHANNEL_ID")
    channel_id = _parse_channel_id(channel_id_str)
    _channel_entity = await client.get_entity(channel_id)
    return _channel_entity


def _parse_channel_id(channel_id_str: str) -> int:
    """Parse channel ID string to integer, handling various formats."""
    try:
        cid = int(channel_id_str.strip())
        return cid
    except (ValueError, AttributeError) as e:
        raise ValueError(f"Invalid TELEGRAM_CHANNEL_ID: '{channel_id_str}' - {e}")


async def upload_video_to_telegram(file_path: str, caption: str = "", is_encrypted: bool = True):
    """
    Uploads a video to the configured Telegram channel using Telethon.
    Supports files up to 2GB.
    Returns a dictionary with file_id and other metadata upon success.
    """
    if not os.getenv("TELEGRAM_CHANNEL_ID"):
        raise ValueError("TELEGRAM_CHANNEL_ID is not set")
    
    client = await _get_client()
    entity = await _get_channel_entity()
    
    try:
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        logger.info(f"Uploading video {file_path} ({file_size_mb:.1f} MB) to Telegram channel (Encrypted: {is_encrypted})...")
        
        if is_encrypted:
            from .crypto import DecryptedReader
            # Decrypt to a temp file first since Telethon needs seekable file
            import uuid
            temp_dir = os.path.dirname(file_path)
            temp_path = os.path.join(temp_dir, f"temp_tg_dec_{uuid.uuid4()}.mp4")
            try:
                with DecryptedReader(file_path) as reader:
                    with open(temp_path, 'wb') as f:
                        while True:
                            chunk = reader.read(1024 * 1024)  # 1MB chunks
                            if not chunk:
                                break
                            f.write(chunk)
                upload_path = temp_path
            except Exception as e:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                raise e
        else:
            upload_path = file_path
            temp_path = None
        
        try:
            # Upload with progress callback for logging
            _last_logged_pct = -10  # Track last logged percentage
            
            async def progress_callback(current, total):
                nonlocal _last_logged_pct
                if total > 0:
                    pct = int(current / total * 100)
                    # Only log every 10% to reduce I/O overhead
                    if pct >= _last_logged_pct + 10:
                        _last_logged_pct = pct
                        logger.info(f"  Upload progress: {pct}% ({current / 1024 / 1024:.1f} / {total / 1024 / 1024:.1f} MB)")
            
            # Step 1: Upload the file with max chunk size for speed
            file_size = os.path.getsize(upload_path)
            uploaded_file = await client.upload_file(
                upload_path,
                part_size_kb=512,  # Max chunk size (512KB) for fewer requests
                file_size=file_size,
                file_name=os.path.basename(upload_path),
                progress_callback=progress_callback,
            )
            
            # Step 2: Send the already-uploaded file to channel
            message = await client.send_file(
                entity,
                uploaded_file,
                caption=caption,
                supports_streaming=True,
                force_document=False,     # Send as video, not document
            )
            
            # Extract video metadata from the message
            if message.video:
                video = message.video
                result = {
                    "channel_message_id": message.id,
                    "file_id": str(video.id),  # Telethon uses numeric IDs
                    "file_unique_id": f"{video.id}_{video.access_hash}",
                    "file_size": video.size,
                    "mime_type": video.mime_type,
                    "duration": getattr(video, 'duration', None),
                    "width": getattr(video.attributes[0], 'w', 0) if video.attributes else 0,
                    "height": getattr(video.attributes[0], 'h', 0) if video.attributes else 0,
                }
            elif message.document:
                doc = message.document
                result = {
                    "channel_message_id": message.id,
                    "file_id": str(doc.id),
                    "file_unique_id": f"{doc.id}_{doc.access_hash}",
                    "file_size": doc.size,
                    "mime_type": doc.mime_type,
                    "duration": None,
                    "width": 0,
                    "height": 0,
                }
            else:
                raise ValueError("Message sent but no video/document content found")
            
            logger.info(f"Upload successful! Message ID: {message.id}, File size: {result.get('file_size', 'unknown')}")
            return result
            
        finally:
            # Clean up decrypted temp file
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
    
    except Exception as e:
        logger.error(f"Telegram Upload Error: {e}", exc_info=True)
        raise e


async def upload_photo_to_telegram(file_path: str, caption: str = ""):
    """
    Uploads a photo to the configured Telegram channel using Telethon.
    Returns a dictionary with file_id and other metadata upon success.
    """
    if not os.getenv("TELEGRAM_CHANNEL_ID"):
        raise ValueError("TELEGRAM_CHANNEL_ID is not set")
    
    client = await _get_client()
    entity = await _get_channel_entity()
    
    try:
        logger.info(f"Uploading photo {file_path} to Telegram channel...")
        
        message = await client.send_file(
            entity,
            file_path,
            caption=caption,
            force_document=False,
        )
        
        if message.photo:
            photo = message.photo
            # Get the largest size
            largest = photo.sizes[-1] if photo.sizes else None
            
            return {
                "channel_message_id": message.id,
                "file_id": str(photo.id),
                "file_unique_id": f"{photo.id}_{photo.access_hash}",
                "file_size": getattr(largest, 'size', 0) if largest else 0,
                "width": getattr(largest, 'w', 0) if largest else 0,
                "height": getattr(largest, 'h', 0) if largest else 0,
            }
        else:
            raise ValueError("Message sent but no photo content found")

    except Exception as e:
        logger.error(f"Telegram Photo Upload Error: {e}", exc_info=True)
        raise e


async def get_telegram_file_bytes(file_id: str) -> Optional[bytes]:
    """
    Downloads file content from Telegram using Telethon.
    Note: file_id from Telethon is different from Bot API file_id.
    This works with message-based retrieval.
    """
    try:
        client = await _get_client()
        entity = await _get_channel_entity()
        
        # Try to get the message by ID and download the file
        # file_id in our DB is the Telethon document ID as string
        # For direct download, we need the message
        message = await client.get_messages(entity, ids=int(file_id))
        if message and message.media:
            return await client.download_media(message, bytes)
        
        logger.warning(f"Could not find message with ID {file_id}")
        return None
    except Exception as e:
        logger.error(f"Download Error: {e}", exc_info=True)
        return None


if __name__ == "__main__":
    # Test block
    import sys
    if len(sys.argv) > 1:
        test_file = sys.argv[1]
        asyncio.run(upload_video_to_telegram(test_file, "Test Upload", is_encrypted=False))
    else:
        print("Usage: python telegram_uploader.py <path_to_video>")
