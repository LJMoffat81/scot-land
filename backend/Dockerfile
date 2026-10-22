# Tippecanoe (pinned felt/tippecanoe commit; no release tags published).
FROM debian:bookworm-slim AS tippecanoe
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        git \
        libsqlite3-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone https://github.com/felt/tippecanoe.git \
    && cd tippecanoe \
    && git checkout 4f2621186acfec33b63ddf636f665623c0fef2dd \
    && make -j"$(nproc)" \
    && make install

FROM python:3.12-slim

# Railway passes the git sha as this build arg. Empty or "unknown" is unset.
ARG RAILWAY_GIT_COMMIT_SHA=unknown
ENV GIT_COMMIT=$RAILWAY_GIT_COMMIT_SHA

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libsqlite3-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=tippecanoe /usr/local/bin/tippecanoe /usr/local/bin/tippecanoe
COPY --from=tippecanoe /usr/local/bin/tippecanoe-decode /usr/local/bin/tippecanoe-decode
COPY --from=tippecanoe /usr/local/bin/tile-join /usr/local/bin/tile-join

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY data /app/data

WORKDIR /app/backend

ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + __import__('os').environ.get('PORT','8000') + '/health')"

CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
