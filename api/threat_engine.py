"""
threat_engine.py
================
Motor de Detección de Amenazas ("El Cerebro") para SafeLock.

Responsabilidades (Persona 1):
1. Analizar el inventario de dispositivos (NetAlertX).
2. Inspeccionar el historial de navegación DNS (Pi-hole) por dispositivo.
3. Identificar 3 señales de alerta:
   - Consultas bloqueadas por listas negras.
   - Beaconing (conexiones periódicas insistentes a dominios externos).
   - Nombres generados al azar (DGA - Domain Generation Algorithm).
4. Calcular el nivel de riesgo: 'green'/'normal', 'yellow'/'sospechoso', 'red'/'peligro'.
5. Exportar la función principal `analizar_red()` compatible al 100% con
   la interfaz de Persona 3 (React) y la API de Persona 2 (FastAPI).
"""

import os
import sqlite3
import json
import time
from datetime import datetime, timedelta

# ==============================================================================
# CONFIGURACIÓN Y RUTAS DE BASES DE DATOS
# ==============================================================================
DATA_DIR = os.environ.get("SAFELOCK_DATA_DIR", "")
if DATA_DIR and os.path.exists(DATA_DIR):
    NETALERTX_DB = os.path.join(DATA_DIR, "netalertx", "data", "db", "app.db")
    PIHOLE_DB = os.path.join(DATA_DIR, "pihole", "etc-pihole", "pihole-FTL.db")
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    NETALERTX_DB = os.path.join(BASE_DIR, "netalertx", "data", "db", "app.db")
    PIHOLE_DB = os.path.join(BASE_DIR, "pihole", "etc-pihole", "pihole-FTL.db")


def _conectar_sqlite(ruta_db: str, solo_lectura: bool = True):
    """
    Abre una conexión segura a SQLite.
    Usa timeout de 10s y modo solo lectura (URI) para no generar contención
    ni bloqueos contra procesos concurrentes (Pi-hole FTL / NetAlertX).
    """
    if not ruta_db or not os.path.exists(ruta_db):
        return None
    try:
        if solo_lectura:
            uri = f"file:{os.path.abspath(ruta_db)}?mode=ro"
            return sqlite3.connect(uri, uri=True, timeout=10.0)
        return sqlite3.connect(ruta_db, timeout=10.0)
    except Exception as e:
        print(f"[threat_engine] Error al conectar a {ruta_db}: {e}")
        return None


# Dominios de segundo nivel comunes para ccTLDs (.co.cr, .com.mx, .co.uk, etc.)
CCTLD_SEGUNDO_NIVEL = {"com", "co", "net", "org", "edu", "gov", "gob", "fi", "ed", "mil"}

# Sufijos de red local a ignorar en análisis de amenazas externas
SUFIJOS_LOCALES = (
    ".arpa", ".local", ".lan", ".localdomain", ".internal",
    ".home", ".corp", ".test", "localhost", "pi.hole"
)

