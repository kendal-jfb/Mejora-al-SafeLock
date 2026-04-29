from typing import Optional

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
from datetime import datetime, timedelta
from pydantic import BaseModel

from packs import (
    get_pack_schedules_with_state,
    get_pack_states,
    load_full_config,
    save_full_config,
    save_schedule,
    set_pack_enabled,
)

app = FastAPI(title="SafeLock API", version="1.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- RUTAS DE ARCHIVOS ---
NETALERTX_DB = "/root/safeLock_SoC/netalertx/data/db/app.db"
OPENCANARY_LOG = "/root/safeLock_SoC/netalertx/data/opencanary/opencanary.log"
P0F_LOG = "/var/log/p0f.log"
PASSIVEDNS_LOG = "/var/log/passivedns.log"
CONFIG_FILE = "/root/safeLock_SoC/api/config.json"
PIHOLE_DB = "/root/safeLock_SoC/pihole/etc-pihole/pihole-FTL.db"
PIHOLE_GRAVITY_DB = "/root/safeLock_SoC/pihole/etc-pihole/gravity.db"

# --- CONFIGURACIÓN SMTP (GMAIL) ---
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "ethancrdr@gmail.com"
SENDER_PASS = "ptkoqxizhtfnienh"

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

def get_full_config():
    """Lee toda la configuración persistida"""
    return load_full_config()

# --- MOTOR DE ENVÍO DE EMAIL ---
# Cooldown de emails — máximo 1 por hora
_last_email_sent = None

def send_email_alert(subject, recipient, ip, port, service):
    global _last_email_sent
    if not recipient: return
    now = datetime.now()
    if _last_email_sent and (now - _last_email_sent).seconds < 3600:
        print(f"Email cooldown activo — faltan {3600 - (now - _last_email_sent).seconds}s")
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
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASS)
            server.sendmail(SENDER_EMAIL, recipient, msg.as_string())
    except Exception as e:
        print(f"Error SMTP: {e}")

# --- ENDPOINTS ---

@app.get("/")
def root():
    return {"status": "SafeLock API operativa", "version": "1.2.0"}

@app.post("/config")
async def save_config(config: UserConfig, request: Request):
    """Guarda configuración y registra automáticamente la IP del admin"""
    try:
        full_config = get_full_config()
        data = config.dict()
        # Registramos la IP desde donde se hace la petición como IP de confianza
        data["admin_ip"] = request.client.host
        full_config.update(data)

        save_full_config(full_config)
        return {"status": "ok", "message": f"Configuración guardada. Admin IP: {data['admin_ip']}"}
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
                                    if not _last_email_sent or (now - _last_email_sent).seconds >= 3600:
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
    return {"total": len(events), "events": events[:100]}
@app.get("/devices")
def get_devices():
    try:
        conn = get_db()
        cursor = conn.execute("SELECT devMac, devName, devVendor, devLastIP, devPresentLastScan as devStatus, devFirstConnection, devLastConnection, devIsNew, devType FROM Devices WHERE devIsArchived = 0 ORDER BY devLastConnection DESC")
        devices = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return {"total": len(devices), "devices": devices}
    except Exception as e: return {"error": str(e), "devices": []}

@app.get("/honeypot/graph")
def get_honeypot_graph():
    try:
        graph_data = []
        for i in range(6, -1, -1):
            h_label = f"-{i}h" if i > 0 else "ahora"
            cutoff_start = datetime.now() - timedelta(hours=i+1)
            cutoff_end   = datetime.now() - timedelta(hours=i)
            count = 0
            if os.path.exists(OPENCANARY_LOG):
                with open(OPENCANARY_LOG, "r") as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            ts = entry.get("local_time", "")
                            if ts:
                                event_time = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
                                if cutoff_start <= event_time <= cutoff_end:
                                    count += 1
                        except:
                            continue
            graph_data.append({"h": h_label, "v": count})
        return {"graph": graph_data}
    except Exception as e:
        return {"graph": [], "error": str(e)}

@app.get("/summary")
def get_summary():
    try:
        conn = get_db()
        total_devices = conn.execute("SELECT COUNT(*) FROM Devices WHERE devIsArchived = 0").fetchone()[0]
        new_devices = conn.execute("SELECT COUNT(*) FROM Devices WHERE devIsNew = 1 AND devIsArchived = 0").fetchone()[0]
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
    ip = get_my_ip_addr()
    return {"ip": ip, "portal_url": f"http://{ip}:5173"}

@app.get("/qr")
def get_qr():
    ip = get_my_ip_addr()
    url = f"http://{ip}:5173"
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

@app.get("/status")
def get_status():
    def pihole_active():
        try:
            # Busca cualquier contenedor activo que tenga "pihole" en el nombre o imagen
            result = subprocess.run(
                "docker ps | grep pihole",
                shell=True, capture_output=True, text=True
            )
            return "pihole" in result.stdout.lower()
        except:
            return False

    services = {
        "netalertx": os.path.exists(NETALERTX_DB),
        "opencanary": os.path.exists(OPENCANARY_LOG),
        "p0f": os.path.exists(P0F_LOG),
        "passivedns": os.path.exists(PASSIVEDNS_LOG),
        "pihole": pihole_active(),
    }
    return {
        "status": "ok" if all(services.values()) else "degradado",
        "services": services,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/pihole/stats")
def get_pihole_stats():
    try:
        # Conectamos a la DB de Pi-hole
        conn = sqlite3.connect(PIHOLE_DB)
        conn.row_factory = sqlite3.Row
        curr = conn.cursor()

        # 1. Total de peticiones hoy
        total = curr.execute("SELECT COUNT(*) FROM queries WHERE CAST(timestamp AS INTEGER) > strftime('%s', 'now', '-24 hours')").fetchone()[0]

        # 2. Total bloqueado hoy
        blocked = curr.execute("SELECT COUNT(*) FROM queries WHERE status IN (1,4,5,9,10,11) AND CAST(timestamp AS INTEGER) > strftime('%s', 'now', '-24 hours')").fetchone()[0]

        # 3. Datos para la gráfica (últimas 6 horas)
        graph_data = []
        for i in range(6, -1, -1):
            h_label = f"-{i}h" if i > 0 else "ahora"
            h_total = curr.execute(f"SELECT COUNT(*) FROM queries WHERE CAST(timestamp AS INTEGER) > strftime('%s', 'now', '-{i+1} hours') AND CAST(timestamp AS INTEGER) <= strftime('%s', 'now', '-{i} hours')").fetchone()[0]
            h_blocked = curr.execute(f"SELECT COUNT(*) FROM queries WHERE status IN (1,4,5,9,10,11) AND CAST(timestamp AS INTEGER) > strftime('%s', 'now', '-{i+1} hours') AND CAST(timestamp AS INTEGER) <= strftime('%s', 'now', '-{i} hours')").fetchone()[0]
            graph_data.append({"time": h_label, "peticiones": h_total, "bloqueado": h_blocked})
        conn.close()

        pct = round((blocked / total * 100), 1) if total > 0 else 0

        return {
            "ads_blocked_today": blocked,
            "dns_queries_today": total,
            "ads_percentage_today": pct,
            "graph": graph_data
        }
    except Exception as e:
        return {"error": str(e), "ads_blocked_today": 0, "dns_queries_today": 0, "ads_percentage_today": 0, "graph": []}

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
