# SafeLock — Diagnóstico de apagones y bricking de unidades de campo

**Fecha:** 2026-06-19 · **Autor:** Equipo técnico · **Audiencia:** Supervisión / dirección
**Estado:** causa raíz aún no *probada* (ver §1); mitigaciones en marcha (ver §4).

---

## 0. Resumen ejecutivo

Varias unidades SafeLock en campo **se apagan sin aviso y no vuelven a encender**, ni siquiera tras desconectar y
reconectar la energía. La última cayó el **2026-06-19 ~02:36 de la madrugada**. Queda **1 unidad sana** (la de
referencia/golden), que es idéntica a la flota y sobre la que estamos trabajando.

El cuadro completo apunta a una **combinación de dos factores** más que a una sola falla:

1. **Un disparador físico** (lo más probable: **caída de tensión / fuente de alimentación marginal**), que provoca el
   apagón súbito; y
2. **Una falta de resiliencia del software** ante ese corte (sin auto-reparación de disco, escrituras frecuentes,
   actualizaciones automáticas nocturnas), que convierte un simple apagón en **corrupción permanente → "no enciende"**.

Las unidades ya muertas requieren **reflasheo físico** (no hay recuperación remota hoy). Lo que sí podemos hacer —y ya
está en marcha— es **evitar que caigan más** y **dejar evidencia** para probar la causa raíz.

---

## 1. Por qué no se pudo "probar" la causa hasta ahora

Las unidades guardaban sus registros (logs) en **memoria RAM volátil**, no en disco. Cuando una se apaga de golpe,
**toda la evidencia del momento del fallo se pierde**. Por eso hasta ahora solo teníamos síntomas, no pruebas.

**Ya corregido:** instalamos un "registrador de vuelo" (*flight recorder*) que graba en disco cada 60 s la
**temperatura, frecuencia, voltaje y señales de caída de tensión (*throttling/under-voltage*)**. La próxima unidad que
falle **dejará rastro del instante del corte** → con eso confirmaremos o descartaremos el brownout de forma definitiva.

---

## 2. Causas posibles (ordenadas por probabilidad)

| # | Causa | Qué explicaría | Indicios a favor | Cómo se confirma / descarta |
|---|-------|----------------|------------------|------------------------------|
| 1 | **Fuente de alimentación marginal / brownout** (caída de tensión 5 V) | El apagón súbito "de la nada" en varias unidades con la **misma fuente** | El SoC RK3566 + 4 contenedores Docker + red pueden superar el amperaje de una fuente de baja calidad; los picos coinciden con el patrón | **Telemetría de voltaje** (ya desplegada) + **probar fuente 5 V ≥3 A** de calidad |
| 2 | **Corrupción de eMMC / sistema de archivos por corte no limpio** | El **"no vuelve a encender"** (el apagón en sí no rompe; el sistema corrupto sí) | En cada arranque los logs salían corruptos; **no había auto-reparación de disco**; escritura constante | Auto-reparación al arrancar (*fsck*, ya activada) + el flight recorder |
| 3 | **Actualizaciones `apt` automáticas nocturnas** (disparador/amplificador) | La **hora** (2:36 a.m.) y el carácter **"de la nada"** (es desatendido) | `apt` programado con retardo aleatorio de hasta 12 h → puede correr de madrugada; *unattended-upgrades* activo; sin bloqueo de kernel en la flota | **Mitigado** (ver §4); se observa si cesan los fallos nocturnos |
| 4 | **Upgrade de kernel/arranque desatendido** que deja una imagen que no bootea | "No enciende" **sin** corte de energía de por medio | La imagen base es una *nightly* (de desarrollo); un paquete nuevo puede no arrancar; sin bloqueos | **Bloqueo (*hold*)** de kernel/u-boot + desactivar auto-upgrade (ver §4) |
| 5 | **Pérdida de red (no apagón real)**: la unidad está **viva pero inalcanzable** | Casos de "dejó de responder" pero el equipo podría estar encendido | Un script congelaba la IP como estática; si la red cambia, la unidad queda invisible | ¿Aparece en el router/DHCP o en Tailscale? ¿Responde la luz de Ethernet? (ver §5) |
| 6 | **Térmico / desgaste de memoria / falta de espacio** | — | — | **Descartado** por evidencia previa: eMMC sana, sin sobrecalentamiento al momento, sin disco lleno, sin falta de memoria |

