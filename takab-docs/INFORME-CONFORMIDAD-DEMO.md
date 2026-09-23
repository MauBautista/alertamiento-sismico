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
| 1 | **El worker de backfill nunca estuvo en el compose de la nube.** `takab_api.backfill` promete correr «co-locado con los demás workers»; `deploy.sh` le exporta su cola y su DLQ; ningún servicio lo arranca. Consecuencia medida: **42 mensajes** esperando en `takab-dev-q-backfill` (0 en vuelo, DLQ vacía), **cero `.mseed`** en el bucket de evidencia (19 objetos: 17 PDF y 2 JPG) y el espectrograma del dictamen vacío en la nube | 🔴 → 🟢 | `T-7.02` — servicio `backfill` en el compose, gate post-deploy que exige que corra todo lo declarado, y el test que deriva del árbol los módulos ejecutables. **Desplegado y verificado vivo el 2026-09-12**: el worker drenó los 65 mensajes; el gabinete volvió a pedir permisos al reconectar y subió sus **siete** evidencias (`pending 0`, cero descartes, cero fallos); los siete miniSEED están en el bucket y el worker los registró uno a uno, ligados a su incidente, con cero rechazos. Es la primera vez que la cadena gabinete → permiso → subida firmada → S3 → registro funciona de punta a punta |
| 2 | **El push móvil está simulado en la nube.** `deploy.sh` no exporta las ARN de FCM/APNS; no hay platform application en SNS (`terraform output` vacío, `sns list-platform-applications` → `[]`); `push_fcm_service_account_json` no está en `local.auto.tfvars`; la app no lleva `google-services.json`. Cada job de push queda `simulated` con `sent_at` NULL. Sin push, la app se entera por sondeo: **hasta 30 s** con la app en primer plano, **sin límite** en segundo plano | 🔴 | `T-7.03` — bloqueada en las credenciales de Firebase (pendientes §4.4). **Respaldo medido el 2026-09-12** con el APK de `HEAD` en el Pixel: incidente de crisis abierto en la nube con la app en primer plano y en reposo ⇒ la pantalla «ALERTA SÍSMICA SASMEX · EVACÚE AHORA» apareció **21 s** después de `opened_at` (grabación de pantalla y fotogramas a 1 s; el sondeo en reposo es de 30 s). En segundo plano no hay sondeo: el tiempo es ilimitado hasta que la persona abre la app |
| 3 | **`console_scope_enforced` decidido y apagado.** `D-18` lo encendió; el código lo trae en `False` y el despliegue no lo exportaba. Además, **todos los usuarios web del pool traen `custom:site_scope='*'`** (7 de 8; el único acotado es un brigadista móvil), así que encenderlo hoy no recorta a nadie | 🟡 | `T-7.06` — exportado en `deploy.sh`; recorta al primer usuario acotado que se dé de alta |
| 4 | **El APK del Pixel era anterior al último cambio de `mobile/`** (instalado 2026-09-10 04:30, último commit 04:48) y **no hay sello de build** en la app: el commit instalado es indemostrable; el único proxy honesto es la fecha | 🟡 | reconstruido e instalado en F0 (esta pasada); el sello de build queda como criterio candidato de `T-7.05` |

**Dos hallazgos que ninguna ficha nombraba**, y que salieron de preguntar al sistema:

