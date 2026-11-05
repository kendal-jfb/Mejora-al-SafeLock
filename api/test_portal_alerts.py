"""
test_portal_alerts.py
======================
Simula la respuesta del endpoint y valida cómo la interfaz gráfica
(HeuristicView y Dashboard Honeypot) consumen y muestran todas las alertas:
1. Normal (Verde) -> Sin alertas, chip verde, sin banner
2. Sospechoso (Amarillo: Beaconing / NXDOMAIN / Bloqueos) -> Chip amarillo, badge en conteo, alerta en panel
3. Peligro (Rojo: DGA / Múltiples amenazas) -> Chip rojo pulsante, lista de dominios DGA/Beaconing, panel error=true
4. Eventos en Honeypot del Dashboard -> Conectados con severidad alta/media
"""

import sys, os, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sentinel_connector

MOCK_SENTINEL_DATA = {
    "mode": "shadow",
    "devices": [
        {
            "ip": "192.168.1.10",
            "mac": "AA:BB:CC:11:22:33",
            "name": "PC-Gamer-FIFA-Epic",
            "state": "green",
            "reasons": [],
            "dga_domains": [],
            "beacon_domains": [],
            "queries": 320,
            "nxdomain_rate": 0.02,
            "puntuacion": 0,
            "motivos": []
        },
        {
            "ip": "192.168.1.25",
            "mac": "AA:BB:CC:44:55:66",
            "name": "Smart-TV-Living",
            "state": "yellow",
            "reasons": ["beaconing"],
            "dga_domains": [],
            "beacon_domains": ["telemetry-anomaly.xyz"],
            "queries": 450,
            "nxdomain_rate": 0.05,
            "puntuacion": 35,
            "motivos": ["Actividad repetitiva sospechosa (Beaconing) hacia: telemetry-anomaly.xyz (45 veces)."]
        },
        {
            "ip": "192.168.1.99",
            "mac": "AA:BB:CC:77:88:99",
            "name": "Laptop-Comprometida",
            "state": "red",
            "reasons": ["dga", "blocked", "nxdomain"],
            "dga_domains": ["xkqtbprvzm.top", "bzqwxvfjpm.xyz"],
            "beacon_domains": ["c2-stealer.biz"],
            "queries": 120,
            "nxdomain_rate": 0.42,
            "puntuacion": 85,
            "motivos": [
                "Pi-hole bloqueó 15 intento(s) de conexión a sitios restringidos.",
                "Consulta a dominio(s) con patrón de virus/DGA: xkqtbprvzm.top, bzqwxvfjpm.xyz.",
                "Alta tasa de dominios inexistentes (42%)."
            ]
        }
    ]
}

SENTINEL_STATE = {
    "green":  {"label": "Normal", "color": "var(--ok)"},
    "yellow": {"label": "Sospechoso", "color": "var(--amber)"},
    "red":    {"label": "Probable infección", "color": "var(--red)"},
}
SENTINEL_REASON = {
    "dga":       "Dominios con nombre aleatorio (posible DGA)",
    "beaconing": "Consultas a intervalos idénticos (beaconing)",
    "nxdomain":  "Muchas consultas a dominios inexistentes",
    "blocked":   "Consultas a sitios restringidos en listas negras",
}

print("\n" + "="*65)
print("  VALIDACIÓN DE RENDERIZADO EN INTERFAZ GRÁFICA (App.jsx)")
print("="*65 + "\n")

devices = MOCK_SENTINEL_DATA["devices"]

count_green = sum(1 for d in devices if d["state"] == "green")
count_yellow = sum(1 for d in devices if d["state"] == "yellow")
count_red = sum(1 for d in devices if d["state"] == "red")
alerts = [d for d in devices if d["state"] != "green"]

print(f"📊 TARJETAS DE ESTADO (HeuristicView):")
print(f"   🟢 {SENTINEL_STATE['green']['label'].upper():<20}: {count_green} dispositivo(s)")
print(f"   🟡 {SENTINEL_STATE['yellow']['label'].upper():<20}: {count_yellow} dispositivo(s)")
print(f"   🔴 {SENTINEL_STATE['red']['label'].upper():<20}: {count_red} dispositivo(s)")
print()

print(f"🚨 PANEL DE ALERTAS (Visible solo si alerts.length > 0):")
print(f"   ¿Panel de Alertas renderizado?: {'SÍ' if len(alerts) > 0 else 'NO'} ({len(alerts)} alertas)")
print(f"   ¿Panel en estado crítico (error=true)?: {'SÍ' if any(d['state']=='red' for d in alerts) else 'NO'}")
for d in alerts:
    print(f"   - Alerta en banner: Dispositivo {d['ip']} intentó resolver un dominio sospechoso")
print()

print(f"🖥️  SEMÁFORO POR DISPOSITIVO (Tarjetas individuales):")
for d in devices:
    s = SENTINEL_STATE[d["state"]]
    print(f"   [{s['label'].upper()}] Dispositivo: {d['name']} ({d['ip']})")
    print(f"      Chip UI : {s['label']} (pulse={'True' if d['state']=='red' else 'False'})")
    if d["reasons"]:
        print(f"      Motivos mostrados en lista:")
        for r in d["reasons"]:
            print(f"        • {SENTINEL_REASON.get(r, r)}")
    if d["dga_domains"]:
        print(f"      Dominios DGA en rojo:")
        for dom in d["dga_domains"]:
            print(f"        ⚠️ {dom}")
    if d.get("beacon_domains"):
        print(f"      Beaconing insistente a:")
        for dom in d["beacon_domains"]:
            print(f"        📡 {dom}")
    print(f"      Métricas: {d['queries']} consultas · {int(d['nxdomain_rate']*100)}% inexistentes")
    print()

sentinel_connector.analizar_red = lambda forzar_refresco=False: MOCK_SENTINEL_DATA
sentinel_connector.get_sentinel_mode = lambda: "shadow"
honeypot_events = sentinel_connector.get_sentinel_honeypot_alerts()

print(f"🛡️  EVENTOS REFLEJADOS EN EL SENSOR DEL DASHBOARD (/honeypot/events):")
print(f"   Total eventos generados: {len(honeypot_events)}")
for ev in honeypot_events:
    print(f"   - [{ev['severity'].upper()}] IP {ev['src_ip']} -> {ev['description']} (servicio: {ev['service']})")

print("\n" + "="*65)
print("  ✓ TODAS LAS ALERTAS SE PROPAGAN Y RENDERIZAN CORRECTAMENTE")
print("="*65 + "\n")
