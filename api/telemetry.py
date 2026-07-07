import os
import subprocess
import requests
from datetime import datetime

# --- CONFIGURACIÓN DEL SOC ---
# Cambia esto por la URL real de tu backend
SOC_URL = "https://telemetry.openlocksecurity.com/heartbeat"
API_SECRET = "openlock2026"

def get_device_id():
    # Usa el hostname de la placa (ej: safelock-001)
    return os.uname()[1] 

def get_tailscale_ip():
    try:
        ip = subprocess.check_output(["tailscale", "ip", "-4"]).decode("utf-8").strip()
        return ip
    except:
        return ""

def is_pihole_active():
    try:
        status = subprocess.check_output(["systemctl", "is-active", "pihole-FTL"]).decode("utf-8").strip()
        return status == "active"
    except:
        return False

def evaluate_health():
    """
    Evalúa si hay un fallo crítico. 
    Retorna True si hay una Alerta Roja, False si todo está OK.
    """
    critical = False
    
    # 1. Revisar si los servicios clave están vivos
    # Si el Honeypot (opencanary) o el escáner de red (p0f) se caen, es crítico.
    services_to_check = ["opencanary", "p0f"]
    
    for service in services_to_check:
        try:
            status = subprocess.check_output(["systemctl", "is-active", service]).decode("utf-8").strip()
            if status != "active":
                print(f"[!] Servicio {service} caído.")
                critical = True
        except:
            critical = True
            
    # Aquí puedes añadir más reglas en el futuro (ej: si CPU > 95%)
    return critical

def send_heartbeat():
    print(f"[{datetime.now()}] Iniciando chequeo de salud...")
    
    payload = {
        "device_id": get_device_id(),
        "pihole_active": is_pihole_active(),
        "tailscale_ip": get_tailscale_ip(),
        "version": "1.3.0",
        "critical_alert": evaluate_health()
    }

    headers = {
        "Content-Type": "application/json",
        "x-api-secret": API_SECRET
    }

    try:
        r = requests.post(SOC_URL, json=payload, headers=headers, timeout=10)
        if r.status_code in [200, 201, 204]:
            print(f"[OK] Telemetría enviada con éxito al SOC. Estado Alerta: {payload['critical_alert']}")
        else:
            print(f"[ERROR] El SOC rechazó la conexión: {r.status_code} - {r.text}")
    except Exception as e:
        print(f"[ERROR] No se pudo conectar con el SOC en Render: {e}")

if __name__ == "__main__":
    send_heartbeat()
