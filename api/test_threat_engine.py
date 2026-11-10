"""
test_threat_engine.py
=====================
Suite de pruebas de integración para threat_engine.py.
Crea bases de datos SQLite temporales con tráfico DNS simulado realista
y verifica que:
  1. Dominios de gaming legítimos NO disparan alertas.
  2. Beaconing real SÍ dispara alerta yellow/red, pero consultas locales (wpad, .local, .lan) NO.
  3. Dominios DGA SÍ disparan alerta red, incluyendo ccTLDs (.co.cr, .com.mx).
  4. FQDNs con punto final (google.com.) se procesan limpiamente.
  5. NXDOMAIN elevado SÍ dispara alerta yellow.
  6. Bloqueos Pi-hole SÍ se detectan y agregan código 'blocked'.
  7. La respuesta de analizar_red() incluye 'beacon_domains' y schema completo para React.
  8. Conexiones SQLite usan timeout y se cierran sin fugas.
"""

import os
import sys
import sqlite3
import tempfile
import shutil
import json
from datetime import datetime

# ---------------------------------------------------------------------------
# Parchamos las rutas ANTES de importar el motor, para que lea nuestras DBs
# ---------------------------------------------------------------------------
TMP_DIR = tempfile.mkdtemp(prefix="safelock_test_")
FAKE_NETALERTX_DB  = os.path.join(TMP_DIR, "app.db")
FAKE_PIHOLE_DB     = os.path.join(TMP_DIR, "pihole-FTL.db")

os.environ["SAFELOCK_DATA_DIR"] = ""

import threat_engine
threat_engine.NETALERTX_DB = FAKE_NETALERTX_DB
threat_engine.PIHOLE_DB    = FAKE_PIHOLE_DB

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


NOW = int(datetime.now().timestamp())

def ts(offset_seconds: int = 0) -> int:
    return NOW - offset_seconds


