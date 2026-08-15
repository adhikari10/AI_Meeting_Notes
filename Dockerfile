FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements-web.txt requirements-base.txt ./
RUN pip install --no-cache-dir -r requirements-web.txt
COPY . .
CMD gunicorn -k eventlet -w 1 -b 0.0.0.0:$PORT meeting_notes_webapp.app:app
