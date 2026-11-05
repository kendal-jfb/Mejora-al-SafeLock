"""
test_threat_engine.py
=====================
Suite de pruebas de integración para threat_engine.py.
Crea bases de datos SQLite temporales con tráfico DNS simulado realista
y verifica que:
  1. Dominios de gaming legítimos NO disparan alertas.
  2. Beaconing real SÍ dispara alerta yellow/red.
  3. Dominios DGA SÍ disparan alerta red.
  4. NXDOMAIN elevado SÍ dispara alerta yellow.
  5. Bloqueos Pi-hole SÍ se detectan.
  6. La respuesta de analizar_red() tiene el schema exacto que espera React.
"""

import os
import sys
import sqlite3
import tempfile
import shutil
import json
import time
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Parchamos las rutas ANTES de importar el motor, para que lea nuestras DBs
# ---------------------------------------------------------------------------
TMP_DIR = tempfile.mkdtemp(prefix="safelock_test_")
FAKE_NETALERTX_DB  = os.path.join(TMP_DIR, "app.db")
FAKE_PIHOLE_DB     = os.path.join(TMP_DIR, "pihole-FTL.db")
FAKE_GRAVITY_DB    = os.path.join(TMP_DIR, "gravity.db")

os.environ["SAFELOCK_DATA_DIR"] = ""  # forzar resolución por BASE_DIR → lo sobreescribimos abajo

# Importamos el módulo y le sobreescribimos las constantes de ruta
import threat_engine
threat_engine.NETALERTX_DB = FAKE_NETALERTX_DB
threat_engine.PIHOLE_DB    = FAKE_PIHOLE_DB


# ==============================================================================
# Colores para terminal
# ==============================================================================
GRN  = "\033[92m"
YLW  = "\033[93m"
RED  = "\033[91m"
CYN  = "\033[96m"
BLD  = "\033[1m"
RST  = "\033[0m"

PASS = f"{GRN}✓ PASS{RST}"
FAIL = f"{RED}✗ FAIL{RST}"
INFO = f"{CYN}ℹ{RST}"

_results = []

def check(name: str, condition: bool, detail: str = ""):
    tag = PASS if condition else FAIL
    suffix = f"  {detail}" if detail else ""
    print(f"  {tag}  {name}{suffix}")
    _results.append((name, condition))


# ==============================================================================
# Helpers para construir las DBs de prueba
# ==============================================================================
NOW = int(datetime.now().timestamp())

def ts(offset_seconds: int = 0) -> int:
    return NOW - offset_seconds


def crear_netalertx_db(dispositivos: list[dict]):
    """
    Crea una DB mínima de NetAlertX con los dispositivos dados.
    dispositivos = [{"ip":..., "name":..., "mac":..., "vendor":...}, ...]
    """
    conn = sqlite3.connect(FAKE_NETALERTX_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS Devices (
            devLastIP TEXT,
            devName   TEXT,
            devMac    TEXT,
            devVendor TEXT,
            devIsArchived INTEGER DEFAULT 0,
            devLastConnection TEXT
        )
    """)
    conn.executemany(
        "INSERT INTO Devices VALUES (?, ?, ?, ?, 0, datetime('now'))",
        [(d["ip"], d["name"], d["mac"], d["vendor"]) for d in dispositivos]
    )
    conn.commit()
    conn.close()


def crear_pihole_db():
    """Crea el schema mínimo de pihole-FTL.db."""
    conn = sqlite3.connect(FAKE_PIHOLE_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS queries (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER,
            client    TEXT,
            domain    TEXT,
            status    INTEGER   -- 2=ok, 3=NXDOMAIN, 1/4/5/9/10/11=blocked
        )
    """)
    conn.commit()
    conn.close()


def insertar_queries(rows: list[tuple]):
    """rows = [(timestamp, client_ip, domain, status), ...]"""
    conn = sqlite3.connect(FAKE_PIHOLE_DB)
    conn.executemany(
        "INSERT INTO queries (timestamp, client, domain, status) VALUES (?, ?, ?, ?)",
        rows
    )
    conn.commit()
    conn.close()


def limpiar_queries():
    conn = sqlite3.connect(FAKE_PIHOLE_DB)
    conn.execute("DELETE FROM queries")
    conn.commit()
    conn.close()


