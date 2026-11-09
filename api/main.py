from typing import Optional
import re

from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import sqlite3
import json
import os
import io
import socket
import qrcode
import smtplib
import subprocess
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pydantic import BaseModel

from packs import (
    ALLOWED_FREQUENCIES,
    CONFIG_FILE,
    get_public_config,
    get_pack_schedules_with_state,
    get_pack_states,
    load_full_config,
    save_full_config,
    save_schedule,
    set_pack_enabled,
)


def _leer_version():
    """La version real la pone el release; fuera de un release, desconocida."""
    ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "VERSION")
    try:
        with open(ruta, "r") as f:
            return f.read().strip() or "dev"
    except OSError:
        return "dev"


APP_VERSION = _leer_version()

app = FastAPI(title="SafeLock API", version=APP_VERSION)

# El portal se sirve desde la LAN del cliente o via Tailscale (acceso remoto
# del dueño); no hay motivo para aceptar origenes de internet publico contra
# una API sin autenticacion. 100.64.0.0/10 = CGNAT que usa Tailscale.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|"
                       r"192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|"
                       r"100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d+\.\d+)(:\d+)?$",
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- RUTAS DE ARCHIVOS ---
# Los datos (bind mounts de docker, bases de netalertx/pihole) siguen viviendo
# donde los dejo el aprovisionamiento de fabrica. El codigo se mueve entre
# releases, los datos no.
DATA_DIR = os.environ.get("SAFELOCK_DATA_DIR", "")
if not DATA_DIR:
    if os.path.exists("/root/safeLock_SoC/pihole"):
        DATA_DIR = "/root/safeLock_SoC"
    elif os.path.exists("/data/pihole"):
        DATA_DIR = "/data"
    else:
        DATA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NETALERTX_DB = f"{DATA_DIR}/netalertx/data/db/app.db"
OPENCANARY_LOG = f"{DATA_DIR}/netalertx/data/opencanary/opencanary.log"
P0F_LOG = "/var/log/p0f.log"
PASSIVEDNS_LOG = "/var/log/passivedns.log"
PIHOLE_DB = f"{DATA_DIR}/pihole/etc-pihole/pihole-FTL.db"
PIHOLE_GRAVITY_DB = f"{DATA_DIR}/pihole/etc-pihole/gravity.db"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
INTERNAL_STATUS_TOKEN = os.getenv("SAFELOCK_INTERNAL_TOKEN", "")

# netalertx guarda sus timestamps naive en su propio TIMEZONE (app.conf),
# no en UTC. Los normalizamos a ISO 8601 con offset para que el navegador
# los interprete igual sin importar en que zona horaria este el cliente.
NETALERTX_TZ = ZoneInfo("America/Costa_Rica")
NEW_DEVICE_WINDOW = timedelta(hours=1)


def _parsear_hora_netalertx(valor: Optional[str]) -> Optional[datetime]:
    if not valor:
        return None
    try:
        return datetime.strptime(valor, "%Y-%m-%d %H:%M:%S").replace(tzinfo=NETALERTX_TZ)
    except ValueError:
        return None


def _es_reciente(valor: Optional[str], ventana: timedelta = NEW_DEVICE_WINDOW) -> bool:
    dt = _parsear_hora_netalertx(valor)
    if dt is None:
        return False
    return datetime.now(NETALERTX_TZ) - dt < ventana

# --- CONFIGURACIÓN SMTP ---
# Las credenciales llegan por EnvironmentFile=/etc/safelock/env, que el agente
# OTA baja del backend. Si no estan, el envio de correo queda desactivado: la
# API tiene que arrancar igual, porque de ella depende el health check que
# decide si una actualizacion se confirma o se revierte.
SMTP_SERVER  = os.environ.get("SMTP_SERVER", "")
SMTP_PORT    = int(os.environ.get("SMTP_PORT", "587") or 587)
SENDER_EMAIL = os.environ.get("SMTP_SENDER", "")
SENDER_PASS  = os.environ.get("SMTP_PASSWORD", "")

