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

<!-- conformidad:inicio -->
_Generado por `deploy/cloud/conformidad.sh` (`make cloud-conformidad`) el 2026-09-12T13:18:24Z · HEAD `721c17a` · consola https://16-58-11-196.sslip.io. Se regenera entero: no editar entre los marcadores._

| Pieza | Veredicto | Evidencia |
|---|---|---|
| build de la nube | 🟢 VERDE | /api/health.build=721c17a == HEAD |
| esquema de la nube | 🟢 VERDE | estado=al_dia aplicada=0062_simulacro_aborto_por_sitio == última migración del repo (0062_simulacro_aborto_por_sitio) |
| servicios del compose en la instancia | 🟢 VERDE | 8/8 declarados corriendo (imagen :721c17a) |
| test compose↔workers | 🟢 VERDE | pytest --noconftest api/tests/test_compose_cubre_los_workers.py: 14 passed in 0.48s |
| entorno que la nube exige | 🟢 VERDE | todo en el heredoc de deploy.sh/takab-secrets.sh: Settings.REQUERIDOS_EN_PRODUCCION (8 nombres) + QUEUE_URL_BACKFILL/DLQ_URL_BACKFILL |
| bandera TAKAB_API_PUSH_FCM_APPLICATION_ARN | 🟡 AMARILLO | NO exportada en deploy.sh · ausente en /etc/takab/cloud.env de la instancia → la nube corre con el default de Settings (push real por FCM: T-7.03) |
| bandera TAKAB_API_OPENROUTER_ENABLED | 🟡 AMARILLO | NO exportada en deploy.sh · ausente en /etc/takab/cloud.env de la instancia → la nube corre con el default de Settings (decisión de la demo) |
| bandera TAKAB_API_CONSOLE_SCOPE_ENFORCED | 🟢 VERDE | exportada en deploy.sh · definida en /etc/takab/cloud.env de la instancia |
| cola de backfill | 🔴 ROJO | takab-dev-q-backfill: 0 visibles, 0 en vuelo · takab-dev-q-backfill-dlq: 1 → sin consumidor hasta que el servicio backfill corra en la nube (T-7.02); si la DLQ tiene mensajes, mirarlos antes de purgar |
| terraform plan | 🟢 VERDE | sin cambios: código == estado == AWS |
| alarmas de CloudWatch | 🔴 ROJO | en ALARM: takab-dev-dlq-telemetry → atender antes de la demo (una alarma que grita durante la demo es la que nadie mira) |
| release activa del Pi | 🟢 VERDE | release 20260910T222639Z-f19aa06: nada de lo que el gabinete ejecuta cambió desde f19aa06 (HEAD 721c17a) |
| modo prueba del Pi | ⚪ NO MEDIDO | /api/status sin test_mode.active |
| APK del Pixel | 🟢 VERDE | com.takab.ailert 0.1.0 instalado 2026-09-12 06:29:45 ≥ último cambio de mobile/ (d608685 2026-09-10T04:48:30-06:00) |

**RESUMEN:** 9 VERDE · 2 AMARILLO · 2 ROJO · 1 NO MEDIDO
<!-- conformidad:fin -->

**Dos apostillas a esa corrida, medidas después de generarla.** El «no medido» del modo prueba del gabinete era un defecto del propio script —leía la bandera con una expresión que trata el `false` como ausente, así que el caso bueno salía sin medir— y quedó corregido; a mano, el modo prueba está **desarmado**, que es lo que la demostración necesita. Y la cola de mensajes muertos del backfill creció a cuatro al desplegar el worker: no son evidencia perdida, son los informes en PDF que la propia API escribe bajo el mismo prefijo y que el worker no sabe reconocer (`T-7.05`, H-2).

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
  `takab_superadmin` en el barrido de solapes; y el **Pixel** en ese barrido (teléfono personal: el
  volcado se filtra a rótulos de la app y lo hace el integrador).
- La **hora exacta del último despliegue** de cada pieza: la nube dice su build, el Pi su release, el
  APK su fecha; ninguno dice cuándo se decidió.

---

## 5 · Lo único que la fase dejó a medias por una credencial

**Las correcciones están en `main` y NO en la nube.** El despliegue murió al renovar el estado de
terraform con `InvalidGrantException`: la caché de la sesión de AWS estaba rancia. Y conviene
subrayar cómo se ve ese fallo, porque engaña: `aws sts get-caller-identity` **responde
correctamente** con la cuenta, así que cualquier comprobación basada en él da un falso positivo;
el que falla es terraform. La salida es renovar la sesión **cerrándola primero** — `aws sso logout`
y después `aws sso login` — y repetir `make cloud-images && make cloud-deploy`, que con la caché
de imágenes caliente es cuestión de minutos.

Hasta que eso ocurra, la nube corre el commit anterior: tiene el worker de evidencia y el alcance
por rol, que es lo que esta fase le añadió de fondo, pero **no** las correcciones visuales ni el
contrato del latido. El censo lo dirá en rojo mientras sea así, que es exactamente su trabajo.

---

## 6 · Cómo terminó la fase

**Cerradas:** el censo de conformidad y su informe; el worker de evidencia corriendo en la nube (y con
él la tarea que llevaba meses abierta); las correcciones de todo lo que el censo midió, en las tres
superficies. **A medias, con su razón escrita:** el aviso real al teléfono, bloqueado en credenciales
de Firebase, con el respaldo medido en 21 s; el barrido del teléfono, porque se desconectó del USB; y
la comprobación por rol del alcance, que exige una sesión real de Cognito y llega con el acto 4 de la
demostración.

**Lo que la fase encontró y nadie había pedido buscar.** Seis cosas, y ninguna salió de leer código:

1. El worker de evidencia **nunca había corrido**: 65 mensajes esperando y cero formas de onda
   archivadas en la historia del sistema.
2. Los permisos se concedían y el gabinete no subía nada. **No era una avería**, era una carrera: el
   gabinete pide al reconectar y un permiso vence en 30 s.
3. El aviso al teléfono estaba **simulado** en la nube, y con la app en segundo plano no hay sondeo:
   el plazo no es largo, es infinito.
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
