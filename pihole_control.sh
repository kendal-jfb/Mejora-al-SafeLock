#!/bin/bash

ACTION=$1

case $ACTION in
  activar)
    docker start pihole
    echo "Pi-hole activado"
    ;;
  desactivar)
    docker stop pihole
    echo "Pi-hole desactivado"
    ;;
  estado)
    if docker ps | grep -q pihole; then
      echo "activo"
    else
      echo "inactivo"
    fi
    ;;
  *)
    echo "Uso: pihole_control.sh [activar|desactivar|estado]"
    ;;
esac
