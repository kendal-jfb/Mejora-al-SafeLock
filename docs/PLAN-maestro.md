# Plan de saneamiento integral — Flota SafeLock

## Contexto
Producto comercial "SafeLock" (appliance de seguridad para el público general) construido sobre **TV box H96 con
SoC Rockchip RK3566**, Armbian *nightly/trunk*, con `pihole + netalertx + opencanary + p0f + Tailscale` en Docker y
una API/portal propios (`/root/safeLock_SoC`, repo `git@github.com:ethancrdr/safelock-device.git`).

**Síntoma reportado:** unidades de campo se apagan de golpe y **no vuelven a encender ni tras ciclar la energía**.
Esta unidad es la de **referencia ("golden")** — misma imagen y código que la flota; las que fallaron son otras y
**no hay acceso físico** a ellas, y **solo el dueño tiene la imagen de flasheo** → hoy las muertas son irrecuperables.

**Objetivo:** dejar el sistema en estado ideal — eliminar la deuda técnica y los errores arrastrados, evitar que
caigan más unidades, lograr **auto-recuperación**, y resolver el acceso al panel por equipo de forma robusta.

## Diagnóstico (resumen)
**Los apagados son cortes NO limpios** (journald corrupto en cada arranque; sin apagado ordenado). Hoy **ninguna
unidad guardaba evidencia del crash** (logs en zram, sin pstore/ramoops) — por eso la causa no se podía *probar*.
Descartado por evidencia: OOM, desgaste de eMMC (sana), térmico al momento, disco lleno, y el watchdog como causa.

**Por qué un equipo no vuelve a levantarse — vectores reales (ningún script hace `reboot/shutdown`; ninguna unidad
tiene `Restart=` en bucle):**
1. **Corrupción de eMMC/FS por corte de energía durante escrituras.** Amplificada por: `commit=120` (hasta 2 min de
   escrituras perdidas por corte), eMMC con caché ON + *barriers* OFF, **sin fsck automático al arrancar**
   (`errors=remount-ro`, max-mount-count=-1), `/boot` en la misma ext4 frágil, y **escritura constante** (OTA
   `git reset --hard` cada 10 min, netalertx reiniciado cada 5 min, scheduler cada 1 min).
2. **`smart_ip_lock.sh`** (servicio `safelock-ip-lock`, enabled, **no versionado**, en `/usr/local/bin`): congela la
   IP DHCP como **estática ifupdown**; si la red cambia, deja la unidad con IP inválida e inalcanzable. *(En la unidad
   de referencia está inerte porque el gestor activo es systemd-networkd, que ignora ifupdown.)*
3. **Fragilidad de identidad/acceso Tailscale:** authkey probablemente vencida (>90 días); scripts de imagen que
   borran estado de Tailscale; sin auto-reregistro fiable → pérdida de acceso (existencial sin acceso físico).
4. **Oscilación del OTA:** un commit malo en `master` se re-aplica cada 10 min (reset→fallo→rollback→repetir).
5. **apt automático nocturno (NUEVO — otra unidad murió 2026-06-19 ~02:36).** `apt-daily.timer` con
   `RandomizedDelaySec=12h` puede dispararse de madrugada; `/etc/cron.d/armbian-updates` corre `armbian-apt-updates`
   `@daily`+`@reboot`; **unattended-upgrades ENABLED, sin `50unattended-upgrades` (defaults) y sin holds en la flota**.
   → pico nocturno de CPU/IO (descarga+dpkg) = **gatillo de brownout** en fuente marginal, y si el corte cae durante
   una escritura de kernel/initramfs/u-boot = **brick que no vuelve**. Encaja con "de la nada, de noche, no enciende".
   `apply-hardening.sh` hoy solo pone *holds* de kernel; **falta neutralizar apt-daily/apt-daily-upgrade + el cron de
   armbian-updates** para quitar el gatillo nocturno por completo.

## Estado de ejecución (rama `audit/phase1-hardening`, 3 commits, SIN push)
**Fase 1 — completa y validada en la unidad de referencia:**
- Forense: flight recorder a eMMC + watchdog systemd + `panic=10`/`loglevel=7` + `systemd-pstore`.
- Anti-brick: `fsck.repair=yes` (staged, activa al reiniciar), `commit=120→15` (en vivo), holds kernel/u-boot,
  anti-churn (OTA no reaplica sin cambios; `update_network` no reinicia netalertx salvo cambio de subred).
