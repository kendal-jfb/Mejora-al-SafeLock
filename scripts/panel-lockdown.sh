#!/bin/bash
# SafeLock - bloquea hacia la LAN los paneles internos sin autenticacion que quedan
# pegados directo a la IP del dispositivo por network_mode: host (NetAlertX :20211
# dashboard + :20212 API, Apprise :8000 API). Nada del stack les habla por HTTP (todo es
# docker exec / lectura directa de DB, ver api/main.py), asi que solo se necesita acceso
# por loopback; se deja tambien tailscale0 para que el dueño pueda depurar en remoto.
# Idempotente (usa -C antes de -A): seguro de re-ejecutar en cada boot, no acumula reglas.
set -u

PORTS="20211,20212,8000"
TS_IFACE="tailscale0"

apply() {
    local cmd="$1"
    command -v "$cmd" >/dev/null 2>&1 || return 0
    "$cmd" -C INPUT -p tcp -m multiport --dports "$PORTS" -i lo -j ACCEPT 2>/dev/null \
        || "$cmd" -A INPUT -p tcp -m multiport --dports "$PORTS" -i lo -j ACCEPT
    "$cmd" -C INPUT -p tcp -m multiport --dports "$PORTS" -i "$TS_IFACE" -j ACCEPT 2>/dev/null \
        || "$cmd" -A INPUT -p tcp -m multiport --dports "$PORTS" -i "$TS_IFACE" -j ACCEPT
    "$cmd" -C INPUT -p tcp -m multiport --dports "$PORTS" -j DROP 2>/dev/null \
        || "$cmd" -A INPUT -p tcp -m multiport --dports "$PORTS" -j DROP
}

apply iptables
apply ip6tables
