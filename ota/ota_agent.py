#!/usr/bin/env python3
"""Agente OTA de SafeLock.

Se ejecuta cada ~10 minutos desde safelock-ota.timer. En cada pasada:

  1. Reporta al backend su version real, estado del OTA y salud.
  2. Pregunta que version le toca a su canal.
  3. Si difiere de la instalada: descarga, verifica firma y sha256, instala en
     un directorio nuevo y cambia el symlink `current` de forma atomica.
  4. Health check amplio. Si falla, revierte al release anterior y anota la
     version como fallida para no reintentarla en bucle.

Reglas de diseno, aprendidas del updater anterior:

  * NADA aborta a medias. El equivalente de `set -e` fue justamente lo que
    dejaba dispositivos en estado inconsistente: aqui todo camino de fallo
    pasa por rollback o por dejar el sistema como estaba.
  * Solo stdlib de python3. El dispositivo no instala dependencias para
    poder actualizarse.
  * La verificacion de firma usa `openssl`, que ya viene en Armbian.
  * Un release roto nunca se reintenta solo: la correccion es publicar un tag
    nuevo. Asi un fallo no se convierte en un bucle de reinicios en la flota.
"""

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

# --- Rutas fijas en el dispositivo ---
OTA_ROOT = "/opt/safelock"
RELEASES_DIR = os.path.join(OTA_ROOT, "releases")
CURRENT_LINK = os.path.join(OTA_ROOT, "current")
AGENT_DIR = os.path.join(OTA_ROOT, "agent")
LKG_DIR = os.path.join(AGENT_DIR, "lkg")

ETC_DIR = "/etc/safelock"
CONF_FILE = os.path.join(ETC_DIR, "ota.conf")
PUBKEY_FILE = os.path.join(ETC_DIR, "ota.pub.pem")
SECRET_FILE = os.path.join(ETC_DIR, "device-secret")
DEVICE_ID_FILE = "/etc/safelock-id"

STATE_DIR = "/var/lib/safelock/ota"
STATE_FILE = os.path.join(STATE_DIR, "state.json")
LOCK_FILE = os.path.join(STATE_DIR, "lock")
LOG_FILE = os.path.join(STATE_DIR, "ota.log")

DEFAULT_BACKEND = "https://telemetry.openlocksecurity.com"
# El repo es privado, asi que los releases no se bajan de GitHub sino del
# backend, que los guarda al publicarlos. La confianza no cambia de sitio: lo
# que valida el release es la firma RSA contra ota.pub.pem, no el origen.
DEFAULT_ARTIFACT_BASE = DEFAULT_BACKEND + "/api/ota/artifact"

MAX_ARTIFACT_BYTES = 200 * 1024 * 1024
KEEP_RELEASES = 3
HEALTH_WAIT_SECONDS = 90
LOG_MAX_BYTES = 2 * 1024 * 1024


# --------------------------------------------------------------------------
# Utilidades basicas
# --------------------------------------------------------------------------

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > LOG_MAX_BYTES:
            shutil.move(LOG_FILE, LOG_FILE + ".1")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def run_cmd(args, timeout=120):
    """Ejecuta un comando sin lanzar excepciones. Devuelve (rc, stdout)."""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as exc:
        return 1, str(exc)


def read_file(path, default=""):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return default


def write_atomic(path, content, mode=0o644):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise


def load_conf():
    conf = {
        "BACKEND_URL": DEFAULT_BACKEND,
        "ARTIFACT_BASE": DEFAULT_ARTIFACT_BASE,
        "LEGACY_SECRET": "",
    }
    for line in read_file(CONF_FILE).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        conf[key.strip()] = value.strip().strip('"').strip("'")
    return conf


def load_state():
    raw = read_file(STATE_FILE)
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                data.setdefault("failed_versions", [])
                return data
        except Exception:
            log("state.json ilegible, se reinicia el estado")
    return {"failed_versions": [], "last_result": "unknown", "last_error": None}


def save_state(state):
    state["last_run"] = now_iso()
    try:
        write_atomic(STATE_FILE, json.dumps(state, indent=2))
    except Exception as exc:
        log(f"no se pudo guardar el estado: {exc}")


def device_id():
    ident = read_file(DEVICE_ID_FILE)
    if ident:
        return ident
    # Respaldo con el mismo formato que usa install/factory_setup.sh.
    mac = read_file("/sys/class/net/end0/address")
    if mac:
        return "safelock-" + mac.replace(":", "")
    return "safelock-" + os.uname()[1]


# --------------------------------------------------------------------------
# Version instalada
# --------------------------------------------------------------------------

