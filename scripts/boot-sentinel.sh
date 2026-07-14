#!/bin/bash
# SafeLock — sentinela de apagado limpio vs corte de energía.
#
# Es el forense CORRECTO para el modo de falla real (las cajas pierden corriente):
# no necesita reservar memoria ni tocar el device-tree (cero riesgo de brick, a
# diferencia de ramoops), y responde directo "¿el apagado anterior fue un corte?".
#
# Idea: un archivo-marca en eMMC.
#   - En cada arranque ('boot'): si la marca dice "running" es que el apagado anterior
#     NUNCA llegó al hook de apagado limpio -> fue CORTE DE ENERGÍA (o pánico). Se
#     registra. Luego se re-arma la trampa escribiendo "running".
#   - En el apagado ORDENADO ('shutdown', vía ExecStop): se escribe "clean" -> desarma.
# Un corte de corriente jamás ejecuta el hook de apagado -> la marca queda "running"
# -> el siguiente arranque lo detecta y lo cuenta. Sobrevive al corte porque está en eMMC.
set -u

RS=/var/lib/safelock
MARK="$RS/power-state"
LOG="$RS/telemetry/boot-events.log"
mkdir -p "$RS/telemetry" 2>/dev/null || true

now_wall="$(date '+%Y-%m-%dT%H:%M:%S%z' 2>/dev/null)"
now_up="$(cut -d' ' -f1 /proc/uptime 2>/dev/null)"
clk="no"; command -v timedatectl >/dev/null 2>&1 && timedatectl show -p NTPSynchronized --value 2>/dev/null | grep -qi yes && clk="yes"

log(){ echo "$now_wall clock_synced=$clk uptime=${now_up}s :: $*" >> "$LOG" 2>/dev/null; logger -t safelock-boot-sentinel "$*" 2>/dev/null; }

case "${1:-boot}" in
boot)
    prev="$(cat "$MARK" 2>/dev/null || echo '')"
    case "$prev" in
        running*)
            # armado y no desarmado -> el apagado anterior fue sucio
            n="$(cat "$RS/unclean-count" 2>/dev/null || echo 0)"; n=$((n+1)); echo "$n" > "$RS/unclean-count"
            log "ARRANQUE TRAS APAGADO SUCIO (corte de energía o pánico). Marca previa: [$prev]. Total sucios: $n"
            ;;
        clean*)
            log "arranque tras apagado LIMPIO. Marca previa: [$prev]"
            ;;
        *)
            log "primer arranque (sin marca previa)"
            ;;
    esac
    # re-armar la trampa: si el próximo corte es sucio, esta marca seguirá aquí
    echo "running $now_wall up=$now_up" > "$MARK"; sync 2>/dev/null || true
    ;;
shutdown)
    echo "clean $now_wall up=$now_up" > "$MARK"; sync 2>/dev/null || true
    log "apagado limpio registrado"
    ;;
*)
    echo "uso: $0 [boot|shutdown]"; exit 1 ;;
esac
exit 0
