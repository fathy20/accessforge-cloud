# REDSEA API image: FastAPI + the in-process job handlers.
#
# One image serves both the HTTP API and (for now) the background jobs, because
# jobs still run inside the API process via BackgroundTasks. When the separate
# worker lands (TECHNICAL_DEBT #1) it reuses this image with a different command.
#
# Build args:
#   INSTALL_MSSQL_DRIVER=1  installs Microsoft ODBC Driver 18 (production SQL Server).
#                           Set to 0 for a smaller SQLite-only development image.

FROM python:3.11-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

ARG INSTALL_MSSQL_DRIVER=1

# tesseract-ocr: pytesseract shells out to it for scanned PDFs.
# unixodbc: driver manager pyodbc talks to; msodbcsql18 is Microsoft's SQL Server driver.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl gnupg2 unixodbc tesseract-ocr; \
    if [ "$INSTALL_MSSQL_DRIVER" = "1" ]; then \
        curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg; \
        echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
            > /etc/apt/sources.list.d/mssql-release.list; \
        apt-get update; \
        ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18; \
    fi; \
    apt-get purge -y --auto-remove curl gnupg2; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first so source edits do not invalidate the pip layer.
COPY backend/requirements.txt backend/requirements.txt
COPY worker/requirements.txt worker/requirements.txt
RUN pip install -r backend/requirements.txt -r worker/requirements.txt

COPY backend ./backend
COPY worker ./worker
COPY alembic ./alembic
COPY alembic.ini pyproject.toml ./
COPY deploy/api/entrypoint.sh /usr/local/bin/redsea-api
RUN chmod +x /usr/local/bin/redsea-api \
    && useradd --system --uid 10001 --create-home redsea \
    && mkdir -p /data/storage \
    && chown -R redsea:redsea /app /data

USER redsea

# Uploads and generated outputs; mount a volume here.
ENV ARTIFACT_STORAGE_DIR=/data/storage \
    WEB_CONCURRENCY=2 \
    PORT=8000
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3).status == 200 else 1)"

ENTRYPOINT ["redsea-api"]
