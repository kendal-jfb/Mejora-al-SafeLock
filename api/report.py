#!/usr/bin/env python3
"""
SafeLock — Sistema de Reportes Periódicos
Corre via cron, detecta frecuencia configurada y envía reporte Base o Premium
"""
import sqlite3
import json
import os
import smtplib
import subprocess
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from packs import DEFAULT_USER_CONFIG, load_full_config

# ── Configuración ──────────────────────────────────────────────────────────────
SMTP_SERVER  = "bh8912.banahosting.com"
SMTP_PORT    = 465
SENDER_EMAIL = "safelock_user_data@openlocksecurity.com"
SENDER_PASS  = "Hy7Vhj%WssN7Uy"
CONFIG_FILE    = "/root/safeLock_SoC/api/config.json"
NETALERTX_DB   = "/root/safeLock_SoC/netalertx/data/db/app.db"
OPENCANARY_LOG = "/root/safeLock_SoC/netalertx/data/opencanary/opencanary.log"
PIHOLE_DB      = "/root/safeLock_SoC/pihole/etc-pihole/pihole-FTL.db"
GRAVITY_DB     = "/root/safeLock_SoC/pihole/etc-pihole/gravity.db"
LAST_REPORT_FILE = "/root/safeLock_SoC/api/last_report.json"

# ── Helpers ────────────────────────────────────────────────────────────────────
def get_config():
    config = DEFAULT_USER_CONFIG.copy()
    try:
        stored = load_full_config()
        if isinstance(stored, dict):
            config.update(stored)
    except Exception:
        pass
    return config

def pihole_active():
    try:
        result = subprocess.run("docker ps | grep pihole", shell=True, capture_output=True, text=True)
        return "pihole" in result.stdout.lower()
    except:
        return False

def should_send_today(frequency):
    """Decide si toca enviar reporte hoy según la frecuencia configurada"""
    try:
        if os.path.exists(LAST_REPORT_FILE):
            with open(LAST_REPORT_FILE) as f:
                data = json.load(f)
                last = datetime.fromisoformat(data.get("last_sent", "2000-01-01"))
        else:
            last = datetime(2000, 1, 1)

        now = datetime.now()
        diff = (now - last).days

        if frequency == "diario"    and diff >= 1:   return True
        if frequency == "semanal"   and diff >= 7:   return True
        if frequency == "quincenal" and diff >= 15:  return True
        if frequency == "mensual"   and diff >= 30:  return True
        return False
    except:
        return True

def save_last_report():
    with open(LAST_REPORT_FILE, "w") as f:
        json.dump({"last_sent": datetime.now().isoformat()}, f)

# ── Datos para el reporte ──────────────────────────────────────────────────────
def get_network_data(days=1):
    try:
        conn = sqlite3.connect(NETALERTX_DB)
        total = conn.execute("SELECT COUNT(*) FROM Devices WHERE devIsArchived=0").fetchone()[0]
        new   = conn.execute("SELECT COUNT(*) FROM Devices WHERE devIsNew=1 AND devIsArchived=0").fetchone()[0]
        conn.close()
        return total, new
    except:
        return 0, 0

def get_honeypot_data(days=1):
    events = []
    try:
        cutoff = datetime.now() - timedelta(days=days)
        if os.path.exists(OPENCANARY_LOG):
            with open(OPENCANARY_LOG) as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        ts = entry.get("local_time", "")
                        if ts:
                            event_time = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
                            if event_time >= cutoff:
                                events.append({
                                    "ip": entry.get("src_host"),
                                    "port": entry.get("dst_port"),
                                    "time": ts[:19]
                                })
                    except:
                        continue
    except:
        pass
    return events

def get_pihole_data(days=1):
    try:
        conn = sqlite3.connect(PIHOLE_DB)
        seconds = days * 86400
        total   = conn.execute(f"SELECT COUNT(*) FROM queries WHERE CAST(timestamp AS INTEGER) > strftime('%s','now','-{days*24} hours')").fetchone()[0]
        blocked = conn.execute(f"SELECT COUNT(*) FROM queries WHERE status IN (1,4,5,9,10,11) AND CAST(timestamp AS INTEGER) > strftime('%s','now','-{days*24} hours')").fetchone()[0]
        # Top 5 dominios bloqueados
        top = conn.execute(f"""
            SELECT domain, COUNT(*) as c FROM queries
            WHERE status IN (1,4,5,9,10,11)
            AND CAST(timestamp AS INTEGER) > strftime('%s','now','-{days*24} hours')
            GROUP BY domain ORDER BY c DESC LIMIT 5
        """).fetchall()
        conn.close()
        pct = round(blocked/total*100, 1) if total > 0 else 0
        return total, blocked, pct, top
    except:
        return 0, 0, 0, []