| # | Hallazgo | Veredicto | Qué se hace |
|---|---|---|---|
| 5 | **El gabinete está ciego en la red de desarrollo.** En la casa de Mauricio (`192.168.3.0/24`) el Pi cerebro está en `192.168.3.140` y el Shake en `192.168.3.139`, pero `/etc/takab/edge.env` apunta a `TAKAB_EDGE_SEEDLINK_HOST=192.168.1.107` (la red de **instalación**). Medido en `/api/status`: `seedlink.packets_seen = 0`, `reconnects = 34`, `seedlink_lag_s ≈ 41 400` (= el uptime), 24 «SeedLink desconectado» en la última hora. La nube sí lo ve (`cloud.online = true`, RTT ≈ 94 ms), el modo prueba está desarmado y los relés reportan `ok`. Es la misma trampa que el commit `3bcca05` dejó escrita el 2026-09-10 | 🔴 → 🟢 | **Corregido en el dispositivo el 2026-09-12** con el procedimiento verificado (respaldo `edge.env.bak-*`, una clave, `diff`, reinicio de `takab-edge`; `D-04`: reiniciar no mueve un relé): `SEEDLINK_HOST=192.168.3.139`, temporal para la red de casa. Medido tras el reinicio: 101 paquetes en el primer minuto, lag 0,2 s, cero reconexiones. **Al volver a la red de instalación (`192.168.1.0/24`) hay que regresarlo a `192.168.1.107`**; los runbooks se quedan con esa red, que es donde se presenta |
| 6 | **La alarma `takab-dev-dlq-telemetry` está en ALARM** con **1 mensaje** real en `takab-dev-q-telemetry-dlq`. Es la única alarma encendida (16 en OK, 0 en INSUFFICIENT_DATA) y el catálogo la marca `NEVER` (no se silencia: es el detector del canary) | 🔴 | **Mirado**: es un latido (`takab/health`) del 2026-09-10 22:27Z, emitido por el gabinete al arrancar la release `f19aa06`, con `packet_loss_pct: null` (y `mqtt_rtt_ms`, `battery_pct`, `ups_runtime_s` también `null`), rechazado porque el esquema exige número. Es un defecto de contrato —`null` es «sin dato» y no `0`— que `T-7.05` (H-1) corrige. El mensaje se leyó entero antes de tocarlo y **se borró el mismo día**, junto con los cuatro de la cola de backfill; las dos colas quedaron en cero y sus alarmas pueden volver a OK, que es lo que les devuelve la voz —solo avisan en las transiciones—. **Lo que no sobrevivió es el archivo**: se guardó en el área temporal de la sesión, que se borró al reiniciarla. Lo que queda del latido es su reconstrucción en el test de `T-7.05`, declarada como tal |

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

> **Para medir el gabinete desde la red de casa.** El censo busca al Pi en `192.168.1.0/24`, que es
> **la red donde se va a instalar**, no la de desarrollo; desde casa lo da por inalcanzable y
> escribe «no medido», que se lee como si el gabinete estuviera caído. Se le dice dónde mirar:
>
> ```
> TAKAB_PI_SSH_HOST=ailert@<ip> TAKAB_PI_PANEL_URL=http://<ip>:8080 make cloud-conformidad
> ```
>
> Y la dirección **cambia**: el 2026-09-12 el Pi pasó de `192.168.3.91` a `192.168.3.140` por DHCP.
> Se encuentra sin adivinar buscando quién contesta en el 8080 de la red (`ip neigh` lista los
> vecinos; las MAC que empiezan por `b8:27:eb` o `e4:5f:01` son Raspberry).

<!-- conformidad:inicio -->
_Generado por `deploy/cloud/conformidad.sh` (`make cloud-conformidad`) el 2026-09-22T17:18:52Z · HEAD `f63b38b` · consola https://16-58-11-196.sslip.io. Se regenera entero: no editar entre los marcadores._