WHITELIST_DOMINIOS = {
    # Google / Alphabet
    "google.com", "gstatic.com", "googleapis.com", "youtube.com",
    "googlevideo.com", "ggpht.com", "googleusercontent.com",
    # Microsoft / Windows
    "microsoft.com", "windows.com", "live.com", "msftncsi.com",
    "windowsupdate.com", "microsoftonline.com", "office.com",
    "office365.com", "sharepoint.com", "outlook.com", "hotmail.com",
    "skype.com", "xbox.com", "xboxlive.com", "azureedge.net",
    # Apple
    "apple.com", "icloud.com", "aaplimg.com", "mzstatic.com",
    # Amazon / AWS / CDN
    "amazon.com", "amazonaws.com", "aws.amazon.com",
    "cloudfront.net", "akamaized.net", "akamai.net",
    "fastly.net", "fastlylb.net", "edgecastcdn.net",
    # Cloudflare / Infra
    "cloudflare.com", "cloudflare-dns.com", "1dot1dot1dot1.cloudflare-dns.com",
    # Tailscale / DevTools
    "tailscale.com", "github.com", "ntp.org", "pool.ntp.org",
    # Redes sociales / Comunicación
    "facebook.com", "fbcdn.net", "instagram.com", "whatsapp.com",
    "whatsapp.net", "twitter.com", "x.com", "twimg.com",
    "discord.com", "discordapp.com", "discord.gg",
    "telegram.org", "t.me", "tiktok.com", "tiktokcdn.com",
    "snapchat.com", "linkedin.com",
    # Streaming / Entretenimiento
    "netflix.com", "nflximg.net", "nflxvideo.net",
    "spotify.com", "spotifycdn.com", "scdn.co",
    "twitch.tv", "twitchsvc.net", "jtvnw.net",
    "youtube.com", "youtu.be",
    "hulu.com", "disneyplus.com", "max.com",
    # Gaming — Epic Games
    "epicgames.com", "epicgames-dns.com", "unrealengine.com",
    # Gaming — EA / FIFA / Origin
    "ea.com", "easports.com", "origin.com", "eaassets-a.akamaihd.net",
    # Gaming — Steam / Valve
    "steampowered.com", "steam.com", "steamcommunity.com",
    "steamcontent.com", "steamstatic.com", "steamstore-a.akamaihd.net",
    # Gaming — Riot / LoL / Valorant
    "riotgames.com", "leagueoflegends.com", "playvalorant.com",
    "riotgames.net", "rgpub.io",
    # Gaming — Activision / Blizzard / COD
    "activision.com", "blizzard.com", "battle.net",
    # Gaming — PlayStation / Sony
    "playstation.com", "playstation.net", "sonyentertainmentnetwork.com",
    "dualshockers.com", "dl.playstation.net",
    # Gaming — Ubisoft
    "ubisoft.com", "ubisoftconnect.com", "ubi.com",
    # Gaming — Nintendo
    "nintendo.com", "nintendo.net", "nintendolife.com",
    # Gaming — Minecraft / Mojang / Microsoft Gaming
    "minecraft.net", "mojang.com", "minecraftservices.com",
    "xboxlive.com",
    # Gaming — Roblox
    "roblox.com", "rbxcdn.com", "robloxlabs.com",
    # IoT / Smart TV / Dispositivos del hogar
    "samsung.com", "samsungelectronics.com",
    "lg.com", "lgelectronics.com",
    "roku.com", "sonos.com", "philips.com",
    # Otros CDNs y servicios comunes
    "doubleclick.net", "googlesyndication.com",
    "licdn.com", "pinimg.com",
    "dropbox.com", "dropboxstatic.com",
    "zoom.us", "zoomgov.com",
    "slack.com", "slack-msgs.com",
}

EXTENSIONES_SOSPECHOSAS = {
    ".xyz", ".top", ".ru", ".tk", ".click", ".buzz",
    ".work", ".icu", ".cc", ".cn", ".biz"
}


# ==============================================================================
# PASO 1: LECTURA DE DISPOSITIVOS (NetAlertX)
# ==============================================================================

# Prefijos de red LAN válidos para el SafeLock (clientes reales).
# Se excluyen:
#   - 172.16.x.x – 172.31.x.x : redes internas de Docker Compose
#   - IPs públicas              : registros fantasma de NetAlertX ("internet")
#   - 127.x.x.x / ::1          : loopback
_PREFIJOS_LAN_VALIDOS = (
    "10.",
    "192.168.",
    "100.64.", "100.65.", "100.66.", "100.67.", "100.68.", "100.69.",
    "100.70.", "100.71.", "100.72.", "100.73.", "100.74.", "100.75.",
    "100.76.", "100.77.", "100.78.", "100.79.", "100.80.", "100.81.",
    "100.82.", "100.83.", "100.84.", "100.85.", "100.86.", "100.87.",
    "100.88.", "100.89.", "100.90.", "100.91.", "100.92.", "100.93.",
    "100.94.", "100.95.", "100.96.", "100.97.", "100.98.", "100.99.",
    "100.100.", "100.101.", "100.102.", "100.103.", "100.104.", "100.105.",
    "100.106.", "100.107.", "100.108.", "100.109.", "100.110.", "100.111.",
    "100.112.", "100.113.", "100.114.", "100.115.", "100.116.", "100.117.",
    "100.118.", "100.119.", "100.120.", "100.121.", "100.122.", "100.123.",
    "100.124.", "100.125.", "100.126.", "100.127.",  # rango Tailscale CGNAT
)

