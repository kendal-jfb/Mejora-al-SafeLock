# SafeLock — Handoff para continuar el trabajo (AGENTS.md)

> **Este archivo y `CLAUDE.md` son espejos**: contienen lo mismo. Léelo completo antes de tocar nada.
> Es un **dispositivo de producción en crisis**, no un proyecto de juguete. Hay acciones que pueden **bricklear
> unidades en remoto sin posibilidad de recuperación**. Lee la sección "⚠️ REGLAS CRÍTICAS" antes de actuar.
>
> Fecha de última actualización: **2026-07-14**. Mantén este archivo al día al final de cada sesión.

---

## 1. Qué es esto
**SafeLock**: appliance de seguridad de red vendido al público general. Hardware = **TV box H96 con SoC Rockchip
RK3566** (4 GB RAM, eMMC 32 GB), **Armbian nightly/trunk** (Debian 12 bookworm). Stack en Docker:
`pihole + netalertx + opencanary + p0f + apprise + tailscale`. Código propio en **`/root/safeLock_SoC`**:
- **API**: FastAPI, `api/main.py`, puerto **8090** (servicio `safelock-api`).
- **Portal/panel web**: Vite/React, `portal/`, puerto **5173** (servicio `safelock-portal`). El cliente lo administra
  por navegador. El frontend deriva la URL de la API de `window.location.hostname` (host-agnóstico).
- **OTA**: basado en git. `update.sh` → `scripts/apply-update.sh` hace `git reset --hard origin/master`.
- Repo: `git@github.com:ethancrdr/safelock-device.git` · dueño: **ethancrdr@gmail.com** (único con acceso al repo y a
  la imagen de flasheo).

**Esta máquina (`/root`, hostname `safelock-<mac>`) es la unidad de REFERENCIA / "golden"** — misma imagen y código que
la flota. Es la **única unidad viva** que queda.

## 2. La crisis (por qué existe este trabajo)
Unidades de campo **se apagan de golpe y NO vuelven a encender** ni ciclando energía (bricking). Al **2026-06-19**:
- **Tailscale: 27/27 unidades de campo OFFLINE** (última conexión entre 15 h y 98 días). Solo vive esta referencia.
- **Sin acceso físico** a las unidades muertas y **solo el dueño tiene la imagen de flasheo** → hoy son
  **irrecuperables en remoto**.
- "Offline en Tailscale" ≠ "bricked": algunas podrían estar **vivas pero inalcanzables** (recuperables). Clasificar en
  sitio.

## 3. Diagnóstico de causa raíz (ordenado por probabilidad)
Los apagados son **cortes NO limpios**. Causa = **combinación**, no una sola falla:
1. **Fuente de alimentación marginal / brownout** (gatillo físico principal; hardware, no software). Las cajas + 4
   contenedores pueden superar el amperaje de una fuente barata; el calor la degrada con el tiempo.
2. **Corrupción de eMMC/FS por corte durante escritura** → explica el "no enciende". Amplificada por `commit=120`
   (hasta 2 min de datos en riesgo), **sin fsck al arrancar**, y **escritura constante** (OTA cada 10 min, netalertx
   cada 5 min, scheduler cada 1 min).
3. **apt automático nocturno** (encaja con la falla de las ~02:36): `apt-daily.timer` con `RandomizedDelaySec=12h`
   dispara de madrugada; `unattended-upgrades` ENABLED sin holds en la flota → pico de IO = gatillo de brownout, y si
   toca kernel/u-boot = brick.
4. **Upgrade de kernel/u-boot desatendido** que deja un nightly que no bootea.
5. **`smart_ip_lock.sh`** (servicio `safelock-ip-lock`, fantasma, no versionado): congelaba la IP como estática
   ifupdown → al cambiar la red, unidad inalcanzable (viva pero perdida).
6. Descartado por evidencia: OOM, desgaste de eMMC (sana, 0-10%), térmico al momento, disco lleno, watchdog.

**"¿Por qué fallaron tras 2 meses si estaban bien?"** No fue "de la nada": el daño se **acumula** (cada microcorte deja
corrupción que el journaling disimula hasta que toca algo crítico), coincide con un **evento raro** (la noche que sí
había un upgrade), y el **hardware se degrada** (la fuente cae con el uso y el calor de junio). La flota se aprovisionó
~mediados de marzo → a los 2-3 meses varias cruzaron el punto de no retorno casi a la vez.

