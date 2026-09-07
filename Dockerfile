FROM node:22 AS frontend-build

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim

WORKDIR /app/backend

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_DATA_DIR=/app/storage

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY backend/ /app/backend/
COPY policies/ /app/policies/
COPY --from=frontend-build /app/frontend/dist/frontend/browser /app/frontend/dist/frontend/browser
COPY docker/bootstrap.sh /usr/local/bin/bootstrap.sh

RUN groupadd --system appuser \
    && useradd --system --gid appuser --home-dir /app --no-create-home appuser \
    && mkdir -p /app/storage \
    && chmod +x /usr/local/bin/bootstrap.sh \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

ENTRYPOINT ["/usr/local/bin/bootstrap.sh"]
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
