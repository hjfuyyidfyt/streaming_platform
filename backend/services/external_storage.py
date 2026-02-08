import os
import httpx
import logging
import mimetypes
from typing import Union
from fastapi import UploadFile, HTTPException

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

async def upload_to_streamtape(file: Union[UploadFile, str]) -> dict:
    login = os.getenv("STREAMTAPE_API_LOGIN")
    key = os.getenv("STREAMTAPE_API_KEY")
    
    if not login or not key:
        raise HTTPException(status_code=500, detail="StreamTape credentials not configured")

    filename = ""
    content_type = "video/mp4"
    file_obj = None
    should_close = False

    if isinstance(file, str):
        filename = os.path.basename(file)
        content_type = mimetypes.guess_type(file)[0] or "video/mp4"
        file_obj = open(file, "rb")
        should_close = True
    else:
        filename = file.filename
        content_type = file.content_type
        file_obj = file.file

    try:
        async with httpx.AsyncClient() as client:
            # 1. Get Upload URL
            try:
                resp = await client.get(f"{STREAMTAPE_BASE}/file/ul", params={"login": login, "key": key})
                data = resp.json()
                if data['status'] != 200:
                    raise Exception(f"StreamTape Auth Failed: {data.get('msg')}")
                upload_url = data['result']['url']
            except Exception as e:
                logger.error(f"StreamTape Get URL Error: {e}")
                raise HTTPException(status_code=502, detail="Failed to connect to StreamTape")

            # 2. Upload File
            try:
                # Seek to 0 just in case
                if hasattr(file_obj, 'seek'):
                     file_obj.seek(0)
                
                files = {'file1': (filename, file_obj, content_type)}
                resp = await client.post(upload_url, files=files, timeout=None) # Unlimited timeout
                res_data = resp.json()
                
                if res_data['status'] != 200:
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
                logger.error(f"StreamTape Upload Error: {e}")
                raise HTTPException(status_code=502, detail="Failed to upload to StreamTape")
    finally:
        if should_close and file_obj:
            file_obj.close()
            

async def upload_to_doodstream(file: Union[UploadFile, str]) -> dict:
    key = os.getenv("DOODSTREAM_API_KEY")
    logger.info(f"DoodStream Upload Start: Key Loaded? {bool(key)}")
    if not key:
        raise HTTPException(status_code=500, detail="DoodStream credentials not configured")

    filename = ""
    content_type = "video/mp4"
    file_obj = None
    should_close = False

    if isinstance(file, str):
        filename = os.path.basename(file)
        content_type = mimetypes.guess_type(file)[0] or "video/mp4"
        file_obj = open(file, "rb")
        should_close = True
    else:
        filename = file.filename
        content_type = file.content_type
        file_obj = file.file

    try:
        async with httpx.AsyncClient() as client:
            # 1. Get Server
            try:
                resp = await client.get(f"{DOODSTREAM_BASE}/upload/server", params={"key": key})
                data = resp.json()
                if data['status'] != 200:
                     raise Exception(f"DoodStream Auth Failed: {data.get('msg')}")
                upload_url = data['result']
            except Exception as e:
                logger.error(f"DoodServer Error: {e}")
                raise HTTPException(status_code=502, detail="Failed to connect to DoodStream")

            # 2. Upload
            try:
                if hasattr(file_obj, 'seek'):
                     file_obj.seek(0)

                files = {'file': (filename, file_obj, content_type)}
                data = {'api_key': key} # Docs say 'api_key' in form data
                resp = await client.post(upload_url, files=files, data=data, timeout=None)
                res_data = resp.json()
                
                if res_data['status'] != 200:
                    logger.error(f"DoodStream Error Resp: {res_data}")
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
            except Exception as e:
                logger.error(f"DoodStream Upload Error: {e}")
                if 'resp' in locals():
                    logger.error(f"DoodStream Raw Response: {resp.text}")
                raise HTTPException(status_code=502, detail=f"Failed to upload to DoodStream: {e}")
    finally:
         if should_close and file_obj:
            file_obj.close()