# ==============================================================================
# Bloque de dominios de gaming y servicios populares a probar
# ==============================================================================
GAMING_DOMAINS = [
    # Epic Games
    "epicgames.com", "epicgames-dns.com", "cdn.epicgames.com",
    "launcher.epicgames.com", "account.epicgames.com",
    # EA / FIFA
    "ea.com", "easports.com", "o10n.ea.com", "dm.origin.com",
    "accounts.ea.com", "eaassets-a.akamaihd.net",
    # Steam / Valve
    "steampowered.com", "steam.com", "store.steampowered.com",
    "steamcommunity.com", "steamcontent.com", "cdn.steamcontent.com",
    # Riot / LoL / Valorant
    "riotgames.com", "leagueoflegends.com", "playvalorant.com",
    "na.leagueoflegends.com", "auth.riotgames.com",
    # Activision / COD / Blizzard
    "activision.com", "blizzard.com", "battle.net",
    "us.battle.net", "agent.battle.net",
    # PlayStation
    "playstation.com", "playstation.net", "sonyentertainmentnetwork.com",
    "dualshockers.com",
    # Xbox / Microsoft Gaming
    "xbox.com", "xboxlive.com", "login.live.com",
    # Nintendo
    "nintendo.com", "accounts.nintendo.com", "eshop.nintendo.net",
    # Ubisoft
    "ubisoft.com", "ubisoftconnect.com", "ubi.com",
    # Minecraft / Mojang
    "minecraft.net", "mojang.com", "api.minecraftservices.com",
    # Roblox
    "roblox.com", "rbxcdn.com", "robloxlabs.com",
    # Otros populares
    "twitch.tv", "discord.com", "discord.gg",
]

# Dominios de servicios comunes del hogar
COMMON_DOMAINS = [
    "netflix.com", "spotify.com", "youtube.com", "google.com",
    "instagram.com", "facebook.com", "whatsapp.net", "twitter.com",
    "amazon.com", "cloudflare.com", "akamaized.net", "fastly.net",
    "windowsupdate.com", "microsoft.com", "apple.com", "icloud.com",
]

# Dominios maliciosos / DGA reales
MALICIOUS_DGA = [
    "xkqtbprvzm.top",        # DGA puro: consonantes > 70%, TLD sospechoso
    "bzqwxvfjpm.xyz",        # DGA puro
    "mwkdzprvyx.cc",         # DGA + TLD sospechoso
    "kwrtzxbmvp.ru",         # DGA + TLD sospechoso
    "zcvbnmqwer.click",      # DGA
]

MALICIOUS_BLOCKED = [
    "phishing.malware-host.tk",
    "stealer.click",
    "ransomware-c2.xyz",
]


# ==============================================================================
# DISPOSITIVOS DE PRUEBA
# ==============================================================================
DEVICES = [
    {"ip": "192.168.1.10", "name": "PC-Gaming",         "mac": "AA:BB:CC:11:22:33", "vendor": "Intel"},
    {"ip": "192.168.1.20", "name": "Samsung-TV",         "mac": "AA:BB:CC:44:55:66", "vendor": "Samsung"},
    {"ip": "192.168.1.30", "name": "Dispositivo-Raro",  "mac": "AA:BB:CC:77:88:99", "vendor": "Unknown"},
    {"ip": "192.168.1.40", "name": "Laptop-Infect",     "mac": "AA:BB:CC:AA:BB:CC", "vendor": "Dell"},
    {"ip": "10.0.0.5",     "name": "Celular-WiFi",      "mac": "DD:EE:FF:11:22:33", "vendor": "Apple"},
    # IPs que NO deberían aparecer (Docker, pública, loopback)
    {"ip": "172.17.0.2",   "name": "DockerInternal",    "mac": "00:00:00:00:00:01", "vendor": ""},
    {"ip": "8.8.8.8",      "name": "GoogleDNS",         "mac": "00:00:00:00:00:02", "vendor": ""},
    {"ip": "127.0.0.1",    "name": "Loopback",          "mac": "00:00:00:00:00:03", "vendor": ""},
]


# ==============================================================================
# CONSTRUIR DBs
# ==============================================================================
def setup():
    print(f"\n{BLD}{CYN}═══ Preparando entorno de prueba ═══{RST}")
    print(f"  {INFO} Directorio temporal: {TMP_DIR}")
    crear_netalertx_db(DEVICES)
    crear_pihole_db()
    print(f"  {INFO} Bases de datos creadas.\n")


