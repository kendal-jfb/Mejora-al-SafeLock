# Handoff — diagnosticar la migracion a OTA v2 en un equipo

Estado al 2026-07-25 05:00 UTC. Este documento es para una sesion que trabaje
**dentro de un SafeLock** (o contra el por `tailscale ssh` desde el servidor).

## Lo que YA esta hecho — no rehacer nada de esto

| Pieza | Estado | Verificado |
|---|---|---|
| Backend `safelock-telemetry` | Desplegado en Contabo, commit `3b9f9f3` | `/status` responde, ruta de artefactos da 401 sin auth |
| Tablas OTA en Supabase | RLS off + grants a `anon` | `/api/ota/status` devuelve los dos canales |
| Release `v2.0.1` | Publicado, firmado y subido al servidor | Firma `Verified OK`, sha256 coincide |
| Canal `stable` | Apunta a `v2.0.1` | — |
| `master` en `safelock-device` | B1 (`368c8fc`) + B2 (`bbba6f0`) | El equipo ya los tiene |

El artefacto se descarga del **backend**, no de GitHub: el repositorio es
privado y los equipos no tienen credenciales para GitHub Releases.

```
https://telemetry.openlocksecurity.com/api/ota/artifact/v2.0.1/<fichero>
```

Se piden con `x-device-id` + `x-device-secret`, o con `x-api-secret:
openlock2026` mientras siga activo el secreto compartido.

## El problema concreto

El equipo `safelock-263ae59285e9` (tailscale `100.65.215.45`) reporta:

```
version:          1.3.1
migration_state:  attempts:1
```

`attempts:1` significa que `scripts/migrate-to-ota.sh` se ejecuto, fallo y
llamo a su funcion `fallo()`, que aborta dejando el equipo **exactamente como
estaba** y reintenta en el siguiente ciclo del updater viejo (~10 min).

Nada esta roto. El equipo sigue dando servicio en 1.3.1. Lo unico que falta es
saber en que paso aborta.

## Paso 1 — leer el motivo

El motivo esta escrito literalmente en el log, en la linea que empieza por
`ABORTA:`.

```bash
tail -60 /var/lib/safelock/ota/migrate.log
```

Si se trabaja desde el servidor:

```bash
tailscale ssh root@100.65.215.45 "tail -60 /var/lib/safelock/ota/migrate.log"
```

Contexto adicional util:

```bash
tail -40 /var/log/safelock-update.log          # el updater que invoca el hook
ls -la /var/lib/safelock/ota/ /etc/safelock/   # que llego a crearse
ls -la /opt/safelock/ 2>&1                     # estructura nueva, si existe
systemctl list-timers 'safelock*' --all --no-pager
```

## Paso 2 — actuar segun el `ABORTA:`

Los mensajes salen de `scripts/migrate-to-ota.sh`. Por orden de aparicion en el
script:

### `no se pudo determinar la MAC de end0`
La interfaz no se llama `end0` en este equipo. Comprobar con `ip -br link`. Es
un cambio en el script, no en el equipo.

### `la clave publica de firma no es valida`
`openssl` no puede leer `/etc/safelock/ota.pub.pem`. Casi siempre son finales
de linea CRLF por una checkout mal configurada. Verificar:
```bash
file /etc/safelock/ota.pub.pem
openssl rsa -pubin -in /etc/safelock/ota.pub.pem -noout
```

### `el backend no respondio con la version objetivo (HTTP xxx)`
Reproducir a mano — esto dice si es red, DNS, TLS o autenticacion:
```bash
curl -v -m 30 https://telemetry.openlocksecurity.com/api/ota/target \
  -H "x-device-id: $(cat /etc/safelock-id)" \
  -H "x-device-secret: $(cat /etc/safelock/device-secret)" \
  -H "x-api-secret: openlock2026"
```
- `401` → el secreto no vale; ver la nota sobre `ENROLLMENT_SECRET` mas abajo.
- `000` / timeout → red o DNS del equipo.
- `200` con `"tag": null` → el canal `stable` perdio el target; se arregla en el
  dashboard, no aqui.

