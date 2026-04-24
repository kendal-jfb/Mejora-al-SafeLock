#!/bin/bash
set -u -o pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/tailscale-common.sh"

LOG_FILE="/var/log/tailscale-autoconnect.log"

log() {
    ts_log "$LOG_FILE" "[TAILSCALE-AUTOCONNECT] $*"
}

exec 9>"$TAILSCALE_LOCK_FILE"
if ! flock -n 9; then
    log "Otro proceso de recuperacion ya esta ejecutandose."
    exit 0
fi

if ! ts_authkey_available; then
    log "No existe $TAILSCALE_AUTHKEY_FILE; no se intenta autenticacion."
    exit 0
fi

if ! ts_wait_for_network "$TAILSCALE_NETWORK_TIMEOUT"; then
    log "La red o el DNS no estuvieron listos a tiempo."
    exit 1
fi

if ! ts_start_daemon_if_needed; then
    log "tailscaled no quedo activo."
    exit 1
fi

TAILSCALE_HOSTNAME="$(ts_get_hostname)" || {
    log "No se pudo derivar hostname unico de Tailscale."
    exit 1
}

ts_set_static_hostname "$TAILSCALE_HOSTNAME"

if ts_running_with_ipv4; then
    log "Tailscale ya esta operativo con IPv4."
    exit 0
fi

if ! ts_needs_login; then
    log "tailscaled esta activo pero no requiere login; se evita reloguear."
    exit 0
fi

AUTHKEY="$(ts_authkey)"

if ts_run_up "$TAILSCALE_HOSTNAME" "$AUTHKEY"; then
    sleep 3
    if ts_running_with_ipv4; then
        log "tailscale up exitoso."
        exit 0
    fi
fi

log "No se pudo completar tailscale up."
exit 1
