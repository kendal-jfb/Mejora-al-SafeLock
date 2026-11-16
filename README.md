# SafeLock — imagen del dispositivo

Software que corre en el SoC (Armbian) de cada unidad SafeLock: API local,
portal del cliente, servicios de red (Pi-hole, NetAlertX, OpenCanary), sistema
de actualizaciones OTA y **motor heurístico de detección de amenazas**.

---

## Motor Heurístico (Heuristic Sentinel)

Funcionalidad añadida sobre la base de SafeLock. Detecta comportamiento
sospechoso en la red **sin depender de listas predefinidas**:

| Señal | Qué detecta |
|-------|-------------|
| **DGA** | Dominios generados por algoritmo (típicos de malware) |
| **Beaconing** | Llamadas periódicas repetitivas a un mismo dominio externo |
| **Bloqueos Pi-hole** | Intentos de acceso a dominios ya catalogados como maliciosos |

### Modos de operación

- **Modo Sombra (`shadow`)** — solo alertas. Nunca bloquea nada. Semáforo y
  notificaciones activas. Ideal para monitoreo sin interferir con la red.
- **Modo Activo (`protect`)** — bloquea **y** alerta. Solo actúa sobre
  dispositivos en estado rojo (puntuación ≥ 80). Los amarillos solo alertan.

> El modo predeterminado es **Sombra**. Cambiar a Activo requiere acción
> explícita del usuario desde el portal.

### Comportamiento con videojuegos

Los juegos usan dominios con hashes, UUIDs y servidores con nombres aleatorios
que pueden disparar falsas alarmas. El motor aplica tres capas de protección:

1. **Whitelist de dominios** — Epic Games, Steam, EA, Riot, Xbox, PlayStation,
   Roblox, Minecraft, Ubisoft, PUBG y más, con cobertura regex de subdominios.
2. **Filtro de prefijos CDN/gaming** — subdominios que empiezan por `cdn`,
   `api`, `game`, `matchmaking`, `relay`, `voice`, etc. se ignoran aunque
   el nombre parezca aleatorio.
3. **Umbral alto de bloqueo** — se requiere puntuación ≥ 80 (no 60) para
   pasar de alerta a bloqueo efectivo.

---

## Estructura

```
api/        API local (FastAPI, puerto 8090) y reportes por correo
  threat_engine.py      Motor de detección de amenazas
  sentinel_connector.py Conector: modos, bloqueos Pi-hole, whitelist gaming
portal/     portal del cliente (React + Vite); se compila en CI, no en el SoC
  HeuristicView.jsx     Vista del motor heurístico (semáforo por dispositivo)
ota/        agente de actualizaciones y unidades systemd del release
rescue/     rescate del dispositivo; el canal OTA nunca lo actualiza
scripts/    health check, migración y utilidades de red/Pi-hole
systemd/    unidades del updater
install/    aprovisionamiento de fábrica
pihole/ netalertx/ opencanary/   configuración de los servicios en Docker
docs/       documentación técnica completa
```

## Actualizaciones OTA

Publicar una versión es crear un tag:

```bash
git tag v2.x.x && git push origin v2.x.x
```

GitHub Actions compila, firma y publica el release; entra por el canal canary y
se promueve a toda la flota desde el dashboard de telemetría.

El detalle completo — puesta en marcha, migración de la flota, operación diaria
y pruebas — está en **[docs/OTA.md](docs/OTA.md)**.
