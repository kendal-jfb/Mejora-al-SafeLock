#!/bin/bash
# SafeLock — preparar el MASTER para capturar la imagen golden, y restaurarlo después.
#
# USO:
#   sudo bash install/prepare-golden.sh prepare   # instala firstboot, hornea id, quiesce escritores
#   <<capturar la imagen por la red>>
#   sudo bash install/prepare-golden.sh restore   # revive servicios (o simplemente reinicia)
#
# 'prepare' NO reinicia y NO borra nada del master: instala el firstboot y hornea la MAC del master
# en /etc/safelock/golden-master-id para que el firstboot sea NO-OP en este equipo. Luego detiene los
# escritores (docker + servicios safelock) y hace sync para que la imagen salga consistente.
set -u
DIR="${SAFELOCK_DIR:-/root/safeLock_SoC}"
IFACE=end0
HW=$(cat "/sys/class/net/$IFACE/address" 2>/dev/null | tr -d ':')
ACTION="${1:-prepare}"

case "$ACTION" in
prepare)
    echo "[prepare-golden] instalando firstboot de re-personalización..."
    install -D -m755 "$DIR/install/golden-firstboot.sh"        /usr/local/sbin/safelock-firstboot.sh
    install -D -m644 "$DIR/systemd/safelock-firstboot.service" /etc/systemd/system/safelock-firstboot.service
    systemctl daemon-reload
    systemctl enable safelock-firstboot.service >/dev/null 2>&1

    echo "[prepare-golden] horneando id del master ($HW) -> firstboot será NO-OP en este equipo"
    mkdir -p /etc/safelock
    echo "$HW" > /etc/safelock/golden-master-id

    echo "[prepare-golden] VERIFICACIÓN (dry-run del firstboot; DEBE decir 'no-op'):"
    bash /usr/local/sbin/safelock-firstboot.sh

    echo "[prepare-golden] deteniendo escritores para imagen consistente..."
    systemctl stop safelock-flight-recorder.timer safelock-heartbeat.timer \
                   safelock-pack-scheduler.timer connectivity-watchdog.timer 2>/dev/null || true
    systemctl stop safelock-api safelock-portal 2>/dev/null || true
    docker stop $(docker ps -q) 2>/dev/null || true
    sync; sync
    # TRIM del espacio libre: deja los bloques no usados en cero -> gzip los comprime casi a nada,
    # así el stream pesa ~ solo los datos usados (no los 29 GB del bloque). Es de bajo desgaste.
    echo "[prepare-golden] fstrim del espacio libre (acelera y reduce la imagen)..."
    fstrim -v / 2>/dev/null || true
    sync
    echo "[prepare-golden] LISTO PARA CAPTURAR. Servicios detenidos, disco sincronizado."
    echo "                 Captura ahora; al terminar: sudo bash $DIR/install/prepare-golden.sh restore"
    ;;
restore)
    echo "[prepare-golden] reviviendo servicios..."
    docker start $(docker ps -aq) 2>/dev/null || true
    systemctl start safelock-api safelock-portal 2>/dev/null || true
    systemctl start safelock-flight-recorder.timer safelock-heartbeat.timer \
                    safelock-pack-scheduler.timer connectivity-watchdog.timer 2>/dev/null || true
    echo "[prepare-golden] servicios revividos. (Si prefieres, un reinicio limpio también sirve.)"
    ;;
*)
    echo "uso: $0 [prepare|restore]"; exit 1 ;;
esac