- Acceso: IP-lock retirado; panel por **mDNS `safelock-<id>.local`** (avahi); `/myip` expone URL `.local`; el
  frontend ya usa `window.location.hostname`. Red verificada intacta.
- Higiene: guards en `cleanup_master.sh`/`pre-image-cleanup.sh`; cron rota eliminada; huérfanos de `/usr/local/bin`
  archivados. Reproducible: `scripts/apply-hardening.sh` + `deploy/`.

**Fase 2 — hecho lo device-side:**
- OTA anti-oscilación (marca `bad_commit`, no reaplica un commit que falló health-check).
- Portal **precompilado** (`portal/dist` versionado) → **sin `npm run build` en el equipo** (anti-brownout) + CI
  workflow `.github/workflows/portal-build.yml`. OTA cadencia 10→30 min, sin update inmediato post-boot.
- Secreto: revertida la externalización por decisión del dueño (repo privado); `heartbeat.sh` con override opcional.
- **Entrega de configs de sistema por OTA (commit `78ce70f`):** `apply-update.sh` ahora invoca `apply-hardening.sh`
  idempotente (gate por hash en `/var/lib/safelock/hardening.done`) → `fsck.repair`/fstab/watchdog/holds por fin
  llegan a unidades vivas. `apply-hardening.sh`: escritura **atómica** de `/boot` (temp+validar+mv+sync) y nueva
  sección que **neutraliza el apt nocturno** (mask `apt-daily`/`apt-daily-upgrade` + `deploy/apt/99safelock-no-auto-upgrade`
  + comenta cron `armbian-updates`). Validado en la referencia. `docs/diagnostico-apagones.md` para supervisión.
  **En la rama `audit/phase1-hardening` (pusheada), NO en master.**

**Respaldos:** `/root/safelock-audit-backups/`, `/boot/armbianEnv.txt.safelock.bak`, `/root/crontab.backup.*`,
`/etc/cron.d/armbian-updates.safelock.bak`.
**OTA PAUSADO** en esta unidad (timer disabled + cron comentado).

## Fase 2 — pendiente (infra/proceso del dueño, no device-code)
- **Releases por tags firmados:** adoptar workflow de tags (cambio de proceso de publicación) → implementar
  `apply-update` para seguir tags en vez de `master` cuando estén listos.
- **Identidad Tailscale:** en la consola, deshabilitar expiración para `tag:safelock` y usar OAuth/authkey no
  expirable; regenerar `/etc/tailscale-authkey` (la actual de mar-13 probablemente venció).
- **Activar CI** (GitHub Actions con permiso de push) para que el workflow del portal compile `dist`.
- **ramoops** (backtrace de panic): paso controlado en sitio (overlay + reinicio).

## Decisiones acordadas
- **Acceso al panel:** DHCP + **mDNS `safelock-<id>.local`** (avahi ya activo) + QR/`/myip` existentes; Tailscale para
  admin remoto. **Se retira la IP estática.**
- **Alcance:** programa completo **por fases**. Despliegue: *pausar OTA → validar en referencia → subir al remoto*.
- **Restricción:** sin acceso físico ni reimagen de unidades fielded; lo de Fase 1/2 debe llegar por el OTA/red.
- **DECISIÓN 2026-06-19 — siguiente paso = IMAGEN GOLDEN.** La flota está 27/27 offline y la recuperación está
  bloqueada (sin acceso físico, solo el dueño tiene la imagen) → el rollout/canario no tiene unidades vivas a las que
  llegar hoy. Por eso el foco pasa a **hornear una imagen estable y reproducible con todo el endurecimiento** para
  unidades nuevas/reemplazo. El dueño hará el flasheo desde otro equipo (su Mac **no** corre `rkdeveloptool`).
  **Entregable inmediato:** dos docs de handoff (`/root/safeLock_SoC/CLAUDE.md` y `AGENTS.md`) para continuar desde
  cualquier chat/equipo nuevo. La referencia ya quedó blindada y validada (reinicio hecho, `fsck.repair` activo).

---

## ⚠️ Realidad de la flota (2026-06-19) — condiciona TODO el rollout
- **Tailscale: 27/27 unidades de campo OFFLINE** (última conexión entre 15 h y 98 días). Esta unidad de referencia
  es **la única viva**. Hay dos generaciones de hostname (`safelock-1..19` y `safelock-<mac>`); la más reciente en
  caer fue hace 15 h.
