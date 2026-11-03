# --- build the frontend -------------------------------------------------------
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- python runtime serving API + built frontend ----------------------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist /app/frontend/dist
ENV FINN_FRONTEND_DIST=/app/frontend/dist
EXPOSE 8000
CMD ["sh", "-c", "uvicorn finn.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