EMAIL_HABILITADO = bool(SMTP_SERVER and SENDER_EMAIL and SENDER_PASS)
if not EMAIL_HABILITADO:
    print("AVISO: SMTP sin configurar en /etc/safelock/env; alertas por correo desactivadas")

# --- MODELOS DE DATOS ---
class UserConfig(BaseModel):
    email: str
    frequency: str
    alerts_enabled: bool
    admin_ip: str = "" # Campo para la Whitelist

class PackToggle(BaseModel):
    pack: str
    enabled: bool


class PackSchedulePayload(BaseModel):
    pack: str
    start: Optional[str] = ""
    end: Optional[str] = ""
    enabled: bool = False

# --- MAPEOS DE LOGS ---
LOGTYPE_MAP = {
    4000: ("SSH", "Conexión SSH detectada"),
    4001: ("SSH", "Handshake SSH - posible reconocimiento"),
    4002: ("SSH", "Intento de login SSH fallido"),
    5000: ("FTP", "Conexión FTP detectada"),
    5001: ("FTP", "Intento de login FTP"),
    8000: ("HTTP", "Acceso HTTP al honeypot"),
    8001: ("HTTP", "Petición HTTP sospechosa"),
    9000: ("Telnet", "Conexión Telnet detectada"),
    9001: ("Telnet", "Login Telnet intentado"),
    3306: ("MySQL", "Intento de conexión a base de datos"),
    3389: ("RDP", "Intento de acceso remoto RDP"),
}

SEVERITY_MAP = {
    4000: "media", 4001: "media", 4002: "alta",
    5000: "media", 5001: "alta",
    8000: "baja", 8001: "media",
    9000: "alta", 9001: "alta",
    3306: "alta", 3389: "alta",
}

# --- FUNCIONES DE APOYO ---
def get_db():
    conn = sqlite3.connect(NETALERTX_DB)
    conn.row_factory = sqlite3.Row
    return conn

def get_my_ip_addr():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except:
        return "127.0.0.1"
    finally:
        s.close()

def read_first_existing(paths):
    for path in paths:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    value = f.read().strip()
                if value:
                    return value
        except:
            continue
    return None

def get_primary_interface():
    try:
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True,
            text=True,
            check=False,
        )
        parts = result.stdout.strip().split()
        if "dev" in parts:
            idx = parts.index("dev")
            if idx + 1 < len(parts):
                return parts[idx + 1]
    except:
        pass

    try:
        for name in os.listdir("/sys/class/net"):
            if name == "lo":
                continue
            if os.path.exists(f"/sys/class/net/{name}/device"):
                return name
    except:
        pass
    return None

def get_mac_addr(interface=None):
    candidates = []
    if interface:
        candidates.append(interface)

    try:
        for name in os.listdir("/sys/class/net"):
            if name not in candidates and name != "lo":
                candidates.append(name)
    except:
        pass

    for name in candidates:
        try:
            with open(f"/sys/class/net/{name}/address", "r", encoding="utf-8") as f:
                mac = f.read().strip().upper()
            if mac and mac != "00:00:00:00:00:00":
                return mac
        except:
            continue
    return "—"

def get_system_info():
    interface = get_primary_interface()
    hostname = socket.gethostname() or "—"
    ip_addr = get_my_ip_addr()
    return {
        "hostname": hostname,
        "local_ip": ip_addr,
        "portal_url": f"http://{ip_addr}:5173",
        # Direccion estable por mDNS (no cambia aunque cambie la IP/red del cliente).
        "portal_url_mdns": "http://safelock.local:5173",
        "primary_interface": interface or "—",
        "mac_address": get_mac_addr(interface),
        "hardware": "SafeLock V2",
        "system": "SafeLockOS",
    }

def get_full_config():
    """Lee toda la configuración persistida"""
    return load_full_config()


