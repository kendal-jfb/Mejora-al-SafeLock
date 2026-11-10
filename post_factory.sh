#!/bin/bash
set -u -o pipefail

LOG="/var/log/safelock-postfactory.log"
DONE_FILE="/etc/safelock-postfactory.done"
PIHOLE_DB="/root/safeLock_SoC/pihole/etc-pihole/gravity.db"
HEARTBEAT_SCRIPT="/root/safeLock_SoC/scripts/heartbeat.sh"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [POSTFACTORY] $*" | tee -a "$LOG"
}

mkdir -p "$(dirname "$LOG")"
touch "$LOG"
chmod 644 "$LOG"

log "Inicio de post_factory"

if [ -f "$DONE_FILE" ]; then
    log "Ya existe $DONE_FILE, no se ejecuta de nuevo"
    exit 0
fi

command -v sqlite3 >/dev/null 2>&1 || { log "sqlite3 no instalado"; exit 0; }
command -v docker >/dev/null 2>&1 || { log "docker no instalado"; exit 0; }

# 1. Esperar gravity.db
READY_DB=0
for i in $(seq 1 24); do
    if [ -f "$PIHOLE_DB" ]; then
        READY_DB=1
        break
    fi
    log "Esperando gravity.db... intento $i/24"
    sleep 5
done

if [ "$READY_DB" -eq 1 ]; then
    sqlite3 "$PIHOLE_DB" "INSERT OR IGNORE INTO domainlist (type, domain, enabled, comment) VALUES (3, '(\.|^)(pornhub\.com|xvideos\.com|bet365\.com|onlyfans\.com|xnxx\.com)$', 0, '[PACK_FAMILY]');" || true
    sqlite3 "$PIHOLE_DB" "INSERT OR IGNORE INTO domainlist (type, domain, enabled, comment) VALUES (3, '(\.|^)(tiktok\.com|tiktokcdn\.com|instagram\.com|facebook\.com|fbcdn\.net|twitter\.com|x\.com)$', 0, '[PACK_DETOX]');" || true
    sqlite3 "$PIHOLE_DB" "INSERT OR IGNORE INTO domainlist (type, domain, enabled, comment) VALUES (3, '(\.|^)(roblox\.com|minecraft\.net|epicgames\.com|epicgames\.dev|fortnite\.com|ea\.com|steampowered\.com|steamcommunity\.com|riotgames\.com|leagueoflegends\.com|playvalorant\.com|battle\.net|blizzard\.com|supercell\.com|pubg\.com)$', 0, '[PACK_GAMES]');" || true
    sqlite3 "$PIHOLE_DB" "INSERT OR IGNORE INTO domainlist (type, domain, enabled, comment) VALUES (3, '(\.|^)(telemetry\.microsoft\.com|logs\.roku\.com|device-metrics-us\.amazon\.com|metric\.apple\.com|usage\.netflix\.com)$', 0, '[PACK_PRIVACY]');" || true

    # Lista blanca de endpoints críticos de gaming para que adlists (StevenBlack, etc.) no rompan Fortnite u otros juegos
    for gdom in tracking.epicgames.com datarouter.ol.epicgames.com api.epicgames.dev dev.epicgames.com easyanticheat.net easy.ac battleye.com vivox.com; do
        sqlite3 "$PIHOLE_DB" "INSERT OR IGNORE INTO domainlist (type, domain, enabled, comment) VALUES (0, '$gdom', 1, '[SAFE_GAMING]');" || true
    done

    chmod 644 "$PIHOLE_DB" || true
    log "Packs y lista blanca de gaming en Pi-hole configurados"
else
    log "No aparecio gravity.db; se omite configuracion de packs"
fi

# 2. Esperar Pi-hole solo si el contenedor esta corriendo
if ! docker ps --format '{{.Names}}' | grep -qx 'pihole'; then
    log "Pi-hole desactivado o contenedor no corriendo; se omite espera"
else
    for i in $(seq 1 24); do
        if docker exec pihole pihole status >/dev/null 2>&1; then
            log "Pi-hole listo"
            break
        fi
        log "Esperando Pi-hole... intento $i/24"
        sleep 5
    done
fi
# 3. Heartbeat
if [ -f "$HEARTBEAT_SCRIPT" ]; then
    [ -x "$HEARTBEAT_SCRIPT" ] || chmod +x "$HEARTBEAT_SCRIPT"
    "$HEARTBEAT_SCRIPT" || true
    log "Heartbeat ejecutado"
else
    log "No existe $HEARTBEAT_SCRIPT"
fi

touch "$DONE_FILE"
chmod 644 "$DONE_FILE"
log "Post-factory completado"
exit 0
