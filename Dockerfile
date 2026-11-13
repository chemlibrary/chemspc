FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CHEMSPC_DATABASE=/data/chemspc.db \
    CHEMSPC_INSTANCE_PATH=/data/instance

WORKDIR /app

COPY requirements.txt requirements-docker.txt ./
RUN pip install --no-cache-dir -r requirements-docker.txt \
    && groupadd --gid 10001 chemspc \
    && useradd --uid 10001 --gid chemspc --no-create-home chemspc \
    && mkdir -p /data/instance \
    && chown -R chemspc:chemspc /data

COPY *.py ./
COPY templates/ ./templates/
COPY static/ ./static/
COPY data/pokemon_names/ ./data/pokemon_names/
COPY docker/entrypoint.py /app/docker-entrypoint.py
COPY LICENSE ./

USER chemspc
VOLUME ["/data"]
EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/', timeout=3).close()"]

ENTRYPOINT ["python", "/app/docker-entrypoint.py"]
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "main:app"]