# ==============================================================================
# TEST 1: Dispositivos LAN correctamente filtrados
# ==============================================================================
def test_filtrado_dispositivos():
    print(f"{BLD}TEST 1: Filtrado de IPs LAN{RST}")
    dispositivos = threat_engine.obtener_dispositivos()
    ips = {d["ip"] for d in dispositivos}

    check("PC-Gaming (192.168.1.x) incluido",   "192.168.1.10" in ips)
    check("Celular (10.0.x.x) incluido",        "10.0.0.5" in ips)
    check("Docker (172.17.x.x) EXCLUIDO",       "172.17.0.2" not in ips)
    check("IP pública (8.8.8.8) EXCLUIDA",      "8.8.8.8" not in ips)
    check("Loopback (127.0.0.1) EXCLUIDO",      "127.0.0.1" not in ips)
    print()


# ==============================================================================
# TEST 2: Dominios de Gaming - NO deben disparar DGA falso positivo
# ==============================================================================
def test_gaming_no_dga():
    print(f"{BLD}TEST 2: Dominios de gaming — sin falsos positivos DGA{RST}")
    falsos_positivos = []
    for dom in GAMING_DOMAINS:
        if threat_engine.es_nombre_dga(dom):
            falsos_positivos.append(dom)

    check(
        f"0 dominios gaming detectados como DGA",
        len(falsos_positivos) == 0,
        f"Falsos positivos detectados: {falsos_positivos}" if falsos_positivos else ""
    )

    # Comprobar algunos individualmente para transparencia
    dominios_clave = {
        "epicgames.com": False,
        "easports.com":  False,
        "steampowered.com": False,
        "riotgames.com": False,
        "battle.net":    False,
        "xbox.com":      False,
        "minecraft.net": False,
        "roblox.com":    False,
        "twitch.tv":     False,
        "discord.com":   False,
    }
    for dom, expected in dominios_clave.items():
        result = threat_engine.es_nombre_dga(dom)
        check(f"  {dom!r:35s} → DGA={result}  (esperado={expected})", result == expected)
    print()


# ==============================================================================
# TEST 3: Dominios DGA maliciosos SÍ deben detectarse
# ==============================================================================
def test_dga_detectados():
    print(f"{BLD}TEST 3: Detección de dominios DGA maliciosos{RST}")
    detectados = []
    for dom in MALICIOUS_DGA:
        r = threat_engine.es_nombre_dga(dom)
        check(f"  {dom!r:40s} → DGA=True", r, "" if r else f"NO detectado ← revisar heurística")
        if r:
            detectados.append(dom)
    check(f"Al menos 3/5 DGA detectados correctamente", len(detectados) >= 3)
    print()


# ==============================================================================
# TEST 4: Escenario VERDE — PC de gaming con tráfico normal
# ==============================================================================
def test_escenario_verde():
    print(f"{BLD}TEST 4: Escenario VERDE — PC gaming con tráfico normal{RST}")
    limpiar_queries()

    ip = "192.168.1.10"
    rows = []
    # Simular ~200 consultas normales de gaming en 24h
    for i, dom in enumerate(GAMING_DOMAINS * 5 + COMMON_DOMAINS * 3):
        rows.append((ts(i * 60), ip, dom, 2))  # status 2 = OK

    insertar_queries(rows)

    total_bloq, ejemplos = threat_engine.contar_bloqueados(ip)
    beacon = threat_engine.detectar_beaconing(ip, horas=1, umbral=20)
    dga    = threat_engine.buscar_dominios_dga(ip)
    tq, nx = threat_engine.obtener_metricas_dns(ip)
    riesgo, state, puntuacion, motivos, reasons = threat_engine.calcular_riesgo(
        total_bloq, ejemplos, beacon, dga, nx
    )

    check("Bloqueos = 0",      total_bloq == 0, f"got {total_bloq}")
    check("Beaconing = []",    len(beacon) == 0, f"got {beacon}")
    check("DGA = []",          len(dga) == 0, f"got {dga}")
    check("Estado = 'green'",  state == "green", f"got state={state!r} puntuacion={puntuacion}")
    check("reasons vacío",     len(reasons) == 0, f"got {reasons}")
    check(f"Total queries detectadas (>0)", tq > 0, f"got {tq}")
    print()