| Pieza | Veredicto | Evidencia |
|---|---|---|
| build de la nube | 🟢 VERDE | /api/health.build=f63b38b == HEAD |
| esquema de la nube | 🟢 VERDE | estado=al_dia aplicada=0069_mapa_de_sacudida == última migración del repo (0069_mapa_de_sacudida) |
| servicios del compose en la instancia | 🟢 VERDE | 8/8 declarados corriendo (imagen :f63b38b) |
| test compose↔workers | 🟢 VERDE | pytest --noconftest api/tests/test_compose_cubre_los_workers.py: 15 passed in 0.45s |
| entorno que la nube exige | 🟢 VERDE | todo en el heredoc de deploy.sh/takab-secrets.sh: Settings.REQUERIDOS_EN_PRODUCCION (8 nombres) + QUEUE_URL_BACKFILL/DLQ_URL_BACKFILL |
| bandera TAKAB_API_CATALOG_USGS_ENABLED | 🟢 VERDE | deploy.sh la fija a «true» y la instancia la trae en true |
| bandera TAKAB_API_CONSOLE_SCOPE_ENFORCED | 🟢 VERDE | deploy.sh la fija a «true» y la instancia la trae en true |
| bandera TAKAB_API_OPENROUTER_ENABLED | 🟢 VERDE | deploy.sh la fija a «true» y la instancia la trae en true |
| bandera TAKAB_API_OPS_METRICS_ENABLED | 🟢 VERDE | deploy.sh la fija a «true» y la instancia la trae en true |
| bandera TAKAB_API_OPENROUTER_MODEL | 🟢 VERDE | deploy.sh la fija a «google/gemini-2.5-flash-lite» y la instancia trae ESE valor (huella sha256 aa393677798a) |
| bandera TAKAB_API_OPENROUTER_SECRET_ID | 🟢 VERDE | la salida «openrouter_secret_id» del terraform y la instancia trae ESE valor (huella sha256 247700f038d9) |
| bandera TAKAB_API_PUSH_FCM_APPLICATION_ARN | 🟢 VERDE | la salida «push_fcm_application_arn» del terraform y la instancia trae ESE valor (huella sha256 5fad9efdb9d1) |
| secreto de la capa narrativa | 🟢 VERDE | el secreto takab/dev/openrouter existe (arn:aws:secretsmanager:us-east-2:634882473845:secret:takab/dev/openrouter-XzgiiU) y la política inline del rol takab-dev-db le concede GetSecretValue |
| cola de backfill | 🟢 VERDE | takab-dev-q-backfill: 0 visibles (0 en vuelo) · takab-dev-q-backfill-dlq: 0 |
| terraform plan | 🟢 VERDE | sin cambios: código == estado == AWS |
| alarmas de CloudWatch | 🟢 VERDE | ninguna alarma en ALARM |
| release activa del Pi | 🟢 VERDE | release 20260921T220025Z-10a8b3b: nada de lo que el gabinete ejecuta cambió desde 10a8b3b (HEAD f63b38b) |
| modo prueba del Pi | 🟢 VERDE | test_mode.active=false · audio.profile: {"applied":{},"rejected":{},"test_tone":true} |
| APK del Pixel | ⚪ NO MEDIDO | sin teléfono por USB (adb get-state: nada); conecta el Pixel con depuración USB |

**RESUMEN:** 18 VERDE · 0 AMARILLO · 0 ROJO · 1 NO MEDIDO
<!-- conformidad:fin -->

### Cuál es esta corrida, y por qué ésta y no la anterior (2026-09-22)

**El bloque de arriba es el de las 17:18:52Z, y se eligió a sabiendas sobre el de las
14:42:40Z, que era mejor en el recuento.** El de las 14:42 daba **19 VERDE · 0 NO MEDIDO**; éste
da 18 y uno sin medir. Se queda éste porque los dos no se equivocan en la misma medida:

- El de las 14:42 certificaba que la nube corre **`anthropic/claude-sonnet-5`**. Eso **dejó de
  ser cierto esa misma mañana**: `T-7.26` cambió el modelo a `google/gemini-2.5-flash-lite`
  porque el anterior devolvía el contenido **vacío** —veinte segundos de latencia y cero
  caracteres, gastándose los 1 600 tokens de salida en razonar—. Leído por SSM en la instancia,
  la bandera trae hoy el modelo nuevo. Una fila verde con el modelo equivocado es una
  **afirmación invertida**, y es justo la clase de cosa que este censo existe para impedir.
