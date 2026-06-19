#!/bin/bash
set -euo pipefail

# GUARD: script SOLO para preparar la imagen maestra (pipeline de build).
# En un equipo de campo DESTRUYE identidad/acceso (Tailscale, machine-id, flags .done).
if [ "${SAFELOCK_ALLOW_IMAGE_CLEANUP:-0}" != "1" ]; then
    echo "ABORT: preparacion de imagen. Exporta SAFELOCK_ALLOW_IMAGE_CLEANUP=1 para confirmar." >&2
    exit 1
fi

echo "[1/10] Deteniendo servicios y contenedores activos..."
systemctl stop safelock-portal || true
systemctl stop safelock-api || true
systemctl stop tailscaled || true
docker stop netalertx || true
pihole-control desactivar || true

echo "[2/10] Limpiando identidad unica del equipo..."
rm -f /etc/safelock-id
rm -f /etc/safelock-ip-lock
rm -f /etc/safelock-factory.done
rm -f /etc/safelock-postfactory.done
rm -f /root/safeLock_SoC/api/config.json

echo "[3/10] Limpiando estado de Tailscale..."
rm -rf /var/lib/tailscale/*
# mantener /etc/tailscale-authkey

echo "[4/10] machine-id se limpia al final manualmente antes del dd"
# NO vaciar aqui para evitar que se regenere antes de tiempo
rm -f /var/lib/dbus/machine-id || true

echo "[5/10] Dejando NetAlertX limpio..."
if [ -f /root/safeLock_SoC/netalertx/data/db/app.db ]; then
  sqlite3 /root/safeLock_SoC/netalertx/data/db/app.db \
  "DELETE FROM Devices;
   DELETE FROM Events;
   DELETE FROM Online_History;
   DELETE FROM Sessions;
   DELETE FROM CurrentScan;
   DELETE FROM Notifications;" || true
fi

echo "[6/10] Asegurando Pi-hole apagado por defecto..."
pihole-control desactivar || true

echo "[7/10] Vaciando logs..."
: > /var/log/safelock-factory.log || true
: > /var/log/safelock-postfactory.log || true
: > /var/log/safelock-update.log || true
: > /var/log/tailscale-autoconnect.log || true
: > /var/log/connectivity-watchdog.log || true
: > /var/log/safelock-ip-lock.log || true
: > /var/log/heartbeat.log || true
: > /var/log/p0f.log || true
: > /var/log/passivedns.log || true
: > /var/log/pihole-setup.log || true
: > /var/log/opencanary.log || true

echo "[8/10] Limpiando leases e historial..."
rm -f /var/lib/misc/dnsmasq.leases || true
rm -f /root/.bash_history || true
history -c || true

echo "[9/10] Verificando servicios enabled..."
for s in \
  safelock-factory \
  safelock-postfactory \
  tailscaled \
  tailscale-autoconnect \
  connectivity-watchdog.timer \
  safelock-network \
  safelock-network.timer \
  docker \
  safelock-api \
  safelock-portal \
  safelock-ip-lock \
  avahi-daemon \
  p0f \
  arpwatch \
  armbian-resize-filesystem
do
  systemctl is-enabled "$s" || true
done

echo "[10/10] Limpieza terminada. Antes del dd ejecutar:"
echo "truncate -s 0 /etc/machine-id && sync && wc -c /etc/machine-id"
