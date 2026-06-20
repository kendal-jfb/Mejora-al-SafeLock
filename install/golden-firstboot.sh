#!/bin/bash
# SafeLock — re-personalización de CLON en el primer arranque (para imagen golden).
#
# Distingue MASTER de CLON por la MAC de end0 vs el id horneado en /etc/safelock/golden-master-id:
#   - MASTER (o clon ya personalizado): MAC == id horneado   -> NO-OP (seguro, no toca nada).
#   - CLON nuevo:                       MAC != id horneado    -> regenera identidad y reinicia.
#
# SEGURIDAD (crítico, esto corre potencialmente sobre la única unidad viva):
#   - Si falta el marcador, NO hace nada (evita borrar identidad por error).
#   - Solo actúa si la MAC NO coincide con la horneada -> imposible que dispare en el master.
set -u

MARKER=/etc/safelock/golden-master-id
IFACE=end0
log(){ logger -t safelock-firstboot "$*" 2>/dev/null; echo "[firstboot] $*"; }

HW=$(cat "/sys/class/net/$IFACE/address" 2>/dev/null | tr -d ':')
[ -z "$HW" ] && { log "sin MAC de $IFACE -> no-op"; exit 0; }

BAKED=$(cat "$MARKER" 2>/dev/null || echo "")
if [ -z "$BAKED" ]; then
    log "marcador ausente (no es imagen golden preparada) -> no-op"
    exit 0
fi
if [ "$HW" = "$BAKED" ]; then
    log "MAC coincide con master/clon-ya-personalizado ($HW) -> no-op"
    exit 0
fi

# ---------- Soy un CLON nuevo (MAC $HW != horneado $BAKED): re-personalizar ----------
log "CLON detectado (MAC $HW, horneado $BAKED). Re-personalizando identidad limpia..."

# 1) machine-id nuevo
rm -f /etc/machine-id /var/lib/dbus/machine-id
systemd-machine-id-setup >/dev/null 2>&1
ln -sf /etc/machine-id /var/lib/dbus/machine-id 2>/dev/null || true

# 2) llaves de host SSH únicas (evita que todos los clones compartan llave)
rm -f /etc/ssh/ssh_host_*
ssh-keygen -A >/dev/null 2>&1

# 3) Tailscale: estado limpio para re-registro (ÚNICO lugar permitido para borrarlo)
systemctl stop tailscaled >/dev/null 2>&1 || true
rm -rf /var/lib/tailscale/* 2>/dev/null || true
systemctl start tailscaled >/dev/null 2>&1 || true
# tailscale-autoconnect re-registra con /etc/tailscale-authkey (DEBE ser no expirable / OAuth)

# 4) hostname único safelock-<mac>
NEWHOST="safelock-$HW"
hostnamectl set-hostname "$NEWHOST" >/dev/null 2>&1 || echo "$NEWHOST" > /etc/hostname

# 5) borrar estado del master que NO debe heredarse
rm -f /var/lib/safelock/telemetry/* /var/lib/safelock/previous_commit \
      /var/lib/safelock/bad_commit /var/lib/safelock/hardening.done 2>/dev/null || true
: > /var/log/safelock-update.log 2>/dev/null || true
rm -f /var/lib/dhcp/* /var/lib/dhcpcd/*.lease 2>/dev/null || true
rm -f /etc/fake-hwclock.data /var/lib/systemd/random-seed 2>/dev/null || true
rm -f /root/safeLock_SoC/api/config.local.json /api/config.local.json 2>/dev/null || true

# 6) marcar ESTA caja como personalizada (su propia MAC) -> no vuelve a correr aquí
mkdir -p /etc/safelock
echo "$HW" > "$MARKER"

log "Re-personalización completa. Reiniciando para aplicar identidad limpia."
sync
systemctl reboot
