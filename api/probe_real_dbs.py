"""
probe_real_dbs.py - Ejecuta analizar_red() contra las DBs reales del proyecto y muestra resultado.
"""
import sys, os, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import threat_engine

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
threat_engine.NETALERTX_DB = os.path.join(BASE, "netalertx", "data", "db", "app.db")
threat_engine.PIHOLE_DB    = os.path.join(BASE, "pihole", "etc-pihole", "pihole-FTL.db")

print("DBs apuntadas a:")
print(f"  NetAlertX : {threat_engine.NETALERTX_DB}")
print(f"  Pi-hole   : {threat_engine.PIHOLE_DB}")
print(f"  NetAlertX existe: {os.path.exists(threat_engine.NETALERTX_DB)}")
print(f"  Pi-hole   existe: {os.path.exists(threat_engine.PIHOLE_DB)}")
print()

resultado = threat_engine.analizar_red()

print("=== SENTINEL STATUS (datos reales) ===")
print(json.dumps(resultado, indent=2, ensure_ascii=False))
print()
print(f"Total dispositivos: {resultado['total_dispositivos']}")
print(f"Modo: {resultado['mode']}")
print()
for d in resultado["devices"]:
    icon = {"green": "✓ VERDE  ", "yellow": "⚠ AMARILLO", "red": "✗ ROJO   "}.get(d["state"], "?")
    print(f"  {icon}  {d['name']:<30s}  {d['ip']:<17s}  puntos={d['puntuacion']:3d}  reasons={d['reasons']}")
    if d["dga_domains"]:
        print(f"           DGA: {d['dga_domains']}")
    if d["motivos"]:
        for m in d["motivos"]:
            print(f"           - {m}")
