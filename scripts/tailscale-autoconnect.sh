#!/bin/bash
set -u -o pipefail

LOG_FILE="/var/log/tailscale-autoconnect.log"
AUTHKEY_FILE="/etc/tailscale-authkey"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [TAILSCALE-AUTOCONNECT] $1" | tee -a "$LOG_FILE"
}

mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"
chmod 644 "$LOG_FILE"

if [ ! -s "$AUTHKEY_FILE" ]; then
    log "No existe $AUTHKEY_FILE; no se intenta tailscale up."
    exit 0
fi

for i in $(seq 1 30); do
    if systemctl is-active --quiet tailscaled; then
        break
    fi
    log "Esperando tailscaled... intento $i/30"
    sleep 2
done

if ! systemctl is-active --quiet tailscaled; then
    log "tailscaled no quedo activo."
    exit 1
fi

if tailscale status --json 2>/dev/null | grep -q '"BackendState":"Running"'; then
    log "Tailscale ya esta en Running."
    exit 0
fi

AUTHKEY=$(tr -d '\r\n' < "$AUTHKEY_FILE")

for i in $(seq 1 10); do
    if tailscale up --authkey="$AUTHKEY" --accept-dns=false --advertise-tags=tag:safelock; then
        log "tailscale up exitoso."
        exit 0
    fi
    log "tailscale up fallo... intento $i/10"
    sleep 5
done

log "No se pudo completar tailscale up."
exit 1
