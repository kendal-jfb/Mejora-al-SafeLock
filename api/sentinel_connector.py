"""
sentinel_connector.py
=====================
Conector de API y Reglas de Bloqueo en Pi-hole (Persona 2 - "El Conector").

Responsabilidades:
1. Consumir `analizar_red()` de `threat_engine.py` (Persona 1) y exponerlo
   en el formato exacto que consume `HeuristicView` en React (Persona 3).
2. Gestionar el interruptor persistente de Modo Seguro ("shadow" vs "protect").
3. Inyectar o desactivar automáticamente las reglas de bloqueo en `gravity.db`
   con la etiqueta `[HEURISTIC_SHIELD]` y recargar Pi-hole (`pihole reloaddns`)
   sin reiniciar el contenedor ni el dispositivo.
"""

import os
import sqlite3
import subprocess
from datetime import datetime, timedelta

from packs import load_full_config, save_full_config
from threat_engine import analizar_red

# Rutas compatibles con Docker Compose (/data) y producción (/root/safeLock_SoC)
DATA_DIR = os.environ.get("SAFELOCK_DATA_DIR", "")
if not DATA_DIR:
    if os.path.exists("/root/safeLock_SoC/pihole"):
        DATA_DIR = "/root/safeLock_SoC"
    elif os.path.exists("/data/pihole"):
        DATA_DIR = "/data"
    else:
        DATA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolver_ruta_gravity(ruta_preferida: str = "") -> str:
    """Resuelve la ruta real existente para gravity.db de Pi-hole."""
    if ruta_preferida and os.path.exists(ruta_preferida):
        return ruta_preferida
    env_r = os.environ.get("SAFELOCK_GRAVITY_DB", "")
    if env_r and os.path.exists(env_r):
        return env_r
    candidatas = [
        "/root/safeLock_SoC/pihole/etc-pihole/gravity.db",
        "/etc/pihole/gravity.db",
        "/data/pihole/etc-pihole/gravity.db",
        "/opt/safelock/current/pihole/etc-pihole/gravity.db",
        os.path.join(DATA_DIR, "pihole", "etc-pihole", "gravity.db"),
    ]
    for c in candidatas:
        if c and os.path.exists(c):
            return c
    return candidatas[0]


GRAVITY_DB = resolver_ruta_gravity()

HEURISTIC_TAG = "[HEURISTIC_SHIELD]"
ALLOWED_MODES = {"shadow", "protect"}


def get_user_whitelist() -> list:
    """Retorna la lista de dominios excluidos/permitidos por el usuario."""
    cfg = load_full_config()
    wl = cfg.get("user_whitelist", [])
    if not isinstance(wl, list):
        return []
    return sorted(list(set(str(d).strip().lower().rstrip(".") for d in wl if d)))


def add_to_user_whitelist(domain: str) -> list:
    """Agrega un dominio a la lista permitida por el usuario y remueve su bloqueo de Pi-hole."""
    dom = str(domain or "").strip().lower().rstrip(".")
    if not dom:
        return get_user_whitelist()
    cfg = load_full_config()
    wl = set(get_user_whitelist())
    wl.add(dom)
    cfg["user_whitelist"] = sorted(list(wl))
    save_full_config(cfg)

    # Si existía en gravity.db con [HEURISTIC_SHIELD], desactivarlo de inmediato
    ruta_grav = resolver_ruta_gravity(GRAVITY_DB)
    if os.path.exists(ruta_grav):
        try:
            conn = sqlite3.connect(ruta_grav, timeout=10.0)
            try:
                conn.execute(
                    "UPDATE domainlist SET enabled = 0 WHERE domain = ? AND comment = ?",
                    (dom, HEURISTIC_TAG),
                )
                conn.commit()
            finally:
                conn.close()
            reload_pihole_dns()
        except Exception as e:
            print(f"[sentinel_connector] Error al desactivar bloqueo para {dom}: {e}")

    try:
        analizar_red(forzar_refresco=True)
    except Exception:
        pass

    return cfg["user_whitelist"]