### `no hay ninguna version publicada todavia`
El backend devolvio `tag: null`. Promover `v2.0.1` a `stable` otra vez.

### `no se pudo descargar el manifest / el artefacto`
La descarga autenticada contra el backend falla. Probar:
```bash
curl -sS -o /tmp/m.json -w '%{http_code}\n' \
  -H "x-api-secret: openlock2026" \
  https://telemetry.openlocksecurity.com/api/ota/artifact/v2.0.1/manifest.json
```
Un `413` seria nginx (`client_max_body_size`), un `404` que el fichero no esta
en `/var/lib/safelock/releases/v2.0.1/` del servidor.

### `FIRMA INVALIDA en el manifest`
**No forzar la instalacion bajo ningun concepto.** O el artefacto se corrompio
en transito, o la clave publica del equipo no corresponde a la privada que
firmo. Comparar el sha256 del manifest local con el del servidor antes que nada.

### `sha256 no coincide`
Descarga corrupta o truncada. Reintentar; si se repite, revisar nginx.

### Fallos posteriores (instalacion, systemd, health check)
Si el log llega a `health-check` y aborta ahi, el sistema nuevo se instalo pero
no arranco. Mirar:
```bash
systemctl status safelock-api safelock-portal --no-pager
journalctl -u safelock-api -n 50 --no-pager
python3 /opt/safelock/current/scripts/health-check.py --wait 5
```
El script ya restauro las unidades viejas por su cuenta; el equipo esta servido
por el sistema anterior.

## Paso 3 — reintentar

No hace falta hacer nada especial: el updater viejo reintenta cada ~10 min. Para
forzarlo:

```bash
bash /root/safeLock_SoC/scripts/migrate-to-ota.sh
tail -30 /var/lib/safelock/ota/migrate.log
```

Es idempotente y siempre termina en `exit 0`.

## Verificar que salio bien

```bash
test -f /var/lib/safelock/ota/migrated && echo MIGRADO
readlink /opt/safelock/current          # debe apuntar a releases/v2.0.1
cat /opt/safelock/current/VERSION       # v2.0.1
systemctl is-active safelock-api safelock-portal safelock-ota.timer
```

En el dashboard, el equipo debe pasar a `version: v2.0.1` y
`migration_state: done`.

## Reglas que no se rompen

1. **Nunca borrar `/root/safeLock_SoC`.** Es el bind mount de los contenedores
   docker (Pi-hole, etc.) ademas del repo viejo. Se retira semanas despues, con
   la flota migrada.
2. **No quitar `set -u` ni añadir `set -e`** a `migrate-to-ota.sh`. Termina
   siempre en `exit 0` a proposito: el updater viejo tiene `set -e` y un codigo
   de salida distinto de cero dispara su rollback, que esta roto.
3. **No instalar un release cuya firma no verifique.** Es la unica barrera real
   entre el backend y ejecucion como root en casa de un cliente.
4. **No tocar `LEGACY_SECRET_ENABLED` ni `ENROLLMENT_OPEN`** en el servidor.
   Hay 22 equipos en stock sin vender que llegaran por el canal viejo cuando se
   activen.

## Pendiente conocido — enrolamiento

`migrate-to-ota.sh` se enrola enviando `openlock2026`. El backend solo lo acepta
si coincide con `ENROLLMENT_SECRET` de su `.env`. Si ahi hay otro valor, el
enrolamiento devuelve 401, **el script lo ignora** (solo lo escribe en el log) y
el equipo se queda sin secreto propio, dependiendo del compartido para siempre.

Comprobar en el servidor:
```bash
grep ENROLLMENT_SECRET /var/www/safelock-telemetry/.env
```

Si no es `openlock2026`, hay que alinear los dos. No bloquea la migracion.
