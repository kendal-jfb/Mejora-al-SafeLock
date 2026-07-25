# SafeLock OTA v2 — Runbook

Sistema de actualizaciones por releases firmados, con toda la flota convergiendo
a una única versión publicada.

## Qué cambia respecto al sistema anterior

| | Antes | Ahora |
|---|---|---|
| Qué se instala | lo que hubiera en `master` en ese momento | un tag concreto, firmado |
| Integridad | ninguna | firma RSA-4096 + sha256 del artefacto |
| Portal | `npm run build` en el SoC | ya compilado en CI |
| Instalación | `git reset --hard` sobre el árbol vivo | directorio nuevo + symlink atómico |
| Rollback | 1 commit, sin reconstruir el portal | release anterior completo, en disco, sin red |
| Health check | solo la API | API + portal + unidades systemd |
| Si el actualizador se rompe | no hay salida | agente last-known-good + rescate independiente |
| Versión reportada | string hardcodeado (y en desacuerdo consigo mismo) | tag y commit reales |

## Flujo de publicación

```
git tag v2.1.0 && git push origin v2.1.0
  └─ GitHub Actions: compila el portal, empaqueta, firma, publica el Release
     y registra el tag en el backend  →  canal canary
  └─ los equipos en canary actualizan en ~10 min y reportan su salud
  └─ botón "Promover canary a toda la flota" en el dashboard
  └─ el resto de la flota converge en ~30 min
```

Un release que falla **nunca se reintenta solo**: el equipo lo anota en
`failed_versions`, vuelve a la versión anterior y sigue funcionando. La
corrección siempre es publicar un tag nuevo.

## Estructura en el dispositivo

```
/opt/safelock/
  releases/v2.1.0/          cada release completo (api, portal_dist, scripts, ota, systemd)
  current -> releases/v2.1.0
  agent/run-agent.sh        lanzador, fuera del árbol de releases
  agent/lkg/ota_agent.py    último agente que demostró funcionar
  rescue/rescue.sh          el canal OTA normal NUNCA lo actualiza
  backup-units/             unidades systemd previas a la migración
/etc/safelock/
  ota.pub.pem   clave pública de firma
  device-secret secreto propio del equipo (0600)
  ota.conf      backend y origen de artefactos
  env           credenciales SMTP (0600)
  config.json   configuración del cliente (sobrevive a las actualizaciones)
/etc/safelock-id            identificador canónico
/var/lib/safelock/ota/      state.json, ota.log, migrate.log, rescue.log
```

`/root/safeLock_SoC` **no se borra**: sigue siendo el directorio de datos
(bind mounts de docker para pihole, netalertx y opencanary). Tras la migración
solo deja de usarse como código.

---

# Puesta en marcha

## Fase 0 — Antes de tocar nada

**a) Rotar las credenciales expuestas.** Están en un repositorio público con
historial, así que hay que darlas por comprometidas:

- Cambiar la contraseña de `safelock_user_data@openlocksecurity.com`.
- Revocar el app-password de Gmail de `ethancrdr@gmail.com` si sigue activo.

Las alertas por correo quedan desactivadas hasta que B2 instale
`/etc/safelock/env`. Es una ventana asumida y corta.

**b) Claves de firma.** Ya generadas en `Documents/safelock-ota-keys/`
(`ota-private.pem`, `ota-public.pem`). La privada **no va a ningún repositorio**:
guardar una copia offline. La pública ya está embebida en
`scripts/migrate-to-ota.sh`.

**c) Secrets en GitHub** (repo `safelock-device` → Settings → Secrets → Actions):

| Secret | Valor |
|---|---|
| `OTA_SIGNING_KEY` | contenido completo de `ota-private.pem` |
| `OTA_ADMIN_TOKEN` | el token generado (el mismo que en Render) |
| `BACKEND_URL` | `https://telemetry.openlocksecurity.com` |

**d) Variables de entorno del backend.** Se añaden a
`/var/www/safelock-telemetry/.env` en el servidor (no está en git; lo lee
`load_dotenv()`):