def remove_from_user_whitelist(domain: str) -> list:
    """Remueve un dominio de la lista permitida por el usuario."""
    dom = str(domain or "").strip().lower().rstrip(".")
    cfg = load_full_config()
    wl = set(get_user_whitelist())
    wl.discard(dom)
    cfg["user_whitelist"] = sorted(list(wl))
    save_full_config(cfg)
    try:
        analizar_red(forzar_refresco=True)
    except Exception:
        pass
    return cfg["user_whitelist"]


def get_sentinel_mode() -> str:
    """Lee el modo actual desde la configuración persistida ('shadow' por defecto)."""
    config = load_full_config()
    mode = str(config.get("sentinel_mode", "shadow") or "shadow").strip().lower()
    return mode if mode in ALLOWED_MODES else "shadow"


def reload_pihole_dns() -> bool:
    """Ejecuta `pihole reloaddns` dentro del contenedor pihole sin reiniciarlo."""
    try:
        res = subprocess.run(
            ["docker", "exec", "pihole", "pihole", "reloaddns"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return res.returncode == 0
    except Exception as e:
        print(f"[sentinel_connector] Aviso al recargar DNS en Pi-hole: {e}")
        return False


def sync_pihole_blocks(domains, enable_block: bool = True):
    """
    Sincroniza los dominios detectados en la tabla `domainlist` de `gravity.db`
    bajo el comentario `[HEURISTIC_SHIELD]` y recarga Pi-hole solo si hubo cambios.
    Asegura consultar y actualizar exclusivamente entradas de tipo bloqueo (type = 0).
    Respeta estrictamente la lista blanca definida por el usuario.
    """
    ruta_grav = resolver_ruta_gravity(GRAVITY_DB)
    if not os.path.exists(ruta_grav):
        return []

    applied_domains = []
    changed = False
    user_wl = set(get_user_whitelist())

    try:
        conn = sqlite3.connect(ruta_grav, timeout=10.0)
        try:
            cursor = conn.cursor()

            if not enable_block:
                # Modo Sombra (Observador): desactivar bloqueos heurísticos sin borrarlos
                cursor.execute(
                    "UPDATE domainlist SET enabled = 0 WHERE comment = ? AND enabled = 1",
                    (HEURISTIC_TAG,),
                )
                if cursor.rowcount > 0:
                    changed = True
            else:
                # Modo Escudo (Protección Activa): reactivar bloqueos previos
                cursor.execute(
                    "UPDATE domainlist SET enabled = 1 WHERE comment = ? AND enabled = 0",
                    (HEURISTIC_TAG,),
                )
                if cursor.rowcount > 0:
                    changed = True

                # Garantizar que cualquier dominio en la whitelist de usuario quede desactivado
                for w in user_wl:
                    cursor.execute(
                        "UPDATE domainlist SET enabled = 0 WHERE domain = ? AND comment = ? AND enabled = 1",
                        (w, HEURISTIC_TAG),
                    )
                    if cursor.rowcount > 0:
                        changed = True

                for dom in sorted(set(domains or [])):
                    dom_clean = str(dom or "").strip().lower().rstrip(".")
                    if not dom_clean:
                        continue
                    # Si el usuario lo marcó como permitido, omitirlo
                    if dom_clean in user_wl or any(dom_clean.endswith("." + w) for w in user_wl):
                        continue

                    row = cursor.execute(
                        "SELECT id, enabled, comment FROM domainlist WHERE domain = ? AND type = 0",
                        (dom_clean,),
                    ).fetchone()

                    if row is None:
                        cursor.execute(
                            "INSERT INTO domainlist (type, domain, enabled, comment) VALUES (0, ?, 1, ?)",
                            (dom_clean, HEURISTIC_TAG),
                        )
                        applied_domains.append(dom_clean)
                        changed = True
                    else:
                        if row[1] == 0:
                            comment = HEURISTIC_TAG if not row[2] or row[2] == HEURISTIC_TAG else row[2]
                            cursor.execute(
                                "UPDATE domainlist SET enabled = 1, comment = ? WHERE id = ?",
                                (comment, row[0]),
                            )
                            changed = True
                        applied_domains.append(dom_clean)

            if changed:
                conn.commit()
        finally:
            conn.close()

        if changed:
            reload_pihole_dns()

    except Exception as e:
        print(f"[sentinel_connector] Error al actualizar gravity.db: {e}")

    return applied_domains


def get_sentinel_status(forzar: bool = False) -> dict:
    """
    Obtiene el análisis en tiempo real de Persona 1 (`analizar_red`),
    le inyecta el modo actual ('shadow' o 'protect'), la lista blanca de usuario
    y, si está en modo 'protect', aplica automáticamente los bloqueos en Pi-hole
    excluyendo las excepciones permitidas por el usuario.
    """
    mode = get_sentinel_mode()
    reporte = analizar_red(forzar_refresco=forzar)

    # Inyectar el modo y la lista blanca de usuario
    reporte["mode"] = mode
    user_wl = set(get_user_whitelist())
    reporte["user_whitelist"] = sorted(list(user_wl))

    # Recolectar todos los dominios sospechosos (DGA y Beaconing) excluyendo whitelist de usuario
    dominios_sospechosos = []
    for dev in reporte.get("devices", []):
        for dom in dev.get("dga_domains", []):
            if dom:
                d_c = dom.strip().lower().rstrip(".")
                if d_c not in user_wl and not any(d_c.endswith("." + w) for w in user_wl):
                    dominios_sospechosos.append(d_c)
        for dom in dev.get("beacon_domains", []):
            if dom:
                d_c = dom.strip().lower().rstrip(".")
                if d_c not in user_wl and not any(d_c.endswith("." + w) for w in user_wl):
                    dominios_sospechosos.append(d_c)

    if mode == "protect" and dominios_sospechosos:
        bloqueados = sync_pihole_blocks(dominios_sospechosos, enable_block=True)
    else:
        bloqueados = []

    # Dominios bloqueados totales visibles en el panel (Heurísticos + Pi-hole + Globales)
    dominios_bloq_dispositivos = []
    for dev in reporte.get("devices", []):
        for b in dev.get("blocked_domains", []):
            if b:
                dominios_bloq_dispositivos.append(b)

    try:
        from threat_engine import obtener_ultimos_bloqueos_globales
        bloqueos_globales = obtener_ultimos_bloqueos_globales(limite=20)
    except Exception:
        bloqueos_globales = []

    reporte["blocked_domains"] = sorted(list(set(bloqueados + dominios_bloq_dispositivos + bloqueos_globales)))
    return reporte


def get_sentinel_diagnostics() -> dict:
    """
    Recopila información diagnóstica completa sobre rutas, permisos,
    conectividad con bases de datos y últimas consultas registradas en Pi-hole.
    Permite validar de inmediato si el motor está recibiendo las consultas DNS.
    """
    from threat_engine import (
        resolver_ruta_pihole,
        resolver_ruta_netalertx,
        _conectar_sqlite,
    )
    pi_path = resolver_ruta_pihole()
    grav_path = resolver_ruta_gravity()
    na_path = resolver_ruta_netalertx()

    def _file_info(p):
        if not p or not os.path.exists(p):
            return {"path": p, "exists": False}
        st = os.stat(p)
        return {
            "path": p,
            "exists": True,
            "size_bytes": st.st_size,
            "modified_iso": datetime.fromtimestamp(st.st_mtime).isoformat(),
        }

    diag = {
        "timestamp": datetime.now().isoformat(),
        "paths": {
            "pihole_db": _file_info(pi_path),
            "gravity_db": _file_info(grav_path),
            "netalertx_db": _file_info(na_path),
        },
        "mode": get_sentinel_mode(),
        "user_whitelist": get_user_whitelist(),
        "pihole_sample": {},
        "heuristica_preview": {},
    }

    conn_pi = _conectar_sqlite(pi_path, solo_lectura=True)
    if conn_pi:
        try:
            cur = conn_pi.cursor()
            limite = int((datetime.now() - timedelta(days=2)).timestamp())
            total = cur.execute("SELECT COUNT(*) FROM queries WHERE timestamp > ?", (limite,)).fetchone()[0]
            ultimas = cur.execute("""
                SELECT timestamp, client, domain, status
                FROM queries
                ORDER BY timestamp DESC
                LIMIT 10
            """).fetchall()
            ultimas_list = [
                {
                    "timestamp": r[0],
                    "timestamp_iso": datetime.fromtimestamp(float(r[0])).isoformat() if r[0] else "",
                    "client": r[1],
                    "domain": r[2],
                    "status": r[3],
                }
                for r in ultimas
            ]
            diag["pihole_sample"] = {
                "queries_recientes": total,
                "ultimas_queries": ultimas_list,
            }
        except Exception as e:
            diag["pihole_sample"] = {"error": str(e)}
        finally:
            conn_pi.close()
    else:
        diag["pihole_sample"] = {"error": f"No se pudo conectar a SQLite de Pi-hole en {pi_path}"}

    try:
        rep = analizar_red(forzar_refresco=True)
        diag["heuristica_preview"] = {
            "total_dispositivos": rep.get("total_dispositivos", 0),
            "dispositivos": [
                {
                    "ip": d.get("ip"),
                    "name": d.get("name"),
                    "state": d.get("state"),
                    "dga": d.get("dga_domains"),
                    "beacon": d.get("beacon_domains"),
                    "blocked": d.get("blocked_domains"),
                }
                for d in rep.get("devices", [])
            ],
            "blocked_domains": rep.get("blocked_domains", []),
        }
    except Exception as e:
        diag["heuristica_preview"] = {"error": str(e)}

    return diag


def update_sentinel_mode(new_mode: str) -> dict:
    """
    Actualiza el modo ('shadow' | 'protect') en la configuración persistida
    y sincroniza inmediatamente las reglas en Pi-hole.
    """
    mode = str(new_mode or "").strip().lower()
    if mode not in ALLOWED_MODES:
        raise ValueError("Modo inválido. Use 'shadow' o 'protect'.")

    config = load_full_config()
    config["sentinel_mode"] = mode
    save_full_config(config)

    if mode == "shadow":
        sync_pihole_blocks([], enable_block=False)
        return {"success": True, "mode": mode, "blocked_domains": []}

    # Si se activa 'protect', forzar actualización inmediata de análisis y reglas
    analizar_red(forzar_refresco=True)
    reporte = get_sentinel_status()
    return {
        "success": True,
        "mode": mode,
        "blocked_domains": reporte.get("blocked_domains", []),
    }


def get_sentinel_honeypot_alerts() -> list:
    """
    Genera eventos de alerta para la tarjeta 'Sensor de intrusiones' del Dashboard
    cuando algún dispositivo está en estado amarillo o rojo.
    """
    alerts = []
    try:
        mode = get_sentinel_mode()
        reporte = analizar_red()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for dev in reporte.get("devices", []):
            state = dev.get("state", "green")
            if state == "green":
                continue

            ip = dev.get("ip", "Desconocido")
            dga = dev.get("dga_domains", [])
            accion = "bloqueado" if mode == "protect" else "detectado"

            if dga:
                desc = f"Dominio DGA {accion} ({dga[0]})"
            elif dev.get("blocked_domains"):
                bloq_ej = dev["blocked_domains"][0]
                desc = f"Sitio malicioso {accion} ({bloq_ej})"
            else:
                motivos = dev.get("motivos", [])
                desc = motivos[0] if motivos else f"Actividad anómala {accion} en red"

            alerts.append({
                "timestamp": now_str,
                "src_ip": ip,
                "dst_port": 53,
                "service": "Heuristic Sentinel",
                "description": desc,
                "severity": "alta" if state == "red" else "media",
            })
    except Exception as e:
        print(f"[sentinel_connector] Error generando alertas para dashboard: {e}")

    return alerts