## 4. Estado del trabajo (rama `audit/phase1-hardening`, **pusheada**, NO en master)
Todo el trabajo está en la rama, **NUNCA se ha tocado `master`** (para no desplegar a la flota sin supervisión).
**Fase 1 + Fase 2 device-side: HECHAS y validadas en esta unidad de referencia.**
- **Anti-brick:** `fsck.repair=yes` + `panic=10`+`loglevel=7` en `/boot/armbianEnv.txt`; `commit=120→15` en `/etc/fstab`;
  `apt-mark hold` de kernel/dtb/u-boot/bsp; watchdog systemd (`RuntimeWatchdogSec=60s`).
- **apt nocturno neutralizado:** `apt-daily`/`apt-daily-upgrade` (timer+service) **masked**;
  `deploy/apt/99safelock-no-auto-upgrade`; cron `armbian-updates` comentado.
- **Forense:** `scripts/flight-recorder.sh` + `systemd/safelock-flight-recorder.{service,timer}` → graba voltaje/temp a
  `/var/lib/safelock/telemetry/` cada 60 s (sobrevive al corte para probar la causa).
- **Acceso:** IP-lock retirado → **DHCP + mDNS** `safelock-<id>.local` (avahi, `deploy/avahi/safelock-panel.service`);
  `/myip` y `/qr` en la API.
- **OTA mejorado:** `scripts/apply-update.sh` ahora (a) anti-oscilación (marca `bad_commit`, no reaplica un commit que
  falló health-check), (b) **invoca `apply-hardening.sh` idempotente** (gate por hash en
  `/var/lib/safelock/hardening.done`) para entregar las configs de sistema que el git OTA **no** transporta, (c) NO
  hace `npm run build` (portal precompilado).
- **Portal precompilado** (`portal/dist` versionado) + CI `.github/workflows/portal-build.yml` → sin build en el equipo
  (anti-brownout).
- **`scripts/apply-hardening.sh`**: instalador idempotente y reproducible de TODO lo anterior. Escribe `/boot` de forma
  **atómica** (temp+validar+mv+sync). Es la pieza central para horneado de imagen y para el rollout.
- **Docs:** `docs/diagnostico-apagones.md` (técnico) y `docs/Informe-Tecnico-Apagones-SafeLock.docx` (para supervisión,
  enfoque blameless).
- **La referencia fue reiniciada 2026-06-19 y `fsck.repair` quedó CONFIRMADO activo** en `/proc/cmdline`. eMMC sana,
  FS clean, todos los servicios arriba.

### 4.1 Longevidad del hardware + limpieza (2026-07-14, misma rama `audit/phase1-hardening`)
**Contexto:** la **unidad maestra/golden murió sin encender (ningún LED)** tras idas de luz → falla de **alimentación
(hardware)**; el dueño lo acepta. La orden fue **exprimir el software para que las cajas duren lo más posible**. Un clon
vivo (`safelock-7a813b145d15`, esta referencia) **sobrevivió 2 cortes sucios** (9 y 14 jul) → el anti-brick funciona.
Todo lo nuevo entra en `scripts/apply-hardening.sh` (pasos **9–13**, idempotentes, mismo estilo) + `deploy/`:
- **CPU (palanca #1):** governor `conservative` + techo `1416000` (`deploy/cpufreq/cpufrequtils` +
  `systemd/safelock-cpufreq.service`, enabled). Recorta el **pico de corriente** que mata fuentes marginales y el calor;
  sin impacto (workload de red usa <1.0 de carga). Aplicado en vivo y al boot.
- **Radios off:** blacklist BT/WiFi (`deploy/modprobe/safelock-no-radios.conf`) + `wpa_supplicant` **disabled** +
  `bluetooth` **masked**. (WiFi ya no cargaba; BT venía por UART.)
- **Menos escritura a eMMC:** p0f `StandardOutput=null` (`deploy/p0f/10-safelock-quiet.conf`, cortó ~4.800 líneas/h al
  journal; evidencia sigue en `/var/log/p0f.log`), journald acotado (`deploy/journald/safelock.conf`), logs Docker
  acotados con `deploy/docker/daemon.json` (default para contenedores **nuevos**) + **logrotate copytruncate**
  (`deploy/logrotate/safelock-docker`, acota los **ya existentes** sin recrear contenedores) + `logging:` en
  `netalertx/docker-compose.yml`. **apply-hardening NO reinicia Docker** a propósito (evita cortar DNS en OTA desatendido;
  `daemon.json` toma efecto al próximo reinicio natural).