def get_active_packs():
    try:
        conn = sqlite3.connect(GRAVITY_DB)
        rows = conn.execute("SELECT comment, enabled FROM domainlist WHERE comment LIKE '[PACK_%]'").fetchall()
        conn.close()
        names = {
            "PACK_FAMILY":  "Family Shield",
            "PACK_DETOX":   "Modo Concentración",
            "PACK_GAMES":   "Filtro Anti-Juegos",
            "PACK_PRIVACY": "Ultra Privacidad"
        }
        return [(names.get(r[0].strip("[]"), r[0]), bool(r[1])) for r in rows]
    except:
        return []

# ── Generador de HTML ──────────────────────────────────────────────────────────
def build_email(is_premium, frequency, total_devs, new_devs, honeypot_events,
                dns_total=0, dns_blocked=0, dns_pct=0, top_domains=[], packs=[]):

    period_map = {"diario":"últimas 24 horas","semanal":"última semana","quincenal":"últimas 2 semanas","mensual":"último mes"}
    period = period_map.get(frequency, "últimas 24 horas")
    date_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    mode_badge = '<span style="background:#29B5B5;color:#000;padding:3px 10px;border-radius:4px;font-size:11px;font-weight:700;">PREMIUM SHIELD</span>' if is_premium else '<span style="background:#555;color:#fff;padding:3px 10px;border-radius:4px;font-size:11px;font-weight:700;">MODO BASE</span>'

    honeypot_rows = ""
    for e in honeypot_events[:5]:
        honeypot_rows += f'<tr><td style="padding:6px 10px;color:#ef4444;">{e["ip"]}</td><td style="padding:6px 10px;color:#9ca3af;">Puerto {e["port"]}</td><td style="padding:6px 10px;color:#9ca3af;">{e["time"]}</td></tr>'
    if not honeypot_rows:
        honeypot_rows = '<tr><td colspan="3" style="padding:10px;color:#6b7280;text-align:center;">Sin eventos detectados</td></tr>'

    premium_section = ""
    if is_premium:
        top_rows = "".join([f'<tr><td style="padding:5px 10px;color:#d1d5db;">{d[0]}</td><td style="padding:5px 10px;color:#ef4444;text-align:right;">{d[1]}</td></tr>' for d in top_domains]) or '<tr><td colspan="2" style="padding:10px;color:#6b7280;text-align:center;">Sin datos</td></tr>'
        pack_rows = "".join([f'<tr><td style="padding:5px 10px;color:#d1d5db;">{p[0]}</td><td style="padding:5px 10px;text-align:right;"><span style="color:{"#10b981" if p[1] else "#6b7280"}">{"● Activo" if p[1] else "○ Inactivo"}</span></td></tr>' for p in packs])

        premium_section = f"""
        <div style="margin-top:24px;">
            <div style="background:#0F5F5F;padding:10px 16px;border-radius:6px 6px 0 0;">
                <span style="color:#29B5B5;font-weight:700;font-size:13px;">🛡️ SAFELOCK SHIELD — FILTRADO DNS</span>
            </div>
            <div style="background:#121417;border:1px solid #1f2937;border-top:none;border-radius:0 0 6px 6px;padding:16px;">
                <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px;">
                    <div style="background:#1a1d21;padding:12px;border-radius:6px;text-align:center;">
                        <div style="font-size:28px;font-weight:700;color:#fff;">{dns_total:,}</div>
                        <div style="font-size:11px;color:#6b7280;">Consultas DNS</div>
                    </div>
                    <div style="background:#1a1d21;padding:12px;border-radius:6px;text-align:center;">
                        <div style="font-size:28px;font-weight:700;color:#ef4444;">{dns_blocked:,}</div>
                        <div style="font-size:11px;color:#6b7280;">Bloqueadas</div>
                    </div>
                    <div style="background:#1a1d21;padding:12px;border-radius:6px;text-align:center;">
                        <div style="font-size:28px;font-weight:700;color:#f59e0b;">{dns_pct}%</div>
                        <div style="font-size:11px;color:#6b7280;">Efectividad</div>
                    </div>
                </div>
                <div style="margin-bottom:16px;">
                    <div style="font-size:11px;color:#6b7280;margin-bottom:6px;text-transform:uppercase;letter-spacing:.1em;">Top dominios bloqueados</div>
                    <table style="width:100%;border-collapse:collapse;">{top_rows}</table>
                </div>
                <div>
                    <div style="font-size:11px;color:#6b7280;margin-bottom:6px;text-transform:uppercase;letter-spacing:.1em;">Control de Red Avanzado</div>
                    <table style="width:100%;border-collapse:collapse;">{pack_rows}</table>
                </div>
            </div>
        </div>
        """

    html = f"""
    <div style="font-family:'IBM Plex Sans',sans-serif;background:#050608;color:#fff;padding:32px;max-width:600px;margin:0 auto;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px;padding-bottom:16px;border-bottom:1px solid #1f2937;">
            <div>
                <div style="font-size:22px;font-weight:700;color:#29B5B5;">SafeLock</div>
                <div style="font-size:11px;color:#6b7280;">Reporte {frequency.capitalize()} · {date_str}</div>
            </div>
            {mode_badge}
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:24px;">
            <div style="background:#121417;border:1px solid #1f2937;border-left:4px solid #29B5B5;padding:16px;border-radius:6px;">
                <div style="font-size:32px;font-weight:700;color:#fff;">{total_devs}</div>
                <div style="font-size:11px;color:#6b7280;text-transform:uppercase;">Dispositivos en red</div>
                {f'<div style="font-size:11px;color:#f59e0b;margin-top:4px;">{new_devs} nuevos detectados</div>' if new_devs > 0 else ''}
            </div>
            <div style="background:#121417;border:1px solid #1f2937;border-left:4px solid #ef4444;padding:16px;border-radius:6px;">
                <div style="font-size:32px;font-weight:700;color:#fff;">{len(honeypot_events)}</div>
                <div style="font-size:11px;color:#6b7280;text-transform:uppercase;">Intentos de intrusión</div>
                <div style="font-size:11px;color:#6b7280;margin-top:4px;">{period}</div>
            </div>
        </div>

        <div style="margin-bottom:24px;">
            <div style="font-size:11px;color:#6b7280;margin-bottom:8px;text-transform:uppercase;letter-spacing:.1em;">Actividad del Honeypot</div>
            <table style="width:100%;border-collapse:collapse;background:#121417;border:1px solid #1f2937;border-radius:6px;">
                <tr style="background:#1a1d21;">
                    <th style="padding:8px 10px;text-align:left;font-size:11px;color:#6b7280;">IP Origen</th>
                    <th style="padding:8px 10px;text-align:left;font-size:11px;color:#6b7280;">Servicio</th>
                    <th style="padding:8px 10px;text-align:left;font-size:11px;color:#6b7280;">Hora</th>
                </tr>
                {honeypot_rows}
            </table>
        </div>

        {premium_section}

        <div style="margin-top:24px;padding-top:16px;border-top:1px solid #1f2937;font-size:11px;color:#4b5563;text-align:center;">
            Reporte automático SafeLock · OpenLock Costa Rica<br>
            Para cambiar la frecuencia visita <span style="color:#29B5B5;">safelock.local:5173</span> → Soporte
        </div>
    </div>
    """
    return html