def current_release_dir():
    try:
        if os.path.islink(CURRENT_LINK):
            return os.path.realpath(CURRENT_LINK)
    except Exception:
        pass
    return None


def installed_version():
    rel = current_release_dir()
    if not rel:
        return "none"
    return read_file(os.path.join(rel, "VERSION"), "unknown")


def installed_commit():
    rel = current_release_dir()
    if not rel:
        return ""
    return read_file(os.path.join(rel, "COMMIT"), "")


# --------------------------------------------------------------------------
# Salud y heartbeat
# --------------------------------------------------------------------------

def collect_health(wait=0):
    """Ejecuta el health-check del release activo. Nunca lanza excepcion."""
    rel = current_release_dir()
    script = os.path.join(rel, "scripts", "health-check.py") if rel else None
    if not script or not os.path.exists(script):
        return {"ok": False, "critical": {}, "warnings": {},
                "failed": ["health_check_ausente"], "disk_free_mb": -1}

    rc, out = run_cmd([sys.executable, script, "--json", "--wait", str(wait)],
                      timeout=max(60, wait + 60))
    for line in reversed(out.strip().splitlines()):
        try:
            data = json.loads(line)
            if isinstance(data, dict) and "critical" in data:
                return data
        except Exception:
            continue
    return {"ok": rc == 0, "critical": {}, "warnings": {},
            "failed": ["health_check_sin_salida"], "disk_free_mb": -1}


def tailscale_ip():
    rc, out = run_cmd(["tailscale", "ip", "-4"], timeout=15)
    if rc == 0:
        for line in out.splitlines():
            line = line.strip()
            if line:
                return line
    return ""


def auth_headers(conf):
    headers = {"Content-Type": "application/json", "x-device-id": device_id()}
    secret = read_file(SECRET_FILE)
    if secret:
        headers["x-device-secret"] = secret
    legacy = conf.get("LEGACY_SECRET")
    if legacy:
        # Solo util durante la ventana de migracion; el backend lo desactiva despues.
        headers["x-api-secret"] = legacy
    return headers


def http_json(url, conf, method="GET", payload=None, timeout=20):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers=auth_headers(conf))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read(1024 * 1024)
    if not body:
        return {}
    return json.loads(body.decode("utf-8", "replace"))


def send_heartbeat(conf, state, health, ota_state):
    warnings = health.get("warnings", {})
    critical = health.get("critical", {})

    # critical_alert conserva la semantica del heartbeat.sh anterior para que
    # el dashboard existente siga marcando lo mismo que antes.
    critical_alert = not all([
        warnings.get("opencanary", False),
        warnings.get("p0f", False),
        warnings.get("tailscaled", False),
        critical.get("api_service", False),
    ])

    payload = {
        "device_id": device_id(),
        "pihole_active": bool(warnings.get("pihole", False)),
        "tailscale_ip": tailscale_ip(),
        "version": installed_version(),
        "commit": installed_commit(),
        "critical_alert": critical_alert,
        "ota": {
            "state": ota_state,
            "last_result": state.get("last_result", "unknown"),
            "last_error": state.get("last_error"),
            "failed_versions": state.get("failed_versions", [])[-5:],
        },
        "health": {
            "ok": bool(health.get("ok")),
            "critical": critical,
            "warnings": warnings,
            "disk_free_mb": health.get("disk_free_mb", -1),
        },
    }

    try:
        http_json(conf["BACKEND_URL"].rstrip("/") + "/heartbeat", conf,
                  method="POST", payload=payload)
        return True
    except Exception as exc:
        log(f"heartbeat fallido (no bloquea): {exc}")
        return False


def get_target(conf):
    """Version objetivo del canal de este dispositivo, o None si no se sabe."""
    try:
        data = http_json(conf["BACKEND_URL"].rstrip("/") + "/api/ota/target", conf)
    except Exception as exc:
        log(f"no se pudo consultar el objetivo OTA: {exc}")
        return None, False
    return data.get("tag") or None, bool(data.get("paused"))


# --------------------------------------------------------------------------
# Descarga y verificacion
# --------------------------------------------------------------------------

