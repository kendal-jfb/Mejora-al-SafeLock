#!/bin/bash
LOG="/var/log/safelock-pihole-setup.log"
echo "[$(date)] Iniciando configuración de listas Pi-hole..." >> $LOG

# Esperar a que Pi-hole esté listo
for i in $(seq 1 30); do
  docker exec pihole pihole status > /dev/null 2>&1 && break
  echo "[$(date)] Esperando Pi-hole... intento $i" >> $LOG
  sleep 5
done

LISTS=(
  "https://phishing.army/download/phishing_army_blocklist_extended.txt"
  "https://raw.githubusercontent.com/mitchellkrogza/Phishing.Database/master/phishing-domains-ACTIVE.txt"
  "https://malware-filter.gitlab.io/malware-filter/urlhaus-filter-domains.txt"
  "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/domains/pro.txt"
)

for url in "${LISTS[@]}"; do
  docker exec pihole sqlite3 /etc/pihole/gravity.db \
    "INSERT OR IGNORE INTO adlist (address, enabled, comment) VALUES ('$url', 1, 'OpenLock default');"
  echo "[$(date)] Lista agregada: $url" >> $LOG
done

# Actualizar gravity (descargar listas)
echo "[$(date)] Actualizando gravity..." >> $LOG
docker exec pihole pihole -g >> $LOG 2>&1
echo "[$(date)] Setup completo." >> $LOG
