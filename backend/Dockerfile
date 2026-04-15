FROM python:3.11-slim

# Install system dependencies + Node.js for yt-dlp
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    wget \
    ca-certificates \
    gnupg \
    fonts-dejavu \
    fonts-noto \
    fonts-noto-cjk \
    libpq-dev \
    gcc \
    g++ \
    python3-dev \
    libcurl4-openssl-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install Node.js for yt-dlp JavaScript extraction
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.deno/bin:$PATH"

WORKDIR /app

COPY requirements.txt .

# Upgrade pip first
RUN pip install --no-cache-dir --upgrade pip

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Force update yt-dlp with all dependencies
RUN pip install --no-cache-dir --upgrade yt-dlp yt-dlp[default]

# Install additional useful tools
RUN pip install --no-cache-dir aiohttp httpx

COPY . .

# Ensure storage structure
RUN mkdir -p /app/storage/clips /app/storage/audio /app/storage/transcripts \
    /app/storage/tts /app/storage/composed /app/storage/thumbnails \
    /app/storage/chill /app/storage/temp /app/logs

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]