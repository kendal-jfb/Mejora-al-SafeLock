#!/bin/bash
# Migracion del updater antiguo (git pull) al sistema OTA v2.
#
# Este script llega a la flota por el propio canal viejo y es la unica parte
# del plan que no se puede ensayar dos veces en el mismo equipo. De ahi sus
# tres reglas:
#
#   1. SIN `set -e`. El updater que lo invoca si lo tiene, y un fallo a medias
#      suyo aborta antes de su propio rollback. Aqui cada paso se comprueba a
#      mano y el script SIEMPRE termina en `exit 0`.
#   2. Todo lo nuevo vive en rutas nuevas (/opt/safelock, /etc/safelock). El
#      sistema viejo no se apaga hasta que el nuevo pasa el health check.
#   3. Idempotente: si algo falla, el equipo se queda como estaba y el timer
#      viejo vuelve a intentarlo dentro de 10 minutos.

set -u

OTA_ROOT="/opt/safelock"
ETC_DIR="/etc/safelock"
STATE_DIR="/var/lib/safelock/ota"
LOG="$STATE_DIR/migrate.log"
MARKER="$STATE_DIR/migrated"
ATTEMPTS_FILE="$STATE_DIR/migrate_attempts"
REPO_DIR="/root/safeLock_SoC"

BACKEND_URL="https://telemetry.openlocksecurity.com"

# El repositorio es privado, asi que los releases no se descargan de GitHub
# sino del backend, que los guarda cuando el CI publica el tag. Lo que valida
# el release sigue siendo la firma RSA contra ota.pub.pem, no de donde venga.
ARTIFACT_BASE="$BACKEND_URL/api/ota/artifact"

# Secreto compartido antiguo; solo sirve para el enrolamiento inicial y se
# desactiva en el backend cuando toda la flota haya migrado.
BOOTSTRAP_SECRET="openlock2026"

# Si se deja vacio, la version a instalar la decide el backend (canal del
# equipo). Se puede fijar aqui para clavar una version concreta.
BOOTSTRAP_TAG=""

mkdir -p "$STATE_DIR" "$ETC_DIR"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"
}

fallo() {
  log "ABORTA: $*"
  log "el equipo sigue en el sistema anterior; se reintentara en el proximo ciclo"
  echo "$(( $(cat "$ATTEMPTS_FILE" 2>/dev/null || echo 0) + 1 ))" > "$ATTEMPTS_FILE"
  [ -n "${WORK:-}" ] && rm -rf "$WORK"
  exit 0
}

if [ -f "$MARKER" ]; then
  exit 0
fi

log "=== inicio de migracion a OTA v2 ==="

# --- 1. Identidad del equipo -----------------------------------------------
# La identidad la manda la MAC de end0, NO lo que venga en /etc/safelock-id. Una
# imagen golden puede arrastrar el id del MASTER en ese archivo (golden-firstboot
# solo lo reescribe en el primer arranque de un clon nuevo); sin corregirlo aqui,
# todos los clones se enrolarian con el mismo id -> 409 y fallo de auth en las
# llamadas target/artifact -> el equipo se queda en v1. Mismo criterio que
# ota_agent.py::canonical_device_id: si la MAC no coincide con el archivo, gana la MAC.
MAC="$(cat /sys/class/net/end0/address 2>/dev/null | tr -d ':')"
if [ -n "$MAC" ]; then
  CANON="safelock-$MAC"
  if [ "$(cat /etc/safelock-id 2>/dev/null)" != "$CANON" ]; then
    echo "$CANON" > /etc/safelock-id
    log "device-id fijado desde la MAC: $CANON (corrige un id arrastrado de la imagen)"
  fi
elif [ ! -s /etc/safelock-id ]; then
  fallo "no se pudo determinar la MAC de end0 ni hay /etc/safelock-id previo"
fi
DEVICE_ID="$(cat /etc/safelock-id)"
log "device-id: $DEVICE_ID"

