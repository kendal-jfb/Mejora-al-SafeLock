#!/bin/bash
set -euo pipefail

export GIT_TERMINAL_PROMPT=0

LOG="/var/log/safelock-update.log"
DIR="/root/safeLock_SoC"
DATE=$(date '+%Y-%m-%d %H:%M:%S')
BACKUP_ROOT="/var/lib/safelock/update-backups"

cd "$DIR"

PREV=$(git rev-parse HEAD)
mkdir -p /var/lib/safelock
echo "$PREV" > /var/lib/safelock/previous_commit
mkdir -p "$BACKUP_ROOT"

git fetch origin master >> "$LOG" 2>&1
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/master)

BAD_COMMIT_FILE="/var/lib/safelock/bad_commit"
# Anti-oscilacion: si el remoto es un commit ya marcado como malo (fallo health-check
# en un ciclo previo), NO lo reapliques cada 10 min; quedate en el ultimo bueno hasta
# que origin/master avance a un commit distinto.
if [ "$LOCAL" != "$REMOTE" ] && [ -f "$BAD_COMMIT_FILE" ] && [ "$REMOTE" = "$(cat "$BAD_COMMIT_FILE")" ]; then
    echo "[$DATE] origin/master ($REMOTE) marcado como MALO; se omite hasta nuevo commit." >> "$LOG"
    exit 0
fi

backup_conflicting_untracked() {
    local backup_dir="$BACKUP_ROOT/$(date '+%Y%m%d-%H%M%S')"
    local moved=0

    mkdir -p "$backup_dir"

    while IFS= read -r path; do
        [ -z "$path" ] && continue
        if [ -e "$path" ] && git ls-files --others --exclude-standard --error-unmatch "$path" >/dev/null 2>&1; then
            mkdir -p "$backup_dir/$(dirname "$path")"
            mv "$path" "$backup_dir/$path"
            echo "[$DATE] Untracked conflict movido a backup: $path" >> "$LOG"
            moved=1
        fi
    done < <(git ls-tree -r --name-only origin/master)

    if [ "$moved" -eq 1 ]; then
        echo "[$DATE] Backup untracked creado en $backup_dir" >> "$LOG"
    else
        rmdir "$backup_dir" 2>/dev/null || true
    fi
}

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "[$DATE] Sin cambios en repo; no se reaplica config (anti-churn eMMC)." >> "$LOG"
    CHANGED=0
else
    echo "[$DATE] Actualizacion disponible - aplicando..." >> "$LOG"
    backup_conflicting_untracked
    git reset --hard origin/master >> "$LOG" 2>&1
    CHANGED=1
fi

if [ "${CHANGED:-1}" = "1" ]; then
cp -f "$DIR"/systemd/*.service /etc/systemd/system/ 2>/dev/null || true
cp -f "$DIR"/systemd/*.timer /etc/systemd/system/ 2>/dev/null || true
cp -f "$DIR"/deploy/systemd/*.service /etc/systemd/system/ 2>/dev/null || true
cp -f "$DIR"/deploy/systemd/*.timer /etc/systemd/system/ 2>/dev/null || true

systemctl daemon-reload >> "$LOG" 2>&1

# habilitar servicios clave si existen
for svc in \
  safelock-factory.service \
  safelock-postfactory.service \
  safelock-api.service \
  safelock-portal.service \
  safelock-network.service \
  safelock-pihole-setup.service \
  tailscale-autoconnect.service \
  safelock-pack-scheduler.timer \
  connectivity-watchdog.timer \
  safelock-network.timer \
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

if [ -f "/etc/systemd/system/connectivity-watchdog.timer" ]; then
    systemctl restart connectivity-watchdog.timer >> "$LOG" 2>&1 || true
    echo "[$DATE] connectivity-watchdog.timer reiniciado" >> "$LOG"
fi

if [ -f "/etc/systemd/system/safelock-network.timer" ]; then
    systemctl restart safelock-network.timer >> "$LOG" 2>&1 || true
    echo "[$DATE] safelock-network.timer reiniciado" >> "$LOG"
fi

if [ -f "/etc/systemd/system/safelock-pack-scheduler.timer" ]; then
    systemctl restart safelock-pack-scheduler.timer >> "$LOG" 2>&1 || true
    echo "[$DATE] safelock-pack-scheduler.timer reiniciado" >> "$LOG"
fi

echo "[$DATE] systemd actualizado" >> "$LOG"
fi

NEW=$(git rev-parse HEAD)
CHANGED_FILES=$(git diff --name-only "$PREV" "$NEW")

if echo "$CHANGED_FILES" | grep -Eq '^(api/|scripts/|systemd/)'; then
    systemctl restart safelock-api
    echo "[$DATE] safelock-api reiniciado" >> "$LOG"
    sleep 5
fi

if echo "$CHANGED_FILES" | grep -q '^portal/'; then
    # El portal se versiona YA COMPILADO (portal/dist) y se construye en CI.
    # NO se hace 'npm run build' en el equipo: evita el pico de RAM/energia en una
    # caja de 4 GB que puede provocar brownout/apagon durante la actualizacion.
    systemctl restart safelock-portal
    echo "[$DATE] Portal actualizado (dist precompilado) y reiniciado" >> "$LOG"
fi

if bash "$DIR/scripts/health-check.sh" >> "$LOG" 2>&1; then
    echo "[$DATE] Health check OK" >> "$LOG"
else
    echo "[$DATE] Health check fallo - marcando commit MALO y haciendo rollback" >> "$LOG"
    echo "$REMOTE" > "$BAD_COMMIT_FILE"
    bash "$DIR/scripts/rollback.sh" >> "$LOG" 2>&1 || true
    exit 1
fi

# Aplicacion exitosa: limpia cualquier marca de commit malo previa.
rm -f "$BAD_COMMIT_FILE" 2>/dev/null || true
echo "[$DATE] Actualizacion completada exitosamente" >> "$LOG"
