from datetime import datetime
from typing import Optional, List
from sqlmodel import Field, SQLModel, Relationship
from pydantic import ConfigDict

class CategoryBase(SQLModel):
    name: str = Field(index=True)
    slug: str = Field(index=True, unique=True)
    description: Optional[str] = None

class Category(CategoryBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    videos: List["Video"] = Relationship(back_populates="category")

class CategoryPublic(CategoryBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class TelegramInfoPublic(SQLModel):
    file_id: str
    file_unique_id: str
    channel_message_id: Optional[int] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class VideoResolutionPublic(SQLModel):
    resolution: str
    file_id: str
    channel_message_id: Optional[int] = None
    file_size: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)

from enum import Enum

class StorageMode(str, Enum):
    LOCAL = "local"
    TELEGRAM = "telegram"
    STREAMTAPE = "streamtape"
    DOODSTREAM = "doodstream"

class VideoBase(SQLModel):
    title: str = Field(index=True)
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration: Optional[int] = None  # in seconds
    views: int = Field(default=0)
    upload_date: datetime = Field(default_factory=datetime.utcnow)
    category_id: Optional[int] = Field(default=None, foreign_key="category.id")
    original_resolution: Optional[str] = None  # e.g., "1080p", "720p"
    uploader_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    storage_mode: str = Field(default="local")
    external_id: Optional[str] = None
    embed_url: Optional[str] = None
    is_short: bool = Field(default=False)

class Video(VideoBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    category: Optional[Category] = Relationship(back_populates="videos")
    telegram_info: Optional["TelegramInfo"] = Relationship(back_populates="video")
    resolutions: List["VideoResolution"] = Relationship(back_populates="video")
    uploader: Optional["User"] = Relationship(back_populates="videos")
    sources: List["VideoSource"] = Relationship(back_populates="video")

class UserPublic(SQLModel):
    id: int
    username: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class VideoSourcePublic(SQLModel):
    id: int
    provider: str
    resolution: Optional[str] = None
    embed_url: Optional[str] = None
    download_url: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class VideoPublic(VideoBase):
    id: int
    category: Optional[CategoryPublic] = None
    uploader: Optional[UserPublic] = None
    sources: List[VideoSourcePublic] = []
    telegram_info: Optional[TelegramInfoPublic] = None
    resolutions: List[VideoResolutionPublic] = []
    is_short: bool = False
    model_config = ConfigDict(from_attributes=True)

class VideoSource(SQLModel, table=True):
    """Stores multiple external links for a single video."""
    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: int = Field(foreign_key="video.id", index=True)
    provider: str  # streamtape, doodstream, telegram
    resolution: Optional[str] = None # e.g. "720p", "480p"
    file_id: Optional[str] = None
    embed_url: Optional[str] = None
    download_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    video: Optional[Video] = Relationship(back_populates="sources")

class TelegramInfo(SQLModel, table=True):
    """Stores the original/highest quality video info from Telegram."""
    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: int = Field(foreign_key="video.id", unique=True)
    file_id: str
    file_unique_id: str
    thumbnail_file_id: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    channel_message_id: Optional[int] = None
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    
    video: Optional[Video] = Relationship(back_populates="telegram_info")

class VideoResolution(SQLModel, table=True):
    """Stores file_id for each resolution variant of a video."""
    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: int = Field(foreign_key="video.id", index=True)
    resolution: str = Field(index=True)  # e.g., "720p", "480p", "360p"
    file_id: str
    file_unique_id: str
    file_size: Optional[int] = None
    channel_message_id: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    video: Optional[Video] = Relationship(back_populates="resolutions")

class AdminUser(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    password_hash: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class ViewHistory(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: int = Field(foreign_key="video.id", index=True)
    viewed_at: datetime = Field(default_factory=datetime.utcnow)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


# ============== PHASE 1: YouTube-like Features ==============

class User(SQLModel, table=True):
    """Public user accounts for comments, likes, subscriptions."""
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    email: str = Field(unique=True, index=True)
    password_hash: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    videos: List["Video"] = Relationship(back_populates="uploader")


class Comment(SQLModel, table=True):
    """Video comments with optional Super Chat support."""
    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: int = Field(foreign_key="video.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    parent_id: Optional[int] = Field(default=None, foreign_key="comment.id")  # For replies
    content: str
    is_super_chat: bool = False
    super_chat_amount: Optional[float] = None
    super_chat_color: Optional[str] = None  # Highlight color
    likes_count: int = 0
    is_edited: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CommentLike(SQLModel, table=True):
    """Likes on comments."""
    id: Optional[int] = Field(default=None, primary_key=True)
    comment_id: int = Field(foreign_key="comment.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class VideoLike(SQLModel, table=True):
    """Like/dislike on videos."""
    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: int = Field(foreign_key="video.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    is_like: bool = True  # True=like, False=dislike
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WatchHistory(SQLModel, table=True):
    """User's watch history with resume position."""
    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: int = Field(foreign_key="video.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    watched_at: datetime = Field(default_factory=datetime.utcnow)
    progress_seconds: int = 0  # Resume position
    duration_watched: int = 0  # Total seconds watched
    completed: bool = False


class Subscription(SQLModel, table=True):
    """User subscriptions to channels (uploaders)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    subscriber_id: int = Field(foreign_key="user.id", index=True)
    channel_id: int = Field(foreign_key="user.id", index=True)  # The uploader
    notifications_enabled: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Playlist(SQLModel, table=True):
    """User-created playlists."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    name: str
    description: Optional[str] = None
    is_public: bool = True
    is_watch_later: bool = False  # Special "Watch Later" playlist
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PlaylistItem(SQLModel, table=True):
    """Videos in a playlist."""
    id: Optional[int] = Field(default=None, primary_key=True)
    playlist_id: int = Field(foreign_key="playlist.id", index=True)
    video_id: int = Field(foreign_key="video.id", index=True)
    position: int = 0
    added_at: datetime = Field(default_factory=datetime.utcnow)