def download(url, dest, max_bytes=MAX_ARTIFACT_BYTES, timeout=120, conf=None):
    headers = {"User-Agent": "safelock-ota"}
    if conf is not None:
        # El repositorio es privado: los artefactos los sirve el backend y hay
        # que identificarse igual que en el resto de llamadas.
        headers.update({k: v for k, v in auth_headers(conf).items()
                        if k != "Content-Type"})
    req = urllib.request.Request(url, headers=headers)
    total = 0
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as f:
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise RuntimeError(f"artefacto excede {max_bytes} bytes")
            f.write(chunk)
    return total


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_signature(manifest_path, sig_path):
    """Firma RSA-4096/SHA-256 verificada con openssl (presente en Armbian)."""
    if not os.path.exists(PUBKEY_FILE):
        raise RuntimeError(f"falta la clave publica {PUBKEY_FILE}")
    rc, out = run_cmd([
        "openssl", "dgst", "-sha256",
        "-verify", PUBKEY_FILE,
        "-signature", sig_path,
        manifest_path,
    ], timeout=60)
    if rc != 0:
        raise RuntimeError(f"firma invalida: {out.strip()}")


def safe_extract(tar_path, dest_dir):
    with tarfile.open(tar_path, "r:gz") as tar:
        try:
            tar.extractall(dest_dir, filter="data")
        except TypeError:
            # python < 3.12 no tiene filter=: validamos las rutas a mano.
            base = os.path.realpath(dest_dir)
            for member in tar.getmembers():
                target = os.path.realpath(os.path.join(dest_dir, member.name))
                if not target.startswith(base + os.sep) and target != base:
                    raise RuntimeError(f"ruta insegura en el tar: {member.name}")
                if member.issym() or member.islnk():
                    raise RuntimeError(f"enlace no permitido en el tar: {member.name}")
            tar.extractall(dest_dir)


def fetch_release(conf, tag):
    """Descarga y verifica un release. Devuelve su directorio ya instalado."""
    base = conf["ARTIFACT_BASE"].rstrip("/") + "/" + tag
    target_dir = os.path.join(RELEASES_DIR, tag)

    if os.path.isdir(target_dir) and os.path.exists(os.path.join(target_dir, "VERSION")):
        log(f"{tag} ya estaba descargado, se reutiliza")
        return target_dir

    os.makedirs(RELEASES_DIR, exist_ok=True)
    work = tempfile.mkdtemp(prefix="ota-", dir=RELEASES_DIR)
    try:
        manifest_path = os.path.join(work, "manifest.json")
        sig_path = manifest_path + ".sig"
        download(base + "/manifest.json", manifest_path, max_bytes=1024 * 1024, timeout=60, conf=conf)
        download(base + "/manifest.json.sig", sig_path, max_bytes=1024 * 1024, timeout=60, conf=conf)

        verify_signature(manifest_path, sig_path)
        manifest = json.loads(read_file(manifest_path))

        # Un manifest firmado de otra version no sirve para esta: evita que un
        # backend comprometido reenvie un release viejo y valido.
        if manifest.get("tag") != tag:
            raise RuntimeError(f"el manifest declara {manifest.get('tag')}, se pidio {tag}")

        artifact = manifest.get("artifact") or {}
        name = artifact.get("name")
        expected_sha = (artifact.get("sha256") or "").lower()
        if not name or len(expected_sha) != 64:
            raise RuntimeError("manifest sin artefacto o sin sha256 valido")

        free_mb = int(shutil.disk_usage(RELEASES_DIR).free / (1024 * 1024))
        needed_mb = int(artifact.get("size", 0) / (1024 * 1024)) * 3 + 100
        if free_mb < needed_mb:
            raise RuntimeError(f"disco insuficiente: {free_mb}MB libres, {needed_mb}MB requeridos")

        tar_path = os.path.join(work, name)
        download(base + "/" + name, tar_path, conf=conf)

        actual_sha = sha256_file(tar_path)
        if actual_sha != expected_sha:
            raise RuntimeError(f"sha256 no coincide: {actual_sha} != {expected_sha}")

        extract_dir = os.path.join(work, "payload")
        os.makedirs(extract_dir)
        safe_extract(tar_path, extract_dir)

        if not os.path.exists(os.path.join(extract_dir, "VERSION")):
            raise RuntimeError("el release no contiene VERSION")

        # Renombrado final: hasta aqui nada toca el arbol de releases activo.
        if os.path.isdir(target_dir):
            shutil.rmtree(target_dir, ignore_errors=True)
        os.rename(extract_dir, target_dir)
        log(f"{tag} verificado e instalado en {target_dir}")
        return target_dir
    finally:
        shutil.rmtree(work, ignore_errors=True)


# --------------------------------------------------------------------------
# Instalacion
# --------------------------------------------------------------------------