def _es_ip_lan(ip: str) -> bool:
    """Devuelve True solo si la IP corresponde a un dispositivo de red local real."""
    return any(ip.startswith(p) for p in _PREFIJOS_LAN_VALIDOS)


def obtener_dispositivos():
    """
    Obtiene la lista de dispositivos LAN registrados y activos desde NetAlertX.
    Excluye IPs públicas, contenedores Docker internos (172.x) y loopback.
    Deduplica por IP para evitar dispositivos repetidos en el análisis.
    """
    conn = _conectar_sqlite(NETALERTX_DB, solo_lectura=True)
    if not conn:
        return []

    dispositivos = []
    ips_vistas = set()

    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        consulta = """
            SELECT devLastIP, devName, devMac, devVendor
            FROM Devices
            WHERE devIsArchived = 0
              AND devLastIP IS NOT NULL
              AND devLastIP != ''
            ORDER BY devLastConnection DESC
        """
        filas = cursor.execute(consulta).fetchall()

        for fila in filas:
            ip = fila["devLastIP"]

            # Descartar IPs que no son de la red del cliente
            if not _es_ip_lan(ip):
                continue

            if ip in ips_vistas:
                continue
            ips_vistas.add(ip)

            nombre = fila["devName"]
            if not nombre or nombre in ("(name not found)", "(unknown)", ""):
                vendor = fila["devVendor"]
                nombre = f"Dispositivo ({vendor})" if vendor else f"Equipo-{ip}"

            dispositivos.append({
                "ip": ip,
                "nombre": nombre,
                "mac": fila["devMac"] or "Desconocida",
                "vendor": fila["devVendor"] or ""
            })

    except Exception as e:
        print(f"[threat_engine] Error al leer NetAlertX: {e}")
    finally:
        conn.close()

    return dispositivos


# ==============================================================================
# PASO 2: CONSULTAS Y ACTIVIDAD DNS GENERAL (Pi-hole)
# ==============================================================================
def obtener_metricas_dns(ip, horas=24):
    """
    Obtiene estadísticas generales de actividad DNS para una IP:
    total de consultas y porcentaje de dominios inexistentes (NXDOMAIN).
    """
    conn = _conectar_sqlite(PIHOLE_DB, solo_lectura=True)
    if not conn:
        return 0, 0.0

    total_queries = 0
    nxdomain_rate = 0.0

    try:
        cursor = conn.cursor()
        limite_tiempo = int((datetime.now() - timedelta(hours=horas)).timestamp())

        # Total de consultas
        total_queries = cursor.execute("""
            SELECT COUNT(*) FROM queries
            WHERE client = ? AND timestamp > ?
        """, (ip, limite_tiempo)).fetchone()[0]

        if total_queries > 0:
            # En Pi-hole status 3 = NXDOMAIN o respondido inexistente
            nx_count = cursor.execute("""
                SELECT COUNT(*) FROM queries
                WHERE client = ? AND status = 3 AND timestamp > ?
            """, (ip, limite_tiempo)).fetchone()[0]
            nxdomain_rate = round(nx_count / total_queries, 2)

    except Exception as e:
        print(f"[threat_engine] Error al obtener métricas DNS para {ip}: {e}")
    finally:
        conn.close()

    return total_queries, nxdomain_rate


