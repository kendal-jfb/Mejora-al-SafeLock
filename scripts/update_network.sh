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
    sed -i "s|^SCAN_SUBNETS=\[.*\]|SCAN_SUBNETS=['$SUBNET --interface=end0']|" "$CONFIG_FILE"
    echo "Configuracion actualizada: $SUBNET --interface=end0"
    cd /root/safeLock_SoC/netalertx
    docker compose restart netalertx
    echo "NetAlertX reiniciado"
else
    echo "Archivo de configuracion no encontrado"
fi