def install_units(release_dir):
    """Copia las unidades systemd del release. Devuelve los timers cambiados."""
    src_dir = os.path.join(release_dir, "systemd")
    changed_timers = []
    if not os.path.isdir(src_dir):
        return changed_timers

    any_change = False
    for name in sorted(os.listdir(src_dir)):
        if not name.endswith((".service", ".timer")):
            continue
        src = os.path.join(src_dir, name)
        dst = os.path.join("/etc/systemd/system", name)
        try:
            if os.path.exists(dst) and read_file(src) == read_file(dst):
                continue
            shutil.copyfile(src, dst)
            os.chmod(dst, 0o644)
            any_change = True
            if name.endswith(".timer"):
                changed_timers.append(name)
            log(f"unidad instalada: {name}")
        except Exception as exc:
            log(f"no se pudo instalar {name}: {exc}")

    if any_change:
        run_cmd(["systemctl", "daemon-reload"], timeout=60)
        for name in sorted(os.listdir(src_dir)):
            if name.endswith((".service", ".timer")):
                run_cmd(["systemctl", "enable", name], timeout=60)
    return changed_timers


def run_post_install(release_dir):
    hook = os.path.join(release_dir, "ota", "hooks", "post-install.sh")
    if not os.path.exists(hook):
        return
    log("ejecutando hook post-install")
    env = os.environ.copy()
    env["RELEASE_DIR"] = release_dir
    try:
        r = subprocess.run(["bash", hook], capture_output=True, text=True,
                           timeout=600, env=env)
        if r.returncode != 0:
            raise RuntimeError((r.stdout or "") + (r.stderr or ""))
        log("hook post-install OK")
    except Exception as exc:
        raise RuntimeError(f"hook post-install fallo: {exc}")


def point_current_to(release_dir):
    """Cambio atomico del symlink: rename(2) sobre el propio enlace."""
    tmp_link = CURRENT_LINK + ".new"
    try:
        os.unlink(tmp_link)
    except FileNotFoundError:
        pass
    os.symlink(release_dir, tmp_link)
    os.replace(tmp_link, CURRENT_LINK)


def restart_services():
    for unit in ("safelock-api", "safelock-portal"):
        rc, out = run_cmd(["systemctl", "restart", unit], timeout=120)
        if rc != 0:
            log(f"fallo al reiniciar {unit}: {out.strip()}")


def prune_releases(keep_paths):
    try:
        keep = {os.path.realpath(p) for p in keep_paths if p}
        entries = []
        for name in os.listdir(RELEASES_DIR):
            path = os.path.join(RELEASES_DIR, name)
            if os.path.isdir(path):
                entries.append((os.path.getmtime(path), path))
        entries.sort(reverse=True)
        for _, path in entries[KEEP_RELEASES:]:
            if os.path.realpath(path) in keep:
                continue
            shutil.rmtree(path, ignore_errors=True)
            log(f"release antiguo eliminado: {os.path.basename(path)}")
    except Exception as exc:
        log(f"no se pudo limpiar releases: {exc}")


def promote_lkg(release_dir):
    """Guarda el agente que acaba de demostrar que funciona."""
    try:
        os.makedirs(LKG_DIR, exist_ok=True)
        src = os.path.join(release_dir, "ota", "ota_agent.py")
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(LKG_DIR, "ota_agent.py"))
    except Exception as exc:
        log(f"no se pudo actualizar el agente LKG: {exc}")


def apply_release(release_dir):
    """Instala y activa un release ya verificado. Lanza excepcion si falla."""
    run_post_install(release_dir)
    install_units(release_dir)
    point_current_to(release_dir)
    restart_services()


def rollback_to(previous_dir):
    log(f"revirtiendo a {previous_dir}")
    try:
        install_units(previous_dir)
        point_current_to(previous_dir)
        restart_services()
        health = collect_health(wait=HEALTH_WAIT_SECONDS)
        if health.get("ok"):
            log("rollback OK")
        else:
            log(f"rollback aplicado pero la salud sigue mal: {health.get('failed')}")
        return health
    except Exception as exc:
        log(f"rollback fallido: {exc}")
        return {"ok": False, "failed": ["rollback_fallido"], "critical": {}, "warnings": {}}


# --------------------------------------------------------------------------
# Ciclo principal
# --------------------------------------------------------------------------