- El de las 17:18 baja la fila del APK a **NO MEDIDO** por una razón que no tiene que ver con el
  sistema: el Pixel no estaba conectado por USB (`adb get-state` no devolvió nada). Eso es una
  **medición ausente, declarada**. No es un aprobado —el propio censo cuenta un NO MEDIDO como
  fallo—, pero tampoco afirma nada falso.

Una medición que falta se recupera enchufando el teléfono; una afirmación invertida viaja en el
papel que se enseña. Por eso se conserva ésta. **Y lo que la fila perdida decía, para que no se
pierda con ella:** a las 14:42 el APK `com.takab.ailert 0.1.0` estaba instalado el 2026-09-22 a
las 08:26:28, por delante del último cambio de `mobile/` (`2793be8`, 2026-09-21T15:30:51-06:00).
Ese último cambio **sigue siendo el mismo hoy**, así que el verde de aquella fila no ha caducado:
sólo no se ha vuelto a medir.

**Y no es sólo criterio: la comprobación 3 de `PLAN-REVISION-PRESENTACION-CLIENTE.md §5` lo
decide sola, y decide lo mismo.** Se corrieron sus cuatro asertos contra los dos bloques:

- Con **éste** (sello `f63b38b`) pasa entero. La fila del APK no lo tumba porque esa comprobación
  **tolera `APK del Pixel` por su nombre** —ya estaba previsto— y el aserto del sello,
  `git diff --quiet "$sello..HEAD" -- $(rutas_que_llegan_a_la_nube)`, sale limpio.
- Con el de las **14:42** (sello `3fb22a6`) **falla**, y falla por el sello: entre `3fb22a6` y
  `HEAD` cambiaron `api/src/takab_api/settings.py`, `api/src/takab_api/narrative/openrouter.py` y
  `deploy/cloud/deploy.sh` — o sea el tope, el cliente del proveedor y el modelo que exporta el
  despliegue. Los tres viajan en la imagen. Ese bloque no está sólo desactualizado en una fila:
  está **caducado por construcción**, porque se generó antes del cambio que describe mal.

**Dos cosas más que hay que saber antes de citar esta tabla.**

1. **Está generada contra `f63b38b` y `HEAD` ya avanzó a `db6684c`.** No implica que la nube vaya
   atrasada: entre los dos commits sólo cambian `api/tests/test_guion_demo.py`,
   `deploy/demo/guion.sh`, `takab-docs/TASKS.md` y `takab-docs/runbooks/RUNBOOK-demo-cliente.md`,
   y **ninguna de las cuatro viaja en las imágenes** (`api/Dockerfile` copia `api/pyproject.toml`,
   `api/alembic.ini`, `api/src`, `api/migrations`, `shared/schemas` y `shared/glossary`, y nada
   más). O sea que el código que la nube sirve es el del repositorio. Lo que hace falta no es
   redesplegar: es re-generar el papel.
2. **Hay que re-generarlo con la sesión de AWS viva, y hoy no lo estaba.** Este bloque **no se
   edita a mano** —lo reescribe entero `deploy/cloud/conformidad.sh`—, y correrlo hoy habría
   dejado algo peor que lo que hay: con la caché del SSO rancia, `terraform` muere con
   `InvalidGrantException` aunque `aws sts get-caller-identity` responda, y el censo sale
   **6 VERDE · 8 AMARILLO · 0 ROJO · 5 NO MEDIDO**. Eso no mide un sistema enfermo: mide un
   instrumento ciego. El orden correcto es `aws sso logout && aws sso login --profile takab-dev`
   —el `logout` **antes** no es adorno— y **después** `make cloud-conformidad`, con el Pixel
   enchufado para recuperar la fila 19.