| Variable | Valor |
|---|---|
| `OTA_ADMIN_TOKEN` | el token generado |
| `ENROLLMENT_SECRET` | el secreto de enrolamiento generado |
| `ENROLLMENT_OPEN` | `true` (se cierra en la fase 5) |
| `LEGACY_SECRET_ENABLED` | `true` (se cierra en la fase 5) |
| `DASHBOARD_PASSWORD` | la contraseña nueva del dashboard |
| `SMTP_SERVER` / `SMTP_PORT` / `SMTP_SENDER` / `SMTP_PASSWORD` | credenciales **nuevas** tras la rotación |

`API_SECRET`, `SUPABASE_URL` y `SUPABASE_KEY` ya están; no se tocan.

**e) Esquema de Supabase.** Ejecutar `schema_ota.sql` (repo `safelock-telemetry`)
en el editor SQL. Es aditivo e idempotente.

**f) Elegir los equipos canary.** Al final de `schema_ota.sql` hay un `UPDATE`
comentado: poner ahí uno o dos `device_id` internos. Sin canary, cada release
salta directo a toda la flota.

## Fase 1 — Desplegar el backend

El backend vive en un servidor propio (`telemetry.openlocksecurity.com`, nginx
con TLS delante de uvicorn en `127.0.0.1:8000`, gestionado por PM2). **No hay
despliegue automático**: cada cambio se aplica a mano.

```bash
ssh root@13.140.185.37
cd /var/www/safelock-telemetry
git pull origin main
venv/bin/pip install -r requirements.txt
pm2 restart safelock-telemetry && pm2 save
```

Comprobar:

```bash
curl https://telemetry.openlocksecurity.com/status     # version 2.0.0
curl -u admin:CONTRASEÑA https://telemetry.openlocksecurity.com/api/ota/status
```

`GET /` redirige al dashboard; la versión se consulta en `/status`.

Los heartbeats antiguos deben seguir entrando: `LEGACY_SECRET_ENABLED=true`
mantiene vivo el canal viejo durante toda la migración.

> El proceso corre bajo PM2 dentro del cgroup de una sesión SSH cerrada, con
> `pm2-root.service` en `inactive`. Conviene reencuadrarlo bajo ese servicio
> **antes de la fase 4**, en una ventana tranquila: durante la migración de la
> flota el backend no puede caerse.

## Fase 2 — Primer release

```bash
cd safelock-device
git tag v2.0.0 && git push origin v2.0.0
```

Verificar en GitHub que el Release tiene los tres ficheros
(`safelock-v2.0.0.tar.gz`, `manifest.json`, `manifest.json.sig`) y que el tag
aparece en `/api/ota/status` como canary.

**Este release es el que instalará la migración**, así que promoverlo a stable
antes de empezar la fase 4 (los equipos sin migrar están en el canal `stable`
por defecto).

## Fase 3 — Ensayo en staging (obligatorio)

Con un SoC de pruebas flasheado con la imagen golden y su `origin` apuntando a
un fork. Recorrer la lista de verificación del final de este documento antes de
tocar producción.

## Fase 4 — Migración de la flota

**Push B1** — solo `api/main.py` y `api/report.py` (credenciales fuera del
código). No toca `portal/` ni `systemd/`, así que el pipeline viejo no ejecuta
`npm build` y su health check pasa.

```bash
git add api/ && git commit -m "API: credenciales SMTP fuera del repositorio" && git push
```

Esperar 30 minutos y confirmar en el dashboard que **siguen llegando heartbeats
de toda la flota**. Si algún equipo se cae aquí, parar y arreglar antes de B2.

**Push B2** — el commit puente: el resto de archivos.

```bash
git add . && git commit -m "OTA v2: agente, rescate y migracion" && git push
```

Qué pasa en cada equipo:

1. Tick actual: el `apply-update.sh` viejo (ya cargado en memoria) trae B2.
2. Tick siguiente (~10 min): el `apply-update.sh` nuevo ejecuta
   `migrate-to-ota.sh` antes que nada.