def normalize_email(value):
    return str(value or "").strip().lower()


def validate_user_config(config: UserConfig):
    email = normalize_email(config.email)
    if not email:
        raise HTTPException(status_code=400, detail="El correo es obligatorio.")
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="El correo no tiene un formato válido.")

    frequency = str(config.frequency or "").strip().lower()
    if frequency not in ALLOWED_FREQUENCIES:
        raise HTTPException(
            status_code=400,
            detail=f"Frecuencia inválida. Opciones: {', '.join(sorted(ALLOWED_FREQUENCIES))}.",
        )

    return {
        "email": email,
        "frequency": frequency,
        "alerts_enabled": bool(config.alerts_enabled),
    }

# --- MOTOR DE ENVÍO DE EMAIL ---
# Cooldown de emails — máximo 1 por hora
_last_email_sent = None

def send_email_alert(subject, recipient, ip, port, service):
    global _last_email_sent
    if not recipient: return
    if not EMAIL_HABILITADO:
        print("Alerta no enviada: SMTP sin configurar")
        return
    now = datetime.now()
    if _last_email_sent and (now - _last_email_sent).total_seconds() < 3600:
        faltan = int(3600 - (now - _last_email_sent).total_seconds())
        print(f"Email cooldown activo — faltan {faltan}s")
        return
    _last_email_sent = now
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"SafeLock SoC Guard <{SENDER_EMAIL}>"
        msg["To"] = recipient
        html = f"""
        <div style="font-family:sans-serif; background:#050608; color:#fff; padding:25px; border:1px solid #ef4444; border-radius:12px; max-width:500px;">
            <h2 style="color:#ef4444; margin-top:0;">🚨 AMENAZA DETECTADA</h2>
            <p style="color:#d1d5db;">SafeLock ha detectado un intento de intrusión crítico.</p>
            <div style="background:#121417; padding:15px; border-radius:8px; border-left:4px solid #ef4444; margin:20px 0;">
                <p style="margin:5px 0;"><b>IP Origen:</b> <span style="color:#29b5b5;">{ip}</span></p>
                <p style="margin:5px 0;"><b>Servicio:</b> {service}</p>
                <p style="margin:5px 0;"><b>Puerto:</b> {port}</p>
                <p style="margin:5px 0;"><b>Estado:</b> <span style="color:#10b981;">IDENTIFICADO</span></p>
            </div>
            <p style="font-size:11px; color:#6b7280; border-top:1px solid #333; padding-top:15px;">
                Reporte automático SafeLock SoC.
            </p>
        </div>
        """
        msg.attach(MIMEText(html, "html"))
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=20) as server:
                server.login(SENDER_EMAIL, SENDER_PASS)
                server.sendmail(SENDER_EMAIL, recipient, msg.as_string())
        else:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=20) as server:
                server.starttls()
                server.login(SENDER_EMAIL, SENDER_PASS)
                server.sendmail(SENDER_EMAIL, recipient, msg.as_string())
    except Exception as e:
        print(f"Error SMTP: {e}")

# --- ENDPOINTS ---

@app.get("/")
def root():
    return {"status": "SafeLock API operativa", "version": APP_VERSION}


@app.get("/config")
def read_config():
    return get_public_config()


