#!/bin/bash
# SafeLock — toggle del modo del producto.
#   El API decide "premium" por si el contenedor pihole está CORRIENDO (no hay flag).
#   premium = pihole activo ; base/normal = pihole detenido.
#
# CLAVE (bug corregido): pihole traía restart=always, con el que un 'docker stop' NO
# sobrevive a un reinicio (Docker lo relevanta) -> el modo base no persistía y tras un
# corte de luz la caja "se auto-activaba" premium. Con 'unless-stopped' el estado
# manual (corriendo/detenido) SÍ persiste across reboots, que es lo correcto para AMBOS
# modos. Por eso cada acción fija primero la política.

ACTION=$1

case $ACTION in
  activar)
    docker update --restart unless-stopped pihole >/dev/null 2>&1
    docker start pihole
    echo "Pi-hole activado (modo premium; persiste al reiniciar)"
    ;;
  desactivar)
    docker update --restart unless-stopped pihole >/dev/null 2>&1
    docker stop pihole
    echo "Pi-hole desactivado (modo base/normal; persiste al reiniciar)"
    ;;
  estado)
    if docker ps --format '{{.Names}}' | grep -qx pihole; then
      echo "activo"
    else
      echo "inactivo"
    fi
    ;;
  *)
    echo "Uso: pihole_control.sh [activar|desactivar|estado]"
    ;;
esac
