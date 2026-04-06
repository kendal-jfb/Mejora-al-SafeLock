#!/bin/bash

# 1. Variables de Identificación
DEVICE_ID="safelock-$(cat /sys/class/net/end0/address | tr -d ':')"
API_URL="https://safelock-telemetry.onrender.com/heartbeat"
API_SECRET="openlock2026"
TAILSCALE_IP=$(tailscale ip -4 2>/dev/null | head -1)

# 2. Revisar si Pi-hole (Premium) está activo
if docker ps | grep -q pihole; then
    PIHOLE_ACTIVE="true"
else
    PIHOLE_ACTIVE="false"
fi

# 3. Revisar la Salud del Sistema (Alerta Roja)
# Si el Honeypot (opencanary) NO está activo, levanta la alerta.
CRITICAL_ALERT="false"
if ! docker ps | grep -q opencanary; then  # ← CORRECTO
    CRITICAL_ALERT="true"
fi

# Regla B: ¿El escáner de red está muerto?
if ! systemctl is-active --quiet p0f; then
    CRITICAL_ALERT="true"
fi

# Regla C: ¿Tú perdiste el acceso remoto?
if ! systemctl is-active --quiet tailscaled; then
    CRITICAL_ALERT="true"
fi

# Regla D: ¿El portal web del cliente se cayó?
# (Asumiendo que tu servicio se llama safelock-api)
if ! systemctl is-active --quiet safelock-api; then
    CRITICAL_ALERT="true"
fi

# 4. Construir y Enviar el JSON al SOC
JSON_PAYLOAD="{\"device_id\":\"$DEVICE_ID\", \"pihole_active\":$PIHOLE_ACTIVE, \"tailscale_ip\":\"$TAILSCALE_IP\", \"version\":\"1.3.1\", \"critical_alert\":$CRITICAL_ALERT}"

curl -s -X POST "$API_URL" \
    -H "Content-Type: application/json" \
    -H "x-api-secret: $API_SECRET" \
    -d "$JSON_PAYLOAD"

# Mensaje para cuando lo ejecutes a mano
echo "Latido enviado: $JSON_PAYLOAD"
