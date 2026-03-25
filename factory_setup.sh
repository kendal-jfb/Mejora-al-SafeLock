#!/bin/bash
set -Eeuo pipefail

LOG="/var/log/safelock-factory.log"
DONE_FILE="/etc/safelock-factory.done"
NET_IF="end0"
SAFELOCK_ID_FILE="/etc/safelock-id"
TAILSCALE_AUTHKEY_FILE="/etc/tailscale-authkey"
PIHOLE_DB="/root/safeLock_SoC/pihole/etc-pihole/gravity.db"
HEARTBEAT_SCRIPT="/root/safeLock_SoC/heartbeat.sh"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [FACTORY] $*"
}

mkdir -p "$(dirname "$LOG")"
touch "$LOG"
chmod 644 "$LOG"
exec >> "$LOG" 2>&1

trap 'log "ERROR en linea $LINENO"; exit 1' ERR

log "Inicio de setup de primer arranque"

if [ -f "$DONE_FILE" ]; then
    log "Ya existe $DONE_FILE, no se ejecuta de nuevo"
    exit 0
fi

sleep 10

command -v sqlite3 >/dev/null 2>&1 || { log "sqlite3 no instalado"; exit 1; }
command -v docker >/dev/null 2>&1 || { log "docker no instalado"; exit 1; }
command -v tailscale >/dev/null 2>&1 || { log "tailscale no instalado"; exit 1; }

# 1. Regenerar machine-id si fue limpiado antes de crear la imagen
if [ ! -s /etc/machine-id ]; then
    systemd-machine-id-setup
    log "machine-id regenerado"
else
    log "machine-id ya presente"
fi

mkdir -p /var/lib/dbus
ln -sf /etc/machine-id /var/lib/dbus/machine-id

# 3. Generar ID unico por placa usando MAC de end0
if [ ! -r "/sys/class/net/$NET_IF/address" ]; then
    log "No existe la interfaz $NET_IF o no tiene address"
    exit 1
fi

MAC_ADDRESS=$(tr -d ':\r\n' < "/sys/class/net/$NET_IF/address")
if [ -z "$MAC_ADDRESS" ]; then
    log "No se pudo obtener MAC de $NET_IF"
    exit 1
fi

echo "safelock-${MAC_ADDRESS}" > "$SAFELOCK_ID_FILE"
chmod 644 "$SAFELOCK_ID_FILE"
log "Device ID generado: safelock-${MAC_ADDRESS}"

# 4. Esperar a que exista gravity.db en la ruta host
for i in $(seq 1 12); do
    [ -f "$PIHOLE_DB" ] && break
    log "Esperando gravity.db... intento $i/12"
    sleep 5
done

[ -f "$PIHOLE_DB" ] || { log "No existe $PIHOLE_DB"; exit 1; }

# 5. Insertar packs por defecto en Pi-hole
sqlite3 "$PIHOLE_DB" "INSERT OR IGNORE INTO domainlist (type, domain, enabled, comment) VALUES (3, '(\.|^)(pornhub\.com|xvideos\.com|bet365\.com|onlyfans\.com|xnxx\.com)$', 0, '[PACK_FAMILY]');"
sqlite3 "$PIHOLE_DB" "INSERT OR IGNORE INTO domainlist (type, domain, enabled, comment) VALUES (3, '(\.|^)(tiktok\.com|tiktokcdn\.com|instagram\.com|facebook\.com|fbcdn\.net|twitter\.com|x\.com)$', 0, '[PACK_DETOX]');"
sqlite3 "$PIHOLE_DB" "INSERT OR IGNORE INTO domainlist (type, domain, enabled, comment) VALUES (3, '(\.|^)(roblox\.com|minecraft\.net|epicgames\.com|ea\.com|steampowered\.com)$', 0, '[PACK_GAMES]');"
sqlite3 "$PIHOLE_DB" "INSERT OR IGNORE INTO domainlist (type, domain, enabled, comment) VALUES (3, '(\.|^)(telemetry\.microsoft\.com|logs\.roku\.com|device-metrics-us\.amazon\.com|metric\.apple\.com|usage\.netflix\.com)$', 0, '[PACK_PRIVACY]');"

chmod 644 "$PIHOLE_DB" || true
log "Pi-hole packs configurados"

# 6. Registrar Tailscale
[ -s "$TAILSCALE_AUTHKEY_FILE" ] || { log "Falta $TAILSCALE_AUTHKEY_FILE"; exit 1; }

AUTHKEY=$(tr -d '\r\n' < "$TAILSCALE_AUTHKEY_FILE")



for i in $(seq 1 15); do
    if systemctl is-active --quiet tailscaled; then
        break
    fi
    log "Esperando tailscaled... intento $i/15"
    sleep 2
done

systemctl is-active --quiet tailscaled || { log "tailscaled no arranco"; exit 1; }

tailscale up --authkey="$AUTHKEY" --accept-dns=false --advertise-tags=tag:safelock
log "Tailscale registrado"

# 7. Esperar a que Pi-hole en Docker este realmente listo
READY=0
for i in $(seq 1 30); do
    if docker exec pihole pihole status >/dev/null 2>&1; then
        READY=1
        break
    fi
    log "Esperando Pi-hole en Docker... intento $i/30"
    sleep 5
done

[ "$READY" -eq 1 ] || { log "Pi-hole no estuvo listo a tiempo"; exit 1; }

# 8. Enviar primer heartbeat
[ -f "$HEARTBEAT_SCRIPT" ] || { log "No existe $HEARTBEAT_SCRIPT"; exit 1; }
[ -x "$HEARTBEAT_SCRIPT" ] || chmod +x "$HEARTBEAT_SCRIPT"

"$HEARTBEAT_SCRIPT"
log "Heartbeat enviado al SOC"

# 9. Marcar como completado
touch "$DONE_FILE"
chmod 644 "$DONE_FILE"
log "Setup completado correctamente"
