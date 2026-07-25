#!/bin/bash
set -u

LOG="/var/log/heartbeat.log"
API_URL="https://telemetry.openlocksecurity.com/heartbeat"

# Secreto compartido de la flota, en el repo privado (riesgo aceptado por el dueno:
# evita provisionar una llave por equipo en 40+ unidades). Override opcional por
# /etc/safelock/telemetry.env si en el futuro se quieren claves por equipo.
API_SECRET="openlock2026"
[ -r /etc/safelock/telemetry.env ] && . /etc/safelock/telemetry.env

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

# Estado de la migracion a OTA v2, para poder seguirla desde el dashboard
# mientras la flota todavia reporta por este canal antiguo.
if [ -f /var/lib/safelock/ota/migrated ]; then
  MIGRATION_STATE="done"
elif [ -f /var/lib/safelock/ota/migrate_attempts ]; then
  MIGRATION_STATE="attempts:$(cat /var/lib/safelock/ota/migrate_attempts 2>/dev/null || echo '?')"
else
  MIGRATION_STATE="pending"
fi

JSON_PAYLOAD="{\"device_id\":\"$DEVICE_ID\",\"pihole_active\":$PIHOLE_ACTIVE,\"tailscale_ip\":\"$TAILSCALE_IP\",\"version\":\"1.3.1\",\"critical_alert\":$CRITICAL_ALERT,\"migration_state\":\"$MIGRATION_STATE\"}"

# curl ya emite "000" en %{http_code} si no hay respuesta; el viejo `|| echo 000`
# concatenaba y producia "000000" en el log. El :-000 cubre curl ausente.
HTTP_CODE="$(curl -sS -o /tmp/heartbeat.out -w '%{http_code}' \
  -X POST "$API_URL" \
  -H "Content-Type: application/json" \
  -H "x-api-secret: $API_SECRET" \
  -d "$JSON_PAYLOAD")"
HTTP_CODE="${HTTP_CODE:-000}"

if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "201" ] || [ "$HTTP_CODE" = "204" ]; then
  log "OK code=$HTTP_CODE payload=$JSON_PAYLOAD"
  echo "Heartbeat OK"
  exit 0
fi

RESP="$(cat /tmp/heartbeat.out 2>/dev/null || true)"
log "ERROR code=$HTTP_CODE payload=$JSON_PAYLOAD resp=$RESP"
echo "Heartbeat ERROR code=$HTTP_CODE"
exit 1
