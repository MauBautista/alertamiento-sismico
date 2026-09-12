# Informe de conformidad para la demostración — ¿lo que está en código está en el sistema?

> **Qué es esto.** El resultado de la **Fase F0** del
> [`PLAN-PROTOTIPO-FUNCIONAL.md`](PLAN-PROTOTIPO-FUNCIONAL.md) (ficha `T-7.01`): un veredicto por
> pieza, **derivado de comandos y no de lectura**, de si lo que el repositorio promete está corriendo
> en la nube dev, en el gabinete de Puebla y en el teléfono. Cada 🔴 nombra la ficha que lo cierra.
>
> **Cómo se regenera.** `make cloud-conformidad` corre `deploy/cloud/conformidad.sh` (solo lee:
> `/api/health`, `compose ps` por SSM, la cola de backfill, `terraform plan`, las alarmas, la release
> activa del Pi y el APK del Pixel) y refresca la tabla de §2 entre sus marcadores. **Sale 0 solo con
> todo VERDE**; un NO MEDIDO es un fallo salvo `CONFORMIDAD_FLAGS=--permitir-no-medido`, y ni así se
> pinta de verde. Lo que no se midió no se aprueba.
>
> **Criterio.** 🟢 VERDE = el código y el sistema coinciden **y se ejercitó** (una llamada real, un
> `docker ps`, un `readlink` en el Pi). 🟡 AMARILLO = coinciden por lectura, o degradación con razón
> escrita, o una bandera apagada por decisión. 🔴 ROJO = el código lo promete y el sistema no lo corre
> (o al revés). NO MEDIDO = no se pudo alcanzar, con el porqué.
>
> **Primera pasada: 2026-09-11/12**, sobre `main` en `6da7108`, nube en `e68a89e`, gabinete en la
> release `20260910T222639Z-f19aa06`, Pixel 8 Pro real. Tres censos (nube · edge · móvil) más el
> barrido de solapes con la alerta en pantalla (`T-7.04`).

---

## 1 · Lo que se encontró, en una página

**Cuatro cosas que el código promete y el sistema no hacía**, y lo que se hizo con cada una:

| # | Hallazgo | Veredicto al arrancar | Qué lo cierra |
|---|---|---|---|
| 1 | **El worker de backfill nunca estuvo en el compose de la nube.** `takab_api.backfill` promete correr «co-locado con los demás workers»; `deploy.sh` le exporta su cola y su DLQ; ningún servicio lo arranca. Consecuencia medida: **42 mensajes** esperando en `takab-dev-q-backfill` (0 en vuelo, DLQ vacía), **cero `.mseed`** en el bucket de evidencia (19 objetos: 17 PDF y 2 JPG) y el espectrograma del dictamen vacío en la nube | 🔴 | `T-7.02` — servicio `backfill` en el compose, gate post-deploy que exige que corra todo lo declarado, test `test_compose_cubre_los_workers.py` que deriva los módulos ejecutables del árbol |
| 2 | **El push móvil está simulado en la nube.** `deploy.sh` no exporta las ARN de FCM/APNS; no hay platform application en SNS (`terraform output` vacío, `sns list-platform-applications` → `[]`); `push_fcm_service_account_json` no está en `local.auto.tfvars`; la app no lleva `google-services.json`. Cada job de push queda `simulated` con `sent_at` NULL. Sin push, la app se entera por sondeo: **hasta 30 s** con la app en primer plano, **sin límite** en segundo plano | 🔴 | `T-7.03` — bloqueada en las credenciales de Firebase (pendientes §4.4); en esta fase se mide y declara el respaldo |
| 3 | **`console_scope_enforced` decidido y apagado.** `D-18` lo encendió; el código lo trae en `False` y el despliegue no lo exportaba. Además, **todos los usuarios web del pool traen `custom:site_scope='*'`** (7 de 8; el único acotado es un brigadista móvil), así que encenderlo hoy no recorta a nadie | 🟡 | `T-7.06` — exportado en `deploy.sh`; recorta al primer usuario acotado que se dé de alta |
| 4 | **El APK del Pixel era anterior al último cambio de `mobile/`** (instalado 2026-09-10 04:30, último commit 04:48) y **no hay sello de build** en la app: el commit instalado es indemostrable; el único proxy honesto es la fecha | 🟡 | reconstruido e instalado en F0 (esta pasada); el sello de build queda como criterio candidato de `T-7.05` |