- **Reloj:** `timesyncd` con **IPs NTP anycast numéricas** (`deploy/timesyncd/safelock.conf`) → no depende del DNS local
  (= pihole); por esa dependencia circular perdía sync a las ~9 h. `NTPSynchronized=yes` confirmado.
- **Disco (bug de fábrica):** `install/golden-firstboot.sh` — `parted` salía con código **!=0** por el warning de "GPT
  backup no al final" **aunque SÍ redimensionaba**, y el script se rendía → el FS quedaba a **9 GB en partición de 29 GB**
  (se habría llenado en semanas). Corregido: no condiciona al exit code, arregla el GPT (`parted -f print`), corre
  `resize2fs` siempre, y loguea el error real. **Este clon expandido a 29 GB a mano** (`resize2fs`, ya al 26 %).
- **heartbeat.sh:** quitado el `|| echo 000` que producía `code=000000` en fallo de red (cosmético).
- **v2 (documentado, NO hecho):** **overlayroot** (raíz de solo-lectura) = blindaje definitivo anti-corte de luz; cambio
  mayor y riesgoso en DTB custom → se planifica aparte para no arriesgar la unidad viva.
- **OTA:** sigue **PAUSADO** (regla 2). Decisión de estado para producción pendiente del dueño; **no reactivar sin canario**.
**Validado en la referencia:** idempotente (2 corridas idénticas), 4 contenedores healthy, heartbeat 200,
`daemon.json` pasa `dockerd --validate`, p0f 0 líneas/h al journal, disco 29 G al 26 %, governor=conservative,
0 módulos BT cargados. **Aún NO desplegado a la flota** (viaja por imagen golden / OTA cuando el dueño lo ordene).

## 5. ⚠️ REGLAS CRÍTICAS (leer antes de actuar)
1. **NO mergear a `master` sin orden explícita y estrategia de canario.** `master` = lo que la flota tira por OTA. Un
   merge despliega a cualquier unidad ONLINE en ≤30 min. Hoy hay 0 online, pero la regla se mantiene.
2. **El OTA hace `git reset --hard origin/master`** → borra cualquier cambio local no commiteado. En **esta unidad el
   OTA está PAUSADO** (timer `disabled` + cron comentado `# [PAUSADO AUDITORIA]`). **No lo reanudes** sin necesidad; si
   corre, revierte el working tree a master.
3. **Las configs de sistema NO viajan por el git OTA** (`/boot/armbianEnv.txt`, `/etc/fstab`, watchdog, holds, apt).
   Se aplican vía `apply-hardening.sh`. Tenlo en cuenta para cualquier despliegue.
4. **Tocar `/boot/armbianEnv.txt` mal = brick.** Siempre escritura atómica + backup (`apply-hardening.sh` ya lo hace).
   Backup en `/boot/armbianEnv.txt.safelock.bak`.
5. **Rollout a la flota debe ser CANARIO primero** (1-2 unidades), y el bulk por master en **2 etapas** (maquinaria sin
   `portal/` primero, porque el `apply-update.sh` VIEJO de master corre `npm run build` en el equipo si cambia
   `portal/` → brownout). Detalle completo en el plan (§ Rollout canario).
6. **Secreto `openlock2026` hardcoded** en `scripts/heartbeat.sh`: **decisión del dueño** mantenerlo (repo privado, no
   quiere provisionar llave a 40+ unidades). **No re-externalizar** sin preguntar.
7. **NO unhold el kernel/u-boot** (`apt-mark hold` los protege del brick-por-upgrade). Imagen nightly.
8. **NUNCA borrar `/var/lib/tailscale`** en unidades de campo (solo en pipeline de imagen). Los scripts
   `cleanup_master.sh` / `install/pre-image-cleanup.sh` son peligrosos — ya tienen guard `SAFELOCK_ALLOW_IMAGE_CLEANUP`.
9. **Reinicios:** pídelos al usuario (los corre él con `!sudo systemctl reboot`); un agente intentando reboot fue
   bloqueado antes. Tras reiniciar, valida (§7).
10. **Quitar el IP-lock → la unidad pasa a DHCP → la IP cambia.** Acceso por `safelock-<id>.local:5173` (mDNS) o
    Tailscale. Verifica acceso ANTES de confiar en el cambio.

