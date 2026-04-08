#!/bin/bash
set -euo pipefail

export GIT_TERMINAL_PROMPT=0

LOG="/var/log/safelock-update.log"
DIR="/root/safeLock_SoC"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

cd "$DIR"

PREV=$(git rev-parse HEAD)
mkdir -p /var/lib/safelock
echo "$PREV" > /var/lib/safelock/previous_commit

git fetch origin master >> "$LOG" 2>&1
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/master)

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "[$DATE] Sin cambios en repo, pero aplicando configuracion..." >> "$LOG"
else
    echo "[$DATE] Actualizacion disponible - aplicando..." >> "$LOG"
    git reset --hard origin/master >> "$LOG" 2>&1
fi

cp -f "$DIR"/systemd/*.service /etc/systemd/system/ 2>/dev/null || true
cp -f "$DIR"/systemd/*.timer /etc/systemd/system/ 2>/dev/null || true

systemctl daemon-reload >> "$LOG" 2>&1

# habilitar servicios clave si existen
for svc in \
  safelock-api.service \
  safelock-portal.service \
  safelock-network.service \
  safelock-pihole-setup.service \
  safelock-update.timer \
  safelock-heartbeat.timer
do
  if [ -f "/etc/systemd/system/$svc" ]; then
    systemctl enable "$svc" >> "$LOG" 2>&1 || true
  fi
done

if [ -f "/etc/systemd/system/safelock-heartbeat.timer" ]; then
    systemctl restart safelock-heartbeat.timer >> "$LOG" 2>&1 || true
    echo "[$DATE] safelock-heartbeat.timer reiniciado" >> "$LOG"
fi

echo "[$DATE] systemd actualizado" >> "$LOG"

NEW=$(git rev-parse HEAD)
CHANGED_FILES=$(git diff --name-only "$PREV" "$NEW")

if echo "$CHANGED_FILES" | grep -Eq '^(api/|scripts/|systemd/)'; then
    systemctl restart safelock-api
    echo "[$DATE] safelock-api reiniciado" >> "$LOG"
    sleep 5
    echo "[$DATE] safelock-api reiniciado" >> "$LOG"
fi

if echo "$CHANGED_FILES" | grep -q '^portal/'; then
    cd "$DIR/portal"
    npm run build >> "$LOG" 2>&1
    systemctl restart safelock-portal
    echo "[$DATE] Portal reconstruido y reiniciado" >> "$LOG"
fi

if bash "$DIR/scripts/health-check.sh" >> "$LOG" 2>&1; then
    echo "[$DATE] Health check OK" >> "$LOG"
else
    echo "[$DATE] Health check fallo - iniciando rollback" >> "$LOG"
    bash "$DIR/scripts/rollback.sh" >> "$LOG" 2>&1 || true
    exit 1
fi

echo "[$DATE] Actualizacion completada exitosamente" >> "$LOG"
