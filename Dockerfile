FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    aria2 \
    ffmpeg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY run.py .

RUN mkdir -p /data

ENV FILMHUB_DATA_DIR=/data \
    FILMHUB_DOWNLOADS=/data/Downloads/FILMS \
    FILMHUB_DLNA=0 \
    FILMHUB_PORT=8888

EXPOSE 8888

CMD ["python", "run.py"]