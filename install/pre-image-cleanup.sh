#!/bin/bash
set -e

echo "=== SafeLock Pre-Image Cleanup ==="

rm -f /etc/safelock-id
rm -f /etc/safelock-ip-lock
rm -f /etc/safelock-factory.done
rm -f /etc/safelock-postfactory.done

echo -n > /etc/machine-id

rm -rf /var/lib/tailscale/*

echo "✓ Limpieza completada"
echo "✓ Host keys SSH: CONSERVADAS"
echo "✓ /etc/tailscale-authkey: CONSERVADA"
echo ""
echo "Listo para crear imagen maestra"
