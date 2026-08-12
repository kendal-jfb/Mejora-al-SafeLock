#!/bin/bash
# Hook post-install de OTA v2. Lo ejecuta ota_agent.py (run_post_install) en CADA
# instalacion de un release, con RELEASE_DIR seteado, ANTES de mover el symlink `current`.
#
# ⚠️ CRITICO: si este hook sale != 0, apply_release lanza excepcion -> do_update REVIERTE
# el release y lo marca como fallido. Por eso TODO aqui es best-effort y el script
# SIEMPRE termina en `exit 0`: un arreglo de conveniencia (mDNS) jamas debe tumbar un
# release por su cuenta.
set -u
log() { echo "[post-install] $*"; }

# ── Resolucion de safelock.local en las TV box Linux ───────────────────────────
# El appliance PUBLICA safelock.local (avahi con host-name=safelock), pero en Linux
# RESOLVER un nombre .local exige el plugin NSS libnss-mdns; sin el, getaddrinfo()
# (lo que usa el navegador/curl) NO resuelve .local aunque el multicast y avahi
# respondan. Ademas se limita avahi a end0 para que anuncie la IP de LAN y no la de
# docker0/tailscale (que un peer de la LAN no puede alcanzar).
# Solo llegan aqui unidades ONLINE (OTA v2 requiere backend) -> apt tiene internet.

if ! dpkg -s libnss-mdns >/dev/null 2>&1; then
    if DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends libnss-mdns >/dev/null 2>&1; then
        log "libnss-mdns instalado"
    elif apt-get update >/dev/null 2>&1 && \
         DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends libnss-mdns >/dev/null 2>&1; then
        log "libnss-mdns instalado (tras apt-get update)"
    else
        log "AVISO: no se pudo instalar libnss-mdns; safelock.local no resolvera hasta lograrlo"
    fi
fi

# nsswitch: insertar mdns4_minimal antes de dns (idempotente). El postinst de Debian
# suele hacerlo al instalar el paquete; esto es red de seguridad si no quedo.
if ! grep -qE '^hosts:.*mdns4_minimal' /etc/nsswitch.conf 2>/dev/null; then
    [ -f /etc/nsswitch.conf.safelock.bak ] || cp -f /etc/nsswitch.conf /etc/nsswitch.conf.safelock.bak 2>/dev/null || true
    if sed -i -E '/^hosts:/ { /mdns4_minimal/! s/\<dns\>/mdns4_minimal [NOTFOUND=return] dns/ }' /etc/nsswitch.conf 2>/dev/null; then
        log "nsswitch: mdns4_minimal anadido"
    fi
fi

# avahi solo por end0 -> anuncia 192.168.x (LAN), no docker0/tailscale
if [ -f /etc/avahi/avahi-daemon.conf ] && ! grep -qE '^allow-interfaces=end0' /etc/avahi/avahi-daemon.conf; then
    sed -i -E 's/^[#[:space:]]*allow-interfaces=.*/allow-interfaces=end0/' /etc/avahi/avahi-daemon.conf 2>/dev/null || true
    grep -qE '^allow-interfaces=end0' /etc/avahi/avahi-daemon.conf 2>/dev/null || \
        echo 'allow-interfaces=end0' >> /etc/avahi/avahi-daemon.conf
    systemctl restart avahi-daemon >/dev/null 2>&1 || true
    log "avahi limitado a end0"
fi

# ── Whitelist de bancos de Costa Rica y firma digital ───────────────────────────
# Las listas de terceros de Pi-hole (phishing.army, Phishing.Database, urlhaus-filter,
# hagezi/pro.txt) cambian constantemente y a veces cazan como falso positivo un
# subdominio real de banca o del sistema de firma digital (ej. mercadeo.promerica.fi.cr
# via hagezi/pro.txt, visto en produccion). Un allow-regex en domainlist (type=2) gana
# siempre sobre cualquier coincidencia de gravity, sin importar que lista lo capture.
# gravity.db es un bind mount de datos que sobrevive a los releases (docs/OTA.md); la
# ruta no cambia entre versiones. No requiere red/apt -> corre tambien en modo base
# (pihole detenido: el INSERT igual queda listo para cuando se active).
GRAVITY_DB="/root/safeLock_SoC/pihole/etc-pihole/gravity.db"
if command -v sqlite3 >/dev/null 2>&1 && [ -f "$GRAVITY_DB" ]; then
    if sqlite3 "$GRAVITY_DB" \
        "INSERT OR IGNORE INTO domainlist (type, domain, enabled, comment) VALUES (2, '(\.|^)(bccr\.fi\.cr|micitt\.go\.cr|gob\.go\.cr|bncr\.fi\.cr|bancobcr\.com|bancopopular\.fi\.cr|bac\.net|davivienda\.cr|scotiabankcr\.com|promerica\.fi\.cr)\$', 1, '[WHITELIST_BANCA_CR]');" 2>/dev/null; then
        log "whitelist banca CR/firma digital OK en domainlist"
    else
        log "AVISO: no se pudo escribir el whitelist de banca CR en gravity.db"
    fi
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx pihole; then
        docker exec pihole pihole reloaddns >/dev/null 2>&1 || true
    fi
else
    log "AVISO: sqlite3 o gravity.db no disponibles; se omite whitelist banca CR"
fi

# best-effort: nunca revertir el release por el fix de mDNS o el whitelist de banca
exit 0
