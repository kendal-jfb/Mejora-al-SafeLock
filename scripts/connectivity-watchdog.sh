#!/bin/bash
set -u -o pipefail

LOG_FILE="/var/log/connectivity-watchdog.log"
AUTHKEY_FILE="/etc/tailscale-authkey"
HOSTNAME_FILE="/etc/hostname"
NET_IF="end0"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WATCHDOG] $1" | tee -a "$LOG_FILE"
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

TAILSCALE_HOSTNAME="$(get_tailscale_hostname)" || {
    log "No se pudo derivar hostname unico de Tailscale."
    exit 1
}

set_static_hostname "$TAILSCALE_HOSTNAME"

if tailscale_is_running && tailscale_has_ipv4; then
    log "Tailscale operativo."
    exit 0
fi

if [ ! -s "$AUTHKEY_FILE" ]; then
    log "Sin authkey disponible para recuperar la sesion."
    exit 1
fi

AUTHKEY=$(tr -d '\r\n' < "$AUTHKEY_FILE")

if tailscale up --authkey="$AUTHKEY" --hostname="$TAILSCALE_HOSTNAME" --accept-dns=false --advertise-tags=tag:safelock; then
    for i in $(seq 1 15); do
        if tailscale_is_running && tailscale_has_ipv4; then
            log "Sesion de Tailscale recuperada."
            exit 0
        fi
        sleep 2
    done
fi

log "No se pudo recuperar Tailscale."
exit 1