- **El OTA solo llega a unidades ONLINE.** Mergear a `master` HOY **no toca a las muertas** (no hacen pull). El rollout
  solo sirve para unidades **vivas/conectadas** o que **vuelvan** (recuperadas, reflasheadas, nuevas).
- **Recuperación bloqueada:** sin acceso físico y solo el dueño tiene la imagen → hoy no hay ninguna unidad a la que
  hacerle canario. ⇒ El canario es **ejecutable cuando exista ≥1 unidad alcanzable**. El valor inmediato del trabajo
  es: (a) blindar esta referencia (hecho), (b) tener el procedimiento listo, (c) imagen golden para producción nueva.

## Rollout canario — procedimiento
**Por qué canario:** el cambio retira la IP estática → DHCP+mDNS → la IP puede cambiar; si mDNS/Tailscale fallan en una
unidad, se pierde acceso (sin reimagen remota = irrecuperable). Por eso se prueba en 1-2 antes de la flota.
**Trampa de diseño:** el OTA actual **no tiene targeting por unidad** (todas siguen `origin/master`). ⇒ el canario NO se
hace por master (sería full-fleet); se hace **directo**. El bulk sí va por master, pero **en 2 etapas**.

### Track A — Canario directo (master intacto) [preferido]
Sobre 1-2 unidades alcanzables (Tailscale SSH / LAN), sin tocar `master`:
1. `cd /root/safeLock_SoC && git fetch origin && git checkout audit/phase1-hardening`
2. `bash scripts/apply-hardening.sh`  →  reinicio controlado  →  **validar** (checklist de §Verificación).
3. **Observar 24-48 h** con energía real: sin reinicios inesperados, telemetría fluyendo, panel accesible por
   `safelock-<id>.local:5173` **y** por Tailscale (confirmar que la IP cambió pero sigue alcanzable).
4. Si OK → bulk.

### Track B — Bulk por OTA en 2 ETAPAS (solo tras canario OK)
El OTA viejo que la flota ejecuta en el **primer pull** hace `npm run build` en el equipo si cambia `portal/`
(`apply-update.sh` en master, línea ~113) → **pico de RAM = riesgo de brownout durante la propia actualización**.
- **Etapa 1 (solo maquinaria):** merge a master de **todo MENOS `portal/`** (scripts/, deploy/, systemd/, api, docs).
  El script viejo no ve cambio en `portal/` → **no compila**. Tras ese pull queda activo el `apply-update.sh` NUEVO,
  que en el ciclo siguiente corre `apply-hardening.sh` (watchdog, avahi, apt-off, `fsck.repair`, holds, commit=15…).
- **Etapa 2 (portal):** merge de `portal/dist` + resto. Ya lo maneja el script NUEVO → **sin build en el equipo**.
- Cada unidad online aplica en ~2 ciclos (10-30 min). `fsck.repair` queda **armado para el próximo arranque**; hacer
  **reinicios controlados por olas** para activarlo en vivo y validar.

### Riesgos del rollout y mitigaciones
- **Cambio de IP (DHCP) — riesgo #1:** acceso por mDNS/Tailscale, verificado en el canario antes del bulk.
- **Brownout por `npm build`:** mitigado por las 2 etapas.
- **Oscilación de commit malo:** el script viejo (etapa 1) no marca `bad_commit`; mantener la etapa 1 mínima y de bajo
  riesgo (health-check = `curl /status`). El script nuevo ya trae anti-oscilación.
- **Brick durante hardening:** `apply-hardening` respalda `armbianEnv` (`.safelock.bak`) y escribe `/boot` atómico; aun
  así, sin reimagen remota, el **canario es la única red de seguridad**.

---

## FASE 1 — Detener el sangrado + acceso (sin reimagen; desplegable a unidades vivas)

### 1a. Anti-brick (resiliencia de almacenamiento/energía)
- **`fsck.repair=yes`** en cmdline (`/boot/armbianEnv.txt` → `extraargs`): la raíz se **auto-repara** al arrancar →
  rompe el "no levanta" por FS corrupta. (Junto al `panic=10` ya presente.)
- **Bajar `commit=120` → `commit=15`** (o defecto) en `/etc/fstab` y confirmar *barriers* activos → menos datos en
  riesgo por corte.
