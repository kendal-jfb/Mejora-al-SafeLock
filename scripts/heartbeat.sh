#!/bin/bash
set -u

LOG="/var/log/heartbeat.log"
API_URL="https://safelock-telemetry.onrender.com/heartbeat"

# El secreto NO va en el codigo versionado: se carga de un fichero local 0600
# (provisionado por fabrica, fuera de git). Si falta, el heartbeat falla de forma
# segura (sin secreto) en vez de exponerlo en el repo.
SECRET_FILE="${SAFELOCK_SECRET_FILE:-/etc/safelock/telemetry.env}"
[ -r "$SECRET_FILE" ] && . "$SECRET_FILE"
API_SECRET="${API_SECRET:-}"

DEVICE_ID="safelock-$(cat /sys/class/net/end0/address | tr -d ':')"
TAILSCALE_IP="$(tailscale ip -4 2>/dev/null | head -1)"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [HEARTBEAT] $*" >> "$LOG"
}

mkdir -p "$(dirname "$LOG")"
touch "$LOG"
chmod 644 "$LOG"

if docker ps --format '{{.Names}}' | grep -qx pihole; then
  PIHOLE_ACTIVE=true
else
  PIHOLE_ACTIVE=false
fi

CRITICAL_ALERT=false

if ! docker ps --format '{{.Names}}' | grep -qx opencanary; then
  CRITICAL_ALERT=true
fi

if ! systemctl is-active --quiet p0f; then
  CRITICAL_ALERT=true
fi

if ! systemctl is-active --quiet tailscaled; then
  CRITICAL_ALERT=true
fi

if ! systemctl is-active --quiet safelock-api; then
  CRITICAL_ALERT=true
fi

JSON_PAYLOAD="{\"device_id\":\"$DEVICE_ID\",\"pihole_active\":$PIHOLE_ACTIVE,\"tailscale_ip\":\"$TAILSCALE_IP\",\"version\":\"1.3.1\",\"critical_alert\":$CRITICAL_ALERT}"

HTTP_CODE="$(curl -sS -o /tmp/heartbeat.out -w '%{http_code}' \
  -X POST "$API_URL" \
  -H "Content-Type: application/json" \
  -H "x-api-secret: $API_SECRET" \
  -d "$JSON_PAYLOAD" || echo 000)"

if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "201" ] || [ "$HTTP_CODE" = "204" ]; then
  log "OK code=$HTTP_CODE payload=$JSON_PAYLOAD"
  echo "Heartbeat OK"
  exit 0
fi

RESP="$(cat /tmp/heartbeat.out 2>/dev/null || true)"
log "ERROR code=$HTTP_CODE payload=$JSON_PAYLOAD resp=$RESP"
echo "Heartbeat ERROR code=$HTTP_CODE"
exit 1