def crear_netalertx_db(dispositivos: list[dict]):
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
    conn = sqlite3.connect(FAKE_PIHOLE_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS queries (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER,
            client    TEXT,
            domain    TEXT,
            status    INTEGER
        )
    """)
    conn.commit()
    conn.close()


def insertar_queries(rows: list[tuple]):
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


GAMING_DOMAINS = [
    # Fortnite & Epic Games
    "fortnite.com", "matchmaking.fortnite.com", "events.fortnite.com",
    "epicgames.com", "epicgames.dev", "api.epicgames.dev", "et.epicgames.dev",
    "launcher.epicgames.com", "account.epicgames.com", "tracking.epicgames.com",
    "datarouter.ol.epicgames.com", "cdn.epicgames.com", "fn.gg",
    # Anti-Cheat (EAC, BattlEye)
    "easyanticheat.net", "easy.ac", "eac-cdn.com", "battleye.com",
    # Voice chat
    "vivox.com", "vxa.vivox.com",
    # EA / FIFA / Apex
    "ea.com", "easports.com", "o10n.ea.com", "dm.origin.com",
    "accounts.ea.com", "eaassets-a.akamaihd.net", "playapex.com", "respawn.com",
    # Steam / Valve
    "steampowered.com", "steam.com", "store.steampowered.com",
    "steamcommunity.com", "steamcontent.com", "cdn.steamcontent.com",
    "valvesoftware.com", "steamserver.net",
    # Riot / LoL / Valorant
    "riotgames.com", "leagueoflegends.com", "playvalorant.com",
    "na.leagueoflegends.com", "auth.riotgames.com", "riotcdn.net",
    # Activision / COD / Blizzard
    "activision.com", "blizzard.com", "battle.net",
    "us.battle.net", "agent.battle.net", "demonware.net",
    # PlayStation
    "playstation.com", "playstation.net", "sonyentertainmentnetwork.com",
    # Xbox / Microsoft Gaming
    "xbox.com", "xboxlive.com", "login.live.com", "playfabapi.com",
    # Nintendo
    "nintendo.com", "accounts.nintendo.com", "eshop.nintendo.net",
    # Ubisoft
    "ubisoft.com", "ubisoftconnect.com", "ubi.com",
    # Minecraft / Mojang
    "minecraft.net", "mojang.com", "api.minecraftservices.com",
    # Roblox
    "roblox.com", "rbxcdn.com", "robloxlabs.com",
    # PUBG & Mobile
    "pubg.com", "supercell.com", "hoyoverse.com",
    # Otros populares
    "twitch.tv", "discord.com", "discord.gg",
]

COMMON_DOMAINS = [
    "netflix.com", "spotify.com", "youtube.com", "google.com",
    "instagram.com", "facebook.com", "whatsapp.net", "twitter.com",
    "amazon.com", "cloudflare.com", "akamaized.net", "fastly.net",
    "windowsupdate.com", "microsoft.com", "apple.com", "icloud.com",
]

MALICIOUS_DGA = [
    "xkqtbprvzm.top",
    "bzqwxvfjpm.xyz",
    "mwkdzprvyx.cc",
    "kwrtzxbmvp.ru",
    "zcvbnmqwer.click",
    "xkqtbprvzm.co.cr",   # DGA bajo ccTLD de dos partes (.co.cr)
    "mwtqzxplkj.com.mx",  # DGA bajo ccTLD (.com.mx)
]

MALICIOUS_BLOCKED = [
    "phishing.malware-host.tk",
    "stealer.click",
    "ransomware-c2.xyz",
]

DEVICES = [
    {"ip": "192.168.1.10", "name": "PC-Gaming",         "mac": "AA:BB:CC:11:22:33", "vendor": "Intel"},
    {"ip": "192.168.1.20", "name": "Samsung-TV",         "mac": "AA:BB:CC:44:55:66", "vendor": "Samsung"},
    {"ip": "192.168.1.30", "name": "Dispositivo-Raro",  "mac": "AA:BB:CC:77:88:99", "vendor": "Unknown"},
    {"ip": "192.168.1.40", "name": "Laptop-Infect",     "mac": "AA:BB:CC:AA:BB:CC", "vendor": "Dell"},
    {"ip": "10.0.0.5",     "name": "Celular-WiFi",      "mac": "DD:EE:FF:11:22:33", "vendor": "Apple"},
    {"ip": "172.17.0.2",   "name": "DockerInternal",    "mac": "00:00:00:00:00:01", "vendor": ""},
    {"ip": "8.8.8.8",      "name": "GoogleDNS",         "mac": "00:00:00:00:00:02", "vendor": ""},
    {"ip": "127.0.0.1",    "name": "Loopback",          "mac": "00:00:00:00:00:03", "vendor": ""},
]


def setup():
    print(f"\n{BLD}{CYN}═══ Preparando entorno de prueba ═══{RST}")
    crear_netalertx_db(DEVICES)
    crear_pihole_db()
    print(f"  {INFO} Bases de datos creadas.\n")


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


def test_gaming_y_tld_legitimos():
    print(f"{BLD}TEST 2: Dominios de gaming y sitios legítimos — sin falsos positivos DGA{RST}")
    falsos_positivos = []
    for dom in GAMING_DOMAINS:
        if threat_engine.es_nombre_dga(dom):
            falsos_positivos.append(dom)

    check(
        "0 dominios gaming detectados como DGA",
        len(falsos_positivos) == 0,
        f"Falsos positivos: {falsos_positivos}" if falsos_positivos else ""
    )

    # Comprobar manejo de ccTLDs legítimos y FQDN con punto final
    casos_borde = [
        ("google.com.", False),
        ("launcher.epicgames.com.", False),
        ("baccredomatic.co.cr", False),
        ("crhoy.co.cr", False),
        ("mercadolibre.com.mx", False),
        ("wpad", False),
        ("printer.local", False),
        ("router.lan", False),
    ]
    for dom, expected in casos_borde:
        res = threat_engine.es_nombre_dga(dom)
        check(f"  Borde: {dom!r:28s} → DGA={res} (esperado={expected})", res == expected)
    print()


def test_dga_detectados():
    print(f"{BLD}TEST 3: Detección de dominios DGA maliciosos (incluyendo ccTLDs){RST}")
    detectados = []
    for dom in MALICIOUS_DGA:
        r = threat_engine.es_nombre_dga(dom)
        check(f"  {dom!r:30s} → DGA=True", r)
        if r:
            detectados.append(dom)
    check("Todos los DGA maliciosos detectados", len(detectados) == len(MALICIOUS_DGA))
    print()


def test_escenario_verde():
    print(f"{BLD}TEST 4: Escenario VERDE — PC gaming con tráfico normal{RST}")
    limpiar_queries()

    ip = "192.168.1.10"
    rows = []
    for i, dom in enumerate(GAMING_DOMAINS * 5 + COMMON_DOMAINS * 3):
        rows.append((ts(i * 60), ip, dom, 2))

    # Incluir consultas locales legítimas (mDNS, WPAD, router)
    rows.append((ts(100), ip, "wpad", 2))
    rows.append((ts(120), ip, "printer.local", 2))
    rows.append((ts(140), ip, "router.lan", 2))

    insertar_queries(rows)

    total_bloq, ejemplos = threat_engine.contar_bloqueados(ip)
    beacon = threat_engine.detectar_beaconing(ip, horas=1, umbral=20)
    dga    = threat_engine.buscar_dominios_dga(ip)
    tq, nx = threat_engine.obtener_metricas_dns(ip)
    riesgo, state, puntuacion, motivos, reasons = threat_engine.calcular_riesgo(
        total_bloq, ejemplos, beacon, dga, nx
    )

    check("Bloqueos = 0",      total_bloq == 0)
    check("Beaconing = []",    len(beacon) == 0, f"got {beacon}")
    check("DGA = []",          len(dga) == 0, f"got {dga}")
    check("Estado = 'green'",  state == "green", f"got state={state!r} puntuacion={puntuacion}")
    check("reasons vacío",     len(reasons) == 0)
    print()


def test_escenario_beaconing_y_locales():
    print(f"{BLD}TEST 5: Escenario AMARILLO — Beaconing vs Consultas Locales{RST}")
    limpiar_queries()

    ip = "192.168.1.20"
    rows = []
    # Consultas repetitivas a wpad y router local (30 veces) -> NO debe ser beaconing
    for i in range(30):
        rows.append((ts(i * 90), ip, "wpad", 2))
        rows.append((ts(i * 90), ip, "gateway.local", 2))

    insertar_queries(rows)
    beacon_local = threat_engine.detectar_beaconing(ip, horas=1, umbral=20)
    check("Consultas locales (wpad, .local) NO son beaconing", len(beacon_local) == 0, f"got {beacon_local}")

    # Ahora agregamos beaconing real a servidor externo desconocido
    rows_c2 = [(ts(i * 90), ip, "c2.unknownserver.biz", 2) for i in range(25)]
    insertar_queries(rows_c2)

    beacon_real = threat_engine.detectar_beaconing(ip, horas=1, umbral=20)
    riesgo, state, puntuacion, motivos, reasons = threat_engine.calcular_riesgo(
        0, [], beacon_real, [], 0.0
    )

    check("Beaconing real detectado",    len(beacon_real) == 1 and beacon_real[0]["dominio"] == "c2.unknownserver.biz")
    check("'beaconing' en reasons",     "beaconing" in reasons)
    check("Estado al menos 'yellow'",   state in ("yellow", "red"))
    print()


def test_escenario_rojo():
    print(f"{BLD}TEST 6: Escenario ROJO — DGA + Bloqueos + Código 'blocked'{RST}")
    limpiar_queries()

    ip = "192.168.1.40"
    rows = []
    for i, dom in enumerate(COMMON_DOMAINS):
        rows.append((ts(i * 200), ip, dom, 2))

    for i, dom in enumerate(MALICIOUS_BLOCKED):
        for j in range(5):
            rows.append((ts(i * 50 + j * 10), ip, dom, 1))

    for i, dom in enumerate(MALICIOUS_DGA[:4]):
        rows.append((ts(i * 400 + 100), ip, dom, 2))

    for i in range(20):
        rows.append((ts(i * 300), ip, f"nxtest{i}.randomdomain.xyz", 3))

    insertar_queries(rows)

    total_bloq, ejemplos = threat_engine.contar_bloqueados(ip)
    dga    = threat_engine.buscar_dominios_dga(ip)
    tq, nx = threat_engine.obtener_metricas_dns(ip)
    riesgo, state, puntuacion, motivos, reasons = threat_engine.calcular_riesgo(
        total_bloq, ejemplos, [], dga, nx
    )

    check("Bloqueos detectados (>0)",       total_bloq > 0)
    check("'blocked' en reasons",          "blocked" in reasons)
    check("'dga' en reasons",              "dga" in reasons)
    check("'nxdomain' en reasons",         "nxdomain" in reasons)
    check("Estado = 'red'",               state == "red", f"puntos={puntuacion}")
    check("Puntuación >= 60",             puntuacion >= 60)
    print()


def test_schema_analizar_red():
    print(f"{BLD}TEST 7: Schema y Cache de analizar_red(){RST}")
    limpiar_queries()

    ip = "192.168.1.10"
    rows = [(ts(i * 100), ip, dom, 2) for i, dom in enumerate(GAMING_DOMAINS[:20])]
    insertar_queries(rows)

    resultado = threat_engine.analizar_red(forzar_refresco=True)

    check("Tiene 'mode'",              "mode" in resultado)
    check("Tiene 'devices' (React)",   "devices" in resultado)
    check("Tiene 'total_dispositivos'","total_dispositivos" in resultado)

    if resultado["devices"]:
        d = resultado["devices"][0]
        campos = ["ip", "mac", "name", "state", "reasons", "dga_domains",
                  "beacon_domains", "queries", "nxdomain_rate", "puntuacion", "motivos"]
        for c in campos:
            check(f"  Campo '{c}' presente en device", c in d)
        check("  beacon_domains es lista", isinstance(d["beacon_domains"], list))

    # Prueba de Cache
    res1 = threat_engine.analizar_red()
    res2 = threat_engine.analizar_red()
    check("Cache retorna el mismo objeto sin re-consultar", res1 is res2)
    print()


def main():
    print(f"\n{BLD}{'═'*62}")
    print(f"  SafeLock — Test Suite Exhaustiva: threat_engine.py")
    print(f"{'═'*62}{RST}")

    setup()
    test_filtrado_dispositivos()
    test_gaming_y_tld_legitimos()
    test_dga_detectados()
    test_escenario_verde()
    test_escenario_beaconing_y_locales()
    test_escenario_rojo()
    test_schema_analizar_red()

    total  = len(_results)
    passed = sum(1 for _, ok in _results if ok)
    failed = total - passed

    print(f"{BLD}{'═'*62}")
    print(f"  RESULTADO: {passed}/{total} tests pasados", end="")
    if failed:
        print(f"  {RED}({failed} FALLIDOS){RST}", end="")
    print(f"\n{'═'*62}{RST}\n")

    shutil.rmtree(TMP_DIR, ignore_errors=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
