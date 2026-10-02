# Multi-runtime Dockerfile: Python 3.11 + Node.js 18 for WASM Signer
FROM python:3.11-slim-bullseye

# Install system dependencies and Node.js 18
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    build-essential \
    libpq-dev \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1. Install Node.js Signer dependencies
COPY signer/package*.json ./signer/
RUN cd signer && npm install --production

# 2. Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Copy application source
COPY run.py .
COPY signer/ ./signer/
COPY app/ ./app/

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Expose FastAPI port (Signer port 3001 runs internally on localhost)
EXPOSE 8000

# Launch unified engine (Uvicorn + Signer child process)
CMD ["python", "run.py"]