def contar_bloqueados(ip, horas=24):
    """
    Consulta en Pi-hole cuántas peticiones de esta IP fueron bloqueadas
    en las últimas 'horas' y extrae ejemplos de dominios bloqueados.
    """
    conn = _conectar_sqlite(PIHOLE_DB, solo_lectura=True)
    if not conn:
        return 0, []

    total_bloqueos = 0
    dominios_bloqueados = []

    try:
        cursor = conn.cursor()
        limite_tiempo = int((datetime.now() - timedelta(hours=horas)).timestamp())

        # Conteo total de bloqueos
        query_count = """
            SELECT COUNT(*)
            FROM queries
            WHERE client = ?
              AND status IN (1, 4, 5, 9, 10, 11)
              AND timestamp > ?
        """
        total_bloqueos = cursor.execute(query_count, (ip, limite_tiempo)).fetchone()[0]

        # Obtener hasta 3 dominios de ejemplo
        query_dominios = """
            SELECT DISTINCT domain
            FROM queries
            WHERE client = ?
              AND status IN (1, 4, 5, 9, 10, 11)
              AND timestamp > ?
            LIMIT 3
        """
        filas = cursor.execute(query_dominios, (ip, limite_tiempo)).fetchall()
        dominios_bloqueados = [f[0] for f in filas if f[0]]

    except Exception as e:
        print(f"[threat_engine] Error al contar bloqueos para {ip}: {e}")
    finally:
        conn.close()

    return total_bloqueos, dominios_bloqueados


# ==============================================================================
# PASO 3: DETECCIÓN DE BEACONING (Llamadas periódicas insistentes)
# ==============================================================================
def detectar_beaconing(ip, horas=1, umbral=20):
    """
    Detecta si el dispositivo realiza demasiadas peticiones al mismo dominio
    en un intervalo corto (comportamiento típico de malware 'llamando a casa').
    Excluye dominios locales, mDNS, consultas reversas y sufijos LAN.
    """
    conn = _conectar_sqlite(PIHOLE_DB, solo_lectura=True)
    if not conn:
        return []

    sospechosos = []

    try:
        cursor = conn.cursor()
        limite_tiempo = int((datetime.now() - timedelta(hours=horas)).timestamp())

        consulta = """
            SELECT domain, COUNT(*) as repeticiones
            FROM queries
            WHERE client = ?
              AND timestamp > ?
            GROUP BY domain
            HAVING repeticiones >= ?
            ORDER BY repeticiones DESC
        """
        filas = cursor.execute(consulta, (ip, limite_tiempo, umbral)).fetchall()

        for dominio, veces in filas:
            if not dominio:
                continue

            dom_clean = dominio.strip().lower().rstrip(".")
            if not dom_clean or "." not in dom_clean:
                continue

            # Ignorar nombres locales y dominios de broadcast
            if dom_clean.endswith(SUFIJOS_LOCALES):
                continue

            es_seguro = any(dom_clean == base or dom_clean.endswith("." + base) for base in WHITELIST_DOMINIOS)
            if not es_seguro:
                sospechosos.append({"dominio": dom_clean, "veces": veces})

    except Exception as e:
        print(f"[threat_engine] Error al detectar beaconing para {ip}: {e}")
    finally:
        conn.close()

    return sospechosos


