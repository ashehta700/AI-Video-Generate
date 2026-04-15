"""
Database Models - SQLAlchemy ORM
VideoForge - Universal Video Generation Platform
"""

from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean,
    DateTime, JSON, Enum, ForeignKey, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from utils.database import Base 


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    APPROVED = "approved"
    REJECTED = "rejected"


class ClipSource(str, enum.Enum):
    CHANNEL12 = "channel12"
    CHANNEL13 = "channel13"
    TWITTER = "twitter"
    TELEGRAM = "telegram"
    YOUTUBE = "youtube"
    RSS = "rss"
    MANUAL = "manual"


# Create PostgreSQL-specific enum types that match the database
job_status_enum = PGEnum(
    'pending', 'running', 'completed', 'failed', 'approved', 'rejected',
    name='job_status',
    create_type=False
)

clip_source_enum = PGEnum(
    'channel12', 'channel13', 'twitter', 'telegram', 'youtube', 'rss', 'manual',
    name='clip_source',
    create_type=False
)


class Clip(Base):
    __tablename__ = "clips"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(2048), nullable=False)
    source = Column(clip_source_enum, nullable=False, default='manual')
    title = Column(String(512))
    duration = Column(Float)
    thumbnail_url = Column(String(1024))
    channel = Column(String(512))
    keywords = Column(JSON, default=list)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    local_path = Column(String(1024))
    is_processed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    jobs = relationship("Job", back_populates="clip")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    clip_id = Column(Integer, ForeignKey("clips.id", ondelete="SET NULL"), nullable=True)
    status = Column(job_status_enum, default='pending')
    stage = Column(String(64))
    is_chill_mode = Column(Boolean, default=False)
    retry_count = Column(Integer, default=0)

    # Stage outputs
    audio_path = Column(String(1024))
    transcript_path = Column(String(1024))
    transcript_json = Column(JSON)
    translation_json = Column(JSON)
    tts_path = Column(String(1024))
    composed_video_path = Column(String(1024))
    thumbnail_path = Column(String(1024))
    metadata_json = Column(JSON)
    youtube_video_id = Column(String(64))
    youtube_url = Column(String(512))

    # Approval flags
    subtitle_approved = Column(Boolean, nullable=True)
    thumbnail_approved = Column(Boolean, nullable=True)

    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    clip = relationship("Clip", back_populates="jobs")
    analytics = relationship("Analytics", back_populates="job", uselist=False)


class AppSettings(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(128), unique=True, nullable=False, index=True)
    value = Column(Text)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Analytics(Base):
    __tablename__ = "analytics"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), unique=True)
    youtube_video_id = Column(String(64))
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    watch_time_hours = Column(Float, default=0.0)
    estimated_revenue_usd = Column(Float, default=0.0)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())

    job = relationship("Job", back_populates="analytics")
