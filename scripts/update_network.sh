#!/bin/bash

CURRENT_IP=$(ip addr show end0 | grep 'inet ' | awk '{print $2}' | cut -d'/' -f1)
SUBNET=$(echo $CURRENT_IP | awk -F'.' '{print $1"."$2"."$3".0/24"}')

if [ -z "$SUBNET" ]; then
    echo "No se pudo detectar la subred"
    exit 1
fi

echo "Subred detectada: $SUBNET"
CONFIG_FILE="/root/safeLock_SoC/netalertx/data/config/app.conf"

if [ -f "$CONFIG_FILE" ]; then
    DESIRED="SCAN_SUBNETS=['$SUBNET --interface=end0']"
    if grep -qF "$DESIRED" "$CONFIG_FILE"; then
        echo "Subred sin cambios ($SUBNET); no se reinicia NetAlertX (anti-churn)."
    else
        sed -i "s|^SCAN_SUBNETS=\[.*\]|$DESIRED|" "$CONFIG_FILE"
        echo "Configuracion actualizada: $SUBNET --interface=end0"
        cd /root/safeLock_SoC/netalertx
        docker compose restart netalertx
        echo "NetAlertX reiniciado"
    fi
else
    echo "Archivo de configuracion no encontrado"
fi
