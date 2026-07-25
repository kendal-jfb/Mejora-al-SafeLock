#!/bin/bash
# SafeLock — re-personalización de CLON en el primer arranque (para imagen golden).
#
# Distingue MASTER de CLON por la MAC de end0 vs el id horneado en /etc/safelock/golden-master-id:
#   - MASTER (o clon ya personalizado): MAC == id horneado   -> NO-OP (seguro, no toca nada).
#   - CLON nuevo:                       MAC != id horneado    -> regenera identidad y reinicia.
#
# ROBUSTEZ (aprendido a la mala en el canario): nada de dbus (hostnamectl cuelga tras cambiar
# machine-id), se actualiza /etc/hosts, todo comando de red/disco lleva 'timeout', y SIEMPRE se
# reinicia al final (nunca dejar la caja colgada con api/ssh caídos).
set -u

MARKER=/etc/safelock/golden-master-id
IFACE=end0
RS=/var/lib/safelock
mkdir -p "$RS" 2>/dev/null || true
# log PERSISTENTE en eMMC (sobrevive a los reboots): si un clon vuelve a fallar, se lee por SSH.
log(){ logger -t safelock-firstboot "$*" 2>/dev/null; echo "[firstboot $(date '+%F %T')] $*" | tee -a "$RS/firstboot.log" 2>/dev/null; }
safe_reboot(){ sync; systemctl reboot 2>/dev/null || reboot -f || true; exit 0; }

HW=$(cat "/sys/class/net/$IFACE/address" 2>/dev/null | tr -d ':')
[ -z "$HW" ] && { log "sin MAC de $IFACE -> no-op"; exit 0; }

BAKED=$(cat "$MARKER" 2>/dev/null || echo "")
[ -z "$BAKED" ]      && { log "marcador ausente (no es imagen golden preparada) -> no-op"; exit 0; }
[ "$HW" = "$BAKED" ] && { log "MAC coincide con master/clon-ya-personalizado ($HW) -> no-op"; exit 0; }

# ---------- Soy un CLON nuevo (MAC $HW != horneado $BAKED) ----------
log "CLON detectado (MAC $HW, horneado $BAKED). Re-personalizando..."
mkdir -p "$RS"

# ---------- 0) Expandir el disco (imagen ENCOGIDA por pishrink) — ONLINE, sin reboot ----------
# BUG HISTÓRICO (probado en el 1er canario 2026-07-14): 'parted resizepart' NO puede
# redimensionar la raíz MONTADA. En modo script (-s) responde "No" al prompt "Partition
# is being used. Are you sure?" y NUNCA reescribe la tabla -> el clon quedaba a 9 GB en un
# disco de 29 GB. (No se detectó antes porque en el master la partición ya era de 29 GB.)
# Método correcto y ONLINE: sfdisk crece la ENTRADA de la partición sin re-leer la tabla,
# 'partx -u' actualiza la vista del kernel EN CALIENTE (partición montada) y resize2fs
# crece el FS montado. Un solo paso, sin reboot. Idempotente (repetirlo es no-op).
DISK=/dev/mmcblk1; ROOTDEV=/dev/mmcblk1p1
if [ ! -f "$RS/resize.done" ]; then
    log "expandiendo disco al 100% (sfdisk + partx + resize2fs, online)..."
    if command -v sfdisk >/dev/null 2>&1 && command -v partx >/dev/null 2>&1; then
        # ', +' = mantener el inicio, crecer la partición 1 hasta el final del disco.
        echo ', +' | timeout 60 sfdisk --no-reread --no-tell-kernel -N 1 "$DISK" >>"$RS/firstboot.log" 2>&1 \
            || log "WARN: sfdisk falló al crecer la partición"
        timeout 30 partx -u "$DISK" >>"$RS/firstboot.log" 2>&1 || log "WARN: partx -u falló"
    else
        # Fallback si faltara util-linux: parted forzando respuestas al prompt interactivo.
        log "WARN: sfdisk/partx ausentes; fallback a parted ---pretend-input-tty"
        printf 'Fix\nYes\n' | timeout 60 parted ---pretend-input-tty "$DISK" resizepart 1 100% >>"$RS/firstboot.log" 2>&1 || true
        timeout 30 partprobe "$DISK" >>"$RS/firstboot.log" 2>&1 || true
    fi
    if timeout 300 resize2fs "$ROOTDEV" >>"$RS/firstboot.log" 2>&1; then
        touch "$RS/resize.done"
        log "disco expandido OK ($(df -h / | awk 'NR==2{print $2" total, "$5" usado"}'))"
    else
        # NO marcar done -> reintenta en el próximo arranque (sfdisk/resize2fs son idempotentes).
        log "WARN: resize2fs falló; se reintentará en el próximo arranque"
    fi
