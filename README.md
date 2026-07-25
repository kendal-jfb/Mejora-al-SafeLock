# SafeLock — imagen del dispositivo

Software que corre en el SoC (Armbian) de cada unidad SafeLock: API local,
portal del cliente, servicios de red (Pi-hole, NetAlertX, OpenCanary) y el
sistema de actualizaciones.

## Estructura

```
api/        API local (FastAPI, puerto 8090) y reportes por correo
portal/     portal del cliente (React + Vite); se compila en CI, no en el SoC
ota/        agente de actualizaciones y unidades systemd del release
rescue/     rescate del dispositivo; el canal OTA nunca lo actualiza
scripts/    health check, migración y utilidades de red/Pi-hole
systemd/    unidades del updater antiguo (se retiran al migrar la flota)
install/    aprovisionamiento de fábrica
pihole/ netalertx/ opencanary/   configuración de los servicios en docker
```

## Actualizaciones

Publicar una versión es crear un tag:

```bash
git tag v2.1.0 && git push origin v2.1.0
```

GitHub Actions compila, firma y publica el release; entra por el canal canary y
se promueve a toda la flota desde el dashboard de telemetría.

El detalle completo — puesta en marcha, migración de la flota, operación diaria
y pruebas — está en **[docs/OTA.md](docs/OTA.md)**.
