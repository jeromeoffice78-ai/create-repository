FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY worker.py /app/worker.py
RUN useradd -m studio && mkdir /data && chown studio:studio /data
USER studio
ENV STUDIO_DATA_DIR=/data
CMD ["python", "worker.py"]
