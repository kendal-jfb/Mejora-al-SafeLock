#!/bin/bash
# Rescate de SafeLock: la ultima red de seguridad del dispositivo.
#
# Este script se instala UNA sola vez (durante la migracion) y el canal OTA
# normal NUNCA lo actualiza. Esa es toda su virtud: lo que no cambia no se
# rompe. Si el agente OTA muere, si el symlink `current` queda colgando o si
# la API lleva horas caida, esto lo devuelve a un estado arrancable y avisa.
#
# Sin `set -e` a proposito: debe llegar hasta el final incluso con errores.

set -u

OTA_ROOT="/opt/safelock"
CURRENT="$OTA_ROOT/current"
RELEASES="$OTA_ROOT/releases"
STATE_DIR="/var/lib/safelock/ota"
STATE_FILE="$STATE_DIR/state.json"
LOG="$STATE_DIR/rescue.log"
CONF="/etc/safelock/ota.conf"
SECRET_FILE="/etc/safelock/device-secret"

ACTIONS=""

mkdir -p "$STATE_DIR"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [rescue] $*" >> "$LOG"
}

note() {
  ACTIONS="${ACTIONS}${ACTIONS:+,}$1"
  log "$1"
}

# --- 1. El agente lleva mas de 26h sin dejar rastro -------------------------
agent_stalled() {
  [ ! -f "$STATE_FILE" ] && return 0
  local age_now age_file
  age_now="$(date +%s)"
  age_file="$(stat -c %Y "$STATE_FILE" 2>/dev/null || echo 0)"
  [ $((age_now - age_file)) -gt 93600 ]
}

if agent_stalled; then
  note "agente_estancado"

  # Restaurar el lanzador si desaparecio o quedo corrupto.
  if [ ! -x "$OTA_ROOT/agent/run-agent.sh" ] && [ -f "$OTA_ROOT/rescue/run-agent.sh" ]; then
    mkdir -p "$OTA_ROOT/agent"
    cp -f "$OTA_ROOT/rescue/run-agent.sh" "$OTA_ROOT/agent/run-agent.sh"
    chmod +x "$OTA_ROOT/agent/run-agent.sh"
    note "lanzador_restaurado"
  fi

  systemctl enable safelock-ota.timer >/dev/null 2>&1
  systemctl restart safelock-ota.timer >/dev/null 2>&1
  note "timer_ota_reiniciado"
fi

# --- 2. El symlink `current` no resuelve ------------------------------------
newest_release() {
  ls -1dt "$RELEASES"/*/ 2>/dev/null | while read -r dir; do
    if [ -f "${dir}VERSION" ]; then
      echo "${dir%/}"
      return
    fi
  done
}

if [ ! -d "$CURRENT" ]; then
  note "current_roto"
  TARGET="$(newest_release)"
  if [ -n "${TARGET:-}" ]; then
    ln -sfn "$TARGET" "$CURRENT.new" && mv -T "$CURRENT.new" "$CURRENT"
    cp -f "$TARGET"/systemd/*.service /etc/systemd/system/ 2>/dev/null
    cp -f "$TARGET"/systemd/*.timer /etc/systemd/system/ 2>/dev/null
    systemctl daemon-reload >/dev/null 2>&1
    systemctl restart safelock-api safelock-portal >/dev/null 2>&1
    note "current_restaurado:$(basename "$TARGET")"
  else
    note "sin_release_al_que_volver"
  fi
fi

# --- 3. La API sigue caida tras varios intentos -----------------------------
api_down() {
  local i
  for i in 1 2 3; do
    if systemctl is-active --quiet safelock-api; then
      return 1
    fi
    sleep 20
  done
  return 0
}

if [ -d "$CURRENT" ] && api_down; then
  note "api_caida"
  systemctl restart safelock-api >/dev/null 2>&1
  sleep 15

  if ! systemctl is-active --quiet safelock-api; then
    # El release activo no arranca: probamos el anterior que tenga VERSION.
    ACTIVE="$(readlink -f "$CURRENT" 2>/dev/null)"
    for dir in $(ls -1dt "$RELEASES"/*/ 2>/dev/null); do
      CAND="${dir%/}"
      [ "$(readlink -f "$CAND")" = "$ACTIVE" ] && continue
      [ -f "$CAND/VERSION" ] || continue
      ln -sfn "$CAND" "$CURRENT.new" && mv -T "$CURRENT.new" "$CURRENT"
      cp -f "$CAND"/systemd/*.service /etc/systemd/system/ 2>/dev/null
      cp -f "$CAND"/systemd/*.timer /etc/systemd/system/ 2>/dev/null
      systemctl daemon-reload >/dev/null 2>&1
      systemctl restart safelock-api safelock-portal >/dev/null 2>&1
      note "revertido_a:$(basename "$CAND")"
      break
    done
  fi
fi

# --- 4. Avisar siempre, aunque no se haya hecho nada ------------------------
BACKEND="https://telemetry.openlocksecurity.com"
if [ -f "$CONF" ]; then
  CONF_BACKEND="$(grep -E '^BACKEND_URL=' "$CONF" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"'"'"' ')"
  [ -n "${CONF_BACKEND:-}" ] && BACKEND="$CONF_BACKEND"
fi

DEVICE_ID="$(cat /etc/safelock-id 2>/dev/null)"
if [ -z "$DEVICE_ID" ]; then
  DEVICE_ID="safelock-$(cat /sys/class/net/end0/address 2>/dev/null | tr -d ':')"
fi
SECRET="$(cat "$SECRET_FILE" 2>/dev/null)"
VERSION="$(cat "$CURRENT/VERSION" 2>/dev/null || echo unknown)"
TAILSCALE_IP="$(tailscale ip -4 2>/dev/null | head -1)"

if [ -z "$ACTIONS" ]; then
  ACTIONS="ok"
else
  log "acciones aplicadas: $ACTIONS"
fi

PAYLOAD="{\"device_id\":\"$DEVICE_ID\",\"version\":\"$VERSION\",\"tailscale_ip\":\"$TAILSCALE_IP\",\"pihole_active\":false,\"critical_alert\":false,\"ota\":{\"state\":\"rescue\",\"last_result\":\"$ACTIONS\"}}"

curl -sS -m 30 -o /dev/null \
  -X POST "$BACKEND/heartbeat" \
  -H "Content-Type: application/json" \
  -H "x-device-id: $DEVICE_ID" \
  -H "x-device-secret: $SECRET" \
  -d "$PAYLOAD" 2>/dev/null

exit 0