**Dos apostillas a la tabla, medidas después de generarla.** El «no medido» del modo prueba del gabinete era un defecto del propio script —leía la bandera con una expresión que trata el `false` como ausente, así que el caso bueno salía sin medir— y quedó corregido; a mano, el modo prueba está **desarmado**, que es lo que la demostración necesita. Y sobre la cola de mensajes muertos del backfill: esta apostilla decía que «creció a cuatro al desplegar el worker … PDF que el worker **no sabe reconocer** (`T-7.05`, H-2)», y eso **dejó de ser verdad el 2026-09-12**, en el commit `9e67b25`. El worker los reconoce por su autor declarado (`_AJENOS_CONOCIDOS` en `api/src/takab_api/backfill/objects.py`), los descarta con acuse y manda a la cola sólo lo que no sabe de quién es. La tabla de arriba lo mide: `takab-dev-q-backfill-dlq: 0`. Se deja escrito el error en vez de borrarlo porque quien lea la DLQ vacía necesita saber que estuvo llena de PDF sanos y por qué ya no lo está.

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
| C-3 | ALTA | `/triage` · detalle abierto antes del dictamen | el detalle nunca se refresca: a los 81 s seguía «SIN DICTAMEN» con el dictamen en la base desde los 60; FIRMAR no aparece hasta cambiar de fila (sin `refetchInterval`, sin frame live de dictamen) | medido con el reloj del arnés | `T-7.05` — refresco por intervalo o frame |
| C-4 | BAJA | alta de gabinete | el acuse del gabinete no enlaza a `/console?sitio=`: la estación nueva llega al mapa sin foco | 8 clics del muro al mapa | `T-7.05` — enlace del acuse (mecanismo de `T-6.14`) |
| P-1 | BAJA | panel · MURO · 15/15 escenas | el tier a 72 px entra 2 px en «Estado del inmueble» | 304 px² | `T-7.05` |
| P-2 | MEDIA | panel · CAMPO · 15/15 escenas × 4 carriles | el nombre del canal (`EHZ`…) se pisa con la nota del carril («rms … · salud …») — la parte medible del `U-10` | 48 px² × 4 × 15 | `T-7.05` — `min-height` del carril en CAMPO |

Observaciones fuera del criterio DOM: los rótulos DEMO de los veinte sitios simulados del seed se apilan
sobre Cholula (capa de símbolos del mapa, no medible en el DOM); la píldora «CONECTADO» se recorta a
«CONECTADC» a 1280×800 sin elipsis; la franja de alerta del shell mide 43 px en las cinco rutas
secundarias y no genera solapes.

**Clics de los tres flujos** (medidos sobre `make soc-local`, sin contar login ni el aviso de privacidad): alerta →
triage → detalle → solicitud de dictamen, **2** (el informe de la reforma contó 3; la fila más severa llega enfocada);
dictamen preliminar → firma → PDF, **4 desde triage** (7 desde el muro si el operador tiene que forzar el refresco: C-3);
alta de cliente → estación → gabinete → mapa, **8** (antes el flujo se rompía en el segundo paso, `U-06`; hoy llega al
tenant correcto y al mapa, sin foco: C-4); simulacro AHORA, **3**; programar → ejecutar → acuse → historial → exportar,
**7** más la espera del reloj.

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
  `takab_superadmin` en el barrido de solapes. El **Pixel** sí entró, pero más tarde ese mismo día
  (§7.1): cuando se escribió esta lista el teléfono estaba desconectado del USB.
- La **hora exacta del último despliegue** de cada pieza: la nube dice su build, el Pi su release, el
  APK su fecha; ninguno dice cuándo se decidió.

---

## 5 · Tres tropiezos del propio despliegue, y lo que enseñan

Ninguno era del producto; los tres son del camino por el que el producto llega al sistema, y los
tres se ven igual: algo que parece estar bien y no lo está.

**La sesión de AWS caducada que responde que sí.** El despliegue murió al leer el estado de
terraform. Lo que engaña es el diagnóstico: `aws sts get-caller-identity` **devuelve la cuenta
correctamente**, así que cualquier comprobación basada en él dice que la sesión está sana; el que
falla es terraform. Y volver a entrar sin cerrar sesión primero no la arregla.