> **Lectura recomendada para dirección:** las causas **#1 y #2 son las principales y se combinan**: la fuente provoca el
> apagón, y la falta de resiliencia lo vuelve permanente. **#3 y #4** son disparadores nocturnos que ya neutralizamos.
> **#5** es importante porque **algunas unidades "muertas" podrían estar vivas pero sin red** (recuperables sin reflasheo).

---

## 3. Lo que sabemos con certeza

- Los apagados son **cortes NO limpios** (no hay un apagado ordenado de por medio).
- **Ningún script del producto** ejecuta `reboot`/`shutdown` ni entra en bucle de reinicio — **no es un error de software
  que apague el equipo**; el apagón viene de afuera (energía) o de una corrupción.
- La memoria eMMC está **sana** (no es desgaste).
- Sin **acceso físico** a las unidades de campo y con la **imagen de flasheo solo en poder del dueño**, las unidades ya
  muertas son hoy **irrecuperables en remoto**.

---

## 4. Mitigaciones ya implementadas (validadas en la unidad de referencia)

1. **Auto-reparación de disco al arrancar** (`fsck.repair`) → ataca directamente el "no vuelve a encender" por corrupción.
2. **Menos datos en riesgo por corte** (intervalo de escritura de 120 s → 15 s).
3. **Bloqueo del kernel/arranque** (`hold`) → impide que un upgrade desatendido deje un sistema que no bootea.
4. **Corte del `apt` automático nocturno** (sospechoso de las 2:36): timers de actualización desactivados + cron
   neutralizado. Las actualizaciones del sistema pasan a hacerse de forma **controlada**, no desatendida de madrugada.
5. **Registrador de vuelo forense** → evidencia del próximo fallo (voltaje/temperatura) para **probar la causa raíz**.
6. **Watchdog de hardware** → auto-recuperación ante cuelgues.
7. **Acceso al panel robusto** (nombre `safelock-<id>.local` + Tailscale) en lugar de IP estática frágil.
8. **Mecanismo de entrega**: todas estas correcciones de sistema ahora pueden llegar a las unidades vivas por
   actualización remota (antes no era posible), de forma idempotente y segura.

> **Importante:** estas correcciones **aún no están desplegadas en la flota** — están listas y validadas en la unidad de
> referencia, pendientes del despliegue controlado (ver §6).

---

## 5. Acciones para el equipo en sitio (clasificar cada unidad muerta)

Para cada unidad caída, anotar:
- **Señales de vida al energizar:** ¿LED encendido/color?, ¿se siente tibia?, ¿la luz del puerto Ethernet parpadea?,
  ¿muestra algo por HDMI si se conecta a una pantalla?
- **Red:** ¿aparece en el router/DHCP con una IP?, ¿responde a *ping*?, ¿figura *online* en Tailscale?
- **Prueba clave:** **conectar una fuente distinta de buena calidad (5 V ≥3 A)** y reintentar.
- **Contexto:** ¿hubo apagón eléctrico en el sitio?, ¿se cambió de red o de router?, ¿estaba actualizándose?
- **Recuperación:** ¿hay una PC con cable USB disponible? (necesaria para el reflasheo asistido).