# ==============================================================================
# PASO 4: DETECCIÓN DE DOMINIOS DGA (Generados por virus)
# ==============================================================================
def es_nombre_dga(dominio):
    """
    Determina si un dominio tiene características de generador aleatorio (DGA).

    Lógica robusta:
      - Limpia espacios y puntos finales DNS (ej: 'google.com.').
      - Ignora nombres locales sin punto y sufijos LAN (.local, .lan, .arpa).
      - Maneja adecuadamente ccTLDs de dos partes (.co.cr, .com.mx, .co.uk).
      - Umbral de consonantes escalonado (0.82 para SLD < 10, 0.75 para SLD >= 10).
      - TLD sospechoso + SLD largo (>= 9 letras) como señal fuerte.
      - Validación previa contra WHITELIST_DOMINIOS.
    """
    if not dominio:
        return False

    dominio_clean = dominio.strip().lower().rstrip(".")
    if len(dominio_clean) < 5 or "." not in dominio_clean:
        return False

    if dominio_clean.endswith(SUFIJOS_LOCALES):
        return False

    # Verificar contra whitelist completa (ápice y subdominio)
    for base in WHITELIST_DOMINIOS:
        if dominio_clean == base or dominio_clean.endswith("." + base):
            return False

    partes = dominio_clean.split(".")
    if len(partes) < 2:
        return False

    # Manejo de ccTLDs de dos partes (ej: .co.cr, .com.mx, .co.uk)
    if len(partes) >= 3 and partes[-2] in CCTLD_SEGUNDO_NIVEL and len(partes[-1]) == 2:
        sld = partes[-3]
        tld = f".{partes[-2]}.{partes[-1]}"
    else:
        sld = partes[-2]
        tld = "." + partes[-1]

    tiene_tld_sospechoso = tld in EXTENSIONES_SOSPECHOSAS

    letras = [c for c in sld if c.isalpha()]
    n = len(letras)

    if n >= 6:
        vocales = set("aeiou")
        consonantes = sum(1 for c in letras if c not in vocales)
        ratio_consonantes = consonantes / n

        # Para nombres cortos (marca posible): umbral más estricto
        if n < 10 and ratio_consonantes >= 0.82:
            return True
        # Para nombres largos (improbable que sea marca): umbral normal
        if n >= 10 and ratio_consonantes >= 0.75:
            return True

    # TLD sospechoso + nombre SLD largo (>= 9 letras) → señal fuerte
    if tiene_tld_sospechoso and len(sld) >= 9:
        return True

    return False


def buscar_dominios_dga(ip, horas=24):
    """
    Revisa los dominios consultados por la IP y detecta cuáles tienen
    patrones típicos de algoritmos DGA.
    """
    conn = _conectar_sqlite(PIHOLE_DB, solo_lectura=True)
    if not conn:
        return []

    dga_detectados = []

    try:
        cursor = conn.cursor()
        limite_tiempo = int((datetime.now() - timedelta(hours=horas)).timestamp())

        consulta = """
            SELECT DISTINCT domain
            FROM queries
            WHERE client = ?
              AND timestamp > ?
            LIMIT 200
        """
        filas = cursor.execute(consulta, (ip, limite_tiempo)).fetchall()

        for fila in filas:
            dom = fila[0]
            if dom and es_nombre_dga(dom):
                dga_detectados.append(dom.strip().rstrip("."))

    except Exception as e:
        print(f"[threat_engine] Error al buscar DGA para {ip}: {e}")
    finally:
        conn.close()

    return dga_detectados[:5]


# ==============================================================================
# PASO 5: SISTEMA DE PUNTUACIÓN Y ASIGNACIÓN DE SEMÁFORO
# ==============================================================================
def calcular_riesgo(bloqueados, ejemplos_bloqueados, beaconing, dga, nxdomain_rate=0.0):
    """
    Calcula una puntuación y devuelve tanto las etiquetas en español
    como los códigos estándar esperados por el frontend ('green', 'yellow', 'red',
    y reasons: ['dga', 'beaconing', 'nxdomain', 'blocked']).
    """
    puntuacion = 0
    motivos_espanol = []
    reasons_codes = []

    # 1. Bloqueos en Pi-hole
    if bloqueados > 0:
        if bloqueados >= 10:
            puntuacion += 40
        else:
            puntuacion += 25
        reasons_codes.append("blocked")
        ejemplos_txt = f" (ej: {', '.join(ejemplos_bloqueados)})" if ejemplos_bloqueados else ""
        motivos_espanol.append(f"Pi-hole bloqueó {bloqueados} intento(s) de conexión a sitios restringidos{ejemplos_txt}.")

    # 2. Beaconing
    if beaconing:
        puntuacion += 35
        reasons_codes.append("beaconing")
        detalles_b = [f"{b['dominio']} ({b['veces']} veces)" for b in beaconing[:2]]
        motivos_espanol.append(f"Actividad repetitiva sospechosa (Beaconing) hacia: {', '.join(detalles_b)}.")

    # 3. DGA
    if dga:
        puntuacion += 45
        reasons_codes.append("dga")
        motivos_espanol.append(f"Consulta a dominio(s) con patrón de virus/DGA: {', '.join(dga[:3])}.")

    # 4. Tasa alta de NXDOMAIN
    if nxdomain_rate >= 0.35:
        puntuacion += 25
        reasons_codes.append("nxdomain")
        motivos_espanol.append(f"Alta tasa de dominios inexistentes ({int(nxdomain_rate*100)}%).")

    puntuacion = min(100, puntuacion)

    # Asignación del semáforo
    if puntuacion >= 60:
        riesgo = "peligro"
        state = "red"
    elif puntuacion >= 21:
        riesgo = "sospechoso"
        state = "yellow"
    else:
        riesgo = "normal"
        state = "green"

    return riesgo, state, puntuacion, motivos_espanol, reasons_codes


