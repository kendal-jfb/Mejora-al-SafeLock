# SafeLock — Filtrado DNS a nivel de red: investigación de dos opciones (documento de referencia, no ejecutar aún)

## Contexto

El modo premium de SafeLock (Pi-hole) hoy solo filtra el dispositivo que alguien apunte manualmente
a la IP del equipo como DNS. El dueño quiere que "activar premium" extienda el filtrado a más
dispositivos de la red del cliente automáticamente, sin depender del router (en Costa Rica, mercado
principal, los routers vienen bloqueados por el ISP y no se pueden reconfigurar).

Ya se habían probado dos caminos al inicio del desarrollo y se abandonaron: configurar el router
(bloqueado por el ISP) y ARP spoofing ("no terminaba de funcionar"). Este documento es el resultado
de investigar a fondo (a) una tercera vía — VPN por dispositivo vía WireGuard/Tailscale — y (b) cómo
se vería un ARP spoof hecho correctamente, para dejar ambas diseñadas y comparadas como referencia.
**No se aprobó construir ninguna de las dos todavía** — el dueño decidió documentar y esperar a que
la flota esté estable (ver `CLAUDE.md` — crisis de apagones/bricking en curso, regla de "canario
primero, nada a `master` sin orden explícita").

Decisiones ya tomadas por el dueño para este documento:
- **Opción A se diseña solo para alcance LAN-doméstica** (no roaming/fuera de casa) — variante
  WireGuard simple, sin Tailscale multi-tenant.
- **No se implementa nada ahora.** Este archivo queda como diseño-en-archivo para retomar cuando la
  flota muestre estabilidad sostenida post-endurecimiento.

---

## Hallazgos de la investigación (grounding, ya verificados contra el repo/dispositivo vivo)

- `gravity.db` de Pi-hole **ya tiene** esquema de políticas por cliente sin usar: tablas `client`
  (0 filas), `group` (1 fila, el grupo "Default"), `client_by_group` (0 filas),
  `domainlist_by_group` (4 filas, vinculando los `PACK_*` al grupo Default). Hoy `api/packs.py`
  `set_pack_enabled()` escribe `domainlist.enabled` directo, sin scoping — el filtrado por-cliente es
  **adopción de esquema existente, no invención**.
- `scripts/health-check.py`, `scripts/rollback.sh`, `systemd/connectivity-watchdog.{service,timer}`
  existen y siguen el patrón: `critical` → dispara `rollback.sh` (revierte OTA); `warnings` → se
  reporta pero nunca revierte. Cualquier señal de salud de las dos opciones debe entrar como
  `warning`, nunca `critical` (evitar que un problema de red dispare un rollback de OTA).
- Tailscale hoy: authkey (no OAuth), tag único `tag:safelock`, `--accept-dns=false` explícito (el
  equipo rechaza DNS del tailnet para sí mismo). Cero MagicDNS, cero ACLs/tags por cliente, cero
  generación de config WireGuard en el repo.
- No existe ningún rastro de ARP spoof/MITM en todo el historial git (0 commits, 0 archivos
  borrados relacionados) — el intento anterior se hizo ad-hoc y nunca se comiteó. `FORWARD` chain
  hoy es `DROP` salvo tailscale0/docker0; no hay reglas DNAT/PREROUTING; `ip_forward=1` en runtime es
  solo efecto colateral de dockerd, no una config deliberada.
- El equipo tiene **una sola interfaz física, Ethernet (`end0`)**, WiFi/BT deshabilitados a propósito
  por consumo. No es el router/DHCP de la red (`pihole.toml` DHCP `active=false`). Esto hace que
  ARP spoofing sea la única forma de interceptar tráfico de otros dispositivos sin acceso al router
  (no hay modo AP ni DHCP takeover disponible).
- CPU deliberadamente capado (`governor=conservative`, techo 1.416 GHz) para cortar picos de
  corriente sospechosos de matar fuentes marginales — la causa raíz de la crisis de apagones. Carga
  actual ~1-2 de 4 núcleos (holgura para la carga pasiva actual), pero **nunca se ha probado
  reenvío de paquetes full-duplex sostenido** en este hardware.

---

## Opción A (recomendada para prototipar después) — VPN WireGuard por dispositivo, solo-LAN

### Arquitectura
- Interfaz `wg0` en el equipo, subred propia (ej. `10.70.70.0/24`, equipo en `.1`) que no choca ni
  con la LAN (`192.168.110.0/24`) ni con el CGNAT de Tailscale (`100.64.0.0/10`).
- Cada dispositivo del cliente es un peer WireGuard con `AllowedIPs = 10.70.70.1/32` **del lado del
  cliente** — el túnel es **solo-DNS**, no `0.0.0.0/0`. El equipo nunca necesita enrutar/NATear el
  tráfico general del dispositivo, solo responder DNS. Esto acota el radio de falla a "no se filtra
  DNS", nunca "se cae internet".
- La IP del peer en `wg0` se usa como `client.ip` en el esquema `client`/`client_by_group` de
  `gravity.db` (ya existe, sin usar) → nuevo `group` `premium_peers` → vincular los `PACK_*`
  deseados vía `domainlist_by_group`. Los dispositivos que hoy apuntan su DNS manualmente al equipo
  siguen en el `group 0` (comportamiento global actual, sin tocar).
- Entrega reutiliza el patrón `/qr` ya existente (`api/main.py` ~línea 478,
  `<img src={API}/qr>` en `portal/src/App.jsx`) — en vez de codificar la URL del portal, un nuevo
  endpoint codifica el `.conf` del peer generado (igual a cómo las apps de WireGuard importan por
  QR con `qrencode`).
- **Gap de seguridad nuevo que esta feature introduce**: la API hoy no tiene autenticación (el
  propio comentario de CORS en `api/main.py` lo reconoce). Emitir una credencial de red (peer
  WireGuard) es más sensible que togglear un pack — necesita algún gate mínimo antes de salir a
  producción (origen LAN/portal, no accesible por Tailscale-scope, o un PIN de admin).

### Archivos/scripts a crear o tocar (cuando se retome)
- `scripts/wg-peer-common.sh` (nuevo, estilo `scripts/tailscale-common.sh`): keygen, alta/baja de
  peer, render de config.
- `install/enable-lan-wg-server.sh` (nuevo, idempotente, gateado `SAFELOCK_ALLOW_WG_PEER_VPN=1`,
  mismo patrón que `install/enable-ramoops.sh`): instala `wireguard-tools`, genera keypair del
  servidor una sola vez, escribe `/etc/wireguard/wg0.conf`. No toca `/boot` ni cmdline — sin riesgo
  clase-brick.
- Adoptar el `wg-quick@wg0.service` estándar del paquete en vez de una unit propia.
- `api/wg_peers.py` (nuevo, mismo patrón que `api/packs.py`): registro persistente de peers en
  `/etc/safelock/wg-peers.json` (sobrevive al `git reset --hard` del OTA, igual que `config.json`),
  alta/baja en caliente vía `wg set wg0 peer ...` (sin reiniciar `wg-quick`), inserts en
  `client`/`client_by_group` + `docker exec pihole pihole reloaddns` (reusa la llamada existente de
  `packs.py`).
- `api/packs.py`: agregar `set_group_packs(group_name, packs)` junto al `set_pack_enabled()` global
  existente — aditivo, no reescribe el comportamiento global.
- `api/main.py`: `POST /premium/peer`, `GET /premium/peer/{id}/qr`, `DELETE /premium/peer/{id}`
  (revocación — necesaria para "el cliente cambió de teléfono").
- `portal/src/App.jsx`: acción "Agregar este dispositivo" en el panel premium + lista de revocación.
- `scripts/pihole_control.sh`: extender `activar`/`desactivar` para también
  `systemctl start/stop wg-quick@wg0` (mismo modelo mental "premium = cosas corriendo").
- `scripts/health-check.py`: chequeo de `wg0` como **warning**, nunca `critical`.

### Secuencia de implementación (cuando se retome)
1. Confirmar soporte WireGuard en el kernel Armbian/RK3566 actual y disponibilidad de
   `wireguard-tools` en apt.
2. Elegir/documentar subred `wg0`.
3. Construir `install/enable-lan-wg-server.sh` gateado, solo canario primero.
4. Validar empíricamente en canario que Pi-hole (`listeningMode=LOCAL`) acepta y filtra
   correctamente consultas que llegan por `wg0` con el scoping por grupo — esto es inferido, nunca
   probado en este código, validar antes de construir el resto.
5. `api/wg_peers.py` + endpoints + gate de autenticación mínimo.
6. UI del portal (QR + revocación).
7. Enganchar ciclo de vida de `wg-quick@wg0` a `pihole_control.sh`.
8. `health-check.py` warning-level.
9. Validación de canario con teléfono real en la topología real, incluyendo que el registro de
   peers sobreviva un ciclo de OTA.

### Riesgos / límites
- Radio de falla acotado: peor caso es "no se filtra DNS de ese dispositivo", nunca pérdida de
  internet — por diseño (túnel solo-DNS).
- Nuevo gap de auth en la API que esta feature expone (emitir credencial de red sin auth hoy).
- Límite compartido con cualquier filtrado por DNS: el dispositivo puede reconfigurarse a mano para
  ignorar el DNS empujado, o usar DoH — mismo techo que el modo manual actual.
- Consentimiento: el cliente elige activamente qué dispositivo agregar (escanea el QR) — postura de
  consentimiento mucho más limpia que la Opción B.

**Esfuerzo: medio.** Sin riesgo clase-brick, sin nueva dependencia de cuenta/API externa, no toca
`ip_forward`/FORWARD chain. El trabajo real es adoptar el esquema de Pi-hole nunca usado, construir
el ciclo de vida de peers con su propia persistencia/revocación, y cerrar el gap de auth nuevo.

*(Variante roaming — descartada por el dueño para este diseño: requeriría Tailscale multi-tenant
real con una cuenta/tailnet aislado por cliente + aprovisionamiento OAuth, y no meter clientes en el
mismo tailnet que las unidades SafeLock del dueño, que hoy no tiene ACLs y sería fuga entre
clientes. Se deja anotado por si el requisito cambia más adelante.)*

---

## Opción B (investigada, engavetada por ahora) — ARP spoof hecho correctamente

### Herramienta: bettercap (daemon supervisado), no scapy a mano
- `arp.spoof` de bettercap en **modo full-duplex** (`arp.spoof.fullduplex=true` — sin esto, el
  spoof falla si el router tiene protección ARP, según la propia documentación de bettercap).
- Usar bettercap **solo** para el transporte ARP/MITM — no su módulo `dns.spoof` (que contesta DNS
  falso él mismo). El filtrado real lo sigue haciendo Pi-hole vía una regla DNAT aparte
  (`PREROUTING`, `udp/tcp dport 53 → DNAT a la IP del equipo:53`) — patrón estándar de "proxy DNS
  transparente".
- **Deshabilitar por completo la REST API de bettercap** — no sumar un segundo servicio sin
  autenticación a un equipo cuya API ya no tiene auth. Manejarlo solo por caplet + lista de targets
  en archivo local.

### El punto duro de verdad: diseño "dead man's switch"
1. **La propia TTL de ARP ya es la red de seguridad real, y hay que decirlo explícito**: bettercap
   re-emite ARP falso cada `arp.spoof.interval` (1000 ms default); si el proceso muere (crash,
   corte de luz), el reenvío para y cada SO recupera la MAC real del gateway solo, por su propio
   TTL de caché ARP (típico: menos de un par de minutos) — **sin que corra código en este equipo**.
   Esto acota el peor caso a "sin internet un rato", no "sin internet indefinido". Hay que
   **validarlo empíricamente en canario** (medir tiempo real de recuperación en SOs reales), no
   solo asumirlo.
2. **Restauración explícita en paradas ordenadas** — `ExecStop=` en la unit de bettercap corre
   `arp.spoof off` (ARP correctivo inmediato) para los casos que systemd sí puede atrapar (stop
   manual, reinicio por OTA, `Restart=on-failure`). Mismo punto ciego que
   `scripts/boot-sentinel.sh` ya tiene: un corte de luz nunca dispara `ExecStop` — por eso el punto
   1 es la protección real, no este.
3. **Watchdog dedicado** — `scripts/arp-spoof-watchdog.sh` +
   `systemd/safelock-arp-spoof-watchdog.{service,timer}` (cadencia tipo
   `connectivity-watchdog.timer`, 30-60s): si bettercap no está activo **o** Pi-hole no está sano,
   fuerza un ARP correctivo a los targets conocidos y desarma el spoof.
- Nota: no hace falta desmontar el DNAT como mecanismo de seguridad aparte — en cuanto ARP se
  autocorrige, el tráfico de puerto 53 de los clientes vuelve solo al gateway real y deja de llegar
  al equipo; la regla DNAT queda inerte sin más código.

### Dónde viven las reglas / integración
- Script nuevo y **separado** `scripts/lan-filter-control.sh {activar|desactivar|estado}` —
  deliberadamente NO fusionado con `pihole_control.sh`: "premium para quien apunta su DNS al equipo"
  y "interceptar toda la LAN" son compromisos de tamaño muy distinto y no deben implicarse en
  silencio por el mismo toggle.
- `FORWARD` `ACCEPT` acotado solo a las IPs de los targets activos (no abrir la política global) +
  regla DNAT de puerto 53, validado con `nft -c` (dry-run) antes de aplicar — mismo criterio de
  "validar antes de escribir" que ya usa `install/enable-ramoops.sh` para `/boot`.
- Doble gate: (1) flag de instalación `SAFELOCK_ALLOW_LAN_ARP_FILTER=1` en
  `install/enable-lan-arp-filter.sh`, y (2) marcador de runtime por unidad
  (`/etc/safelock/allow-lan-arp-filter`) que `lan-filter-control.sh` exige antes de correr
  `activar` — más fuerte que el patrón de un solo env-var existente, porque es la primera feature
  del repo que puede afectar la conectividad de dispositivos que no son del equipo mismo.

### Antes de siquiera pensar en rollout a la flota
- `health-check.py`: `arp_spoof_active`, conteo de targets, y verificación de que la propia ARP del
  equipo hacia el gateway real siga apuntando al gateway real — todo como **warning**, nunca
  `critical` (no debe disparar `rollback.sh`).
- Extender `scripts/flight-recorder.sh` con carga de CPU y paquetes/seg reenviados bajo spoof activo
  — para comparar contra la telemetría ya existente de la crisis de apagones.
- Gate explícito go/no-go: prueba sostenida de reenvío full-duplex (ej. `iperf3` a través de un
  cliente de prueba spoofeado) en hardware real antes de tocar un segundo equipo — carga que nunca
  se ha probado en este hardware, capado de CPU justo para evitar picos de corriente.

### MVP vs producción real
- **No-goals explícitos del MVP**: IPv6/NDP (ARP es solo IPv4 — cualquier cliente con DNS/ruteo
  IPv6, común en ISPs modernos, queda sin filtrar); DoH/DoT (no hay arreglo a nivel ARP); equipos con
  protección anti-ARP-spoof. Lista de targets fija y curada a mano (1-2 dispositivos propios del
  operador), nunca auto-target de toda la LAN, y nunca auto-armado por `pihole_control.sh activar`.
- **Para producción real** hace falta además: lista de targets dinámica desde el descubrimiento ya
  existente de `netalertx`, con allowlist visible al cliente (necesidad de ingeniería y de
  consentimiento/legal — hoy intercepta en silencio dispositivos que nunca dieron opt-in, incluido
  el celular de una visita); validación de throughput/térmica realista con tráfico mixto, no solo
  sintético; kill switch remoto rápido para soporte (`lan-filter-control.sh desactivar` por
  Tailscale).

### Riesgos
- Radio de falla: **la conectividad de internet de toda la casa**, no solo el filtrado — mucho más
  grande que cualquier otra cosa que tenga el producto hoy.
- Infraestructura nueva en todas las dimensiones para este repo: primer código L2/MITM, primeras
  reglas `iptables`/`nft`, primera dependencia deliberada de `ip_forward`, primer binario externo de
  este tamaño (bettercap) — en un equipo cuyo esfuerzo reciente entero fue *quitar* carga de CPU/
  disco, no sumar una nueva carga sostenida.
- El intento anterior de exactamente esto se abandonó sin dejar rastro — señal real de fragilidad,
  no un descuido.
- El techo de eficacia ya se erosiona a nivel industria (crecimiento de IPv6, DoH por default en
  navegadores/SOs modernos).
- Consentimiento/legal: intercepta dispositivos sin opt-in — pregunta de producto/legal para el
  dueño, no solo ingeniería.

**Esfuerzo: grande.** Clase de infraestructura genuinamente nueva de punta a punta, diseño de
seguridad ante fallos desde cero (nada en el repo cubre hoy el punto ciego de "corte de luz sin
aviso" para un intercept de red con estado), y trabajo de benchmarking en hardware real que tiene
que pasar *antes* de que sea seguro correrlo en un canario.

---

## Comparación

| | Opción A (WireGuard solo-LAN) | Opción B (ARP spoof + DNAT) |
|---|---|---|
| Radio de falla | Acotado al filtrado DNS de ese equipo | Internet de toda la casa |
| Clase de infra nueva | Aditiva (peer VPN + scoping de Pi-hole, ambos acotados) | Fundacional (primer MITM L2, primer nft, primera dependencia de ip_forward) |
| Toca la causa raíz de la crisis (CPU/energía) | No | Sí, y sin probar en este hardware |
| Consentimiento | Opt-in explícito por dispositivo (el cliente escanea el QR) | Intercepción sin consentimiento de todo lo que esté en la LAN |
| Huecos de cobertura permanentes | Override manual de DNS, DoH (igual que hoy) | + IPv6, + DoH/DoT, + equipos con protección ARP |
| Dependencia externa | Ninguna (variante WireGuard simple) | Nuevo binario (bettercap), nuevo camino de forwarding en kernel |
| Esfuerzo relativo | Medio | Grande |

## Recomendación

**Ninguna se construye ahora.** El dispositivo está en medio de la respuesta a la crisis de apagones
(captura de imagen golden y reactivación de OTA en la flota siguen siendo decisiones abiertas —
ver `CLAUDE.md`) y agregar cualquiera de las dos features encima de eso agrega riesgo a un blanco en
movimiento.

Cuando la flota muestre estabilidad sostenida post-endurecimiento, prototipar primero la **Opción A
(WireGuard solo-LAN)**: no toca la postura de CPU/energía que se protegió con tanto esfuerzo, su
falla se acota a "no filtra" en vez de "no hay internet", y no suma una clase de infraestructura
nueva grande. La Opción B queda engavetada — este documento es su diseño de referencia si se
retoma — con la señal de "N semanas seguidas sin apagones de campo post-endurecimiento" como
condición para siquiera empezarla, dado que es lo más riesgoso que se le podría sumar a este equipo
en este momento.

## Verificación (cuando se retome cualquiera de las dos)

- Opción A: validar en un canario real que Pi-hole filtra correctamente por `client`/`group` para
  consultas llegando por `wg0` (paso 4 de la secuencia arriba) antes de construir el resto del
  ciclo de vida de peers; probar que `/etc/safelock/wg-peers.json` sobrevive un ciclo completo de
  OTA (`git reset --hard`).
- Opción B: correr `iperf3` full-duplex sostenido a través de un cliente spoofeado en el canario y
  registrar CPU/temperatura vs. la telemetría ya existente en `scripts/flight-recorder.sh` antes de
  considerar un segundo equipo; medir tiempo real de recuperación de ARP tras matar el proceso de
  bettercap sin `ExecStop` (simular corte de luz) para confirmar el argumento del "dead man's
  switch" del punto 1.
