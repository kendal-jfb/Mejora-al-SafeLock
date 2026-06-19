#!/bin/bash
set -euo pipefail

# GUARD: script SOLO para preparar la imagen maestra (pipeline de build).
# En un equipo de campo DESTRUYE identidad/acceso (Tailscale, machine-id, flags .done).
if [ "${SAFELOCK_ALLOW_IMAGE_CLEANUP:-0}" != "1" ]; then
    echo "ABORT: preparacion de imagen. Exporta SAFELOCK_ALLOW_IMAGE_CLEANUP=1 para confirmar." >&2
    exit 1
fi

echo "=== SafeLock Pre-Image Cleanup ==="

echo "[1/8] Deteniendo servicios que fijan estado..."
systemctl stop tailscale-autoconnect.service || true
systemctl stop connectivity-watchdog.service || true
systemctl stop tailscaled || true

echo "[2/8] Limpiando marcadores y archivos unicos..."
rm -f /etc/safelock-id
rm -f /etc/safelock-ip-lock
rm -f /etc/safelock-factory.done
rm -f /etc/safelock-postfactory.done
rm -f /root/safeLock_SoC/api/config.json

echo "[3/8] Limpiando identidad de Tailscale..."
rm -rf /var/lib/tailscale/*

echo "[4/8] Limpiando machine-id..."
truncate -s 0 /etc/machine-id
rm -f /var/lib/dbus/machine-id

echo "[5/8] Conservando host keys SSH para no romper acceso remoto..."

echo "[6/8] Ajustando hostname temporal de imagen..."
printf '%s\n' "safelock-template" > /etc/hostname
hostname safelock-template || true

echo "[7/8] Vaciando logs de SafeLock..."
: > /var/log/safelock-factory.log || true
: > /var/log/safelock-postfactory.log || true
: > /var/log/tailscale-autoconnect.log || true
: > /var/log/connectivity-watchdog.log || true
: > /var/log/heartbeat.log || true

echo "[8/8] Sincronizando cambios..."
sync

echo "✓ Limpieza completada"
echo "✓ Host keys SSH: CONSERVADAS"
echo "✓ /etc/tailscale-authkey: CONSERVADA"
echo "✓ Tailscale state: ELIMINADO"
echo "✓ machine-id: LIMPIO"
echo ""
echo "Listo para crear imagen maestra"