## 6. Decisión actual y SIGUIENTE TAREA
**Acordado 2026-06-19: el siguiente paso es la IMAGEN GOLDEN (Fase 3).** La flota está caída y la recuperación está
bloqueada → el rollout no tiene unidades vivas. Por eso se hornea una **imagen estable y reproducible con TODO el
endurecimiento** para unidades **nuevas/reemplazo**. El dueño hará el flasheo desde **otro equipo** (su Mac no corre
`rkdeveloptool`).

**Qué debe llevar la imagen golden (objetivo de Fase 3):**
- Migrar de Armbian **nightly/trunk → release estable** con **kernel fijado** (pinned).
- Aplicar `scripts/apply-hardening.sh` en el horneado (todo el anti-brick + apt-off + watchdog + mDNS + flight recorder).
- Holds de kernel/u-boot desde el inicio; `unattended-upgrades` y apt-daily desactivados de fábrica.
- Tailscale: auth por **OAuth/tags no expirables** (no authkey de 90 días); **no** borrar estado de TS en campo.
- Evaluar **raíz read-only / overlay** y **boot A/B / SD de recuperación** para auto-recuperación sin maskrom.
- **Fuente de alimentación de calidad (5 V ≥3 A)** + valorar UPS/capacitor (esto es hardware/logística del dueño).
- Guía de **recuperación maskrom (rkdeveloptool)** para revivir unidades muertas (Fase 3 / operativo).

## 7. Cómo validar la salud de esta unidad de referencia
```bash
grep -o 'fsck.repair=[a-z]*' /proc/cmdline      # debe decir fsck.repair=yes
findmnt -no OPTIONS /                            # debe incluir commit=15
systemctl is-enabled apt-daily.timer             # masked
apt-mark showhold | wc -l                        # 4
systemctl show -p RuntimeWatchdogUSec            # 1min ; ls /dev/watchdog
systemctl is-enabled safelock-update.timer       # disabled (OTA pausado)
for s in safelock-api safelock-portal safelock-flight-recorder.timer avahi-daemon; do systemctl is-active $s; done
docker ps --format '{{.Names}}: {{.Status}}'
curl -fsS http://localhost:8090/status           # responde
cat /sys/block/mmcblk1/device/life_time          # 0x01 0x00 = eMMC sana
```

## 8. Mapa de archivos críticos
- Arranque/FS: `/boot/armbianEnv.txt` (`extraargs`), `/etc/fstab` (`commit`).
- OTA: `update.sh`, `scripts/apply-update.sh`, `scripts/rollback.sh`, `systemd/safelock-update.timer`.
- Endurecimiento: **`scripts/apply-hardening.sh`** (pieza clave) + `deploy/` (`apt/`, `avahi/`, `system.conf.d/`,
  `systemd/`).
- Forense: `scripts/flight-recorder.sh`, `systemd/safelock-flight-recorder.*`, datos en `/var/lib/safelock/telemetry/`.
- Red/acceso: `scripts/update_network.sh`, avahi, `portal/` (panel), `api/main.py` (`/myip`, `/qr`, `/status`).
- Identidad: `scripts/tailscale-common.sh`, `/etc/tailscale-authkey`, `install/factory_setup.sh`.
- Secreto: `scripts/heartbeat.sh` (+ override opcional `/etc/safelock/telemetry.env`).
- **Fantasma a vigilar:** `/usr/local/bin/smart_ip_lock.sh` (archivado en `/root/safelock-audit-backups/`).
- Respaldos: `/root/safelock-audit-backups/`, `/boot/armbianEnv.txt.safelock.bak`, `/root/crontab.backup.*`,
  `/etc/cron.d/armbian-updates.safelock.bak`.

## 9. Convenciones del repo
- Trabaja en la rama **`audit/phase1-hardening`**. **No** pushees a `master`.
- Mensajes de commit terminan con: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Pushear la rama es seguro (no dispara despliegue ni el CI del portal, que es solo en `master`).

## 10. Punteros
- **Plan maestro** (lo más completo): **`docs/PLAN-maestro.md`** (copia en el repo, viaja a cualquier equipo) —
  diagnóstico, 3 fases, procedimiento de rollout canario completo y verificación. (El original vive en la máquina de
  referencia en `/root/.claude/plans/…`; la copia del repo es la que debes usar desde otro equipo.)
- Diagnóstico para supervisión: `docs/diagnostico-apagones.md` + `docs/Informe-Tecnico-Apagones-SafeLock.docx`.
- Estado pendiente (infra/dueño): tags firmados para releases; identidad Tailscale no expirable; activar CI con permiso
  de push; ramoops; limpiar `openlock2026` del historial (si algún día se decide rotar).