# --- 2. Clave publica de firma ---------------------------------------------
cat > "$ETC_DIR/ota.pub.pem" <<'PUBKEY'
-----BEGIN PUBLIC KEY-----
MIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEAvlooVfx6pnEHwp09SEfc
LBuL81b2+EEbyfyb81f8zMVVEU9E69dZfEh+zrf1uypjDHGsfv/I+2wjSwz0scd6
AA0lUvL6Otxn8NkDXqc5aeWeQMBOwr5KWaPj+p9POR4tJjsms9xuJdQwMEWM1vg4
+5vtfAkHi8GRRb6zRoGGJ4SgSVcodp1UlXcqXyz3eo+5GsmX3Jm/czWL0RxQi262
/7mEtRixNTLC2TGhJdcWYFPx6JvRbAClo7Ovfl3PB6EJGvWtuAIbxcRGhTtdo1oQ
mRHMWx6V1wPihRVf3hYTT0Ntn+zHm/RodYiH7fQaqu4TiKf2kKDCf9gNGq8XBroQ
k4bBTbHeh3s3bdgonsV+x4fI0U0C99a4P+FPAD7P6h57MXd500Nuj4ZyOrqgXHTR
txw6+0hzwNT4FRLBND28Gam20vaDJvwxxCzrom41La1x+7+QSt22/zgNh1FGspyT
omMV5m6RvrKRis+8OdBOx0WWOgMWHZUhv0vOQecS9KiwyK+PXhLRh2jSpTtl+wgo
1rwpbSetnkdP4Ir/N1guFJ0GoZEIP2xx/g/jioPkhrIyuwNBlHupt1eSa3HNktHb
0CQPqhumh3nmYrcNXJsE7QnUAqSlcPDoP+lo3M8oYBU1zaZLPS68kXFGMeyeCNw+
gjBsNGZ3Y41i4yeeWioJ3oUCAwEAAQ==
-----END PUBLIC KEY-----
PUBKEY
chmod 644 "$ETC_DIR/ota.pub.pem"

if ! openssl rsa -pubin -in "$ETC_DIR/ota.pub.pem" -noout >/dev/null 2>&1; then
  fallo "la clave publica de firma no es valida"
fi

# --- 3. Secreto propio del equipo ------------------------------------------
if [ ! -s "$ETC_DIR/device-secret" ]; then
  openssl rand -hex 32 > "$ETC_DIR/device-secret" 2>/dev/null
  chmod 600 "$ETC_DIR/device-secret"
  log "secreto de dispositivo generado"
fi
DEVICE_SECRET="$(cat "$ETC_DIR/device-secret")"
if [ -z "$DEVICE_SECRET" ]; then
  fallo "no se pudo generar el secreto del dispositivo"
fi

# Enrolar. Un 409 significa "ya estaba enrolado": no es un error.
ENROLL_CODE="$(curl -sS -m 30 -o /tmp/enroll.out -w '%{http_code}' \
  -X POST "$BACKEND_URL/api/enroll" \
  -H "Content-Type: application/json" \
  -H "x-api-secret: $BOOTSTRAP_SECRET" \
  -d "{\"device_id\":\"$DEVICE_ID\",\"secret\":\"$DEVICE_SECRET\"}" 2>/dev/null || echo 000)"
log "enrolamiento: HTTP $ENROLL_CODE"

# --- 4. Configuracion local -------------------------------------------------
cat > "$ETC_DIR/ota.conf" <<CONF
BACKEND_URL=$BACKEND_URL
ARTIFACT_BASE=$ARTIFACT_BASE
LEGACY_SECRET=$BOOTSTRAP_SECRET
CONF
chmod 600 "$ETC_DIR/ota.conf"

# Credenciales SMTP: ya no viven en el repositorio.
CFG_CODE="$(curl -sS -m 30 -o /tmp/devcfg.json -w '%{http_code}' \
  "$BACKEND_URL/api/device-config" \
  -H "x-device-id: $DEVICE_ID" \
  -H "x-device-secret: $DEVICE_SECRET" \
  -H "x-api-secret: $BOOTSTRAP_SECRET" 2>/dev/null || echo 000)"

if [ "$CFG_CODE" = "200" ]; then
  python3 - <<'PY' >> "$LOG" 2>&1
import json
try:
    with open("/tmp/devcfg.json") as f:
        cfg = json.load(f)
    smtp = cfg.get("smtp") or {}
    lineas = [f"{k}={v}" for k, v in smtp.items() if v]
    if lineas:
        with open("/etc/safelock/env", "w") as f:
            f.write("\n".join(lineas) + "\n")
        print("credenciales SMTP escritas en /etc/safelock/env")
    else:
        print("el backend no devolvio credenciales SMTP")
except Exception as exc:
    print(f"no se pudo escribir /etc/safelock/env: {exc}")
PY
  chmod 600 "$ETC_DIR/env" 2>/dev/null
else
  log "no se pudo bajar la configuracion del backend (HTTP $CFG_CODE); el correo quedara desactivado"
fi

# La configuracion del cliente debe sobrevivir a las actualizaciones.
if [ -f "$REPO_DIR/api/config.json" ] && [ ! -f "$ETC_DIR/config.json" ]; then
  cp -f "$REPO_DIR/api/config.json" "$ETC_DIR/config.json"
  log "config del cliente copiada a $ETC_DIR/config.json"
fi