fi

# ---------- 1) machine-id nuevo (NO llamar dbus/hostnamectl después de esto) ----------
rm -f /etc/machine-id /var/lib/dbus/machine-id
systemd-machine-id-setup >/dev/null 2>&1
ln -sf /etc/machine-id /var/lib/dbus/machine-id 2>/dev/null || true

# ---------- 2) llaves de host SSH únicas ----------
rm -f /etc/ssh/ssh_host_*
ssh-keygen -A >/dev/null 2>&1

# ---------- 3) hostname SIN dbus: escritura directa + /etc/hosts (evita cuelgues de resolución) ----------
NEWHOST="safelock-$HW"
echo "$NEWHOST" > /etc/hostname
if grep -qE '^127\.0\.1\.1' /etc/hosts 2>/dev/null; then
    sed -i "s/^127\.0\.1\.1.*/127.0.1.1\t$NEWHOST/" /etc/hosts
else
    printf '127.0.1.1\t%s\n' "$NEWHOST" >> /etc/hosts
fi

# ---------- 3b) identidad OTA: /etc/safelock-id debe ser LA DE ESTE CLON ----------
# El agente OTA v2 (ota/ota_agent.py) reporta al backend con lo que haya aqui.
# Sin esto, un clon hereda el id horneado en la imagen y suplanta a otra maquina.
echo "$NEWHOST" > /etc/safelock-id
chmod 644 /etc/safelock-id

# ---------- 4) Tailscale: estado limpio (con timeout; NO lo arranco aquí, lo hace el reboot) ----------
timeout 20 systemctl stop tailscaled >/dev/null 2>&1 || true
rm -rf /var/lib/tailscale/* 2>/dev/null || true
# al reiniciar, tailscaled + tailscale-autoconnect re-registran con /etc/tailscale-authkey (OAuth no-expirable)

# ---------- 5) borrar estado del master que NO debe heredarse ----------
rm -f /var/lib/safelock/telemetry/* /var/lib/safelock/previous_commit \
      /var/lib/safelock/bad_commit /var/lib/safelock/hardening.done 2>/dev/null || true
# sentinela de apagado: que el clon empiece su propio conteo (no herede el del master)
rm -f /var/lib/safelock/power-state /var/lib/safelock/unclean-count 2>/dev/null || true
: > /var/log/safelock-update.log 2>/dev/null || true
: > /var/log/heartbeat.log 2>/dev/null || true
# journal del master: no debe viajar al clon (privacidad + tamaño)
journalctl --rotate >/dev/null 2>&1 || true; journalctl --vacuum-time=1s >/dev/null 2>&1 || true
rm -f /var/lib/dhcp/* /var/lib/dhcpcd/*.lease 2>/dev/null || true
rm -f /etc/fake-hwclock.data /var/lib/systemd/random-seed 2>/dev/null || true

# ---------- 6) reclamar identidad (AL FINAL) -> no vuelve a correr aquí ----------
mkdir -p /etc/safelock
echo "$HW" > "$MARKER"

log "Re-personalización completa. Reiniciando limpio."
safe_reboot
