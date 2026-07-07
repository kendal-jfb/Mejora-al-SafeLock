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
log(){ logger -t safelock-firstboot "$*" 2>/dev/null; echo "[firstboot] $*"; }
safe_reboot(){ sync; systemctl reboot 2>/dev/null || reboot -f || true; exit 0; }

HW=$(cat "/sys/class/net/$IFACE/address" 2>/dev/null | tr -d ':')
[ -z "$HW" ] && { log "sin MAC de $IFACE -> no-op"; exit 0; }

BAKED=$(cat "$MARKER" 2>/dev/null || echo "")
[ -z "$BAKED" ]      && { log "marcador ausente (no es imagen golden preparada) -> no-op"; exit 0; }
[ "$HW" = "$BAKED" ] && { log "MAC coincide con master/clon-ya-personalizado ($HW) -> no-op"; exit 0; }

# ---------- Soy un CLON nuevo (MAC $HW != horneado $BAKED) ----------
log "CLON detectado (MAC $HW, horneado $BAKED). Re-personalizando..."
mkdir -p "$RS"

# ---------- 0) Expandir el disco (imagen ENCOGIDA por pishrink) — 2 fases, con timeout ----------
DISK=/dev/mmcblk1; ROOTDEV=/dev/mmcblk1p1
if [ ! -f "$RS/resize.done" ]; then
    if [ ! -f "$RS/resize.part" ]; then
        log "expandiendo partición al 100% del disco..."
        if timeout 60 parted -s -f "$DISK" resizepart 1 100% >/dev/null 2>&1; then
            touch "$RS/resize.part"
            log "partición expandida; reinicio para que el kernel relea la tabla..."
            safe_reboot
        else
            log "WARN: parted resizepart falló; continúo sin expandir"
            touch "$RS/resize.done"
        fi
    else
        log "creciendo filesystem (resize2fs)..."
        timeout 300 resize2fs "$ROOTDEV" >/dev/null 2>&1 || log "WARN: resize2fs falló"
        touch "$RS/resize.done"; rm -f "$RS/resize.part"
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

# ---------- 4) Tailscale: estado limpio (con timeout; NO lo arranco aquí, lo hace el reboot) ----------
timeout 20 systemctl stop tailscaled >/dev/null 2>&1 || true
rm -rf /var/lib/tailscale/* 2>/dev/null || true
# al reiniciar, tailscaled + tailscale-autoconnect re-registran con /etc/tailscale-authkey (OAuth no-expirable)

# ---------- 5) borrar estado del master que NO debe heredarse ----------
rm -f /var/lib/safelock/telemetry/* /var/lib/safelock/previous_commit \
      /var/lib/safelock/bad_commit /var/lib/safelock/hardening.done 2>/dev/null || true
: > /var/log/safelock-update.log 2>/dev/null || true
rm -f /var/lib/dhcp/* /var/lib/dhcpcd/*.lease 2>/dev/null || true
rm -f /etc/fake-hwclock.data /var/lib/systemd/random-seed 2>/dev/null || true

# ---------- 6) reclamar identidad (AL FINAL) -> no vuelve a correr aquí ----------
mkdir -p /etc/safelock
echo "$HW" > "$MARKER"

log "Re-personalización completa. Reiniciando limpio."
safe_reboot
