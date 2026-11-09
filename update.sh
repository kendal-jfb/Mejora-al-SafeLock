#!/bin/bash
set -euo pipefail

DIR="/root/safeLock_SoC"
cd "$DIR"

# Sincronizar archivos hacia /opt/safelock/current si el servicio corre desde alli
if [ -d /opt/safelock/current ]; then
    mkdir -p /opt/safelock/current/api /opt/safelock/current/portal_dist /opt/safelock/current/scripts
    cp -rf "$DIR"/api/* /opt/safelock/current/api/ 2>/dev/null || true
    cp -rf "$DIR"/portal/dist/* /opt/safelock/current/portal_dist/ 2>/dev/null || true
    cp -rf "$DIR"/scripts/* /opt/safelock/current/scripts/ 2>/dev/null || true
fi

bash /root/safeLock_SoC/scripts/apply-update.sh
