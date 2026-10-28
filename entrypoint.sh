#!/bin/sh
set -e

# Iniciar servidor estático del portal (puerto 5173) en segundo plano
python3 /app/scripts/serve-portal.py --dir /app/portal/dist --port 5173 &

# Iniciar API FastAPI (puerto 8090) en primer plano
exec python3 -m uvicorn main:app --app-dir /app/api --host 0.0.0.0 --port 8090
