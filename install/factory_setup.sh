#!/bin/bash
set -u -o pipefail

LOG="/var/log/safelock-factory.log"
DONE_FILE="/etc/safelock-factory.done"
NET_IF="end0"
SAFELOCK_ID_FILE="/etc/safelock-id"
TAILSCALE_AUTHKEY_FILE="/etc/tailscale-authkey"
HOSTNAME_FILE="/etc/hostname"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [FACTORY] $*" | tee -a "$LOG"
}

fail() {
    log "ERROR: $*"
    exit 1
}

set_static_hostname() {
    local new_hostname="$1"
    local current_hostname

    current_hostname="$(cat "$HOSTNAME_FILE" 2>/dev/null || hostname 2>/dev/null || true)"

    if [ "$current_hostname" != "$new_hostname" ]; then
        printf '%s\n' "$new_hostname" > "$HOSTNAME_FILE"
        hostname "$new_hostname" || true
        log "Hostname configurado: $new_hostname"
    else
        log "Hostname ya configurado: $new_hostname"
    fi
}

tailscale_is_running() {
    tailscale status --json 2>/dev/null | grep -q '"BackendState":"Running"'
}

tailscale_has_ipv4() {
    tailscale ip -4 2>/dev/null | grep -q '.'
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

if [ ! -r "/sys/class/net/$NET_IF/address" ]; then
    fail "No existe la interfaz $NET_IF o no tiene address"
fi

MAC_ADDRESS=$(tr -d ':\r\n' < "/sys/class/net/$NET_IF/address")
[ -n "$MAC_ADDRESS" ] || fail "No se pudo obtener MAC de $NET_IF"

echo "safelock-${MAC_ADDRESS}" > "$SAFELOCK_ID_FILE"
chmod 644 "$SAFELOCK_ID_FILE"
log "Device ID generado: safelock-${MAC_ADDRESS}"

TAILSCALE_HOSTNAME="safelock-${MAC_ADDRESS}"
set_static_hostname "$TAILSCALE_HOSTNAME"

HAS_IP=0
for i in $(seq 1 30); do
    if ip -4 addr show dev "$NET_IF" | grep -q "inet "; then
        HAS_IP=1
        break
    fi
    log "Esperando IP en $NET_IF... intento $i/30"
    sleep 2
done

[ "$HAS_IP" -eq 1 ] || fail "La interfaz $NET_IF no obtuvo IP"

TS_OK=0
for i in $(seq 1 30); do
    if systemctl is-active --quiet tailscaled; then
        TS_OK=1
        break
    fi
    log "Esperando tailscaled... intento $i/30"
    sleep 2
done

[ "$TS_OK" -eq 1 ] || fail "tailscaled no arranco"

AUTHKEY=$(tr -d '\r\n' < "$TAILSCALE_AUTHKEY_FILE")

if tailscale_is_running && tailscale_has_ipv4; then
    log "Tailscale ya estaba activo con IPv4 asignada"
else
    TS_UP=0
    for i in $(seq 1 10); do
        if tailscale up --authkey="$AUTHKEY" --hostname="$TAILSCALE_HOSTNAME" --accept-dns=false --advertise-tags=tag:safelock; then
            for j in $(seq 1 15); do
                if tailscale_is_running && tailscale_has_ipv4; then
                    TS_UP=1
                    break
                fi
                sleep 2
            done
        fi
        if [ "$TS_UP" -eq 1 ]; then
            break
        fi
        log "tailscale up fallo... intento $i/10"
        sleep 5
    done

    [ "$TS_UP" -eq 1 ] || fail "No se pudo registrar Tailscale"
    log "Tailscale registrado correctamente"
fi

touch "$DONE_FILE"
chmod 644 "$DONE_FILE"
log "Factory completado correctamente"
exit 0