# ── Envío ──────────────────────────────────────────────────────────────────────
def send_report(recipient, subject, html):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"SafeLock Reports <{SENDER_EMAIL}>"
        msg["To"]      = recipient
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=20) as server:
            server.login(SENDER_EMAIL, SENDER_PASS)
            server.sendmail(SENDER_EMAIL, recipient, msg.as_string())
        print(f"[OK] Reporte enviado a {recipient}")
        return True
    except Exception as e:
        print(f"[ERROR] {e}")
        return False

# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    config = get_config()
    email     = config.get("email")
    frequency = config.get("frequency", "semanal")

    if not email:
        print("[SKIP] No hay email configurado")
        exit(0)

    if not should_send_today(frequency):
        print(f"[SKIP] No toca enviar hoy (frecuencia: {frequency})")
        exit(0)

    days_map = {"diario":1,"semanal":7,"quincenal":15,"mensual":30}
    days = days_map.get(frequency, 1)

    is_premium    = pihole_active()
    total_devs, new_devs = get_network_data(days)
    honeypot_events      = get_honeypot_data(days)

    dns_total = dns_blocked = dns_pct = 0
    top_domains = []
    packs = []

    if is_premium:
        dns_total, dns_blocked, dns_pct, top_domains = get_pihole_data(days)
        packs = get_active_packs()

    mode   = "Premium Shield" if is_premium else "Base"
    subject = f"SafeLock — Reporte {frequency.capitalize()} · {mode} · {datetime.now().strftime('%d/%m/%Y')}"

    html = build_email(is_premium, frequency, total_devs, new_devs, honeypot_events,
                       dns_total, dns_blocked, dns_pct, top_domains, packs)

    if send_report(email, subject, html):
        save_last_report()
