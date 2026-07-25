#!/usr/bin/env python3
"""Health check del dispositivo SafeLock.

Distingue dos niveles:

  criticos  -> si alguno falla, el agente OTA revierte la actualizacion.
               Solo cosas que un release puede romper: los servicios propios.
  warnings  -> se reportan en el heartbeat pero NUNCA revierten. Un contenedor
               docker caido casi siempre es ajeno al release y revertir por eso
               produciria flapping de la flota.

Salida con --json (la que consume el agente):

  {"ok": true,
   "critical": {"api_service": true, ...},
   "warnings": {"pihole": true, ...},
   "disk_free_mb": 3120,
   "failed": []}

Codigo de salida: 0 si todos los criticos pasan, 1 si alguno falla.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

API_URL = "http://127.0.0.1:8090/status"
PORTAL_URL = "http://127.0.0.1:5173/"
MIN_DISK_FREE_MB = 500


def systemd_is_active(unit):
    try:
        r = subprocess.run(
            ["systemctl", "is-active", "--quiet", unit],
            capture_output=True, timeout=15,
        )
        return r.returncode == 0
    except Exception:
        return False


def docker_running(name):
    try:
        r = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=20,
        )
        if r.returncode != 0:
            return False
        return name in r.stdout.split()
    except Exception:
        return False


def http_ok(url, expect_json=False, timeout=8):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status != 200:
                return False
            body = resp.read(65536)
        if expect_json:
            json.loads(body.decode("utf-8", "replace"))
        return True
    except Exception:
        return False


def any_safelock_unit_failed():
    """True si alguna unidad safelock-* quedo en estado failed."""
    try:
        r = subprocess.run(
            ["systemctl", "list-units", "--state=failed", "--no-legend",
             "--plain", "safelock-*"],
            capture_output=True, text=True, timeout=20,
        )
        if r.returncode != 0:
            return False
        return bool(r.stdout.strip())
    except Exception:
        return False


def disk_free_mb(path="/"):
    try:
        return int(shutil.disk_usage(path).free / (1024 * 1024))
    except Exception:
        return -1


def collect(check_portal=True):
    critical = {
        "api_service": systemd_is_active("safelock-api"),
        "api_http": http_ok(API_URL, expect_json=True),
        "no_failed_units": not any_safelock_unit_failed(),
    }
    if check_portal:
        critical["portal_service"] = systemd_is_active("safelock-portal")
        critical["portal_http"] = http_ok(PORTAL_URL)

    free_mb = disk_free_mb("/")
    warnings = {
        "pihole": docker_running("pihole"),
        "netalertx": docker_running("netalertx"),
        "opencanary": docker_running("opencanary"),
        "p0f": systemd_is_active("p0f"),
        "tailscaled": systemd_is_active("tailscaled"),
        "disk_ok": free_mb < 0 or free_mb >= MIN_DISK_FREE_MB,
    }

    failed = [k for k, v in critical.items() if not v]
    return {
        "ok": not failed,
        "critical": critical,
        "warnings": warnings,
        "disk_free_mb": free_mb,
        "failed": failed,
    }


def run(wait_seconds=0, check_portal=True):
    """Reintenta hasta wait_seconds; los servicios tardan en arrancar en el SoC."""
    deadline = time.monotonic() + max(0, wait_seconds)
    result = collect(check_portal)
    while not result["ok"] and time.monotonic() < deadline:
        time.sleep(5)
        result = collect(check_portal)
    return result


def main():
    ap = argparse.ArgumentParser(description="Health check de SafeLock")
    ap.add_argument("--wait", type=int, default=0,
                    help="segundos a reintentar antes de declarar fallo")
    ap.add_argument("--json", action="store_true", help="salida JSON")
    ap.add_argument("--no-portal", action="store_true",
                    help="omitir los chequeos del portal")
    args = ap.parse_args()

    result = run(args.wait, check_portal=not args.no_portal)

    if args.json:
        print(json.dumps(result))
    else:
        estado = "OK" if result["ok"] else "FALLO"
        print(f"health: {estado}")
        for nombre, valor in sorted(result["critical"].items()):
            print(f"  critico  {nombre}: {'ok' if valor else 'FALLO'}")
        for nombre, valor in sorted(result["warnings"].items()):
            print(f"  warning  {nombre}: {'ok' if valor else 'degradado'}")
        print(f"  disco libre: {result['disk_free_mb']} MB")

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
