#!/bin/bash
set -u -o pipefail

LOG_FILE="/var/log/connectivity-watchdog.log"
AUTHKEY_FILE="/etc/tailscale-authkey"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WATCHDOG] $1" | tee -a "$LOG_FILE"
}

mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"
chmod 644 "$LOG_FILE"

if ! systemctl is-active --quiet tailscaled; then
    log "tailscaled inactivo; iniciando servicio."
    systemctl start tailscaled || true
fi

for i in $(seq 1 15); do
    if systemctl is-active --quiet tailscaled; then
        break
    fi
    sleep 2
done

if ! systemctl is-active --quiet tailscaled; then
    log "tailscaled sigue inactivo despues del reintento."
    exit 1
fi

if tailscale status --json 2>/dev/null | grep -q '"BackendState":"Running"'; then
    log "Tailscale operativo."
    exit 0
fi

if [ ! -s "$AUTHKEY_FILE" ]; then
    log "Sin authkey disponible para recuperar la sesion."
    exit 1
fi

AUTHKEY=$(tr -d '\r\n' < "$AUTHKEY_FILE")

if tailscale up --authkey="$AUTHKEY" --accept-dns=false --advertise-tags=tag:safelock; then
    log "Sesion de Tailscale recuperada."
    exit 0
fi

log "No se pudo recuperar Tailscale."
exit 1
