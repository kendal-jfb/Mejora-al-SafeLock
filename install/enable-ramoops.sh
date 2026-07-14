#!/bin/bash
# SafeLock — habilitar ramoops (dump de pánico de kernel persistente en RAM).
#
# ⚠️ SOLO PARA CANARIO / HORNEADO DE IMAGEN. NUNCA en la única unidad viva de referencia.
#    Cambia la cmdline del kernel (/boot) y REQUIERE REINICIO; una cmdline mala = brick.
#    Por eso el script:
#      - exige SAFELOCK_ALLOW_RAMOOPS=1 (opt-in explícito),
#      - se NIEGA a correr en el master horneado (MAC == golden-master-id),
#      - escribe /boot de forma ATÓMICA (temp+validar+mv+sync) y deja backup.
#
# Método SEGURO (kernel 6.12): 'reserve_mem=SIZE:ALIGN:NAME' reserva una región con
# nombre y el KERNEL elige la dirección (no se hardcodea ninguna dirección física, que
# es lo que podría corromper el arranque). ramoops la toma vía 'mem_name'.
#
# Tras reiniciar, validar:  cat /sys/fs/pstore/*   (debe existir tras el primer pánico)
#                           dmesg | grep -i ramoops
#   Prueba destructiva de pánico (solo canario):  echo c > /proc/sysrq-trigger  (reinicia)
#     -> al volver: /sys/fs/pstore/dmesg-ramoops-0 tendrá el rastro del pánico.
set -u

[ "${SAFELOCK_ALLOW_RAMOOPS:-0}" = "1" ] || {
    echo "ABORTA: exporta SAFELOCK_ALLOW_RAMOOPS=1 para confirmar (solo canario/horneado)."; exit 1; }

IFACE=end0
HW=$(cat "/sys/class/net/$IFACE/address" 2>/dev/null | tr -d ':')
BAKED=$(cat /etc/safelock/golden-master-id 2>/dev/null || echo "")
if [ -n "$BAKED" ] && [ "$HW" = "$BAKED" ]; then
    echo "ABORTA: esta es la unidad MASTER/referencia ($HW). Ramoops se valida en un CANARIO, no aquí."
    exit 1
fi

ENV=/boot/armbianEnv.txt
[ -f "$ENV" ] || { echo "ABORTA: no existe $ENV"; exit 1; }

# módulo + parámetro + carga al arranque
install -D -m644 /dev/stdin /etc/modprobe.d/ramoops.conf <<'EOF'
# SafeLock: ramoops toma la región reservada por 'reserve_mem=...:ramoops' en cmdline.
options ramoops mem_name=ramoops record_size=131072 console_size=131072 max_reason=2
EOF
echo ramoops > /etc/modules-load.d/ramoops.conf

# cmdline: añadir reserve_mem (1 MiB, alineado 4 KiB, nombre 'ramoops') de forma idempotente y atómica
if grep -q 'reserve_mem=.*ramoops' "$ENV"; then
    echo "[ramoops] reserve_mem ya presente en $ENV"
else
    [ -f "$ENV.ramoops.bak" ] || cp -f "$ENV" "$ENV.ramoops.bak"
    tmp="$(mktemp "${ENV}.XXXXXX")" && cp -f "$ENV" "$tmp" || { echo "ABORTA: mktemp"; exit 1; }
    if grep -q '^extraargs=' "$tmp"; then
        sed -i 's|^extraargs=.*|& reserve_mem=1M:0x1000:ramoops|' "$tmp"
    else
        echo 'extraargs=reserve_mem=1M:0x1000:ramoops' >> "$tmp"
    fi
    # validar: no vacío y con la clave; recién entonces reemplazar
    if [ -s "$tmp" ] && grep -q 'reserve_mem=1M:0x1000:ramoops' "$tmp"; then
        mv -f "$tmp" "$ENV"; sync
        echo "[ramoops] cmdline actualizada: $(grep '^extraargs=' "$ENV")"
    else
        rm -f "$tmp"; echo "ABORTA: armbianEnv generado inválido; original intacto"; exit 1
    fi
fi

echo "[ramoops] LISTO. REINICIA el canario y valida: dmesg | grep -i ramoops ; ls /sys/fs/pstore/"
