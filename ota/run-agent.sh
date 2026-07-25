#!/bin/bash
# Lanzador del agente OTA con red de seguridad "last known good".
#
# Vive en /opt/safelock/agent/, FUERA del arbol de releases, para que un
# release roto no pueda dejar al dispositivo sin forma de actualizarse.
# Si el agente del release activo no existe o termina con error, se ejecuta
# la ultima copia que demostro funcionar.
#
# Deliberadamente sin `set -e`: aqui abortar a la primera es justo lo que
# rompio el updater anterior.

set -u

LOG="/var/lib/safelock/ota/ota.log"
CURRENT_AGENT="/opt/safelock/current/ota/ota_agent.py"
LKG_AGENT="/opt/safelock/agent/lkg/ota_agent.py"

mkdir -p /var/lib/safelock/ota

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [run-agent] $*" >> "$LOG"
}

if [ -f "$CURRENT_AGENT" ]; then
  python3 "$CURRENT_AGENT"
  rc=$?
  if [ "$rc" -eq 0 ]; then
    exit 0
  fi
  log "el agente del release activo fallo (rc=$rc)"
else
  log "no existe $CURRENT_AGENT"
fi

if [ -f "$LKG_AGENT" ]; then
  log "usando el agente last-known-good"
  python3 "$LKG_AGENT" --recover
  exit $?
fi

log "no hay agente LKG disponible; queda para el rescate"
exit 1
