#!/bin/bash
set -e

echo "=== SafeLock Pre-Image Cleanup ==="

# Archivos a eliminar
rm -f /etc/safelock-id
rm -f /etc/safelock-ip-lock
rm -f /etc/safelock-factory.done

# Vaciar machine-id
echo -n > /etc/machine-id

# Limpiar Tailscale state
rm -rf /var/lib/tailscale/*

echo "✓ Limpieza completada"
echo "✓ Host keys SSH: CONSERVADAS"
echo "✓ /etc/tailscale-authkey: CONSERVADA"
echo ""
echo "Listo para crear imagen maestra"