- **Reducir churn de escrituras a eMMC:**
  - `scripts/update_network.sh`: reiniciar netalertx **solo si la subred cambió** (hoy lo hace siempre) + subir el
    intervalo del timer.
  - `scripts/apply-update.sh`: cuando `LOCAL==REMOTE` (sin cambios) **no** copiar units / `daemon-reload` / reiniciar
    timers (hoy lo hace cada 10 min aunque no haya cambios).
  - `api/pack_scheduler.py`/`packs.py`: no escribir `gravity.db` si no hay cambio; bajar cadencia (1 min → 5 min).
- **`apt-mark hold`** de kernel/u-boot/bsp + desactivar upgrades desatendidos del kernel → elimina el brick-por-flasheo.

### 1b. Acceso al panel (mDNS) y retiro del IP-lock
- **Neutralizar `safelock-ip-lock`:** `stop`+`disable` del servicio, borrar `/etc/network/interfaces.d/end0(.bak)` y
  retirar `/usr/local/bin/smart_ip_lock.sh`. Dejar DHCP (systemd-networkd) como único gestor.
- **mDNS por equipo:** confirmar que `safelock-<id>.local` resuelve; **publicar un servicio avahi** `_http._tcp`
  anunciando el panel (5173) y la API (8090) para descubrimiento. Hostname estable ya = `safelock-<mac>`.
- **Frontend agnóstico de host:** el portal debe derivar la URL de la API de `window.location.hostname` (con CORS `*`
  ya abierto, el panel funciona igual por IP, `.local` o Tailscale). Verificar/parchear en el código del portal.
- **Documentar** la dirección del panel para el cliente: `http://safelock-<id>.local:5173` + el QR (`/qr`) ya existente.

### 1c. Higiene de despliegue (quick wins)
- Sacar de las unidades de campo los scripts peligrosos `cleanup_master.sh` / `install/pre-image-cleanup.sh`
  (solo deben vivir en el pipeline de imagen), o blindarlos con guard "solo build".
- Corregir rutas obsoletas `/root/safeLock_SoC/heartbeat.sh` → `scripts/heartbeat.sh` (cron y cualquier script).
- Reconciliar copias divergentes en `/usr/local/bin` (`connectivity-watchdog.sh`, `tailscale-autoconnect.sh`): única
  fuente desde el repo.

---

## FASE 2 — Rediseño del OTA + identidad + deuda técnica

### 2a. OTA seguro (el mayor riesgo de flota)
- Reemplazar `git reset --hard origin/master` cada 10 min por: despliegue desde **tags/releases firmados** (no la
  punta de la rama), aplicar **solo en release nueva**, cadencia mayor (p.ej. horaria), **apply atómico**
  (escribir+rename+`sync`), y **rollback que marca la release como mala** para no re-aplicarla (corrige la oscilación).
- **Build del portal en CI** y enviar `dist/` ya compilado → quitar `npm run build` del dispositivo (elimina el pico
  de RAM en 4 GB y la dependencia de node/npm en producción).
- **Todo el código que corre en el equipo debe estar en el repo** (sin fantasmas en `/usr/local/bin`): traer al repo
  el reemplazo de ip-lock, `connectivity-watchdog`, `tailscale-autoconnect`, `flight-recorder`, con un **instalador
  determinista** que los coloca.

### 2b. Identidad / ciclo de vida de Tailscale
- Auth por **OAuth client + tags** o **authkeys no expirables/rotadas** para que un equipo siempre pueda (re)registrarse;
  **deshabilitar expiración de clave** para `tag:safelock` en la consola.
- **Nunca** borrar `/var/lib/tailscale` en equipos de campo (solo en el pipeline de imagen). Documentar recuperación remota.

### 2c. Secretos / observabilidad / deuda
- Rotar `openlock2026` → secreto **por dispositivo** provisionado en fábrica; validar tokens por equipo en el backend;
  **limpiar el historial de git**. Endurecer CORS si es viable.
- Forensia: decidir journald persistente en eMMC vs flight recorder (balance escrituras/forensia); desplegar
  **ramoops** (captura de backtrace de panic) de forma controlada (requiere reinicio/overlay).

---

## FASE 3 — Imagen estable + recuperación + producción nueva

- Migrar de Armbian **nightly/trunk** a **release estable** con kernel **fijado** para la imagen de producción
  (aplica a unidades **nuevas**; las fielded no se pueden reimagen en remoto).
