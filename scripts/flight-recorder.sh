#!/bin/bash
# SafeLock flight recorder - muestrea estado de salud a eMMC (NO zram) y lo
# fuerza a disco con sync(), para que la ULTIMA muestra antes de un apagon
# subito (brownout / panic / termico) sobreviva al corte y quede para forensia.
#
# Diseno: barato, sin dependencias, idempotente. Pensado para correr cada minuto
# via systemd timer. Toda la salida va a /var/lib/safelock/telemetry (eMMC).
set -u

DIR="/var/lib/safelock/telemetry"
CSV="$DIR/telemetry.csv"
KLOG="$DIR/kernel-last.log"
MAX_BYTES=$((5 * 1024 * 1024))   # ~5 MB, luego rota a .1

mkdir -p "$DIR"

# --- rotacion simple por tamano ---
if [ -f "$CSV" ]; then
    sz=$(stat -c %s "$CSV" 2>/dev/null || echo 0)
    if [ "$sz" -gt "$MAX_BYTES" ]; then
        mv -f "$CSV" "$CSV.1"
    fi
fi

# cabecera si el fichero es nuevo
if [ ! -f "$CSV" ]; then
    echo "ts_iso,clock_synced,uptime_s,load1,mem_avail_kb,swap_used_kb,cpu_cur_khz,cpu_max_khz,throttled,cpu_temp_mc,gpu_temp_mc,saradc_raw,saradc_scale" > "$CSV"
fi

# --- reloj sincronizado? (relevante: RTC sin bateria arranca en 2017) ---
CLK="no"
if command -v timedatectl >/dev/null 2>&1; then
    timedatectl show -p NTPSynchronized --value 2>/dev/null | grep -qi yes && CLK="yes"
fi
TS="$(date '+%Y-%m-%dT%H:%M:%S%z' 2>/dev/null)"

# --- metricas baratas ---
UPTIME_S="$(cut -d' ' -f1 /proc/uptime 2>/dev/null)"
LOAD1="$(cut -d' ' -f1 /proc/loadavg 2>/dev/null)"
MEM_AVAIL="$(awk '/MemAvailable/{print $2}' /proc/meminfo 2>/dev/null)"
SWAP_USED="$(awk '/SwapTotal/{t=$2} /SwapFree/{f=$2} END{print (t-f)+0}' /proc/meminfo 2>/dev/null)"
CPU_CUR="$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null || echo NA)"
CPU_MAX="$(cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq 2>/dev/null || echo NA)"
THROT="no"; [ "$CPU_CUR" != "NA" ] && [ "$CPU_MAX" != "NA" ] && [ "$CPU_CUR" -lt "$CPU_MAX" ] 2>/dev/null && THROT="yes"

CPU_TEMP="NA"; GPU_TEMP="NA"
for z in /sys/class/thermal/thermal_zone*; do
    t="$(cat "$z/type" 2>/dev/null)"
    v="$(cat "$z/temp" 2>/dev/null)"
    case "$t" in
        *cpu*) CPU_TEMP="$v" ;;
        *gpu*) GPU_TEMP="$v" ;;
    esac
done

# SARADC: util para detectar caida de tension de alimentacion (brownout)
SARADC_RAW="$(cat /sys/bus/iio/devices/iio:device0/in_voltage0_raw 2>/dev/null || echo NA)"
SARADC_SCALE="$(cat /sys/bus/iio/devices/iio:device0/in_voltage_scale 2>/dev/null || echo NA)"

echo "$TS,$CLK,$UPTIME_S,$LOAD1,$MEM_AVAIL,$SWAP_USED,$CPU_CUR,$CPU_MAX,$THROT,$CPU_TEMP,$GPU_TEMP,$SARADC_RAW,$SARADC_SCALE" >> "$CSV"

# --- snapshot de la cola del ring del kernel (sobre eMMC) ---
# Captura panics/oops/undervoltage/mmc-error que precedan a una caida.
{
    echo "# snapshot $TS (clock_synced=$CLK)"
    journalctl -k -b --no-pager 2>/dev/null | tail -n 120
} > "$KLOG.tmp" 2>/dev/null && mv -f "$KLOG.tmp" "$KLOG"

# fuerza ambos ficheros a la eMMC: si la energia se corta justo despues,
# la ultima muestra ya esta en disco.
sync
