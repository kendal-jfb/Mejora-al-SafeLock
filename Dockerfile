# Etapa 1: Compilar Frontend React
FROM node:20-alpine AS frontend-builder
WORKDIR /build
COPY portal/package*.json ./
RUN npm ci
COPY portal/ ./
RUN npm run build

# Etapa 2: Backend Python y ejecución
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 curl iproute2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ ./api/
COPY scripts/ ./scripts/
COPY VERSION ./VERSION 2>/dev/null || true
COPY --from=frontend-builder /build/dist ./portal/dist

COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

EXPOSE 8090 5173
ENTRYPOINT ["/app/entrypoint.sh"]
