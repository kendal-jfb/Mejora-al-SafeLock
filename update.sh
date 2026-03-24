#!/bin/bash
set -euo pipefail

export GIT_TERMINAL_PROMPT=0

LOG="/var/log/safelock-update.log"
DIR="/root/safeLock_SoC"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

cd "$DIR"

PREV=$(git rev-parse HEAD)

git fetch origin master >> "$LOG" 2>&1
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/master)

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "[$DATE] Sin cambios" >> "$LOG"
    exit 0
fi

echo "[$DATE] Actualizacion disponible - aplicando..." >> "$LOG"

git pull origin master >> "$LOG" 2>&1
NEW=$(git rev-parse HEAD)

systemctl restart safelock-api
echo "[$DATE] safelock-api reiniciado" >> "$LOG"

if git diff --name-only "$PREV" "$NEW" | grep -q '^portal/'; then
    cd "$DIR/portal"
    npm run build >> "$LOG" 2>&1
    systemctl restart safelock-portal
    echo "[$DATE] Portal reconstruido y reiniciado" >> "$LOG"
fi

echo "[$DATE] Actualizacion completada exitosamente" >> "$LOG"