# ==============================================================================
# TEST 5: Escenario AMARILLO — Beaconing (conexiones repetitivas)
# ==============================================================================
def test_escenario_beaconing():
    print(f"{BLD}TEST 5: Escenario AMARILLO — Beaconing sospechoso{RST}")
    limpiar_queries()

    ip = "192.168.1.20"
    rows = []
    # Dominio normal de gaming
    for i in range(10):
        rows.append((ts(3600 - i * 300), ip, "netflix.com", 2))

    # Beaconing: 30 veces al mismo dominio externo desconocido en 1 hora
    for i in range(30):
        rows.append((ts(i * 90), ip, "c2.unknownserver.biz", 2))  # cada 90s

    insertar_queries(rows)

    beacon = threat_engine.detectar_beaconing(ip, horas=1, umbral=20)
    riesgo, state, puntuacion, motivos, reasons = threat_engine.calcular_riesgo(
        0, [], beacon, [], 0.0
    )

    check("Beaconing detectado",        len(beacon) > 0, f"dominios: {[b['dominio'] for b in beacon]}")
    check("'beaconing' en reasons",     "beaconing" in reasons)
    check("Estado al menos 'yellow'",   state in ("yellow", "red"), f"got {state!r}")
    check("Puntuación >= 21",           puntuacion >= 21, f"got {puntuacion}")
    print()


# ==============================================================================
# TEST 6: Escenario ROJO — DGA + Bloqueos Pi-hole
# ==============================================================================
def test_escenario_rojo():
    print(f"{BLD}TEST 6: Escenario ROJO — DGA + Bloqueos en Pi-hole{RST}")
    limpiar_queries()

    ip = "192.168.1.40"
    rows = []
    # Consultas normales
    for i, dom in enumerate(COMMON_DOMAINS):
        rows.append((ts(i * 200), ip, dom, 2))

    # Bloqueos Pi-hole (status 1 = blocked by gravity)
    for i, dom in enumerate(MALICIOUS_BLOCKED):
        for j in range(5):
            rows.append((ts(i * 50 + j * 10), ip, dom, 1))  # 15 bloqueos total

    # Dominios DGA en últimas 24h
    for i, dom in enumerate(MALICIOUS_DGA):
        rows.append((ts(i * 400 + 100), ip, dom, 2))

    # NXDOMAIN elevado (40%)
    for i in range(20):
        rows.append((ts(i * 300), ip, f"nxtest{i}.randomdomain.xyz", 3))

    insertar_queries(rows)

    total_bloq, ejemplos = threat_engine.contar_bloqueados(ip)
    dga    = threat_engine.buscar_dominios_dga(ip)
    tq, nx = threat_engine.obtener_metricas_dns(ip)
    riesgo, state, puntuacion, motivos, reasons = threat_engine.calcular_riesgo(
        total_bloq, ejemplos, [], dga, nx
    )

    check("Bloqueos detectados (>0)",       total_bloq > 0, f"got {total_bloq}")
    check("DGA detectados (>0)",            len(dga) > 0, f"got {dga}")
    check("NXDOMAIN >= 35%",               nx >= 0.35, f"got nxdomain_rate={nx:.2f}")
    check("'dga' en reasons",              "dga" in reasons)
    check("'nxdomain' en reasons",         "nxdomain" in reasons)
    check("Estado = 'red'",               state == "red", f"got state={state!r} puntuacion={puntuacion}")
    check("Puntuación >= 60",             puntuacion >= 60, f"got {puntuacion}")
    check("motivos no vacíos",            len(motivos) > 0)
    print()


# ==============================================================================
# TEST 7: Schema completo de analizar_red() compatible con React
# ==============================================================================
def test_schema_analizar_red():
    print(f"{BLD}TEST 7: Schema de analizar_red() — compatibilidad con React{RST}")

    # Preparar datos variados para todos los dispositivos LAN
    limpiar_queries()
    for ip in ["192.168.1.10", "192.168.1.20", "192.168.1.30", "192.168.1.40", "10.0.0.5"]:
        rows = [(ts(i * 100), ip, dom, 2) for i, dom in enumerate(GAMING_DOMAINS[:20])]
        insertar_queries(rows)

    resultado = threat_engine.analizar_red()

    # Campos de primer nivel
    check("Tiene 'mode'",              "mode" in resultado)
    check("Tiene 'last_run'",          "last_run" in resultado)
    check("Tiene 'devices' (React)",   "devices" in resultado)
    check("Tiene 'dispositivos'",      "dispositivos" in resultado)
    check("Tiene 'total_dispositivos'","total_dispositivos" in resultado)

    # Verificar que las IPs Docker/pública no estén en devices
    ips_en_respuesta = {d["ip"] for d in resultado["devices"]}
    check("Docker IPs AUSENTES en devices", "172.17.0.2" not in ips_en_respuesta)
    check("IP pública AUSENTE en devices",  "8.8.8.8" not in ips_en_respuesta)

    # Verificar campos por dispositivo
    if resultado["devices"]:
        d = resultado["devices"][0]
        campos_requeridos = ["ip", "mac", "name", "state", "reasons", "dga_domains",
                             "queries", "nxdomain_rate", "nombre", "riesgo", "puntuacion", "motivos"]
        for campo in campos_requeridos:
            check(f"  Campo '{campo}' presente en device", campo in d)

        check("  'state' en valores válidos",
              d["state"] in ("green", "yellow", "red"),
              f"got {d['state']!r}")
        check("  'reasons' es lista",   isinstance(d["reasons"], list))
        check("  'dga_domains' es lista", isinstance(d["dga_domains"], list))
        check("  'queries' es int",    isinstance(d["queries"], int))

    print()


