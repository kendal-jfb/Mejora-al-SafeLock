#!/bin/bash
set -u -o pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/../scripts/tailscale-common.sh"

LOG="/var/log/safelock-factory.log"
DONE_FILE="/etc/safelock-factory.done"
NET_IF="end0"
SAFELOCK_ID_FILE="/etc/safelock-id"

log() {
    ts_log "$LOG" "[FACTORY] $*"
}

fail() {
    log "ERROR: $*"
    exit 1
}

mkdir -p "$(dirname "$LOG")"
touch "$LOG"
chmod 644 "$LOG"

log "Inicio de factory_setup"

if [ -f "$DONE_FILE" ]; then
    log "Ya existe $DONE_FILE, no se ejecuta de nuevo"
    exit 0
fi

command -v tailscale >/dev/null 2>&1 || fail "tailscale no instalado"
[ -s "$TAILSCALE_AUTHKEY_FILE" ] || fail "Falta $TAILSCALE_AUTHKEY_FILE"

if [ ! -s /etc/machine-id ]; then
    systemd-machine-id-setup || fail "No se pudo regenerar machine-id"
    log "machine-id regenerado"
else
    log "machine-id ya presente"
fi

mkdir -p /var/lib/dbus
ln -sf /etc/machine-id /var/lib/dbus/machine-id
log "machine-id enlazado para dbus"

if ! ls /etc/ssh/ssh_host_* >/dev/null 2>&1; then
    ssh-keygen -A || fail "No se pudieron regenerar las host keys SSH"
    log "Host keys SSH regeneradas"
else
    log "Host keys SSH ya presentes"
fi

if [ ! -r "/sys/class/net/$NET_IF/address" ]; then
    fail "No existe la interfaz $NET_IF o no tiene address"
fi

MAC_ADDRESS=$(tr -d ':\r\n' < "/sys/class/net/$NET_IF/address")
[ -n "$MAC_ADDRESS" ] || fail "No se pudo obtener MAC de $NET_IF"

echo "safelock-${MAC_ADDRESS}" > "$SAFELOCK_ID_FILE"
chmod 644 "$SAFELOCK_ID_FILE"
log "Device ID generado: safelock-${MAC_ADDRESS}"

TAILSCALE_HOSTNAME="safelock-${MAC_ADDRESS}"
ts_set_static_hostname "$TAILSCALE_HOSTNAME"

if ! ts_wait_for_network 120; then
    fail "La red o el DNS no estuvieron listos a tiempo"
fi
log "Red util confirmada"

if ! ts_start_daemon_if_needed; then
    fail "tailscaled no arranco"
fi
log "tailscaled activo"

if ts_running_with_ipv4; then
    log "Tailscale ya estaba activo con IPv4 asignada"
else
    if ! ts_needs_login; then
        log "tailscaled activo sin requerir login; se espera siguiente ciclo de watchdog"
    else
        if ts_run_up "$TAILSCALE_HOSTNAME" "$(ts_authkey)"; then
            sleep 3
        fi

        ts_running_with_ipv4 || fail "No se pudo registrar Tailscale"
        log "Tailscale registrado correctamente"
    fi
fi

touch "$DONE_FILE"
chmod 644 "$DONE_FILE"
log "Factory completado correctamente"
exit 0