**La guarda de rama que protege de verdad.** El despliegue a la nube y al gabinete exigen estar en
la rama principal, y abortaron cuando el árbol estaba en otra. Es molesto y es correcto: lo que se
despliega tiene que ser lo que la integración vio. Ese mismo día un commit de documentación se
empujó directo a la rama principal saltándose las nueve comprobaciones —la protección no alcanza a
los administradores y el aviso llega **después**—, así que la lección es al revés de lo que parece:
la guarda del despliegue es la que queda, y conviene crear la rama **antes** de comitear.

**El censo ensucia el árbol y la siguiente release hereda la mancha.** `make cloud-conformidad`
reescribe la tabla de este documento, así que deja el árbol modificado; el despliegue al gabinete
etiqueta su release con el estado del árbol y la marcó como sucia, pese a que este documento **no
viaja al gabinete** y el código instalado corresponde exactamente a su commit. Una release que no
se puede reconstruir a partir de un commit no sirve como evidencia: se redesplegó desde limpio.

---

## 6 · El veredicto, tras desplegar

> **Leído a posteriori:** este veredicto es el de la pasada del censo, por la mañana. Los dos ámbares
> y el «no medido» se cerraron esa misma tarde — está contado en §7.1.

**Cero rojos.** El censo, corrido con la nube y el gabinete en el **mismo commit**, da 11 verdes, dos
ámbares y un «no medido». Los dos ámbares son decisiones conscientes —el aviso real al teléfono
espera credenciales, la redacción asistida está apagada hasta su fase— y el no medido es el teléfono,
desconectado del USB. Además, la consola desplegada pasa sus doce comprobaciones y la verificación
completa del repositorio está en verde: 2 386 pruebas de consola, 1 510 del gabinete, 646 de la app y
el resto.

**Un falso rojo que valió la pena entender.** El censo marcó en rojo el commit desplegado porque había
cambiado un fichero bajo la carpeta del despliegue… que **no viaja en ninguna imagen**: es la propia
herramienta del censo. Clasifica por carpeta, y ahí se pasa de celoso. Se resolvió redesplegando —con
la caché caliente son minutos— en vez de enseñarle una lista de excepciones, que es la clase de cosa
que envejece mal y acaba tapando un rojo de verdad.

---

## 7 · Cómo terminó la fase

**Cerradas:** el censo de conformidad y su informe; el worker de evidencia corriendo en la nube (y con
él la tarea que llevaba meses abierta); las correcciones de todo lo que el censo midió, en las tres
superficies. Y, esa misma tarde, **las tres que quedaban a medias**: el aviso real al teléfono, el
barrido del teléfono y la comprobación por rol del alcance. La fase cierra sin nada a medias.

### 7.1 · Las tres que se cerraron al final, y lo que costó cada una

**El aviso al teléfono sonó, con la pantalla apagada.** Es el primer push entregado en la historia
del producto: antes había cinco «simulados» y dos fallidos, y ninguno había despertado nada. El
registro del teléfono deja la prueba que importa —pantalla apagada y bloqueada, la app **congelada**
por el sistema— y el aviso la descongeló, encendió la pantalla y se pintó. Para llegar ahí hubo que
cazar **tres defectos que ningún test podía ver sin un teléfono de verdad**:

1. **El rol podía crear el destino pero no escribirle.** Amazon autoriza el envío a un teléfono
   contra la *aplicación* de notificaciones, no contra el destino concreto, y el permiso solo
   cubría lo segundo. Resultado: el destino se creaba sin problema y el envío rebotaba. Tres
   intentos, aviso fallido, silencio.