@app.post("/config")
async def save_config(config: UserConfig, request: Request):
    """Guarda configuración y registra automáticamente la IP del admin"""
    try:
        full_config = get_full_config()
        data = validate_user_config(config)
        # Registramos la IP desde donde se hace la petición como IP de confianza
        data["admin_ip"] = request.client.host if request.client else ""
        full_config.update(data)

        save_full_config(full_config)
        return {
            "status": "ok",
            "message": f"Configuración guardada. Admin IP: {data['admin_ip']}",
            **get_public_config(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Variable para rastrear último evento alertado
_last_alerted_timestamp = None
_last_email_sent = None

@app.get("/honeypot")
def get_honeypot_events(background_tasks: BackgroundTasks):
    global _last_alerted_timestamp, _last_email_sent
    events = []
    config = get_full_config()
    admin_email = config.get("email")
    admin_ip = config.get("admin_ip")
    alerts_enabled = config.get("alerts_enabled", False)

    try:
        if os.path.exists(OPENCANARY_LOG):
            with open(OPENCANARY_LOG, "r") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        src_ip = entry.get("src_host")
                        if admin_ip and src_ip == admin_ip:
                            continue
                        logtype = entry.get("logtype", 0)
                        if src_ip:
                            service, desc = LOGTYPE_MAP.get(logtype, ("Desconocido", "Actividad sospechosa"))
                            severity = SEVERITY_MAP.get(logtype, "media")
                            event_timestamp = entry.get("local_time")
                            event_data = {
                                "timestamp": event_timestamp,
                                "src_ip": src_ip,
                                "dst_port": entry.get("dst_port"),
                                "service": service,
                                "description": desc,
                                "severity": severity
                            }
                            events.append(event_data)

                            # Solo alertar si es evento NUEVO y no está en cooldown
                            if severity == "alta" and admin_email and alerts_enabled:
                                if event_timestamp != _last_alerted_timestamp:
                                    now = datetime.now()
                                    if not _last_email_sent or (now - _last_email_sent).total_seconds() >= 3600:
                                        _last_alerted_timestamp = event_timestamp
                                        _last_email_sent = now
                                        background_tasks.add_task(
                                            send_email_alert,
                                            "🚨 ALERTA SOC: Intento de Intrusión",
                                            admin_email,
                                            event_data["src_ip"],
                                            event_data["dst_port"],
                                            event_data["service"]
                                        )
                    except:
                        continue
    except Exception as e:
        return {"error": str(e), "events": []}

    events.reverse()
    try:
        sentinel_events = get_sentinel_honeypot_alerts()
        events = sentinel_events + events
    except Exception:
        pass
    return {"total": len(events), "events": events[:100]}
@app.get("/devices")
def get_devices():
    try:
        conn = get_db()
        cursor = conn.execute("SELECT devMac, devName, devVendor, devLastIP, devPresentLastScan as devStatus, devFirstConnection, devLastConnection, devIsNew, devType FROM Devices WHERE devIsArchived = 0 ORDER BY devLastConnection DESC")
        devices = [dict(row) for row in cursor.fetchall()]
        conn.close()
        for d in devices:
            d["devIsNew"] = 1 if (d["devIsNew"] == 1 and _es_reciente(d["devFirstConnection"])) else 0
            for campo in ("devFirstConnection", "devLastConnection"):
                dt = _parsear_hora_netalertx(d[campo])
                if dt is not None:
                    d[campo] = dt.isoformat()
        return {"total": len(devices), "devices": devices}
    except Exception as e: return {"error": str(e), "devices": []}

@app.get("/honeypot/graph")
def get_honeypot_graph():
    try:
        now = datetime.now()
        intervals = [
            (now - timedelta(hours=i+1), now - timedelta(hours=i), f"-{i}h" if i > 0 else "ahora")
            for i in range(6, -1, -1)
        ]
        counts = [0] * len(intervals)

        if os.path.exists(OPENCANARY_LOG):
            with open(OPENCANARY_LOG, "r") as f:
                for line in f:
                    line_s = line.strip()
                    if not line_s:
                        continue
                    try:
                        entry = json.loads(line_s)
                        ts = entry.get("local_time", "")
                        if ts:
                            event_time = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
                            for idx, (c_start, c_end, _) in enumerate(intervals):
                                if c_start <= event_time <= c_end:
                                    counts[idx] += 1
                                    break
                    except Exception:
                        continue

        graph_data = [{"h": label, "v": counts[idx]} for idx, (_, _, label) in enumerate(intervals)]
        return {"graph": graph_data}
    except Exception as e:
        return {"graph": [], "error": str(e)}

@app.get("/summary")
def get_summary():
    try:
        conn = get_db()
        total_devices = conn.execute("SELECT COUNT(*) FROM Devices WHERE devIsArchived = 0").fetchone()[0]
        nuevos_candidatos = conn.execute(
            "SELECT devFirstConnection FROM Devices WHERE devIsNew = 1 AND devIsArchived = 0"
        ).fetchall()
        new_devices = sum(1 for row in nuevos_candidatos if _es_reciente(row["devFirstConnection"]))
        recent_events = conn.execute("SELECT COUNT(*) FROM Events WHERE eve_DateTime > datetime('now', '-24 hours')").fetchone()[0]
        conn.close()
        honeypot_data = get_honeypot_events(BackgroundTasks())
        return {
            "total_devices": total_devices,
            "new_devices": new_devices,
            "events_24h": recent_events,
            "honeypot_attempts": honeypot_data.get("total", 0)
        }
    except Exception as e: return {"error": str(e)}

@app.get("/myip")
def get_myip():
    info = get_system_info()
    return {"ip": info["local_ip"], "portal_url": info["portal_url"], "portal_url_mdns": info["portal_url_mdns"]}

@app.get("/system-info")
def get_system_info_endpoint():
    return get_system_info()

@app.get("/qr")
def get_qr():
    info = get_system_info()
    url = info["portal_url_mdns"]
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

def container_running(name):
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip().lower() == "true"
    except:
        return False


def service_active(name):
    try:
        result = subprocess.run(
            ["systemctl", "is-active", name],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip() == "active"
    except:
        return False


def build_internal_status():
    services = {
        "safelock_api": True,
        "pihole": container_running("pihole"),
        "netalertx": container_running("netalertx") and os.path.exists(NETALERTX_DB),
        "opencanary": container_running("opencanary") and os.path.exists(OPENCANARY_LOG),
        "apprise": container_running("apprise"),
        "tailscale": service_active("tailscaled"),
        "p0f": os.path.exists(P0F_LOG),
        "passivedns": os.path.exists(PASSIVEDNS_LOG),
    }
    return {
        "status": "ok" if all(services.values()) else "degradado",
        "services": services,
        "timestamp": datetime.now().isoformat(),
    }


def build_customer_status():
    internal = build_internal_status()
    services = internal["services"]
    premium_active = services.get("pihole", False)
    customer_services = {
        "system": {
            "label": "Sistema principal",
            "ok": services.get("safelock_api", False),
        },
        "network_monitor": {
            "label": "Monitor de dispositivos",
            "ok": services.get("netalertx", False),
        },
        "intrusion_sensor": {
            "label": "Sensor de intrusiones",
            "ok": services.get("opencanary", False),
        },
        "threat_blocking": {
            "label": "Bloqueo de anuncios y amenazas",
            "ok": premium_active,
            "premium": True,
        },
    }
    required = ["system", "network_monitor", "intrusion_sensor"]
    base_ok = all(customer_services[key]["ok"] for key in required)
    protection_ok = premium_active

    if base_ok and protection_ok:
        status = "ok"
        headline = "SafeLock activo"
    elif base_ok:
        status = "monitoreo"
        headline = "Monitoreo activo"
    else:
        status = "degradado"
        headline = "Requiere revision de soporte"

    return {
        "status": status,
        "headline": headline,
        "mode": "premium_dns" if premium_active else "free",
        "premium_active": premium_active,
        "services": customer_services,
        "timestamp": internal["timestamp"],
    }


def require_internal_access(request: Request):
    client_host = request.client.host if request.client else ""
    if client_host in {"127.0.0.1", "::1", "localhost"}:
        return

    token = request.headers.get("x-safelock-internal-token", "")
    if INTERNAL_STATUS_TOKEN and token == INTERNAL_STATUS_TOKEN:
        return

    raise HTTPException(status_code=403, detail="Acceso interno restringido.")


@app.get("/status")
def get_status():
    return build_customer_status()


@app.get("/customer-status")
def get_customer_status():
    return build_customer_status()


@app.get("/internal/status")
def get_internal_status(request: Request):
    require_internal_access(request)
    return build_internal_status()

@app.get("/pihole/stats")
def get_pihole_stats():
    if not os.path.exists(PIHOLE_DB):
        return {"ads_blocked_today": 0, "dns_queries_today": 0, "ads_percentage_today": 0, "graph": []}
    conn = None
    try:
        uri = f"file:{os.path.abspath(PIHOLE_DB)}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=10.0)
        conn.row_factory = sqlite3.Row
        curr = conn.cursor()

        now_ts = int(datetime.now().timestamp())
        ts_24h = now_ts - 86400

        # 1. Total de peticiones hoy usando timestamp entero (aprovecha índices)
        total_row = curr.execute("SELECT COUNT(*) FROM queries WHERE timestamp > ?", (ts_24h,)).fetchone()
        total = total_row[0] if total_row else 0

        # 2. Total bloqueado hoy
        blocked_row = curr.execute(
            "SELECT COUNT(*) FROM queries WHERE status IN (1,4,5,9,10,11) AND timestamp > ?",
            (ts_24h,),
        ).fetchone()
        blocked = blocked_row[0] if blocked_row else 0

        # 3. Datos para la gráfica (últimas 6 horas)
        graph_data = []
        for i in range(6, -1, -1):
            h_label = f"-{i}h" if i > 0 else "ahora"
            start_h = now_ts - (i + 1) * 3600
            end_h = now_ts - i * 3600
            h_total = curr.execute(
                "SELECT COUNT(*) FROM queries WHERE timestamp > ? AND timestamp <= ?",
                (start_h, end_h),
            ).fetchone()[0]
            h_blocked = curr.execute(
                "SELECT COUNT(*) FROM queries WHERE status IN (1,4,5,9,10,11) AND timestamp > ? AND timestamp <= ?",
                (start_h, end_h),
            ).fetchone()[0]
            graph_data.append({"time": h_label, "peticiones": h_total, "bloqueado": h_blocked})

        pct = round((blocked / total * 100), 1) if total > 0 else 0

        return {
            "ads_blocked_today": blocked,
            "dns_queries_today": total,
            "ads_percentage_today": pct,
            "graph": graph_data
        }
    except Exception as e:
        return {"error": str(e), "ads_blocked_today": 0, "dns_queries_today": 0, "ads_percentage_today": 0, "graph": []}
    finally:
        if conn:
            conn.close()


@app.get("/pihole/recent-blocks")
def get_recent_blocks():
    """Retorna los últimos dominios bloqueados por Pi-hole con cliente y marca de tiempo."""
    from threat_engine import resolver_ruta_pihole
    ruta_pi = resolver_ruta_pihole(PIHOLE_DB)
    if not os.path.exists(ruta_pi):
        return {"total": 0, "blocks": []}
    conn = None
    try:
        uri = f"file:{os.path.abspath(ruta_pi)}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
        curr = conn.cursor()
        rows = curr.execute("""
            SELECT domain, client, timestamp, status
            FROM queries
            WHERE status IN (1, 4, 5, 9, 10, 11)
            ORDER BY timestamp DESC
            LIMIT 25
        """).fetchall()
        blocks = []
        for r in rows:
            ts_val = r["timestamp"]
            try:
                dt_str = datetime.fromtimestamp(float(ts_val)).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                dt_str = str(ts_val)
            blocks.append({
                "domain": r["domain"],
                "client": r["client"],
                "timestamp": dt_str,
                "status": r["status"]
            })
        return {"total": len(blocks), "blocks": blocks}
    except Exception as e:
        return {"error": str(e), "total": 0, "blocks": []}
    finally:
        if conn:
            conn.close()

@app.get("/pihole/packs")
def get_pihole_packs():
    try:
        return get_pack_states()
    except Exception as e:
        return {"error": str(e)}

@app.post("/pihole/packs/toggle")
def toggle_pihole_pack(payload: PackToggle):
    try:
        return set_pack_enabled(payload.pack, payload.enabled, source="manual")
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/pihole/packs/schedules")
def get_pihole_pack_schedules():
    try:
        return get_pack_schedules_with_state()
    except Exception as e:
        return {"error": str(e)}


@app.post("/pihole/packs/schedules")
def save_pihole_pack_schedule(payload: PackSchedulePayload):
    try:
        schedule = save_schedule(payload.pack, payload.start, payload.end, payload.enabled)
        return {"success": True, "pack": payload.pack, "schedule": schedule}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── SafeLock Heuristic Sentinel (Persona 2: El Conector) ─────────────────────
from sentinel_connector import (
    add_to_user_whitelist,
    get_sentinel_diagnostics,
    get_sentinel_honeypot_alerts,
    get_sentinel_status,
    get_user_whitelist,
    remove_from_user_whitelist,
    sync_pihole_blocks,
    update_sentinel_mode,
)


class SentinelModePayload(BaseModel):
    mode: str


class SentinelBlockPayload(BaseModel):
    domain: str
    enabled: bool = True


class SentinelWhitelistPayload(BaseModel):
    domain: str
    action: str = "add"  # "add" o "remove"


@app.get("/sentinel/status")
def read_sentinel_status(force: bool = False):
    """Devuelve el estado del Modo Seguro y el semáforo de dispositivos (Persona 1 -> Persona 3)."""
    try:
        return get_sentinel_status(forzar=force)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sentinel/refresh")
def refresh_sentinel():
    """Fuerza un re-análisis en tiempo real de todos los dispositivos y consultas en SQLite."""
    try:
        return get_sentinel_status(forzar=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sentinel/debug")
def read_sentinel_debug():
    """Diagnóstico integral de bases de datos, últimas consultas DNS registradas y heurística."""
    try:
        return get_sentinel_diagnostics()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sentinel/mode")
def change_sentinel_mode(payload: SentinelModePayload):
    """Cambia entre Modo Sombra ('shadow') y Protección Activa ('protect')."""
    try:
        return update_sentinel_mode(payload.mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sentinel/block")
def block_sentinel_domain(payload: SentinelBlockPayload):
    """
    Permite bloquear o desbloquear un dominio manualmente bajo [HEURISTIC_SHIELD].
    Si enabled=False, el dominio se agrega a la lista de permitidos del usuario
    de forma persistente para evitar falsos positivos y re-bloqueos.
    """
    try:
        dom = payload.domain.strip().lower().rstrip(".")
        if not payload.enabled:
            # Desbloquear = persistir en lista blanca del usuario
            add_to_user_whitelist(dom)
            return {"success": True, "domain": dom, "enabled": False, "whitelisted": True}
        else:
            # Bloquear = remover de permitidos y registrar en domainlist
            remove_from_user_whitelist(dom)
            applied = sync_pihole_blocks([dom], enable_block=True)
            return {"success": True, "domain": dom, "enabled": True, "applied": applied}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sentinel/whitelist")
def list_sentinel_whitelist():
    """Retorna la lista de excepciones/dominios permitidos por el usuario."""
    try:
        return {"user_whitelist": get_user_whitelist()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sentinel/whitelist")
def manage_sentinel_whitelist(payload: SentinelWhitelistPayload):
    """Permite agregar o quitar dominios de la lista permitida por el usuario."""
    try:
        dom = payload.domain.strip().lower().rstrip(".")
        if payload.action == "remove":
            wl = remove_from_user_whitelist(dom)
        else:
            wl = add_to_user_whitelist(dom)
        return {"success": True, "domain": dom, "action": payload.action, "user_whitelist": wl}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
