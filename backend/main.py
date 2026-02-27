# Load environment variables FIRST before any other imports
# This is the single source of truth for all credentials
import os
from pathlib import Path
from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent / '.env'
load_dotenv(dotenv_path=_env_path, override=True)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine
from .routers import videos, upload, stream, categories, analytics, thumbnails, auth, comments, likes, history, playlists, admin, subscriptions
from .models import SQLModel
import logging
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

# Logger setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add file handler to root logger to capture all logs in upload_debug.log
f_handler = logging.FileHandler('backend/upload_debug.log')
f_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
f_handler.setFormatter(formatter)
logging.getLogger().addHandler(f_handler)

logger.info("Main router loaded.")

# Rate Limiter
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

# Security Headers Middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

class RequestLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method
        client = request.client.host if request.client else "unknown"
        logger.info(f"REQUEST: {method} {path} from {client}")
        try:
            response = await call_next(request)
            logger.info(f"RESPONSE: {method} {path} -> {response.status_code}")
            return response
        except Exception as e:
            logger.error(f"ERROR: {method} {path} -> {str(e)}")
            raise

app = FastAPI(
    title="Video Streaming API",
    description="Backend for Video Streaming Platform",
    version="1.0.0"
)

# CORS Configuration - MUST BE ADDED FIRST before other middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Other middleware (added after CORS)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(RequestLoggerMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

# Include Routers
app.include_router(auth.router)
app.include_router(videos.router)
app.include_router(upload.router)
app.include_router(stream.router)
app.include_router(categories.router)
app.include_router(analytics.router)
app.include_router(thumbnails.router)
app.include_router(comments.router)
app.include_router(likes.router)
app.include_router(history.router)
app.include_router(playlists.router)
app.include_router(admin.router)
app.include_router(subscriptions.router)

_keep_alive_task = None

async def _db_keep_alive():
    """Ping database every 4 minutes to prevent Neon free-tier auto-suspend."""
    import asyncio
    from sqlalchemy import text
    from .database import engine
    while True:
        await asyncio.sleep(240)  # 4 minutes
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                conn.commit()
            logger.debug("DB keep-alive ping OK")
        except Exception as e:
            logger.warning(f"DB keep-alive ping failed: {e}")

@app.on_event("startup")
async def on_startup():
    global _keep_alive_task
    logger.info("Application starting up...")
    # Start the Telegram upload queue worker
    from .services.telegram_queue import telegram_queue
    telegram_queue.start()
    logger.info("Telegram upload queue started.")
    # Start DB keep-alive
    import asyncio
    _keep_alive_task = asyncio.create_task(_db_keep_alive())
    logger.info("DB keep-alive started (ping every 4 min).")

@app.on_event("shutdown")
async def on_shutdown():
    global _keep_alive_task
    from .services.telegram_queue import telegram_queue
    telegram_queue.stop()
    if _keep_alive_task:
        _keep_alive_task.cancel()
    logger.info("Telegram upload queue + DB keep-alive stopped.")

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "streaming-platform-backend"}

# Serve Frontend Static Files
# This should be at the end to avoid catching API routes
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, Response

# Path to the built frontend
frontend_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dist")
logger.info(f"Frontend dist path: {frontend_dist}, exists: {os.path.exists(frontend_dist)}")

if os.path.exists(frontend_dist):
    # Check if index.html exists
    index_html_path = os.path.join(frontend_dist, "index.html")
    if os.path.exists(index_html_path):
        logger.info("Frontend build found, mounting static files...")
        # Serve assets from /assets directly
        assets_dir = os.path.join(frontend_dist, "assets")
        if os.path.exists(assets_dir):
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
        
        @app.get("/{full_path:path}")
        async def serve_react_app(request: Request, full_path: str):
            # Prevent catching API/System routes
            if any(full_path.startswith(prefix) for prefix in ["api", "thumbnails", "stream", "health"]):
                return Response(status_code=404)
                
            # Check if the requested file exists in dist
            file_path = os.path.join(frontend_dist, full_path)
            if os.path.isfile(file_path):
                return FileResponse(file_path)
                
            # Fallback to index.html for React SPA routing
            return FileResponse(index_html_path)
    else:
        logger.warning("Frontend dist exists but index.html not found!")
        @app.get("/")
        async def root():
            return {"message": "Frontend build incomplete - index.html missing"}
else:
    logger.info("Frontend dist not found, serving API only")
    @app.get("/")
    async def root():
        return {"message": "Welcome to the Video Streaming Platform API (Frontend not built)"}

