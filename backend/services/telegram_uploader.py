import os
import asyncio
from telegram import Bot, InputFile
from telegram.error import TelegramError
from dotenv import load_dotenv
from pathlib import Path
from .crypto import DecryptedReader

# Load .env from backend directory
env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

print(f"[TelegramUploader] TOKEN loaded: {'Yes' if TOKEN else 'No'}, CHANNEL_ID: {CHANNEL_ID}")

async def upload_video_to_telegram(file_path: str, caption: str = "", is_encrypted: bool = True):
    """
    Uploads a video to the configured Telegram channel.
    Returns a dictionary with file_id and other metadata upon success.
    """
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set")
    # Channel ID validation is loose as it can be string or int
    
    bot = Bot(token=TOKEN)
    
    try:
        print(f"Uploading video {file_path} to Telegram channel {CHANNEL_ID} (Encrypted: {is_encrypted})...")
        
        if is_encrypted:
            # Use DecryptedReader to read encryptd file on-the-fly
            f_ctx = DecryptedReader(file_path)
        else:
            # Regular open
            f_ctx = open(file_path, 'rb')

        # Send video - timeout increased for larger files
        with f_ctx as video_file:
            message = await bot.send_video(
                chat_id=CHANNEL_ID,
                video=video_file,
                caption=caption,
                supports_streaming=True,
                read_timeout=3600, 
                write_timeout=3600,
                connect_timeout=60,
                pool_timeout=3600
            )
            
        video = message.video
        if not video:
             raise ValueError("Message sent but no video content found (unexpected)")

        return {
            "channel_message_id": message.message_id,
            "file_id": video.file_id,
            "file_unique_id": video.file_unique_id,
            "file_size": video.file_size,
            "mime_type": video.mime_type,
            "duration": video.duration,
            "width": video.width,
            "height": video.height
        }

    except TelegramError as e:
        print(f"Telegram API Error: {e}")
        raise e
    except Exception as e:
        print(f"Upload Error: {e}")
        raise e


async def upload_photo_to_telegram(file_path: str, caption: str = ""):
    """
    Uploads a photo to the configured Telegram channel.
    Returns a dictionary with file_id and other metadata upon success.
    """
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set")
    
    bot = Bot(token=TOKEN)
    
    try:
        print(f"Uploading photo {file_path} to Telegram channel {CHANNEL_ID} (Decrypted)...")
        
        with DecryptedReader(file_path) as photo_file:
            message = await bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=photo_file,
                caption=caption,
                read_timeout=60,
                write_timeout=60,
                connect_timeout=60
            )
            
        photo = message.photo[-1] # Get the largest size
        if not photo:
             raise ValueError("Message sent but no photo content found")

        return {
            "channel_message_id": message.message_id,
            "file_id": photo.file_id,
            "file_unique_id": photo.file_unique_id,
            "file_size": photo.file_size,
            "width": photo.width,
            "height": photo.height
        }

    except TelegramError as e:
        print(f"Telegram API Error (Photo): {e}")
        raise e
    except Exception as e:
        print(f"Photo Upload Error: {e}")
        raise e

async def get_telegram_file_bytes(file_id: str):
    """
    Downloads file content from Telegram.
    """
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set")
    
    bot = Bot(token=TOKEN)
    try:
        new_file = await bot.get_file(file_id)
        # download_as_bytearray is the method in newer versions, or download_to_memory
        # checking python-telegram-bot docs, download_as_bytearray is widely supported
        return await new_file.download_as_bytearray()
    except Exception as e:
        print(f"Download Error: {e}")
        return None

if __name__ == "__main__":
    # Test block
    import sys
    if len(sys.argv) > 1:
        test_file = sys.argv[1]
        asyncio.run(upload_video_to_telegram(test_file, "Test Upload"))
    else:
        print("Usage: python telegram_uploader.py <path_to_video>")
