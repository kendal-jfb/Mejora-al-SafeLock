#!/bin/bash
set -u -o pipefail

LOG_FILE="/var/log/tailscale-autoconnect.log"
AUTHKEY_FILE="/etc/tailscale-authkey"
HOSTNAME_FILE="/etc/hostname"
NET_IF="end0"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [TAILSCALE-AUTOCONNECT] $1" | tee -a "$LOG_FILE"
}

get_tailscale_hostname() {
    local mac_address

    if [ ! -r "/sys/class/net/$NET_IF/address" ]; then
        log "No existe la interfaz $NET_IF para derivar hostname."
        return 1
    fi

    mac_address="$(tr -d ':\r\n' < "/sys/class/net/$NET_IF/address")"
    [ -n "$mac_address" ] || return 1
    printf 'safelock-%s\n' "$mac_address"
}

set_static_hostname() {
    local new_hostname="$1"
    local current_hostname

    current_hostname="$(cat "$HOSTNAME_FILE" 2>/dev/null || hostname 2>/dev/null || true)"

    if [ "$current_hostname" != "$new_hostname" ]; then
        printf '%s\n' "$new_hostname" > "$HOSTNAME_FILE"
        hostname "$new_hostname" || true
        log "Hostname configurado: $new_hostname"
    fi
}

tailscale_is_running() {
    tailscale status --json 2>/dev/null | grep -q '"BackendState":"Running"'
}

tailscale_has_ipv4() {
    tailscale ip -4 2>/dev/null | grep -q '.'
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

TAILSCALE_HOSTNAME="$(get_tailscale_hostname)" || {
    log "No se pudo derivar hostname unico de Tailscale."
    exit 1
}

set_static_hostname "$TAILSCALE_HOSTNAME"

if tailscale_is_running && tailscale_has_ipv4; then
    log "Tailscale ya esta operativo con IPv4."
    exit 0
fi

AUTHKEY=$(tr -d '\r\n' < "$AUTHKEY_FILE")

for i in $(seq 1 10); do
    if tailscale up --authkey="$AUTHKEY" --hostname="$TAILSCALE_HOSTNAME" --accept-dns=false --advertise-tags=tag:safelock; then
        for j in $(seq 1 15); do
            if tailscale_is_running && tailscale_has_ipv4; then
                log "tailscale up exitoso."
                exit 0
            fi
            sleep 2
        done
    fi
    log "tailscale up fallo... intento $i/10"
    sleep 5
done

log "No se pudo completar tailscale up."
exit 1
