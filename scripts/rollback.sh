#!/bin/bash
set -euo pipefail

LOG="/var/log/safelock-update.log"
DIR="/root/safeLock_SoC"

PREV=$(cat /var/lib/safelock/previous_commit)

cd "$DIR"
git reset --hard "$PREV" >> "$LOG" 2>&1

cp -f "$DIR"/systemd/*.service /etc/systemd/system/ 2>/dev/null || true
cp -f "$DIR"/systemd/*.timer /etc/systemd/system/ 2>/dev/null || true
systemctl daemon-reload >> "$LOG" 2>&1

if [ -f /etc/systemd/system/safelock-api.service ]; then
  systemctl restart safelock-api >> "$LOG" 2>&1 || true
fi

if [ -f /etc/systemd/system/safelock-portal.service ]; then
  systemctl restart safelock-portal >> "$LOG" 2>&1 || true
fi

echo "Rollback aplicado a $PREV" >> "$LOG"
