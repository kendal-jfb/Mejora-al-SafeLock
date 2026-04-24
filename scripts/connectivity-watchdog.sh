#!/bin/bash
set -u -o pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/tailscale-common.sh"

LOG_FILE="/var/log/connectivity-watchdog.log"

log() {
    ts_log "$LOG_FILE" "[WATCHDOG] $*"
}

exec 9>"$TAILSCALE_LOCK_FILE"
if ! flock -n 9; then
    log "Otro proceso de recuperacion de Tailscale ya esta corriendo."
    exit 0
fi

if ! ts_wait_for_network 30; then
    log "La red o el DNS no estan listos; se reintentara en el siguiente ciclo."
    exit 1
fi

if ! ts_start_daemon_if_needed; then
    log "tailscaled sigue inactivo despues del reintento."
    exit 1
fi

for _ in $(seq 1 15); do
    if ts_running_with_ipv4; then
        log "Tailscale operativo."
        exit 0
    fi
    sleep 2
done

if ts_needs_login; then
    if ! ts_authkey_available; then
        log "Sin authkey disponible para recuperar la sesion."
        exit 1
    fi

    TAILSCALE_HOSTNAME="$(ts_get_hostname)" || {
        log "No se pudo derivar hostname unico de Tailscale."
        exit 1
    }

    ts_set_static_hostname "$TAILSCALE_HOSTNAME"
    log "tailscaled requiere login; intentando recuperar la sesion."
    if ts_run_up "$TAILSCALE_HOSTNAME" "$(ts_authkey)"; then
        sleep 3
        if ts_running_with_ipv4; then
            log "Sesion de Tailscale recuperada."
            exit 0
        fi
    fi

    log "No se pudo recuperar Tailscale."
    exit 1
fi

if [ "$(ts_backend_state)" = "Starting" ]; then
    log "tailscaled sigue calentando; se validara de nuevo en el siguiente ciclo."
    exit 0
fi

log "tailscaled esta activo pero aun sin IP de Tailscale; se reinicia el daemon."
systemctl restart tailscaled
sleep 10

for _ in $(seq 1 10); do
    if ts_running_with_ipv4; then
        log "Tailscale recuperado despues del reinicio del daemon."
        exit 0
    fi
    sleep 2
done

if [ "$(ts_backend_state)" = "Starting" ]; then
    log "tailscaled reiniciado y aun calentando; se validara de nuevo en el siguiente ciclo."
    exit 0
fi

log "No se pudo recuperar Tailscale."
exit 1