> Si la unidad **enciende pero no aparece en red** → probablemente viva pero aislada (caso #5): recuperable.
> Si **no da señales de vida** con otra fuente → corrupción de arranque (caso #2): requiere reflasheo.

---

## 6. Recomendaciones a dirección

1. **Hardware (alta prioridad):** estandarizar y enviar una **fuente de alimentación de calidad (5 V ≥3 A)**. Es la
   defensa más directa contra el disparador #1 y barata frente al costo de unidades perdidas.
2. **Despliegue por fases:** aplicar las mitigaciones primero a **1–2 unidades "canario"** y observar 24–48 h antes de
   ir a toda la flota (el cambio de acceso por IP a nombre/Tailscale debe verificarse por unidad).
3. **Recuperación de unidades muertas:** definir logística para hacer llegar la **imagen + guía de reflasheo** a alguien
   con acceso físico, o **enviar unidades de reemplazo pre-flasheadas**.
4. **Producción nueva (medio plazo):** migrar de la imagen *nightly* (desarrollo) a una **imagen estable y fija**, y
   evaluar un esquema de **arranque con respaldo (A/B)** para que las unidades futuras se auto-recuperen sin reflasheo.

---

## 7. Actualización 2026-07-14 — muerte de la unidad maestra y blindaje por software

**Qué pasó:** tras varias idas de luz en el sitio, la **unidad maestra/golden** (la de referencia sobre la que se
construyó la imagen) **se apagó y ya no enciende: sin ningún LED**. Ese síntoma —cero señales de vida— apunta a
**hardware de alimentación** (la fuente de pared o la etapa de poder de la placa), no a software: el endurecimiento
anti-corrupción no puede salvar una fuente muerta. Es coherente con la causa raíz #1 (fuentes marginales que se degradan
con los picos al volver la luz). La unidad es **recuperable** porque la imagen golden está respaldada fuera del equipo.

**Confirmación de que el anti-brick funciona:** una unidad clon viva sobrevivió **dos cortes eléctricos sucios** (9 y 14
de julio) sin dañarse — arrancó sola, se auto-reparó el disco y los 4 servicios quedaron sanos. El blindaje de software
hace su trabajo; lo que falla es la energía.

**Nuevo objetivo: que las cajas vivan lo más posible.** Como el disparador es físico, se aplicó **todo lo posible desde
software para reducir el estrés que degrada el hardware** (validado en la unidad viva, horneable en la imagen y
entregable por actualización remota):

1. **Techo de CPU + arranque suave de frecuencia** (governor *conservative*, máximo 1.8 → 1.416 GHz). El mayor gatillo de
   muerte de fuentes es el **pico de corriente** cuando la CPU salta a máxima velocidad de golpe; ahora sube gradual y
   con tope. Menos corriente pico y menos calor, **sin impacto** en el servicio (el trabajo de red usa una fracción de la
   CPU).
2. **Radios apagadas** (Bluetooth/WiFi que el producto no usa): menos consumo, menos calor interno, menos superficie de
   ataque.
3. **Menos escritura a la memoria** (fuente de corrupción ante cortes): se silenció un componente que escribía ~4.800
   líneas/hora de registro, se acotaron los registros del sistema y de los contenedores (antes crecían **sin límite** y
   llenaban el disco). Menos escritura = menos ventanas en las que un corte puede corromper + menos desgaste.
4. **Reloj estable** (sincronización horaria que ya no depende de sí misma) → la evidencia forense queda con hora fiable.
5. **Espacio de disco corregido:** un error de aprovisionamiento dejaba a las unidades nuevas usando **9 GB de 29 GB**
   (se habrían llenado en semanas); corregido en la unidad viva y en el script de fábrica.

**Sigue siendo indispensable el hardware (recomendación #1 de §6):** **fuente de calidad 5 V ≥3 A** + protección contra
picos al volver la luz. El software alarga la vida y evita que un corte se vuelva permanente, pero **no sustituye** una
fuente decente.

**Pendiente evaluado (fase v2):** raíz de solo-lectura (*overlay*) — es el blindaje definitivo contra cortes de energía
en casas con luz inestable, pero es un cambio mayor y se planifica aparte para no arriesgar la unidad viva.

---

*Este documento se actualizará en cuanto el registrador de vuelo capture el primer fallo y permita confirmar la causa raíz.*
