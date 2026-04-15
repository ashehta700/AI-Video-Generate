# Arabic News Automation — Universal Video Generation for YouTube

This repository contains a complete automation platform for generating Arabic news videos. It combines scraping, audio transcription, translation, text-to-speech, video composition, thumbnail creation, metadata generation, and optional YouTube upload.

## Key Features

- Keyword-driven news scraping from YouTube, Twitter/X, RSS, and manual video URLs
- Automatic pipeline orchestration: clip ingestion → transcript → translation → TTS → composer → thumbnail → metadata → upload
- Daily scheduled automation via APScheduler
- FastAPI backend with REST endpoints for jobs, scraper, pipeline, translation, TTS, composer, thumbnail, uploader, metadata, analytics, and settings
- Static dashboard served by the API at `/dashboard`
- Flexible provider support: OpenAI / Anthropic for translation, Edge / ElevenLabs / PlayHT / gTTS for voice generation
- Output storage under `storage/` and logs under `logs/`

## What’s Included

- `backend/`: FastAPI application, routers, service modules, utilities, and Docker build context
- `scheduler/`: APScheduler-based routine that runs the daily pipeline
- `dashboard/`: static UI files for the app dashboard
- `database_schema.sql`: PostgreSQL schema for `clips`, `jobs`, and `app_settings`
- `.env`: environment configuration example for local deployment
- `docker-compose.yml`: Docker Compose setup for the API and scheduler services
- `screen shots/`: screenshots from the running application

## Repository Structure

- `backend/main.py` — FastAPI app startup, CORS, dashboard static mount, router registration
- `backend/routers/` — API endpoints for scraper, pipeline, settings, analytics, tts, composer, thumbnail, uploader, metadata, translate, chill
- `backend/services/` — business logic for scraping, pipeline orchestration, TTS, composing, uploading, translation, audio processing, thumbnails, and scripts
- `backend/utils/` — database connection, environment helpers, logging, storage utilities
- `scheduler/scheduler.py` — daily job scheduler using the same backend services
- `storage/` — generated audio, video, thumbnails, transcripts, temporary files

## Setup Instructions

### 1. Install PostgreSQL and create the database

Create the database locally:

```bash
createdb video_generate
```

Apply the schema:

```bash
psql -U postgres -d video_generate -f database_schema.sql
```

### 2. Configure environment variables

Copy `.env` or update the existing file with your values.
Make sure to configure at least:

- `DATABASE_URL`
- `OUTPUT_LANGUAGE`
- `TTS_PROVIDER`
- `EDGE_TTS_VOICE` or `ELEVENLABS_API_KEY` / `PLAYHT_API_KEY`
- `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`, `YOUTUBE_CHANNEL_ID`

Example database setting for Docker Desktop on Windows:

```text
DATABASE_URL=postgresql+asyncpg://postgres:postgres@host.docker.internal:5432/video_generate
```

For Linux with Docker host gateway:

```text
DATABASE_URL=postgresql+asyncpg://postgres:postgres@host-gateway:5432/video_generate
```

### 3. Build and run with Docker Compose

```bash
docker-compose up -d --build
```

Once started:

- API: `http://localhost:8000`
- Dashboard: `http://localhost:8000/dashboard`
- Health: `http://localhost:8000/health`

### 4. Start scheduler service

The scheduler runs automatically through Docker Compose as defined in `docker-compose.yml`.
If you want to run it manually:

```bash
python scheduler/scheduler.py
```

## Important Environment Variables

- `DATABASE_URL` — PostgreSQL connection string
- `OUTPUT_LANGUAGE` — default output language (e.g. `Arabic`)
- `TTS_PROVIDER` — `edge`, `elevenlabs`, `playht`, or `gtts`
- `EDGE_TTS_VOICE` — e.g. `ar-SA-HamedNeural`
- `WHISPER_MODEL` — speech-to-text model: `tiny`, `base`, `small`, `medium`, `large-v3`
- `WHISPER_DEVICE` — `cpu` or `cuda`
- `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`, `YOUTUBE_CHANNEL_ID`
- `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` — translation / script generation provider keys
- `CUSTOM_RSS_FEEDS` — comma-separated RSS feed URLs
- `MAX_VIDEOS_PER_DAY` — daily maximum content generation limit

## Main API Endpoints

- `GET /health` — service health check
- `POST /api/pipeline/run` — start a manual or auto-search pipeline job
- `POST /api/pipeline/daily` — start the daily pipeline job on demand
- `GET /api/pipeline/jobs` — list recent jobs
- `GET /api/pipeline/jobs/{job_id}` — inspect a job
- `POST /api/scraper/run` — trigger scraper with keywords and sources
- `GET /api/scraper/clips` — list saved clips
- `POST /api/uploader/upload` — upload a generated video to YouTube
- `GET /api/uploader/auth-url` — retrieve first-time YouTube OAuth URL
- `POST /api/tts/generate` — generate TTS audio for text
- `POST /api/translate/translate` — translate Hebrew text to Arabic content
- `POST /api/translate/script` — build a formatted Arabic script
- `POST /api/metadata/generate` — build SEO metadata for YouTube
- `POST /api/thumbnail/generate` — create video thumbnails

## How the Pipeline Works

1. Scrape videos from YouTube, Twitter/X, Telegram, RSS, or manual URLs
2. Store clips in the database
3. Transcribe audio using Whisper
4. Translate or build Arabic script text
5. Generate voice-over using selected TTS provider
6. Compose the final video with audio, text and visuals
7. Generate thumbnail, metadata, tags, and YouTube-ready assets
8. Upload to YouTube if enabled

## Screenshots

The `screen shots/` folder contains example screenshots from the running app, including:

- `Auto Generate.png`
- `dashboard.png`
- `Job Queue.png`
- `Kids videos create.png`
- `progress.png`
- `Scheduler.png`
- `search and create.png`
- `Setting.png`

## Notes

- The backend uses `backend/Dockerfile` to install Python, ffmpeg, Node.js, and required dependencies.
- The app writes generated assets under `storage/` and logs under `logs/`.
- Use `host.docker.internal` or `host-gateway` when connecting Docker containers to a host PostgreSQL database.

## Recommended Improvements

- Add a `.env.example` file for safe sharing without secret values
- Add dashboard documentation or screenshots inside the repo README
- Add an authentication layer for API access and dashboard protection

## License

Use this repo as the starting point for news automation and content generation workflows.