# --- 5. Que version instalar ------------------------------------------------
TAG="$BOOTSTRAP_TAG"
if [ -z "$TAG" ]; then
  TARGET_CODE="$(curl -sS -m 30 -o /tmp/target.json -w '%{http_code}' \
    "$BACKEND_URL/api/ota/target" \
    -H "x-device-id: $DEVICE_ID" \
    -H "x-device-secret: $DEVICE_SECRET" \
    -H "x-api-secret: $BOOTSTRAP_SECRET" 2>/dev/null || echo 000)"
  if [ "$TARGET_CODE" != "200" ]; then
    fallo "el backend no respondio con la version objetivo (HTTP $TARGET_CODE)"
  fi
  TAG="$(python3 -c 'import json;print(json.load(open("/tmp/target.json")).get("tag") or "")' 2>/dev/null)"
fi

if [ -z "$TAG" ]; then
  fallo "no hay ninguna version publicada todavia"
fi
log "version objetivo: $TAG"

# --- 6. Descargar y verificar ------------------------------------------------
WORK="$(mktemp -d /tmp/safelock-migrate.XXXXXX)"
BASE="$ARTIFACT_BASE/$TAG"

# Los artefactos los sirve el backend (el repositorio es privado), asi que la
# descarga va autenticada igual que el resto de llamadas.
AUTH=(-H "x-device-id: $DEVICE_ID"
      -H "x-device-secret: $DEVICE_SECRET"
      -H "x-api-secret: $BOOTSTRAP_SECRET")

curl -fsSL -m 120 "${AUTH[@]}" -o "$WORK/manifest.json" "$BASE/manifest.json" 2>/dev/null \
  || fallo "no se pudo descargar el manifest de $TAG"
curl -fsSL -m 120 "${AUTH[@]}" -o "$WORK/manifest.json.sig" "$BASE/manifest.json.sig" 2>/dev/null \
  || fallo "no se pudo descargar la firma de $TAG"

if ! openssl dgst -sha256 -verify "$ETC_DIR/ota.pub.pem" \
      -signature "$WORK/manifest.json.sig" "$WORK/manifest.json" >/dev/null 2>&1; then
  fallo "FIRMA INVALIDA en el manifest de $TAG"
fi
log "firma del manifest verificada"

ARTIFACT="$(python3 -c 'import json;print(json.load(open("'"$WORK"'/manifest.json"))["artifact"]["name"])' 2>/dev/null)"
EXPECTED_SHA="$(python3 -c 'import json;print(json.load(open("'"$WORK"'/manifest.json"))["artifact"]["sha256"])' 2>/dev/null)"
MANIFEST_TAG="$(python3 -c 'import json;print(json.load(open("'"$WORK"'/manifest.json"))["tag"])' 2>/dev/null)"

[ -n "$ARTIFACT" ] || fallo "manifest sin nombre de artefacto"
[ "$MANIFEST_TAG" = "$TAG" ] || fallo "el manifest declara $MANIFEST_TAG y se pidio $TAG"

curl -fsSL -m 600 "${AUTH[@]}" -o "$WORK/$ARTIFACT" "$BASE/$ARTIFACT" 2>/dev/null \
  || fallo "no se pudo descargar el artefacto $ARTIFACT"

ACTUAL_SHA="$(sha256sum "$WORK/$ARTIFACT" | cut -d' ' -f1)"
if [ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]; then
  fallo "sha256 no coincide ($ACTUAL_SHA != $EXPECTED_SHA)"
fi
log "artefacto verificado"

# --- 6b. Dependencias de Python de la API -----------------------------------
# La unidad systemd del release usa /usr/bin/python3 (paquetes del sistema),
# no una venv: la venv historica vive en $REPO_DIR/api/venv y esa ruta se
# retira semanas despues de terminar la migracion, asi que nada permanente
# puede depender de ella (bug real en v2.0.1: faltaban estos paquetes en el
# sistema y la API no arrancaba).
APT_PKGS="python3-fastapi python3-uvicorn python3-pydantic python3-qrcode python3-pil"
if ! dpkg -s python3-fastapi >/dev/null 2>&1; then
  if ! DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends $APT_PKGS >>"$LOG" 2>&1; then
    apt-get update >>"$LOG" 2>&1
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends $APT_PKGS >>"$LOG" 2>&1 \
      || fallo "no se pudieron instalar los paquetes de Python de la API: $APT_PKGS"
  fi
fi
log "dependencias de Python de la API listas (paquetes del sistema)"

# --- 7. Instalar el arbol nuevo ---------------------------------------------
mkdir -p "$OTA_ROOT/releases" "$OTA_ROOT/agent/lkg" "$OTA_ROOT/rescue"
RELEASE_DIR="$OTA_ROOT/releases/$TAG"
rm -rf "$WORK/payload" "$RELEASE_DIR"
mkdir -p "$WORK/payload"
tar -xzf "$WORK/$ARTIFACT" -C "$WORK/payload" || fallo "no se pudo extraer el artefacto"
[ -f "$WORK/payload/VERSION" ] || fallo "el artefacto no contiene VERSION"
mv "$WORK/payload" "$RELEASE_DIR" || fallo "no se pudo mover el release a su sitio"
log "release instalado en $RELEASE_DIR"