2. **El canal sísmico y la prioridad alta se perdían en la traducción.** El mensaje viajaba en el
   formato antiguo, y al convertirlo se **descarta el bloque de Android entero** — justo donde
   viven las dos cosas que distinguen una alerta de una notificación cualquiera: el canal que salta
   el «No molestar» y suena con el tono de TAKAB, y la prioridad que entrega de inmediato aunque el
   teléfono esté dormido. El aviso llegaba, sí, y se pintaba… en el canal de reserva y en prioridad
   normal. Es la regla de oro 7 en su forma más cara: todo verde, y la alerta no era una alerta.
3. **El error que se guardaba no servía para arreglar nada:** el nombre de la excepción, sin decir
   qué llamada rebotó ni el motivo. Diagnosticarlo costó abrir una sesión contra el servidor.

Y un cuarto, del propio banco de pruebas: **el arnés de staging no producía ningún aviso y nadie lo
notaba**. Sus comandos mueven la fase que la app deduce **cuando pregunta**, y con la app detrás no
pregunta nadie; se podía ensayar una crisis entera sin que sonara un teléfono. Ahora hay un comando
que sí pide un pase de lista, y su prueba se escribe contra la consulta real del notificador.

**El barrido del teléfono: 0 parejas encimadas**, en ocupante (inicio, crisis, check-in) y en
brigadista (panel y sus seis pestañas). La herramienta habitual **no sirve en una pantalla viva** —
espera a que la ventana quede quieta y la de crisis redibuja el cronómetro cada segundo, así que
falla en silencio y se lee como «la pantalla no llegó». Y el filtro por aplicación no es cortesía:
el teléfono es personal, y un volcado sin acotar arrastró la persiana de notificaciones del dueño.

**El alcance por rol recorta de verdad**, medido con una sesión real de consola: con alcance total,
dos inmuebles; acotado a Puebla, uno. **La primera medición dijo que no recortaba, y era falsa:**
recargar la página no renueva la credencial —el navegador reutiliza la que ya tenía, con el permiso
viejo dentro—. Hace falta pedir una nueva, y la renovación relee los atributos sin exigir otro
código al operador.

**Lo que la fase encontró y nadie había pedido buscar.** Seis cosas, y ninguna salió de leer código:

1. El worker de evidencia **nunca había corrido**: 65 mensajes esperando y cero formas de onda
   archivadas en la historia del sistema.
2. Los permisos se concedían y el gabinete no subía nada. **No era una avería**, era una carrera: el
   gabinete pide al reconectar y un permiso vence en 30 s.
3. El aviso al teléfono estaba **simulado** en la nube, y con la app en segundo plano no hay sondeo:
   el plazo no es largo, es infinito. Cerrado esa misma tarde (§7.1), con tres defectos más debajo.
4. El gabinete estaba **ciego** en la red de desarrollo porque su configuración apunta al sensor por
   dirección fija.
5. Un latido con «sin dato» **moría en la cola de mensajes muertos** y dejaba una alarma encendida, que
   es peor que apagada: una alarma que lleva días gritando ya no avisa de nada.
6. El propio censo tenía un defecto que daba «no medido» justo en el caso bueno.

**Y una lección de método que vale más que cualquiera de las seis.** Las correcciones se revisaron con
un lector adversario por área, cuyo trabajo era refutar y no felicitar. **Rechazó las cinco.** El peor
defecto que encontró no estaba en lo que se arregló mal, sino en lo que parecía bien arreglado: la
solución al solape reservaba altura para la tarjeta de alerta y la **recortaba en silencio**, dejando
fuera de pantalla la línea que dice quién originó la alerta. Ningún test lo veía, la hoja de estilos
afirmaba por escrito lo contrario, y habría llegado a una demostración delante de un cliente.

Tres rondas después, la tercera midió lo que las dos anteriores habían supuesto y encontró que **un
criterio de la propia ficha era falso**: pedía «cero solapes» en una superficie donde nadie había
contado. Se enmendó la ficha en lugar de maquillar la cifra, y el residuo quedó vigilado por una prueba
que avisa en cada corrida y que **cae el día que alguien lo arregle**, para que una ficha no sobreviva a
su defecto.