# ==============================================================================
# TEST 8: Resumen con datos mixtos — simula red real completa
# ==============================================================================
def test_red_completa():
    print(f"{BLD}TEST 8: Simulación de red completa — resumen final{RST}")

    limpiar_queries()

    # PC Gaming: tráfico 100% normal
    ip_ok = "192.168.1.10"
    rows_ok = [(ts(i * 60), ip_ok, dom, 2)
               for i, dom in enumerate(GAMING_DOMAINS * 3 + COMMON_DOMAINS)]
    insertar_queries(rows_ok)

    # Laptop infectada: DGA + bloqueos + beaconing
    ip_bad = "192.168.1.40"
    rows_bad = []
    for i in range(25):
        rows_bad.append((ts(i * 60), ip_bad, "malware-c2.xyz", 2))  # beaconing
    for dom in MALICIOUS_DGA:
        rows_bad.append((ts(500), ip_bad, dom, 2))
    for dom in MALICIOUS_BLOCKED:
        rows_bad.append((ts(600), ip_bad, dom, 1))
    insertar_queries(rows_bad)

    resultado = threat_engine.analizar_red()
    devices_map = {d["ip"]: d for d in resultado["devices"]}

    if ip_ok in devices_map:
        d_ok = devices_map[ip_ok]
        check("PC Gaming → state='green'", d_ok["state"] == "green",
              f"got state={d_ok['state']!r}, reasons={d_ok['reasons']}, dga={d_ok['dga_domains']}")
    else:
        check("PC Gaming presente en resultado", False, "No encontrado en devices")

    if ip_bad in devices_map:
        d_bad = devices_map[ip_bad]
        check("Laptop infectada → state='red'",
              d_bad["state"] == "red",
              f"got state={d_bad['state']!r}, puntuacion={d_bad['puntuacion']}")
        check("Laptop infectada → reasons no vacío", len(d_bad["reasons"]) > 0, f"{d_bad['reasons']}")
    else:
        check("Laptop infectada presente en resultado", False, "No encontrado en devices")

    print()
    print(f"  {INFO} JSON completo del resultado (extracto):")
    extracto = {
        "mode": resultado["mode"],
        "total_dispositivos": resultado["total_dispositivos"],
        "devices": [
            {k: v for k, v in d.items() if k not in ("motivos",)}
            for d in resultado["devices"]
            if d["ip"] in (ip_ok, ip_bad)
        ]
    }
    print(json.dumps(extracto, indent=4, ensure_ascii=False))
    print()


# ==============================================================================
# EJECUCIÓN
# ==============================================================================
def main():
    print(f"\n{BLD}{'═'*62}")
    print(f"  SafeLock — Test Suite: threat_engine.py")
    print(f"{'═'*62}{RST}")

    setup()
    test_filtrado_dispositivos()
    test_gaming_no_dga()
    test_dga_detectados()
    test_escenario_verde()
    test_escenario_beaconing()
    test_escenario_rojo()
    test_schema_analizar_red()
    test_red_completa()

    # Resumen
    total  = len(_results)
    passed = sum(1 for _, ok in _results if ok)
    failed = total - passed

    print(f"{BLD}{'═'*62}")
    print(f"  RESULTADO: {passed}/{total} tests pasados", end="")
    if failed:
        print(f"  {RED}({failed} FALLIDOS){RST}", end="")
    print(f"\n{'═'*62}{RST}\n")

    # Limpiar tmp
    shutil.rmtree(TMP_DIR, ignore_errors=True)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