- **Imagen golden reproducible** vía pipeline (los scripts de cleanup/pre-image viven aquí, en CI, no en los equipos).
- **Recuperación:** guía de re-flasheo **maskrom** (rkdeveloptool) + distribuir la imagen a quien tenga acceso físico,
  o enviar unidades pre-flasheadas. Evaluar **boot A/B / SD de recuperación** para que las unidades futuras se
  auto-recuperen sin maskrom.
- **Energía:** especificar/enviar una **fuente de calidad (5 V ≥3 A)**; confirmar brownout con la telemetría ya
  desplegada; valorar capacitor de entrada/UPS mínimo para apagado limpio.
- **Resiliencia eMMC:** evaluar **raíz read-only / overlay** (SO inmutable, solo datos escribibles) → reduce
  drásticamente la corrupción por corte.

---

## Recuperación de las unidades ya muertas (operativo, urgente)
Bloqueada hoy: solo el dueño tiene la imagen y no hay acceso físico. Acciones: (1) usar las **preguntas para el equipo
en sitio** (abajo) para clasificar cada unidad; (2) hacer llegar **imagen + guía maskrom** a alguien en sitio, o enviar
reemplazos pre-flasheados; (3) si una unidad "enciende pero sin red", probablemente es el IP-lock/identidad
(recuperable reflasheando o, a futuro, evitado por Fase 1b); si "no arranca", es eMMC corrupta (reflasheo).

**Preguntas para el equipo en sitio:** señales de vida al energizar (LED/color, ventilador, HDMI muestra algo, luz del
puerto ethernet); ¿aparece en el router/DHCP con IP?, ¿responde a ping?, ¿online en Tailscale?; **probar otra fuente
buena (5 V ≥3 A)**; ¿se movió de red/cambió subred?, ¿hubo apagón?, ¿estaba actualizándose?; ¿hay PC+USB para maskrom?

## Verificación
- **Fase 1 (en referencia, antes de subir):** crash-test controlado (`echo c >/proc/sysrq-trigger`) → confirmar
  auto-reboot (`panic=10`) y que tras un corte simulado la raíz monta limpia (fsck) y la telemetría llega al instante
  del corte. Mover el equipo a **otra subred** y confirmar que el panel sigue accesible por `safelock-<id>.local:5173`
  (mDNS) y que ya **no** se congela IP. Verificar OTA "sin cambios" no escribe.
- **Fase 2:** simular un push de release mala → confirmar que el equipo **no oscila** (marca la release y no reaplica),
  rollback OK; confirmar que un equipo con estado de Tailscale borrado se re-registra solo.
- **Fase 3:** flashear una unidad nueva con la imagen estable y validar arranque + recuperación A/B; prueba de
  resistencia a cortes de energía repetidos con la fuente nueva.

## Archivos / puntos críticos
- Arranque/FS: `/boot/armbianEnv.txt` (`extraargs`), `/etc/fstab` (`commit`), apt holds.
- IP-lock (fantasma): `/etc/systemd/system/safelock-ip-lock.service`, `/usr/local/bin/smart_ip_lock.sh`,
  `/etc/network/interfaces.d/end0`.
- OTA: `scripts/apply-update.sh`, `update.sh`, `scripts/rollback.sh`, `systemd/safelock-update.timer`.
- Red/acceso: `scripts/update_network.sh`, avahi (`/etc/avahi/`), portal (`portal/` — base URL de la API).
- Identidad: `scripts/tailscale-common.sh`, `/etc/tailscale-authkey`, factory (`install/factory_setup.sh`).
- Secreto: `scripts/heartbeat.sh` + `/etc/safelock/telemetry.env`.

## Riesgos / restricciones operativas
- **OTA pausado:** reanudar con `systemctl enable --now safelock-update.timer` + descomentar cron (solo tras Fase 2,
  con el OTA ya rediseñado). Cualquier cambio local se revierte si el OTA viejo corre.
- **Sin reimagen remota:** Fases 1–2 deben aplicarse por OTA/red; configs de sistema (cmdline, fstab, watchdog) **no**
  las transporta el OTA actual → requieren un mecanismo de aplicación (parte de Fase 2) o factory para nuevas.
- **Secuencia de despliegue:** provisionar `/etc/safelock/telemetry.env` en cada unidad **antes** de subir el
  `heartbeat.sh` modificado; no subir scripts sueltos.
- **Sin acceso físico:** la recuperación de unidades muertas es operativa (no la resuelve el código); Fase 3 evita que
  vuelva a ocurrir.
