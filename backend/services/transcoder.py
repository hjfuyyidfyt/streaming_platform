"""
Video Transcoder Service using FFmpeg.
Handles video resolution detection and transcoding to multiple qualities.
"""
import subprocess
import os
import json
import uuid
import contextlib
from pathlib import Path
from typing import Dict, List, Optional
import logging
from .crypto import decrypt_file_generator

# Explicit file logging for debugging
logger = logging.getLogger(__name__)
f_handler = logging.FileHandler('backend/server_debug.log')
f_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
f_handler.setFormatter(formatter)
logger.addHandler(f_handler)
logger.setLevel(logging.DEBUG)

# Resolution configurations - HIGH quality settings
RESOLUTIONS = {
    "1080p": {"height": 1080, "min_height": 900, "bitrate": "3000k"},
    "720p": {"height": 720, "min_height": 600, "bitrate": "1500k"},
    "480p": {"height": 480, "min_height": 400, "bitrate": "800k"},
    "240p": {"height": 240, "min_height": 200, "bitrate": "300k"},
}

FFMPEG_PRESET = "faster"
FFMPEG_CRF = "26"
FFMPEG_THREADS = "2"

def check_ffmpeg_installed() -> bool:
    """Check if FFmpeg is available on the system."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

@contextlib.contextmanager
def decrypted_temp_file(file_path: str, is_encrypted: bool = True):
    """
    Context manager that decrypts an encrypted file to a temporary file if needed,
    yields the path, and deletes it afterwards.
    """
    if not is_encrypted:
        yield file_path
        return

    temp_dir = os.path.dirname(file_path)
    temp_name = f"temp_dec_{uuid.uuid4()}.mp4"
    temp_path = os.path.join(temp_dir, temp_name)
    
    try:
        # Decrypt to temp file
        logger.info(f"Decrypting {file_path} to temp file: {temp_path}")
        gen = decrypt_file_generator(file_path)
        with open(temp_path, 'wb') as f:
            for chunk in gen:
                f.write(chunk)
        
        yield temp_path
        
    except Exception as e:
        logger.error(f"Error in decrypted_temp_file: {e}")
        raise
    finally:
        # Cleanup
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                logger.info(f"Removed temp file: {temp_path}")
            except Exception as e:
                logger.error(f"Failed to remove temp file {temp_path}: {e}")

def get_video_info(file_path: str, is_encrypted: bool = True) -> Dict:
    """
    Get video metadata using FFprobe.
    """
    try:
        with decrypted_temp_file(file_path, is_encrypted=is_encrypted) as temp_path:
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                temp_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.error(f"FFprobe failed: {result.stderr}")
                return {}
            
            data = json.loads(result.stdout)
            
            # Find video stream
            video_stream = None
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    video_stream = stream
                    break
            
            if not video_stream:
                return {}
            
            width = int(video_stream.get("width", 0))
            height = int(video_stream.get("height", 0))
            duration = float(data.get("format", {}).get("duration", 0))
            
            # Determine resolution label based on ACTUAL height
            resolution = "unknown"
            if height >= 900: resolution = "1080p"
            elif height >= 600: resolution = "720p"
            elif height >= 400: resolution = "480p"
            elif height >= 200: resolution = "240p"
            else: resolution = f"{height}p"
            
            logger.info(f"Detected video: {width}x{height} -> {resolution}")
            
            return {
                "width": width,
                "height": height,
                "resolution": resolution,
                "duration": duration,
                "codec": video_stream.get("codec_name", "unknown"),
            }
            
    except Exception as e:
        logger.error(f"Error getting video info: {e}")
        return {}

import zipfile

def extract_multi_thumbnails(file_path: str, output_dir: str, video_id: int, is_encrypted: bool = True) -> tuple[Optional[str], Optional[str]]:
    """
    Extract 10 thumbnails at regular intervals from the video and package them into a ZIP file.
    Returns (first_thumbnail_path, zip_path) on success, or (None, None) on failure.
    """
    try:
        if not check_ffmpeg_installed():
            logger.warning("FFmpeg not installed, cannot extract thumbnails")
            return None, None

        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Get duration
        v_info = get_video_info(file_path, is_encrypted=is_encrypted)
        duration = float(v_info.get("duration", 0))
        if duration <= 0:
            logger.warning("Could not determine video duration for thumbnail extraction.")
            duration = 10.0 # fallback

        # Calculate 10 timestamps (avoid exact 0 and exact end)
        interval = duration / 11
        timestamps = [interval * i for i in range(1, 11)]

        zip_filename = f"{video_id}_thumbs.zip"
        zip_path = os.path.join(output_dir, zip_filename)
        first_thumb_path = os.path.join(output_dir, f"{video_id}.jpg")
        
        extracted_files = []

        with decrypted_temp_file(file_path, is_encrypted=is_encrypted) as temp_path:
            for i, ts in enumerate(timestamps):
                # Format timestamp to HH:MM:SS.xxx
                hours = int(ts // 3600)
                minutes = int((ts % 3600) // 60)
                seconds = ts % 60
                ts_str = f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"
                
                # First thumbnail is named ID.jpg, others are temp
                if i == 0:
                    out_name = first_thumb_path
                else:
                    out_name = os.path.join(output_dir, f"temp_{video_id}_thumb_{i+1}.jpg")
                
                cmd = [
                    "ffmpeg",
                    "-y",                   # Overwrite output files
                    "-ss", ts_str,          # Seek to position
                    "-i", temp_path,        # Input file
                    "-vframes", "1",        # Output 1 frame
                    "-q:v", "2",            # Quality (lower is better, 2 is good)
                    "-f", "image2",         # Output format
                    out_name
                ]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0 and os.path.exists(out_name):
                    extracted_files.append((out_name, f"thumbnail_{i+1}.jpg"))
                else:
                    logger.warning(f"Failed to extract thumbnail at {ts_str}: {result.stderr}")
        
        if not extracted_files:
            logger.error("Failed to extract any thumbnails.")
            return None, None
            
        # Create ZIP archive
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path_disk, archive_name in extracted_files:
                    zipf.write(file_path_disk, archive_name)
            logger.info(f"Successfully created thumbnail ZIP at {zip_path}")
        except Exception as e:
            logger.error(f"Error creating ZIP file: {e}")
            return None, None
            
        # Cleanup temporary loose thumbnails (keep the first one)
        for file_path_disk, _ in extracted_files:
            if file_path_disk != first_thumb_path and os.path.exists(file_path_disk):
                try:
                    os.remove(file_path_disk)
                except OSError:
                    pass

        return first_thumb_path, zip_path

    except Exception as e:
        logger.error(f"Error extracting multi thumbnails: {e}", exc_info=True)
        return None, None

def get_lower_resolutions(source_resolution: str) -> List[str]:
    """
    Get ALL lower resolutions than source.
    """
    # Resolution hierarchy from highest to lowest
    resolution_order = ["1080p", "720p", "480p", "240p"]
    
    if source_resolution not in resolution_order:
        # Unknown resolution - try to create 480p and 240p
        return ["480p", "240p"]
    
    source_index = resolution_order.index(source_resolution)
    lower_resolutions = resolution_order[source_index + 1:]
    
    logger.info(f"Source: {source_resolution} -> Will create: {lower_resolutions}")
    return lower_resolutions


def transcode_video(
    input_path: str,
    output_dir: str,
    target_resolutions: Optional[List[str]] = None,
    is_encrypted: bool = True
) -> Dict[str, str]:
    """
    Transcode video to multiple resolutions.
    """
    if not check_ffmpeg_installed():
        raise RuntimeError("FFmpeg is not installed. Please install it first.")
    
    # Get source video info (this will do its own temp decrypt if is_encrypted=True)
    video_info = get_video_info(input_path, is_encrypted=is_encrypted)
    if not video_info:
        raise ValueError(f"Could not get video info for {input_path}")
    
    source_resolution = video_info["resolution"]
    logger.info(f"Source video: {source_resolution} ({video_info['width']}x{video_info['height']})")
    
    # Determine target resolutions
    if target_resolutions is None:
        target_resolutions = get_lower_resolutions(source_resolution)
    
    if not target_resolutions:
        logger.info("No lower resolutions to create")
        return {}
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Get base filename
    input_path_obj = Path(input_path)
    base_name = input_path_obj.stem
    
    output_files = {}
    
    # Decrypt ONCE for all transcode operations to save I/O? 
    # Or per operation? Transcoding takes time, keeping temp file is okay.
    # Let's keep it for the duration of all transcodes.
    try:
        with decrypted_temp_file(input_path, is_encrypted=is_encrypted) as temp_source_path:
            
            for res in target_resolutions:
                if res not in RESOLUTIONS:
                    logger.warning(f"Unknown resolution {res}, skipping")
                    continue
                
                res_config = RESOLUTIONS[res]
                output_filename = f"{base_name}_{res}.mp4"
                output_path = os.path.join(output_dir, output_filename)
                
                logger.info(f"Transcoding to {res}...")
                
                target_height = res_config['height']
                
                cmd = [
                    "ffmpeg",
                    "-threads", FFMPEG_THREADS,
                    "-i", temp_source_path, # Read from temp file
                    "-vf", f"scale='trunc(oh*a/2)*2':{target_height}",
                    "-c:v", "libx264",
                    "-preset", FFMPEG_PRESET,
                    "-crf", FFMPEG_CRF,
                    "-maxrate", res_config["bitrate"],
                    "-bufsize", res_config["bitrate"],
                    "-c:a", "aac",
                    "-b:a", "96k",
                    "-ac", "2",
                    "-movflags", "+faststart",
                    "-y",
                    output_path
                ]
                
                try:
                    logger.info(f"Running FFmpeg for {res}...")
                    
                    # No pipe needed
                    result = subprocess.run(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=3600
                    )
                    
                    if result.returncode == 0 and os.path.exists(output_path):
                        file_size = os.path.getsize(output_path)
                        if file_size > 10000:
                            output_files[res] = output_path
                            logger.info(f"Successfully created {res} ({file_size/1024/1024:.1f} MB)")
                        else:
                            logger.error(f"Output file too small ({file_size} bytes)")
                            os.remove(output_path)
                    else:
                        logger.error(f"Failed to create {res}")
                        if result.stderr:
                             # Log last few lines
                             err_lines = result.stderr.decode('utf-8', errors='ignore').split('\n')[-10:]
                             for line in err_lines:
                                 logger.error(f"  FFmpeg: {line}")
                
                except subprocess.TimeoutExpired:
                    logger.error(f"Timeout while creating {res}")
                except Exception as e:
                    logger.error(f"Error creating {res}: {e}")
                    
    except Exception as e:
        logger.error(f"Error during bulk transcoding: {e}")
        return {}
    
    return output_files


# Test function
if __name__ == "__main__":
    import sys
    
    if not check_ffmpeg_installed():
        print("FFmpeg is not installed!")
        sys.exit(1)
    
    print("FFmpeg is available!")
    
    if len(sys.argv) > 1:
        video_path = sys.argv[1]
        try:
             info = get_video_info(video_path)
             print(f"Video info: {info}")
             
             if len(sys.argv) > 2:
                 output_dir = sys.argv[2]
                 results = transcode_video(video_path, output_dir)
                 print(f"Created files: {results}")
        except Exception as e:
            print(f"FAILED: {e}")
