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
4. Calcular el nivel de riesgo: 'normal', 'sospechoso' o 'peligro'.
5. Exportar la función principal `analizar_red()` para que Persona 2 (API)
   la consuma directamente.
"""

import os
import sqlite3
import json
from datetime import datetime, timedelta

# ==============================================================================
# CONFIGURACIÓN Y RUTAS DE BASES DE DATOS
# ==============================================================================
# Compatible tanto con el entorno de producción en SafeLock (/root/safeLock_SoC)
# como con el entorno de desarrollo local en Windows.
DATA_DIR = os.environ.get("SAFELOCK_DATA_DIR", "")
if DATA_DIR and os.path.exists(DATA_DIR):
    NETALERTX_DB = os.path.join(DATA_DIR, "netalertx", "data", "db", "app.db")
    PIHOLE_DB = os.path.join(DATA_DIR, "pihole", "etc-pihole", "pihole-FTL.db")
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    NETALERTX_DB = os.path.join(BASE_DIR, "netalertx", "data", "db", "app.db")
    PIHOLE_DB = os.path.join(BASE_DIR, "pihole", "etc-pihole", "pihole-FTL.db")

# Dominios y extensiones comunes para evitar falsos positivos
WHITELIST_DOMINIOS = {
    "google.com", "gstatic.com", "googleapis.com", "youtube.com",
    "microsoft.com", "windows.com", "live.com", "msftncsi.com", "windowsupdate.com",
    "apple.com", "icloud.com", "aaplimg.com",
    "cloudflare.com", "amazon.com", "aws.amazon.com",
    "tailscale.com", "github.com", "ntp.org"
}

EXTENSIONES_SOSPECHOSAS = {
    ".xyz", ".top", ".ru", ".tk", ".click", ".buzz",
    ".work", ".icu", ".cc", ".cn", ".biz"
}


# ==============================================================================
# PASO 1: LECTURA DE DISPOSITIVOS (NetAlertX)
# ==============================================================================
def obtener_dispositivos():
    """
    Obtiene la lista de dispositivos registrados y activos desde NetAlertX.
    Deduplica por IP para evitar dispositivos repetidos en el análisis.
    """
    if not os.path.exists(NETALERTX_DB):
        return []

    dispositivos = []
    ips_vistas = set()

    try:
        conn = sqlite3.connect(NETALERTX_DB)
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
        conn.close()

        for fila in filas:
            ip = fila["devLastIP"]
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

    return dispositivos


# ==============================================================================
# PASO 2: SEÑAL 1 - CONSULTAS BLOQUEADAS POR PI-HOLE
# ==============================================================================
def contar_bloqueados(ip, horas=24):
    """
    Consulta en Pi-hole cuántas peticiones de esta IP fueron bloqueadas
    en las últimas 'horas' y extrae ejemplos de dominios bloqueados.
    """
    if not os.path.exists(PIHOLE_DB):
        return 0, []

    total_bloqueos = 0
    dominios_bloqueados = []

    try:
        conn = sqlite3.connect(PIHOLE_DB)
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

        conn.close()
    except Exception as e:
        print(f"[threat_engine] Error al contar bloqueos para {ip}: {e}")

    return total_bloqueos, dominios_bloqueados


# ==============================================================================
# PASO 3: SEÑAL 2 - DETECCIÓN DE BEACONING (Llamadas periódicas insistentes)
# ==============================================================================
def detectar_beaconing(ip, horas=1, umbral=20):
    """
    Detecta si el dispositivo realiza demasiadas peticiones al mismo dominio
    en un intervalo corto (comportamiento típico de malware 'llamando a casa').
    """
    if not os.path.exists(PIHOLE_DB):
        return []

    sospechosos = []

    try:
        conn = sqlite3.connect(PIHOLE_DB)
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
        conn.close()

        for dominio, veces in filas:
            if not dominio or dominio.endswith(".arpa") or dominio == "localhost":
                continue

            # Filtrar si pertenece a la lista blanca de dominios gigantes conocidos
            es_seguro = any(dominio == base or dominio.endswith("." + base) for base in WHITELIST_DOMINIOS)
            if not es_seguro:
                sospechosos.append({"dominio": dominio, "veces": veces})

    except Exception as e:
        print(f"[threat_engine] Error al detectar beaconing para {ip}: {e}")

    return sospechosos


# ==============================================================================
# PASO 4: SEÑAL 3 - DETECCIÓN DE DOMINIOS DGA (Generados por virus)
# ==============================================================================
def es_nombre_dga(dominio):
    """
    Analiza las características léxicas de un dominio para determinar
    si parece haber sido generado automáticamente por un virus:
    - Alta concentración de consonantes / letras aleatorias.
    - Extensiones (.tld) frecuentemente abusadas por malware.
    - Longitud inusualmente azarosa sin vocales.
    """
    if not dominio or len(dominio) < 5:
        return False

    partes = dominio.lower().split(".")
    if len(partes) < 2:
        return False

    subnombre = partes[0]
    tld = "." + partes[-1]

    # Verificar si usa una extensión sospechosa
    tiene_tld_sospechoso = tld in EXTENSIONES_SOSPECHOSAS

    # Extraer solo letras
    letras = [c for c in subnombre if c.isalpha()]
    if len(letras) >= 6:
        vocales = set("aeiou")
        consonantes = sum(1 for c in letras if c not in vocales)
        ratio_consonantes = consonantes / len(letras)

        # Si más del 70% son consonantes (ej: xk3mq2vp), es altamente sospechoso
        if ratio_consonantes >= 0.70:
            return True

    if tiene_tld_sospechoso and len(subnombre) >= 7:
        return True

    return False


def buscar_dominios_dga(ip, horas=24):
    """
    Revisa los dominios consultados por la IP y detecta cuáles tienen
    patrones típicos de algoritmos DGA.
    """
    if not os.path.exists(PIHOLE_DB):
        return []

    dga_detectados = []

    try:
        conn = sqlite3.connect(PIHOLE_DB)
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
        conn.close()

        for fila in filas:
            dom = fila[0]
            if dom and es_nombre_dga(dom):
                dga_detectados.append(dom)

    except Exception as e:
        print(f"[threat_engine] Error al buscar DGA para {ip}: {e}")

    return dga_detectados[:5]  # Devolver máximo 5 evidencias


# ==============================================================================
# PASO 5: SISTEMA DE PUNTUACIÓN Y ASIGNACIÓN DE SEMÁFORO
# ==============================================================================
def calcular_riesgo(bloqueados, ejemplos_bloqueados, beaconing, dga):
    """
    Calcula una puntuación de riesgo entre 0 y 100 basada en las 3 señales:
    - 0 a 20 puntos:   'normal' (🟢)
    - 21 a 59 puntos:  'sospechoso' (🟡)
    - 60 a 100 puntos: 'peligro' (🔴)
    """
    puntuacion = 0
    motivos = []

    # 1. Puntos por dominios bloqueados en Pi-hole
    if bloqueados > 0:
        if bloqueados >= 10:
            puntuacion += 40
        else:
            puntuacion += 25
        ejemplos_txt = f" (ej: {', '.join(ejemplos_bloqueados)})" if ejemplos_bloqueados else ""
        motivos.append(f"Pi-hole bloqueó {bloqueados} intento(s) de conexión a sitios restringidos{ejemplos_txt}.")

    # 2. Puntos por Beaconing
    if beaconing:
        puntuacion += 35
        detalles_b = [f"{b['dominio']} ({b['veces']} veces)" for b in beaconing[:2]]
        motivos.append(f"Actividad repetitiva sospechosa (Beaconing) hacia: {', '.join(detalles_b)}.")

    # 3. Puntos por DGA
    if dga:
        puntuacion += 45
        motivos.append(f"Consulta a dominio(s) con patrón de virus/DGA: {', '.join(dga[:3])}.")

    # Limitar puntuación a un máximo de 100
    puntuacion = min(100, puntuacion)

    # Clasificar en el semáforo acordado en el contrato
    if puntuacion >= 60:
        riesgo = "peligro"
    elif puntuacion >= 21:
        riesgo = "sospechoso"
    else:
        riesgo = "normal"

    return riesgo, puntuacion, motivos


# ==============================================================================
# FUNCIÓN PRINCIPAL EXPORTABLE (Consumida por Persona 2 en api/main.py)
# ==============================================================================
def analizar_red():
    """
    Punto de entrada principal del motor de detección.
    Escanea todos los dispositivos, calcula sus métricas y devuelve el
    resultado en el formato JSON acordado por el equipo.
    """
    dispositivos_raw = obtener_dispositivos()
    resultado_dispositivos = []

    for dev in dispositivos_raw:
        ip = dev["ip"]
        nombre = dev["nombre"]
        mac = dev["mac"]

        # 1. Analizar bloqueos
        total_bloqueados, ejemplos_bloq = contar_bloqueados(ip, horas=24)

        # 2. Analizar beaconing
        sospechosos_beaconing = detectar_beaconing(ip, horas=1, umbral=20)

        # 3. Analizar DGA
        dominios_dga = buscar_dominios_dga(ip, horas=24)

        # 4. Calcular nivel de riesgo
        riesgo, puntuacion, motivos = calcular_riesgo(
            total_bloqueados,
            ejemplos_bloq,
            sospechosos_beaconing,
            dominios_dga
        )

        resultado_dispositivos.append({
            "ip": ip,
            "nombre": nombre,
            "mac": mac,
            "riesgo": riesgo,
            "puntuacion": puntuacion,
            "motivos": motivos
        })

    return {
        "analizado_en": datetime.now().isoformat(),
        "total_dispositivos": len(resultado_dispositivos),
        "dispositivos": resultado_dispositivos
    }


# ==============================================================================
# EJECUCIÓN DIRECTA DESDE TERMINAL (Para pruebas independientes)
# ==============================================================================
if __name__ == "__main__":
    print("[*] Ejecutando análisis del motor de detección de amenazas...")
    informe = analizar_red()
    print(json.dumps(informe, indent=2, ensure_ascii=False))
