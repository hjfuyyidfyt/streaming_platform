import os
import re
import asyncio
import httpx
import logging
import mimetypes
from typing import Union, Optional
from fastapi import UploadFile, HTTPException

def _sanitize_filename(title: str) -> str:
    """Sanitize title for use as a filename."""
    # Remove characters not safe for filenames
    clean = re.sub(r'[<>:"/\\|?*]', '', title)
    # Replace multiple spaces/underscores with single underscore
    clean = re.sub(r'[\s_]+', '_', clean.strip())
    return clean[:200]  # Limit length

logger = logging.getLogger(__name__)
# Add file handler
f_handler = logging.FileHandler('backend/upload_debug.log') # Separate log for uploads
f_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
f_handler.setFormatter(formatter)
logger.addHandler(f_handler)
logger.setLevel(logging.DEBUG)

STREAMTAPE_BASE = "https://api.streamtape.com"
DOODSTREAM_BASE = "https://doodapi.co/api"

async def upload_to_streamtape(file: Union[UploadFile, str], title: Optional[str] = None) -> dict:
    login = os.getenv("STREAMTAPE_API_LOGIN")
    key = os.getenv("STREAMTAPE_API_KEY")
    
    if not login or not key:
        raise HTTPException(status_code=500, detail="StreamTape credentials not configured")

    filename = ""
    content_type = "video/mp4"
    file_obj = None
    should_close = False

    if isinstance(file, str):
        ext = os.path.splitext(file)[1] or '.mp4'
        filename = f"{_sanitize_filename(title)}{ext}" if title else os.path.basename(file)
        content_type = mimetypes.guess_type(file)[0] or "video/mp4"
        file_obj = open(file, "rb")
        should_close = True
    else:
        filename = file.filename
        content_type = file.content_type
        file_obj = file.file

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. Get Upload URL (with retries for 502/503/Timeout)
            upload_url = None
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    resp = await client.get(f"{STREAMTAPE_BASE}/file/ul", params={"login": login, "key": key})
                    if resp.status_code == 200:
                        data = resp.json()
                        if data['status'] == 200:
                            upload_url = data['result']['url']
                            break
                        else:
                            logger.error(f"StreamTape API Error: {data.get('msg')}")
                    else:
                        logger.warning(f"StreamTape API returned {resp.status_code} on attempt {attempt+1}")
                except Exception as e:
                    logger.warning(f"StreamTape Get URL attempt {attempt+1} failed: {e}")
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)

            if not upload_url:
                raise HTTPException(status_code=502, detail="Failed to get upload URL from StreamTape after multiple attempts")

            # 2. Upload File
            try:
                if hasattr(file_obj, 'seek'):
                     file_obj.seek(0)
                
                files = {'file1': (filename, file_obj, content_type)}
                resp = await client.post(upload_url, files=files, timeout=None)
                res_data = resp.json()
                
                if res_data['status'] != 200:
                     logger.error(f"StreamTape Upload Error Response: {res_data}")
                     raise Exception(f"Upload Failed: {res_data.get('msg')}")
                     
                result = res_data['result']
                return {
                    "storage_mode": "streamtape",
                    "provider": "streamtape",
                    "file_id": result['id'],
                    "external_id": result['id'],
                    "embed_url": f"https://streamtape.com/e/{result['id']}/",
                    "thumbnail_url": None 
                }
            except Exception as e:
                logger.error(f"StreamTape Post-Upload Error: {e}")
                if 'resp' in locals():
                    logger.error(f"StreamTape Raw Response: {resp.text[:500]}")
                raise HTTPException(status_code=502, detail=f"Failed to upload to StreamTape: {e}")
    finally:
        if should_close and file_obj:
            file_obj.close()
            