**Dos hallazgos que ninguna ficha nombraba**, y que salieron de preguntar al sistema:

| # | Hallazgo | Veredicto | Qué se hace |
|---|---|---|---|
| 5 | **El gabinete está ciego en la red de desarrollo.** En la casa de Mauricio (`192.168.3.0/24`) el Pi cerebro está en `192.168.3.140` y el Shake en `192.168.3.139`, pero `/etc/takab/edge.env` apunta a `TAKAB_EDGE_SEEDLINK_HOST=192.168.1.107` (la red de **instalación**). Medido en `/api/status`: `seedlink.packets_seen = 0`, `reconnects = 34`, `seedlink_lag_s ≈ 41 400` (= el uptime), 24 «SeedLink desconectado» en la última hora. La nube sí lo ve (`cloud.online = true`, RTT ≈ 94 ms), el modo prueba está desarmado y los relés reportan `ok`. Es la misma trampa que el commit `3bcca05` dejó escrita el 2026-09-10 | 🔴 | decisión de Mauricio: apuntar `edge.env` al Shake de la red donde esté el gabinete (o a un nombre estable) y reiniciar `takab-edge` (`D-04`: reiniciar no mueve un relé). Los runbooks se quedan con la red de instalación `192.168.1.0/24`, que es donde se presenta |
| 6 | **La alarma `takab-dev-dlq-telemetry` está en ALARM** con **1 mensaje** real en `takab-dev-q-telemetry-dlq`. Es la única alarma encendida (16 en OK, 0 en INSUFFICIENT_DATA) y el catálogo la marca `NEVER` (no se silencia: es el detector del canary) | 🔴 | mirar el mensaje antes de purgar o redirigir; una alarma que grita durante la demo es la que nadie mira |

**Lo que coincide y se ejercitó** (🟢): build de la nube (`e68a89e`, dos commits por detrás y los dos
solo documentos); esquema `0062` al día; `terraform plan` sin cambios (código = estado = AWS); Hosted UI
de Cognito aplicado (logo servido y 929 bytes de CSS para `ALL`); el modo prueba del WR-1 desarmado; las
dos unidades del gabinete activas y habilitadas (`takab-edge`, `takab-gpio`; `takab-cctv` no existe, como
manda `D-25`) con `NRestarts = 0`; la release del Pi `f19aa06` es **byte-idéntica** a `HEAD` en todo lo
que el gabinete ejecuta (`edge/takab_edge`, `deploy/edge`, `edge/systemd`, `shared/`); ninguna
configuración ni runbook apunta ya a la subred vieja `192.168.3.91/.92` (solo las dos actas fechadas);
el canal de notificación `seismic_alert_v2` con el tono propio empaquetado.

**Banderas del gabinete leídas de `edge.env`** (para el guion de la demo, no son defectos):
`DEV_MODE=false`, `COMMAND_ENABLED=true` (acepta comandos firmados de la nube), `AUDIO_SIREN_ENABLED=true`
(sirena por jack), `GPIO_OWNER=gpio` (el dueño de los pines es la unidad aparte, `D-04`), PIN del panel
provisionado. `INSTRUMENTAL_ACTUATION` y `AUDIO_ENABLED` ausentes ⇒ `False` (solo aviso visual; sin voceo).

---

## 2 · La tabla viva

La regenera `make cloud-conformidad`. Lo de aquí abajo entre marcadores es la última corrida; lo de
arriba es la interpretación y no se regenera.

<!-- conformidad:inicio -->
_Pendiente de la primera corrida completa con credenciales de AWS renovadas; la pasada del 2026-09-11
(solo lectura, `--permitir-no-medido`) dio **4 VERDE · 5 AMARILLO · 3 ROJO · 2 NO MEDIDO**: los tres
rojos son el compose sin `backfill`, la cola de backfill con 42 mensajes y la alarma de la DLQ de
telemetría; los dos no medidos son el Pi, entonces fuera de la red._
<!-- conformidad:fin -->

---

## 3 · Solapes y flujo con la alerta EN PANTALLA (`T-7.04`)

