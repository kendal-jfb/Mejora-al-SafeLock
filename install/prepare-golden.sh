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

    echo "[prepare-golden] aplicando endurecimiento (idempotente) para hornearlo en la imagen..."
    bash "$DIR/scripts/apply-hardening.sh" || echo "[prepare-golden] WARN: apply-hardening devolvió error (revisar arriba)"

    echo "[prepare-golden] limpieza de imagen (cache de apt; los logs del dispositivo los limpia el firstboot del clon)..."
    apt-get clean >/dev/null 2>&1 || true

    echo "[prepare-golden] deteniendo escritores para imagen consistente..."
    # OTA PRIMERO: con el OTA activo, su health-check exige safelock-api activo; si lo
    # paramos antes de frenar el timer, el ciclo de 30 min lo marca "no sano" y
    # rollback.sh lo reinicia solo -> el quiesce se deshace a mitad de captura (bug
    # real observado 2026-07-15). Frenar el timer ANTES evita la carrera.
    systemctl stop safelock-update.timer 2>/dev/null || true
    systemctl stop safelock-flight-recorder.timer safelock-heartbeat.timer \
                   safelock-pack-scheduler.timer connectivity-watchdog.timer 2>/dev/null || true
    systemctl stop safelock-api safelock-portal 2>/dev/null || true
    # Docker: PAUSE (no stop). 'docker stop' con restart=unless-stopped marca el contenedor como
    # "detenido por el usuario" y NO se reiniciaria en el clon. 'pause' congela las escrituras
    # (imagen consistente) pero deja el contenedor como en ejecución -> el clon lo levanta solo.
    docker pause $(docker ps -q) 2>/dev/null || true
    # que el clon arranque la expansión de disco y el log de firstboot desde cero
    rm -f /var/lib/safelock/resize.part /var/lib/safelock/resize.done \
          /var/lib/safelock/firstboot.log 2>/dev/null || true
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
    docker unpause $(docker ps -q) 2>/dev/null || true
    systemctl start safelock-api safelock-portal 2>/dev/null || true
    systemctl start safelock-flight-recorder.timer safelock-heartbeat.timer \
                    safelock-pack-scheduler.timer connectivity-watchdog.timer 2>/dev/null || true
    # Reactivar el OTA solo si esta unidad lo tenia habilitado (no forzarlo en unidades
    # donde el OTA sigue pausado a proposito).
    systemctl is-enabled --quiet safelock-update.timer 2>/dev/null && \
        systemctl start safelock-update.timer 2>/dev/null || true
    echo "[prepare-golden] servicios revividos. (Si prefieres, un reinicio limpio también sirve.)"
    ;;
*)
    echo "uso: $0 [prepare|restore]"; exit 1 ;;
esac
