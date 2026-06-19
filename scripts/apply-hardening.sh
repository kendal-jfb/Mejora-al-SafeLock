#!/bin/bash
# SafeLock - endurecimiento idempotente del sistema (Fase 1). Seguro de re-ejecutar.
# Aplica resiliencia anti-brick + acceso mDNS + watchdog + flight recorder a UNA unidad.
# Pensado para correr una vez por equipo (via systemd oneshot con flag .done) en el rollout.
#
# NOTA DE ROLLOUT: retira el congelado de IP estatica y deja DHCP+mDNS. Tras aplicarlo, una
# unidad que estaba en una IP "congelada" puede cambiar de IP; acceder por su nombre mDNS
# (safelock-<id>.local) o por Tailscale.
set -u

DIR="${SAFELOCK_DIR:-/root/safeLock_SoC}"
log() { echo "[hardening] $*"; }

# 1) cmdline del kernel: panic=10 + loglevel=7 + fsck.repair=yes (auto-reparacion de raiz)
ENV=/boot/armbianEnv.txt
if [ -f "$ENV" ]; then
    [ -f "$ENV.safelock.bak" ] || cp -f "$ENV" "$ENV.safelock.bak"
    if ! grep -q '^extraargs=' "$ENV"; then
        echo 'extraargs=panic=10 loglevel=7 fsck.repair=yes' >> "$ENV"
    else
        for kv in panic=10 loglevel=7 fsck.repair=yes; do
            grep -q -- "$kv" "$ENV" || sed -i "s|^extraargs=.*|& $kv|" "$ENV"
        done
    fi
    log "cmdline OK ($(grep '^extraargs=' "$ENV"))"
fi

# 2) fstab: commit=120 -> commit=15 (menos datos en riesgo por corte de energia)
if grep -qE '[[:space:]]/[[:space:]].*commit=120' /etc/fstab; then
    sed -i 's/commit=120/commit=15/' /etc/fstab
    mount -o remount,commit=15 / 2>/dev/null || true
    log "fstab commit=15"
fi

# 3) holds de kernel/u-boot/bsp (evita brick por flasheo desatendido interrumpido)
apt-mark hold linux-image-current-rockchip64 linux-dtb-current-rockchip64 \
    linux-u-boot-h96-tvbox-3566-current armbian-bsp-cli-h96-tvbox-3566-current >/dev/null 2>&1 || true
log "holds aplicados"

# 4) retirar el IP-lock fantasma (congelaba IP estatica -> inalcanzable al cambiar de red)
systemctl disable --now safelock-ip-lock.service >/dev/null 2>&1 || true
rm -f /etc/network/interfaces.d/end0 /etc/network/interfaces.d/end0.bak
rm -f /usr/local/bin/smart_ip_lock.sh
log "ip-lock neutralizado (DHCP+mDNS)"

# 5) watchdog systemd (auto-recuperacion de cuelgues + bootstatus)
install -D -m644 "$DIR/deploy/system.conf.d/10-safelock-watchdog.conf" \
    /etc/systemd/system.conf.d/10-safelock-watchdog.conf

# 6) panel por mDNS
install -D -m644 "$DIR/deploy/avahi/safelock-panel.service" \
    /etc/avahi/services/safelock-panel.service
systemctl reload avahi-daemon 2>/dev/null || systemctl restart avahi-daemon 2>/dev/null || true

# 7) flight recorder forense (telemetria a eMMC)
install -D -m644 "$DIR/systemd/safelock-flight-recorder.service" /etc/systemd/system/safelock-flight-recorder.service
install -D -m644 "$DIR/systemd/safelock-flight-recorder.timer"   /etc/systemd/system/safelock-flight-recorder.timer
chmod +x "$DIR/scripts/flight-recorder.sh" 2>/dev/null || true

systemctl daemon-reload
systemctl enable --now safelock-flight-recorder.timer >/dev/null 2>&1 || true
systemctl daemon-reexec   # arma el watchdog sin reiniciar

log "endurecimiento completado"