3. La migración instala todo en rutas nuevas, cambia los servicios y pasa el
   health check. Solo entonces deshabilita los timers viejos.
4. Si falla en cualquier punto: restaura las unidades anteriores, cuenta el
   intento y sale con 0. El equipo sigue funcionando y reintenta en 10 minutos.

Seguimiento: la columna **Versión** del dashboard marca `sin migrar` mientras
llegue el heartbeat antiguo, y muestra el tag real en cuanto migra. Objetivo:
100 % en 24-48 h.

**Rezagados:**

```bash
tailscale ssh root@safelock-XXXX
cat /var/lib/safelock/ota/migrate.log      # dice exactamente dónde abortó
bash /root/safeLock_SoC/scripts/migrate-to-ota.sh
```

## Fase 5 — Cierre (solo con el 100 % migrado)

1. En Render: `ENROLLMENT_OPEN=false` y `LEGACY_SECRET_ENABLED=false`.
   Esto mata definitivamente `openlock2026`.
2. Borrar la rama `master` del repositorio `safelock-telemetry` en GitHub: es
   basura del repo git accidental (tiene los archivos anidados bajo
   `Documents/safelock-telemetry-main/`). La rama buena es `main`.
3. Ya se puede hacer privado `safelock-device` o purgar su historial.

> ⚠️ **Nunca antes.** Mientras quede un equipo en el updater viejo, hacer
> privado el repositorio o reescribir `master` lo deja huérfano para siempre:
> no podrá recibir la migración.

---

# Operación diaria

**Publicar una versión**

```bash
git tag v2.1.0 && git push origin v2.1.0
# esperar a que canary reporte OK, luego botón "Promover" en el dashboard
```

**Parar un rollout en marcha** — botón "Pausar rollout". No revierte nada: los
equipos se quedan donde están.

**Deshacer un release malo** — publicar un tag nuevo con la corrección. Los
equipos que ya revirtieron solos no volverán a intentar el tag malo.

**Ver el estado de un equipo**

```bash
tailscale ssh root@safelock-XXXX
python3 /opt/safelock/current/ota/ota_agent.py --status
tail -50 /var/lib/safelock/ota/ota.log
python3 /opt/safelock/current/scripts/health-check.py     # legible
```

**Forzar una comprobación ahora**

```bash
systemctl start safelock-ota.service
```

---

# Lista de verificación en staging

Cada punto debe observarse en el dashboard o en los logs del equipo.

1. **Camino feliz** — publicar un tag, promoverlo, el equipo actualiza solo y
   reporta la versión correcta.
2. **Migración** — desde la imagen golden con el pipeline viejo activo: migra
   sin intervención y los timers viejos quedan deshabilitados.
3. **Rollback por API rota** — publicar un release con un `raise` al arrancar la
   API: el equipo revierte, marca `failed_versions` y **no** lo reintenta.
4. **Rollback por portal roto** — release con `portal_dist` vacío: el health
   check del portal falla y revierte. (El bug del sistema viejo, que revertía el
   código pero dejaba el build roto, ya no existe: cada release lleva su dist.)
5. **Agente corrompido** — romper `current/ota/ota_agent.py` a mano: el
   siguiente tick usa la copia LKG.
6. **Rescate** — `systemctl disable --now safelock-ota.timer` y borrar el
   symlink `current`; luego `systemctl start safelock-rescue.service`: lo
   restaura.
7. **Corte de energía** — desenchufar durante la descarga y durante la
   extracción: `current` queda intacto y el siguiente tick reintenta limpio.
8. **Backend caído** — el equipo queda `idle` y plenamente funcional; al volver
   el backend, converge.
9. **Artefacto manipulado** — cambiar un byte del `.tar.gz` del Release: la
   verificación falla y no se instala nada.
10. **Migración sin red** — bloquear la salida durante B2: `migrate_attempts`
    crece, el equipo sigue sano y migra solo al recuperar la conexión.