async def upload_to_doodstream(file: Union[UploadFile, str], title: Optional[str] = None) -> dict:
    key = os.getenv("DOODSTREAM_API_KEY")
    logger.info(f"DoodStream Upload Start: Key Loaded? {bool(key)}")
    if not key:
        raise HTTPException(status_code=500, detail="DoodStream credentials not configured")

    filename = ""
    content_type = "video/mp4"
    file_obj = None
    should_close = False

    if isinstance(file, str):
        ext = os.path.splitext(file)[1] or '.mp4'
        filename = f"{_sanitize_filename(title)}{ext}" if title else os.path.basename(file)
        content_type = mimetypes.guess_type(file)[0] or "video/mp4"
        file_obj = open(file, "rb")
        should_close = True
    else:
        filename = file.filename
        content_type = file.content_type
        file_obj = file.file

    try:
        # Retry the entire upload flow (get server + upload) up to 2 times
        max_upload_attempts = 2
        last_error = None
        
        for upload_attempt in range(max_upload_attempts):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    # 1. Get Server (with retries for 502/503/Timeout)
                    upload_url = None
                    for attempt in range(3):
                        try:
                            resp = await client.get(f"{DOODSTREAM_BASE}/upload/server", params={"key": key})
                            if resp.status_code == 200:
                                data = resp.json()
                                if data.get('status') == 200:
                                    upload_url = data['result']
                                    break
                                else:
                                    logger.error(f"DoodStream API Error: {data.get('msg')}")
                            else:
                                logger.warning(f"DoodStream Server API returned {resp.status_code} on attempt {attempt+1}")
                        except Exception as e:
                            logger.warning(f"DoodStream Server API attempt {attempt+1} failed: {e}")
                        
                        if attempt < 2:
                            await asyncio.sleep(2)

                    if not upload_url:
                        raise Exception("Failed to get upload server from DoodStream")

                    # 2. Upload (seek to start for retries)
                    if hasattr(file_obj, 'seek'):
                        file_obj.seek(0)

                    files = {'file': (filename, file_obj, content_type)}
                    data = {'api_key': key} 
                    resp = await client.post(upload_url, files=files, data=data, timeout=None)
                    
                    # Validate response is JSON
                    resp_text = resp.text
                    if not resp_text.strip():
                        raise Exception("DoodStream returned empty response")
                    
                    try:
                        res_data = resp.json()
                    except Exception:
                        logger.error(f"DoodStream non-JSON response: {resp_text[:500]}")
                        raise Exception(f"DoodStream returned non-JSON: {resp_text[:200]}")
                    
                    if res_data.get('status') != 200:
                        logger.error(f"DoodStream Upload Error Response: {res_data}")
                        raise Exception(f"Upload Failed: {res_data.get('msg')}")
                        
                    result = res_data['result']
                    # Handle list vs dict
                    if isinstance(result, list):
                        if not result:
                            raise Exception("Empty result list from DoodStream")
                        result = result[0]
                    
                    return {
                        "storage_mode": "doodstream",
                        "provider": "doodstream",
                        "file_id": result['filecode'],
                        "external_id": result['filecode'],
                        "embed_url": f"https://dood.li/e/{result['filecode']}", 
                        "thumbnail_url": result.get('splash_img')
                    }
            except HTTPException:
                raise
            except Exception as e:
                last_error = e
                logger.warning(f"DoodStream upload attempt {upload_attempt+1} failed: {e}")
                if upload_attempt < max_upload_attempts - 1:
                    await asyncio.sleep(3)
        
        logger.error(f"DoodStream Upload FAILED after {max_upload_attempts} attempts: {last_error}")
        raise HTTPException(status_code=502, detail=f"Failed to upload to DoodStream: {last_error}")
    finally:
         if should_close and file_obj:
            file_obj.close()


async def remotedl_to_streamtape(url: str, title: Optional[str] = None) -> dict:
    login = os.getenv("STREAMTAPE_API_LOGIN")
    key = os.getenv("STREAMTAPE_API_KEY")
    
    if not login or not key:
        raise HTTPException(status_code=500, detail="StreamTape credentials not configured")

    async with httpx.AsyncClient() as client:
        try:
            params = {
                "login": login,
                "key": key,
                "url": url
            }
            if title:
                params["name"] = _sanitize_filename(title)
                
            resp = await client.get(f"{STREAMTAPE_BASE}/remotedl/add", params=params)
            data = resp.json()
            
            if data['status'] != 200:
                raise Exception(f"StreamTape Remote DL Failed: {data.get('msg')}")
                
            result = data['result']
            return {
                "provider": "streamtape",
                "remote_id": result['id'],
                "status": "pending"
            }
        except Exception as e:
            logger.error(f"StreamTape Remote DL Error: {e}")
            raise HTTPException(status_code=502, detail=f"Failed to trigger StreamTape Remote DL: {e}")

async def remotedl_to_doodstream(url: str, title: Optional[str] = None) -> dict:
    key = os.getenv("DOODSTREAM_API_KEY")
    if not key:
        raise HTTPException(status_code=500, detail="DoodStream credentials not configured")

    async with httpx.AsyncClient(timeout=30.0) as client:
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                params = {
                    "key": key,
                    "url": url
                }
                if title:
                    params["new_title"] = title
                    
                # Correct endpoint: upload/url (not remotedl/add)
                resp = await client.get(f"{DOODSTREAM_BASE}/upload/url", params=params)
                data = resp.json()
                
                if data.get('status') == 200:
                    result = data['result']
                    # DoodStream sometimes returns a list of results
                    if isinstance(result, list):
                        if not result:
                            raise Exception("Empty result list from DoodStream Remote DL")
                        result = result[0]
                        
                    return {
                        "provider": "doodstream",
                        "remote_id": result.get('filecode') or result.get('id'),
                        "status": "pending"
                    }
                else:
                    last_error = f"DoodStream Remote Upload Failed: {data.get('msg')}"
                    logger.warning(f"DoodStream upload/url attempt {attempt+1} failed: {last_error}")
                    
            except HTTPException:
                raise
            except Exception as e:
                last_error = str(e)
                logger.warning(f"DoodStream upload/url attempt {attempt+1} error: {e}")
            
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
        
        logger.error(f"DoodStream Remote DL Error after {max_retries} attempts: {last_error}")
        raise HTTPException(status_code=502, detail=f"Failed to trigger DoodStream Remote DL: {last_error}")