# ==============================================================================
# FUNCIÓN PRINCIPAL EXPORTABLE (Consumida por Persona 2 en api/main.py)
# ==============================================================================
_CACHE_REPORTE = None
_CACHE_TIMESTAMP = 0.0
CACHE_TTL_SEGUNDOS = 15.0


def analizar_red(forzar_refresco=False):
    """
    Escanea todos los dispositivos y genera el reporte completo.
    Estructurado para satisfacer tanto el contrato original como la vista Heurística
    creada en React por Persona 3.
    Incorpora caché en memoria con TTL de 15s para evitar sobrecarga de lecturas
    recurrentes a SQLite/eMMC en el SoC RK3566.
    """
    global _CACHE_REPORTE, _CACHE_TIMESTAMP
    ahora = time.time()
    if not forzar_refresco and _CACHE_REPORTE is not None and (ahora - _CACHE_TIMESTAMP < CACHE_TTL_SEGUNDOS):
        return _CACHE_REPORTE

    dispositivos_raw = obtener_dispositivos()
    resultado_dispositivos = []

    for dev in dispositivos_raw:
        ip = dev["ip"]
        nombre = dev["nombre"]
        mac = dev["mac"]

        # Métricas generales de consultas
        total_queries, nxdomain_rate = obtener_metricas_dns(ip, horas=24)

        # Señales de amenaza
        total_bloqueados, ejemplos_bloq = contar_bloqueados(ip, horas=24)
        sospechosos_beaconing = detectar_beaconing(ip, horas=1, umbral=20)
        dominios_dga = buscar_dominios_dga(ip, horas=24)

        # Cálculo de riesgo y semáforo
        riesgo, state, puntuacion, motivos, reasons = calcular_riesgo(
            total_bloqueados,
            ejemplos_bloq,
            sospechosos_beaconing,
            dominios_dga,
            nxdomain_rate
        )

        resultado_dispositivos.append({
            # Campos consumidos por el componente React de Persona 3
            "ip": ip,
            "mac": mac,
            "name": nombre,
            "state": state,                # 'green', 'yellow', 'red'
            "reasons": reasons,            # ['beaconing', 'dga', 'nxdomain', 'blocked']
            "dga_domains": dominios_dga,
            "beacon_domains": [b["dominio"] for b in sospechosos_beaconing],
            "queries": total_queries,
            "nxdomain_rate": nxdomain_rate,

            # Campos en español del contrato original
            "nombre": nombre,
            "riesgo": riesgo,              # 'normal', 'sospechoso', 'peligro'
            "puntuacion": puntuacion,
            "motivos": motivos
        })

    reporte = {
        "mode": "shadow",  # Modo por defecto (Sombra / Auditoría)
        "last_run": datetime.now().isoformat(),
        "analizado_en": datetime.now().isoformat(),
        "total_dispositivos": len(resultado_dispositivos),
        "devices": resultado_dispositivos,      # Esperado por React
        "dispositivos": resultado_dispositivos   # Esperado por contrato
    }

    _CACHE_REPORTE = reporte
    _CACHE_TIMESTAMP = ahora
    return reporte


# ==============================================================================
# EJECUCIÓN DIRECTA DESDE TERMINAL
# ==============================================================================
if __name__ == "__main__":
    print("[*] Ejecutando análisis del motor de detección de amenazas...")
    informe = analizar_red()
    print(json.dumps(informe, indent=2, ensure_ascii=False))
