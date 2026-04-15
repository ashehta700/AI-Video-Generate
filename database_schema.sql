-- VideoForge - Universal Video Generation Platform
-- Complete Database Schema
-- Run this in PostgreSQL to create the database

-- Create database
-- CREATE DATABASE video_generate;

-- Connect to the database and run the following:
-- psql -U postgres -d video_generate -f database_schema.sql

-- Enable UUID extension (optional, for future use)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─────────────────────────────────────────────────────────────
-- ENUMS
-- ─────────────────────────────────────────────────────────────

CREATE TYPE job_status AS ENUM (
    'pending',
    'running',
    'completed',
    'failed',
    'approved',
    'rejected'
);

CREATE TYPE clip_source AS ENUM (
    'channel12',
    'channel13',
    'twitter',
    'telegram',
    'youtube',
    'rss',
    'manual'
);

-- ─────────────────────────────────────────────────────────────
-- TABLE: clips (Source Videos)
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS clips (
    id SERIAL PRIMARY KEY,
    url VARCHAR(2048) NOT NULL,
    source clip_source NOT NULL DEFAULT 'manual',
    title VARCHAR(512),
    duration DOUBLE PRECISION,
    thumbnail_url VARCHAR(1024),
    channel VARCHAR(512),
    keywords JSONB DEFAULT '[]'::jsonb,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    local_path VARCHAR(1024),
    is_processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_clips_source ON clips(source);
CREATE INDEX IF NOT EXISTS idx_clips_created_at ON clips(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_clips_keywords ON clips USING GIN(keywords);

-- ─────────────────────────────────────────────────────────────
-- TABLE: jobs (Pipeline Jobs)
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS jobs (
    id SERIAL PRIMARY KEY,
    clip_id INTEGER REFERENCES clips(id) ON DELETE SET NULL,
    status job_status DEFAULT 'pending',
    stage VARCHAR(64),
    is_chill_mode BOOLEAN DEFAULT FALSE,
    retry_count INTEGER DEFAULT 0,
    
    -- Stage outputs
    audio_path VARCHAR(1024),
    transcript_path VARCHAR(1024),
    transcript_json JSONB,
    translation_json JSONB,
    tts_path VARCHAR(1024),
    composed_video_path VARCHAR(1024),
    thumbnail_path VARCHAR(1024),
    metadata_json JSONB,
    youtube_video_id VARCHAR(64),
    youtube_url VARCHAR(512),
    
    -- Approval flags
    subtitle_approved BOOLEAN,
    thumbnail_approved BOOLEAN,
    
    -- Error tracking
    error_message TEXT,
    
    -- Timestamps
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_clip_id ON jobs(clip_id);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_youtube_id ON jobs(youtube_video_id);

-- ─────────────────────────────────────────────────────────────
-- TABLE: app_settings (Configuration)
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS app_settings (
    id SERIAL PRIMARY KEY,
    key VARCHAR(128) UNIQUE NOT NULL,
    value TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_app_settings_key ON app_settings(key);

-- Insert default settings (ignore if exists)
INSERT INTO app_settings (key, value) VALUES
    ('keywords', '["news","technology","sports"]'),
    ('max_videos_per_day', '3'),
    ('video_length_min', '2'),
    ('video_length_max', '5'),
    ('voice_style', 'news'),
    ('upload_hour_utc', '15'),
    ('chill_mode_enabled', 'true'),
    ('ai_thumbnail', 'true'),
    ('translation_provider', 'openai'),
    ('tts_provider', 'edge'),
    ('watermark_text', 'videoforge'),
    ('schedule_hour', '8'),
    ('schedule_minute', '0'),
    ('output_language', 'Arabic'),
    ('twitter_accounts', ''),
    ('rss_feeds', '')
ON CONFLICT (key) DO NOTHING;

-- ─────────────────────────────────────────────────────────────
-- TABLE: analytics (YouTube Statistics)
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS analytics (
    id SERIAL PRIMARY KEY,
    job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE UNIQUE,
    youtube_video_id VARCHAR(64),
    views INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    watch_time_hours DOUBLE PRECISION DEFAULT 0.0,
    estimated_revenue_usd DOUBLE PRECISION DEFAULT 0.0,
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_analytics_job_id ON analytics(job_id);
CREATE INDEX IF NOT EXISTS idx_analytics_fetched_at ON analytics(fetched_at DESC);

-- ─────────────────────────────────────────────────────────────
-- TABLE: campaigns (Saved Campaigns)
-- ─────────────────────────────────────────────────────────────

CREATE TABLE campaigns (
    id SERIAL PRIMARY KEY,
    name VARCHAR(256) NOT NULL,
    keywords JSONB DEFAULT '[]'::jsonb,
    language VARCHAR(64) DEFAULT 'Arabic',
    max_videos INTEGER DEFAULT 3,
    twitter_accounts TEXT,
    schedule_cron VARCHAR(128),
    is_active BOOLEAN DEFAULT TRUE,
    include_shorts BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_campaigns_active ON campaigns(is_active);

-- ─────────────────────────────────────────────────────────────
-- TABLE: scheduler_logs (Automation History)
-- ─────────────────────────────────────────────────────────────

CREATE TABLE scheduler_logs (
    id SERIAL PRIMARY KEY,
    run_type VARCHAR(64),
    keywords JSONB,
    jobs_created INTEGER DEFAULT 0,
    jobs_completed INTEGER DEFAULT 0,
    jobs_failed INTEGER DEFAULT 0,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT
);

CREATE INDEX idx_scheduler_logs_started ON scheduler_logs(started_at DESC);

-- ─────────────────────────────────────────────────────────────
-- Function to update updated_at timestamp
-- ─────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to app_settings
CREATE TRIGGER update_app_settings_updated_at
    BEFORE UPDATE ON app_settings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Apply trigger to campaigns
CREATE TRIGGER update_campaigns_updated_at
    BEFORE UPDATE ON campaigns
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ─────────────────────────────────────────────────────────────
-- Views for easy querying
-- ─────────────────────────────────────────────────────────────

-- View: Active jobs with clip details
CREATE OR REPLACE VIEW active_jobs_view AS
SELECT 
    j.id,
    j.status,
    j.stage,
    j.is_chill_mode,
    j.clip_id,
    c.url as clip_url,
    c.title as clip_title,
    c.source as clip_source,
    j.youtube_url,
    j.created_at,
    j.started_at,
    j.completed_at,
    j.error_message
FROM jobs j
LEFT JOIN clips c ON j.clip_id = c.id
ORDER BY j.created_at DESC;

-- View: Pipeline statistics
CREATE OR REPLACE VIEW pipeline_stats AS
SELECT 
    COUNT(*) FILTER (WHERE status = 'pending') as pending_count,
    COUNT(*) FILTER (WHERE status = 'running') as running_count,
    COUNT(*) FILTER (WHERE status = 'completed') as completed_count,
    COUNT(*) FILTER (WHERE status = 'failed') as failed_count,
    COUNT(*) FILTER (WHERE completed_at >= CURRENT_DATE) as completed_today,
    COUNT(*) FILTER (WHERE completed_at >= CURRENT_DATE - INTERVAL '7 days') as completed_week,
    COUNT(*) FILTER (WHERE completed_at >= CURRENT_DATE - INTERVAL '30 days') as completed_month
FROM jobs;

-- View: Daily production summary
CREATE OR REPLACE VIEW daily_summary AS
SELECT 
    DATE(completed_at) as date,
    COUNT(*) as total_jobs,
    COUNT(*) FILTER (WHERE status = 'completed') as completed,
    COUNT(*) FILTER (WHERE status = 'failed') as failed
FROM jobs
WHERE completed_at IS NOT NULL
GROUP BY DATE(completed_at)
ORDER BY date DESC
LIMIT 30;