# Lanzador y agente LKG (fuera del arbol de releases).
cp -f "$REPO_DIR/ota/run-agent.sh" "$OTA_ROOT/agent/run-agent.sh" || fallo "falta ota/run-agent.sh"
chmod +x "$OTA_ROOT/agent/run-agent.sh"
cp -f "$RELEASE_DIR/ota/ota_agent.py" "$OTA_ROOT/agent/lkg/ota_agent.py"

# Rescate: se instala una vez y el canal OTA normal no lo actualiza nunca.
cp -f "$REPO_DIR/rescue/rescue.sh" "$OTA_ROOT/rescue/rescue.sh" || fallo "falta rescue/rescue.sh"
chmod +x "$OTA_ROOT/rescue/rescue.sh"
cp -f "$OTA_ROOT/agent/run-agent.sh" "$OTA_ROOT/rescue/run-agent.sh"
cp -f "$REPO_DIR/rescue/safelock-rescue.service" /etc/systemd/system/
cp -f "$REPO_DIR/rescue/safelock-rescue.timer" /etc/systemd/system/

# --- 8. Cambiar los servicios, guardando los antiguos -----------------------
BACKUP="$OTA_ROOT/backup-units"
mkdir -p "$BACKUP"
for unit in safelock-api.service safelock-portal.service; do
  [ -f "$BACKUP/$unit" ] && continue
  if [ -f "/etc/systemd/system/$unit" ]; then
    cp -f "/etc/systemd/system/$unit" "$BACKUP/$unit"
    log "respaldo de $unit"
  elif systemctl cat "$unit" >/dev/null 2>&1; then
    # La unidad de fabrica puede vivir en /lib/systemd/system; systemctl cat
    # la encuentra alli tambien (su primera linea es la ruta, se descarta).
    systemctl cat "$unit" 2>/dev/null | tail -n +2 > "$BACKUP/$unit"
    log "respaldo de $unit (via systemctl cat)"
  else
    log "aviso: no existe $unit todavia; nada que respaldar"
  fi
done

restaurar_unidades() {
  for unit in safelock-api.service safelock-portal.service; do
    [ -f "$BACKUP/$unit" ] && cp -f "$BACKUP/$unit" "/etc/systemd/system/$unit"
  done
  rm -f /etc/systemd/system/safelock-ota.service /etc/systemd/system/safelock-ota.timer
  systemctl daemon-reload >/dev/null 2>&1
  systemctl restart safelock-api >/dev/null 2>&1
  systemctl restart safelock-portal >/dev/null 2>&1
}

cp -f "$RELEASE_DIR"/systemd/*.service /etc/systemd/system/ 2>/dev/null
cp -f "$RELEASE_DIR"/systemd/*.timer /etc/systemd/system/ 2>/dev/null
systemctl daemon-reload >/dev/null 2>&1

ln -sfn "$RELEASE_DIR" "$OTA_ROOT/current.new" && mv -T "$OTA_ROOT/current.new" "$OTA_ROOT/current"
log "symlink current -> $TAG"

systemctl restart safelock-api >/dev/null 2>&1
systemctl restart safelock-portal >/dev/null 2>&1

# --- 9. Verificar antes de apagar lo viejo ----------------------------------
if ! python3 "$RELEASE_DIR/scripts/health-check.py" --wait 120 >> "$LOG" 2>&1; then
  log "health check FALLO tras instalar $TAG; restaurando el sistema anterior"
  restaurar_unidades
  rm -f "$OTA_ROOT/current"
  fallo "el sistema nuevo no paso el health check"
fi
log "health check OK"

# --- 10. Apagar el sistema viejo --------------------------------------------
systemctl enable safelock-ota.timer >/dev/null 2>&1
systemctl start safelock-ota.timer >/dev/null 2>&1
systemctl enable safelock-rescue.timer >/dev/null 2>&1
systemctl start safelock-rescue.timer >/dev/null 2>&1

# El servicio de update viejo puede estar ejecutandonos ahora mismo: se
# deshabilita el timer (no se mata el servicio en curso).
systemctl disable safelock-update.timer >/dev/null 2>&1
systemctl stop safelock-update.timer >/dev/null 2>&1
systemctl disable safelock-heartbeat.timer >/dev/null 2>&1
systemctl stop safelock-heartbeat.timer >/dev/null 2>&1

date -u +%Y-%m-%dT%H:%M:%SZ > "$MARKER"
rm -rf "$WORK"
log "=== migracion completada en $TAG ==="
exit 0