El barrido anterior (`layout.spec.ts`) toleraba que la alerta «pudiera no estar» y pasaba en verde con
la consola en reposo. Ahora la fuerza (`POST :9100/sasmex` sobre `make soc-local`) y barre las seis
pantallas por tres viewports en las escenas `normal` y `alert`; la escena `review` no existe todavía
(llega en F3, `T-7.16`) y queda declarada como pendiente, no fingida. Resultado de la corrida con la
escena puesta: **48 pasan, 24 fallan, 18 pendientes**; los 24 fallos son exactamente los dos defectos de
abajo, en los tres viewports. El panel del gabinete se barrió en sus **15** escenas (la ficha decía 13;
`simulacro_abortado` y `prueba_actuadores_en_curso` entraron después) por tres modos.

| Id | Sev. | Dónde | Qué se encima | Medida | Va a |
|---|---|---|---|---|---|
| C-1 | ALTA | `/console` · `alert` · 1280×800, 1440×900, 1920×1080 | la tarjeta de alerta (arriba-derecha) tapa las leyendas y la botonera de CAPAS del mapa (abajo-derecha): nombre del sitio sobre CATÁLOGO/ENLACE/ONDAS, «PGA MAX» sobre la leyenda del enlace, la atribución sobre las filas de la leyenda | 9 parejas a 1280 y 1440 (hasta 821 px²), 2 a 1920; contenedores: 74 160 px² | `T-7.05` — partir de verdad la columna derecha bajo alerta; nunca con z-index |
| C-2 | BAJA | `/triage`, `/tenants`, `/audit` · ambas escenas · 3 viewports | la caja del valor del KPI (`--tk-text-2xl`, `line-height: 1`) invade 3 px la del rótulo; la tinta no se toca hoy porque los valores son dígitos | 51–102 px² por pantalla | `T-7.05` — `line-height` o `gap` del `.soc-kpi` |
| P-1 | BAJA | panel · MURO · 15/15 escenas | el tier a 72 px entra 2 px en «Estado del inmueble» | 304 px² | `T-7.05` |
| P-2 | MEDIA | panel · CAMPO · 15/15 escenas × 4 carriles | el nombre del canal (`EHZ`…) se pisa con la nota del carril («rms … · salud …») — la parte medible del `U-10` | 48 px² × 4 × 15 | `T-7.05` — `min-height` del carril en CAMPO |

Observaciones fuera del criterio DOM: los rótulos DEMO de los veinte sitios simulados del seed se apilan
sobre Cholula (capa de símbolos del mapa, no medible en el DOM); la píldora «CONECTADO» se recorta a
«CONECTADC» a 1280×800 sin elipsis; la franja de alerta del shell mide 43 px en las cinco rutas
secundarias y no genera solapes. Conteo de clics de los tres flujos: en el censo del lote B
(`scratchpad`, §5), al cierre de esta pasada.

**Trampa medida que vale para la demo:** una alerta SASMEX queda **enclavada** en el gabinete; el
segundo pulso del WR-1 **no abre incidente** hasta que alguien pulsa CERRAR ALERTA (`POST /api/reset`).
Dos pulsos seguidos sin cerrar enseñan **una** alerta.

---

## 4 · Lo que esta pasada NO midió, y por qué

- El estado de la ventana del **modo demostración** en la tabla `demo_mode`: `GET /api/demo-mode`
  exige JWT y `/dev/token` no se monta en la nube a propósito. Se mide con sesión de consola en F1.
- La tabla **`evidence_objects`** de la nube: exige túnel a la base. El bucket sí se listó.
- El **`/etc/takab/cloud.env` materializado** en la instancia se leyó por SSM en la corrida del script
  (nombres, no valores); las banderas de push, OpenRouter y alcance estaban ausentes.
- El **brigadista** en el pool táctico y los códigos de enrolamiento en Postgres (solo se contó el pool
  de ocupantes: 1 usuario).
- **Texto en canvas o en SVG**, pseudo-elementos, menús abiertos, modales y roles distintos de
  `takab_superadmin` en el barrido de solapes; y el **Pixel** en ese barrido (teléfono personal: el
  volcado se filtra a rótulos de la app y lo hace el integrador).
- La **hora exacta del último despliegue** de cada pieza: la nube dice su build, el Pi su release, el
  APK su fecha; ninguno dice cuándo se decidió.
