from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine
from .routers import videos, upload, stream, categories, analytics, thumbnails, auth, comments, likes, history, playlists, admin, subscriptions
from .models import SQLModel
import logging
import os
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

# Load environment variables
load_dotenv()

# Logger setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
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

app = FastAPI(
    title="Video Streaming API",
    description="Backend for Video Streaming Platform",
    version="1.0.0"
)

# CORS Configuration - MUST BE ADDED FIRST before other middleware
origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Other middleware (added after CORS)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
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

@app.on_event("startup")
def on_startup():
    logger.info("Application starting up...")

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "streaming-platform-backend"}

# Serve Frontend Static Files
# This should be at the end to avoid catching API routes
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

# Path to the built frontend
frontend_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dist")

if os.path.exists(frontend_dist):
    # Serve assets from /static/assets (mapping /static to the dist root)
    app.mount("/static", StaticFiles(directory=frontend_dist), name="static")
    
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
        return FileResponse(os.path.join(frontend_dist, "index.html"))
else:
    @app.get("/")
    async def root():
        return {"message": "Welcome to the Video Streaming Platform API (Frontend not built)"}
