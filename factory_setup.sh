#!/bin/bash
# SafeLock Factory Setup v1.0
# Corre una sola vez en el primer arranque de cada placa nueva

# Esperar a que la red esté completamente lista
sleep 10

# 1. Generar ID único por placa basado en MAC
MAC_ADDRESS=$(ip link show end0 | awk '/ether/ {print $2}' | sed 's/://g')
echo "safelock-${MAC_ADDRESS}" > /etc/safelock-id
echo "[FACTORY] Device ID generado: safelock-${MAC_ADDRESS}"

# 2. Configurar Pi-hole Packs por defecto (INSERT OR IGNORE = seguro si ya existen)
sqlite3 /root/safeLock_SoC/pihole/etc-pihole/gravity.db "INSERT OR IGNORE INTO domainlist (type, domain, enabled, comment) VALUES (3, '(\.|^)(pornhub\.com|xvideos\.com|bet365\.com|onlyfans\.com|xnxx\.com)$', 0, '[PACK_FAMILY]');"
sqlite3 /root/safeLock_SoC/pihole/etc-pihole/gravity.db "INSERT OR IGNORE INTO domainlist (type, domain, enabled, comment) VALUES (3, '(\.|^)(tiktok\.com|tiktokcdn\.com|instagram\.com|facebook\.com|fbcdn\.net|twitter\.com|x\.com)$', 0, '[PACK_DETOX]');"
sqlite3 /root/safeLock_SoC/pihole/etc-pihole/gravity.db "INSERT OR IGNORE INTO domainlist (type, domain, enabled, comment) VALUES (3, '(\.|^)(roblox\.com|minecraft\.net|epicgames\.com|ea\.com|steampowered\.com)$', 0, '[PACK_GAMES]');"
sqlite3 /root/safeLock_SoC/pihole/etc-pihole/gravity.db "INSERT OR IGNORE INTO domainlist (type, domain, enabled, comment) VALUES (3, '(\.|^)(telemetry\.microsoft\.com|logs\.roku\.com|device-metrics-us\.amazon\.com|metric\.apple\.com|usage\.netflix\.com)$', 0, '[PACK_PRIVACY]');"
chmod 666 /root/safeLock_SoC/pihole/etc-pihole/gravity.db
echo "[FACTORY] Pi-hole packs configurados"

# 3. Autenticar Tailscale usando authkey del archivo (no hardcodeada)
systemctl start tailscaled
sleep 5
tailscale up --authkey=$(cat /etc/tailscale-authkey) --accept-dns=false --advertise-tags=tag:safelock
echo "[FACTORY] Tailscale registrado"

# 4. Esperar a que Docker y Pi-hole estén listos antes del heartbeat
echo "[FACTORY] Esperando Docker..."
for i in {1..12}; do
    docker ps | grep -q pihole && break
    echo "[FACTORY] Intento $i — esperando pihole..."
    sleep 5
done

# 5. Enviar primer heartbeat al SOC
/root/safeLock_SoC/heartbeat.sh
echo "[FACTORY] Heartbeat enviado al SOC"

# 6. Desactivar este servicio para que no vuelva a correr
systemctl disable safelock-factory.service
echo "[FACTORY] Setup completado — servicio desactivado"
