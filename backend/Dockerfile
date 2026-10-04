FROM python:3.12-slim

# Railway passes the git sha as this build arg. Empty or "unknown" is unset.
ARG RAILWAY_GIT_COMMIT_SHA=unknown
ENV GIT_COMMIT=$RAILWAY_GIT_COMMIT_SHA

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY data /app/data

WORKDIR /app/backend

ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + __import__('os').environ.get('PORT','8000') + '/health')"

CMD ["sh", "-c", "uvicorn api.main_platform:app --host 0.0.0.0 --port ${PORT:-8000}"]
