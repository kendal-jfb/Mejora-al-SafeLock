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

# 9) CPU: governor conservative + techo de frecuencia (LONGEVIDAD del hardware).
#    ondemand salta a 1.8 GHz de golpe -> pico de corriente que degrada/mata fuentes
#    marginales (gatillo #1 de los apagones). conservative sube gradual y 1.416 GHz
#    recorta pico y calor sin impacto (workload de red usa <1.0 de carga).
install -D -m644 "$DIR/deploy/cpufreq/cpufrequtils" /etc/default/cpufrequtils
install -D -m644 "$DIR/systemd/safelock-cpufreq.service" /etc/systemd/system/safelock-cpufreq.service
systemctl enable safelock-cpufreq.service >/dev/null 2>&1 || true
for p in /sys/devices/system/cpu/cpufreq/policy*; do   # aplicar en vivo, sin reiniciar
    [ -w "$p/scaling_governor" ] && echo conservative > "$p/scaling_governor" 2>/dev/null || true
    [ -w "$p/scaling_max_freq" ] && echo 1416000 > "$p/scaling_max_freq" 2>/dev/null || true
done
log "cpu governor=conservative max=1.416GHz"

# 10) Apagar radios (BT/WiFi) y servicios inutiles: menos consumo, calor y superficie.
install -D -m644 "$DIR/deploy/modprobe/safelock-no-radios.conf" /etc/modprobe.d/safelock-no-radios.conf
systemctl disable --now wpa_supplicant.service >/dev/null 2>&1 || true
systemctl mask bluetooth.service >/dev/null 2>&1 || true
modprobe -r hci_uart btbcm btintel btqca btrtl bluetooth >/dev/null 2>&1 || true  # si en uso, el blacklist actua al reiniciar
log "radios BT/WiFi desactivadas (blacklist + wpa_supplicant off + bluetooth masked)"

# 11) Reducir escrituras a eMMC: p0f deja de inundar el journal (~4800 lineas/h; la
#     evidencia queda en /var/log/p0f.log) y el journal persistente se acota.
install -D -m644 "$DIR/deploy/p0f/10-safelock-quiet.conf" /etc/systemd/system/p0f.service.d/10-safelock-quiet.conf
install -D -m644 "$DIR/deploy/journald/safelock.conf" /etc/systemd/journald.conf.d/safelock.conf
log "p0f silenciado + journald acotado"

# 12) Logs de Docker acotados. daemon.json = default para contenedores NUEVOS (clones
#     recien provisionados); logrotate = acota los json-file YA existentes (contenedores
#     horneados en la imagen, que el clon no recrea) sin reiniciar Docker (copytruncate).
#     NO se reinicia Docker aqui a proposito (evita cortar el DNS en una corrida OTA
#     desatendida); daemon.json toma efecto al proximo reinicio natural.
if [ ! -f /etc/docker/daemon.json ]; then
    install -D -m644 "$DIR/deploy/docker/daemon.json" /etc/docker/daemon.json
elif ! cmp -s "$DIR/deploy/docker/daemon.json" /etc/docker/daemon.json; then
    cp -f /etc/docker/daemon.json /etc/docker/daemon.json.safelock.bak
    install -D -m644 "$DIR/deploy/docker/daemon.json" /etc/docker/daemon.json
fi
install -D -m644 "$DIR/deploy/logrotate/safelock-docker" /etc/logrotate.d/safelock-docker
log "logs de Docker acotados (daemon.json + logrotate)"

# 13) Reloj estable: timesyncd con IPs NTP anycast (no depende del DNS local = pihole).
install -D -m644 "$DIR/deploy/timesyncd/safelock.conf" /etc/systemd/timesyncd.conf.d/safelock.conf
systemctl restart systemd-timesyncd >/dev/null 2>&1 || true
log "timesyncd con NTP numerico (sin dependencia del DNS local)"

# 14) Sentinela de apagado: distingue apagado limpio de CORTE DE ENERGIA (forense real
#     del modo de falla, sin reservar memoria ni tocar el device-tree = cero riesgo de brick).
chmod +x "$DIR/scripts/boot-sentinel.sh" 2>/dev/null || true
install -D -m644 "$DIR/systemd/safelock-boot-sentinel.service" /etc/systemd/system/safelock-boot-sentinel.service
log "sentinela de apagado instalado"

# 15) Cerrar paneles internos sin autenticacion hacia la LAN. Todos los contenedores usan
#     network_mode: host -> sus webs (NetAlertX :20211 dashboard + :20212 API, Apprise
#     :8000 API) quedan pegadas directo a la IP del dispositivo, SIN login, visibles a
#     cualquiera en la red (mismo problema que ya se corrigio en Pi-hole via pihole.toml).
#     Nada del stack les habla por HTTP -> se bloquean hacia la LAN; se deja loopback y
#     Tailscale para que el dueño pueda depurar en remoto. Reglas en memoria del kernel,
#     por eso el servicio debe correr en cada boot (no hay iptables-persistent instalado).
chmod +x "$DIR/scripts/panel-lockdown.sh" 2>/dev/null || true
install -D -m644 "$DIR/systemd/safelock-panel-lockdown.service" /etc/systemd/system/safelock-panel-lockdown.service
log "paneles internos (netalertx/apprise) bloqueados hacia la LAN (permitido: loopback + tailscale)"

systemctl daemon-reload
systemctl enable --now safelock-flight-recorder.timer >/dev/null 2>&1 || true
systemctl enable --now safelock-boot-sentinel.service >/dev/null 2>&1 || true
systemctl enable --now safelock-panel-lockdown.service >/dev/null 2>&1 || true
systemctl enable safelock-cpufreq.service >/dev/null 2>&1 || true
systemctl restart p0f >/dev/null 2>&1 || true               # aplica StandardOutput=null
systemctl restart systemd-journald >/dev/null 2>&1 || true  # aplica el techo del journal
systemctl daemon-reexec   # arma el watchdog sin reiniciar

log "endurecimiento completado"
