#!/bin/bash
# SafeLock - endurecimiento idempotente del sistema (Fase 1). Seguro de re-ejecutar.
# Aplica resiliencia anti-brick + acceso mDNS + watchdog + flight recorder + corte del
# apt automatico nocturno a UNA unidad. Lo invoca el OTA (apply-update.sh) una vez por
# version (flag por hash), o se puede correr a mano. NO usa 'set -e' a proposito: si un
# paso falla, el resto debe seguir aplicandose (resiliencia > atomicidad global).
#
# NOTA DE ROLLOUT: retira el congelado de IP estatica y deja DHCP+mDNS. Tras aplicarlo, una
# unidad que estaba en una IP "congelada" puede cambiar de IP; acceder por su nombre mDNS
# (safelock-<id>.local) o por Tailscale. POR ESO se despliega primero en 1-2 unidades CANARIO.
set -u

DIR="${SAFELOCK_DIR:-/root/safeLock_SoC}"
log() { echo "[hardening] $*"; }

# 1) cmdline del kernel: panic=10 + loglevel=7 + fsck.repair=yes (auto-reparacion de raiz).
#    Escritura ATOMICA de /boot: editar copia temporal, validar, y recien mv+sync. Un
#    armbianEnv.txt corrupto = brick que no arranca, asi que nunca se edita in-place.
ENV=/boot/armbianEnv.txt
if [ -f "$ENV" ]; then
    [ -f "$ENV.safelock.bak" ] || cp -f "$ENV" "$ENV.safelock.bak"
    tmp="$(mktemp "${ENV}.XXXXXX")" || tmp=""
    if [ -n "$tmp" ]; then
        cp -f "$ENV" "$tmp"
        if ! grep -q '^extraargs=' "$tmp"; then
            echo 'extraargs=panic=10 loglevel=7 fsck.repair=yes' >> "$tmp"
        else
            for kv in panic=10 loglevel=7 fsck.repair=yes; do
                grep -q -- "$kv" "$tmp" || sed -i "s|^extraargs=.*|& $kv|" "$tmp"
            done
        fi
        # Validar antes de reemplazar: archivo no vacio y con las claves criticas presentes.
        if [ -s "$tmp" ] && grep -q 'fsck.repair=yes' "$tmp" && grep -q 'panic=10' "$tmp"; then
            mv -f "$tmp" "$ENV"
            sync
            log "cmdline OK ($(grep '^extraargs=' "$ENV"))"
        else
            rm -f "$tmp"
            log "ERROR: armbianEnv generado invalido; se conserva el original intacto"
        fi
    fi
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

# 8) NEUTRALIZAR APT AUTOMATICO NOCTURNO (sospechoso #1 de los apagones de madrugada).
#    apt-daily.timer tiene RandomizedDelaySec=12h -> puede dispararse de madrugada; el pico
#    de descarga/dpkg es gatillo de brownout y, si toca kernel/u-boot, brick. Las
#    actualizaciones se haran de forma controlada por el dueño, no desatendidas de noche.
install -D -m644 "$DIR/deploy/apt/99safelock-no-auto-upgrade" \
    /etc/apt/apt.conf.d/99safelock-no-auto-upgrade
systemctl mask --now apt-daily.timer apt-daily-upgrade.timer >/dev/null 2>&1 || true
systemctl mask --now apt-daily.service apt-daily-upgrade.service >/dev/null 2>&1 || true
# cron de Armbian que refresca apt @daily/@reboot -> neutralizar idempotente (conserva backup)
CRON_ARM=/etc/cron.d/armbian-updates
if [ -f "$CRON_ARM" ] && grep -qE '^[[:space:]]*[^#].*armbian-apt-updates' "$CRON_ARM"; then
    [ -f "$CRON_ARM.safelock.bak" ] || cp -f "$CRON_ARM" "$CRON_ARM.safelock.bak"
    sed -i 's|^\([[:space:]]*[^#].*armbian-apt-updates\)|#SAFELOCK-disabled \1|' "$CRON_ARM"
fi
log "apt automatico nocturno deshabilitado (timers enmascarados + cron neutralizado)"

systemctl daemon-reload
systemctl enable --now safelock-flight-recorder.timer >/dev/null 2>&1 || true
systemctl daemon-reexec   # arma el watchdog sin reiniciar

log "endurecimiento completado"
