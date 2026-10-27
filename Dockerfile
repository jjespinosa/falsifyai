# Stage 1 builds the judge-facing screen. It does not receive MODEL_API_KEY.
FROM node:22-bookworm-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2 runs FastAPI and serves the built screen from the same origin.
FROM python:3.12-slim-bookworm
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    FALSIFY_STATIC_DIR=/app/frontend/dist
COPY pyproject.toml README.md ./
COPY backend/app ./backend/app
RUN pip install --no-cache-dir .
COPY --from=frontend /src/frontend/dist ./frontend/dist
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}"]
