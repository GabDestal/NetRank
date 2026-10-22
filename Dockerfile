FROM python:3.11.17-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/GabDestal/NetRank" \
      org.opencontainers.image.description="NetRank API: tennis knowledge graph on Neo4j + GDS"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# Dependencies first so code edits do not invalidate this layer.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

RUN useradd --create-home --uid 10001 netrank
USER netrank

EXPOSE 8000

# Liveness only: a Neo4j outage must not make Docker restart the API.
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