def do_update(conf, state, tag):
    previous_dir = current_release_dir()
    log(f"actualizando {installed_version()} -> {tag}")

    release_dir = fetch_release(conf, tag)

    try:
        apply_release(release_dir)
    except Exception as exc:
        log(f"instalacion fallida: {exc}")
        state["last_result"] = "rollback"
        state["last_error"] = str(exc)[:500]
        if tag not in state["failed_versions"]:
            state["failed_versions"].append(tag)
        if previous_dir and os.path.isdir(previous_dir):
            rollback_to(previous_dir)
        return False

    health = collect_health(wait=HEALTH_WAIT_SECONDS)
    if health.get("ok"):
        log(f"health check OK, {tag} confirmado")
        state["last_result"] = "success"
        state["last_error"] = None
        state["installed"] = tag
        promote_lkg(release_dir)
        prune_releases([release_dir, previous_dir])
        return True

    fallos = ", ".join(health.get("failed", [])) or "desconocido"
    log(f"health check FALLO ({fallos}) tras instalar {tag}")
    state["last_result"] = "rollback"
    state["last_error"] = f"health check fallo: {fallos}"[:500]
    if tag not in state["failed_versions"]:
        state["failed_versions"].append(tag)

    if previous_dir and os.path.isdir(previous_dir):
        rollback_to(previous_dir)
    else:
        log("no hay release anterior al que revertir; se deja el actual")
    return False


def cycle(conf, state):
    health = collect_health()
    version = installed_version()

    target, paused = get_target(conf)

    if target is None:
        # Backend inaccesible o sin objetivo: el dispositivo sigue funcionando.
        send_heartbeat(conf, state, health, "idle")
        log("sin objetivo OTA (backend inaccesible o sin release); nada que hacer")
        return

    if paused:
        send_heartbeat(conf, state, health, "paused")
        log(f"rollout en pausa (objetivo {target})")
        return

    if target == version:
        send_heartbeat(conf, state, health, "idle")
        log(f"al dia en {version}")
        return

    if target in state.get("failed_versions", []):
        send_heartbeat(conf, state, health, "blocked")
        log(f"{target} ya fallo en este equipo; se ignora hasta que se publique otro tag")
        return

    send_heartbeat(conf, state, health, "updating")
    ok = do_update(conf, state, target)

    # Segundo heartbeat con el resultado real, para que el dashboard lo vea ya.
    send_heartbeat(conf, state, collect_health(), "idle" if ok else "failed")


def recover(conf, state):
    """Modo de rescate del wrapper: el agente de `current` no arranco."""
    log("modo recover: revisando el release activo")
    rel = current_release_dir()
    if not rel or not os.path.isdir(rel):
        log("el symlink current esta roto")
        candidates = []
        try:
            for name in os.listdir(RELEASES_DIR):
                path = os.path.join(RELEASES_DIR, name)
                if os.path.isdir(path) and os.path.exists(os.path.join(path, "VERSION")):
                    candidates.append((os.path.getmtime(path), path))
        except Exception:
            pass
        if candidates:
            candidates.sort(reverse=True)
            rollback_to(candidates[0][1])
        state["last_result"] = "recovered"
        save_state(state)
        return

    health = collect_health(wait=30)
    if not health.get("ok"):
        installed = state.get("installed")
        if installed and installed not in state["failed_versions"]:
            state["failed_versions"].append(installed)
        for _, path in sorted(
            ((os.path.getmtime(os.path.join(RELEASES_DIR, n)), os.path.join(RELEASES_DIR, n))
             for n in os.listdir(RELEASES_DIR)
             if os.path.isdir(os.path.join(RELEASES_DIR, n))),
            reverse=True,
        ):
            if os.path.realpath(path) != os.path.realpath(rel):
                rollback_to(path)
                break
    state["last_result"] = "recovered"
    state["last_error"] = "el agente activo fallo; se uso la copia LKG"
    save_state(state)
    send_heartbeat(conf, state, collect_health(), "recovered")


def main():
    ap = argparse.ArgumentParser(description="Agente OTA de SafeLock")
    ap.add_argument("--recover", action="store_true",
                    help="modo rescate invocado por el wrapper LKG")
    ap.add_argument("--status", action="store_true",
                    help="imprime el estado local y sale")
    args = ap.parse_args()

    if args.status:
        print(json.dumps({
            "device_id": device_id(),
            "version": installed_version(),
            "commit": installed_commit(),
            "current": current_release_dir(),
            "state": load_state(),
        }, indent=2))
        return 0

    os.makedirs(STATE_DIR, exist_ok=True)
    lock_fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log("ya hay otra ejecucion en curso; se omite esta pasada")
        return 0

    conf = load_conf()
    state = load_state()
    try:
        if args.recover:
            recover(conf, state)
        else:
            cycle(conf, state)
    except Exception as exc:
        # Ultima red: nada de lo anterior debe dejar el proceso sin registrar.
        log(f"error no controlado: {exc}")
        state["last_result"] = "error"
        state["last_error"] = str(exc)[:500]
        save_state(state)
        return 1
    finally:
        try:
            save_state(state)
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
