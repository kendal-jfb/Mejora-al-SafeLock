# SafeLock — Checklist de imagen golden (para venta / reemplazo)

**Fecha:** 2026-07-14 · **Rama:** `audit/phase1-hardening`

> Objetivo: capturar UNA imagen reproducible, endurecida y limpia, para flashear unidades
> nuevas o de reemplazo. **La imagen NO detiene los apagones** (eso es la fuente 5V≥3A +
> protector de picos); su valor es que cada unidad salga **blindada y con buen forense**.
> Correr en la unidad de **referencia/master** (`safelock-7a813b145d15`), que ya tiene todo aplicado.

---

## 0. Qué ya está resuelto por software (en esta rama)

**Anti-brick (Fase 1):** `fsck.repair=yes`, `commit=15`, holds de kernel/u-boot, watchdog, apt nocturno cortado.
**Longevidad (Fase C):** CPU governor `conservative` + techo 1.416 GHz, radios BT/WiFi off, menos escritura a eMMC
(p0f silenciado, journald acotado, logs Docker acotados), reloj NTP robusto.
**Forense:** flight recorder (voltaje NO fiable — ver nota), **sentinela de apagado** (distingue corte de energía de
apagado limpio), fix del bug de resize (disco completo).
Todo idempotente en `scripts/apply-hardening.sh` (pasos 1–14) + `deploy/`, entregable por imagen y por OTA.

---

## 1. Pre-captura (en el master)

- [ ] `git -C /root/safeLock_SoC status` limpio y en `audit/phase1-hardening`.
- [ ] `bash scripts/apply-hardening.sh` corre sin error (lo re-aplica `prepare-golden.sh` igualmente).
- [ ] Validación de salud (ver `CLAUDE.md` §7): `fsck.repair=yes`, `commit=15`, holds=4, 4 contenedores healthy,
      `safelock-api`/`portal` activos, heartbeat 200, `governor=conservative`, disco 29 G, `NTPSynchronized=yes`,
      `systemctl is-active safelock-boot-sentinel` = active.
- [ ] eMMC sana: `cat /sys/block/mmcblk1/device/life_time` (0x01 0x0x = 0–10 %).

## 2. Ramoops en un CANARIO (opcional pero recomendado — dump de pánico persistente)

Ramoops cambia la cmdline del kernel y requiere reinicio → **NUNCA en el master/única unidad viva**. Validar en un
clon canario ANTES de meterlo a la imagen:

- [ ] En el **canario** (no en el master): `SAFELOCK_ALLOW_RAMOOPS=1 bash install/enable-ramoops.sh`
      (el script se niega a correr en el master por MAC; escribe `/boot` atómico con backup).
- [ ] Reiniciar el canario. Validar: `dmesg | grep -i ramoops` y `ls /sys/fs/pstore/`.
- [ ] Prueba destructiva (solo canario): `echo c > /proc/sysrq-trigger` → reinicia → al volver
      `/sys/fs/pstore/dmesg-ramoops-0` tiene el rastro del pánico. `systemd-pstore` lo archiva a
      `/var/lib/systemd/pstore/`.
- [ ] Si funciona en el canario, incorporar a la imagen (correr el script en el master **solo** dentro del pipeline de
      horneado, o bakearlo aparte y validar). Método seguro: `reserve_mem=1M:0x1000:ramoops` (el kernel 6.12 elige la
      dirección; no se hardcodea nada).

## 3. Preparar y capturar

```bash
# En el master (deja el master intacto; instala firstboot, hornea MAC, aplica hardening, apt clean, quiesce, trim):
sudo bash install/prepare-golden.sh prepare
# Verifica que el dry-run del firstboot diga "no-op" y que termine en "LISTO PARA CAPTURAR".

# Desde el equipo del dueño (Windows/Mac), jalar la imagen por SSH/Tailscale:
ssh root@safelock-7a813b145d15  "dd if=/dev/mmcblk1 bs=4M | gzip -1"  > safelock_master.img.gz

# Reducir con PiShrink (WSL/Linux): comprime el espacio libre (ya trimeado) casi a cero.
sudo pishrink.sh -s -z safelock_master.img   # (descomprime primero si hace falta)

# En el master, revivir:
sudo bash install/prepare-golden.sh restore    # o simplemente reiniciar
```

## 4. Validar 1 CANARIO recién flasheado (antes de producción en serie)

Flashear la imagen en una caja NUEVA, encender, esperar 2–3 reboots (firstboot re-personaliza), y validar:

- [ ] **Disco completo:** `df -h /` ≈ 29 G, uso <30 % (prueba de que el fix de resize funcionó).
- [ ] **Contenedores:** `docker ps` = 4 corriendo/healthy.
- [ ] **Identidad nueva:** hostname `safelock-<MAC-del-clon>`, machine-id/SSH nuevos, **Tailscale online con nombre nuevo**.
      ⚠️ La authkey `/etc/tailscale-authkey` debe ser **reutilizable** (OAuth/no-expirable) o solo el 1er clon entra al tailnet.
- [ ] **Reloj:** `timedatectl` `synchronized=yes`.
- [ ] **Sentinela:** `cat /var/lib/safelock/telemetry/boot-events.log` (debe registrar arranques; contador de sucios en
      `/var/lib/safelock/unclean-count`) y `systemctl is-active safelock-boot-sentinel`.
- [ ] **Heartbeat:** `tail /var/log/heartbeat.log` → `code=200`.
- [ ] **Longevidad activa:** `cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor` = conservative;
      `lsmod | grep -c bluetooth` = 0.

## 5. Decisión OTA (definir antes de vender)

Hoy la imagen hornea el OTA **PAUSADO** (`safelock-update.timer` disabled + cron comentado). Para producción, elegir:

- **(Recomendado) Manual/pausado** hasta tener canario estable + estrategia; el dueño dispara updates controlados.
  Reactivar cuando toque: `systemctl enable --now safelock-update.timer` + descomentar el cron.
- **Automático:** solo tras validar que `apply-update.sh` en la flota nueva NO corre `npm run build` (portal precompilado)
  y que el canario aguanta un ciclo OTA completo. Ver reglas críticas en `CLAUDE.md` §5 (rollout en 2 etapas).

## 6. Lo que la imagen NO resuelve (hardware — decisión del dueño)

- **Fuente 5 V ≥ 3 A de calidad + protector de picos** — es lo único que ataca la causa raíz de los apagones.
- **RTC sin batería** (arranca en 2017; mitigado por fake-hwclock + NTP, pero es hardware).
- **eMMC viejo** (fab 2018) y cajas H96 baratas — factor de fiabilidad inherente; valorar mejor proveedor.
- **Voltaje no medible** en RK3566 (SARADC no cableado al riel; el corte solo se *infiere* del reset abrupto — para eso
  está el sentinela de apagado).
