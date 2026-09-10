# Plan de reforma visual — de lo que se midió a lo que se puede enseñar

> **De dónde sale.** De [`INFORME-UIUX.md`](INFORME-UIUX.md), la auditoría UI/UX del **2026-09-06**
> sobre `main` en `2e0c02d`. Cada ficha cierra uno o varios hallazgos `U-nn` de allí; la ficha
> es el estado vivo, el informe es la foto.
>
> **Bloque de numeración: `T-6.xx`, y no colisiona con nada.** Verificado antes de escribirlo:
> `takab-docs/TASKS.md` no contiene ninguna ocurrencia de `T-6.`; los máximos vivos son `T-2.172`,
> `T-3.16`, `T-4.05` y `T-5.29`. Las 31 fichas van de `T-6.01` a `T-6.31`. **Por mandato del
> encargo (§10.1) esta sesión no las inserta en `TASKS.md`**: cuando se inserten, hay que tocar la
> cabecera de conteo en el mismo commit, porque un test la verifica.
>
> **Una superficie por sesión, una ficha por sesión.** Cada ficha declara su superficie (Consola,
> Móvil, Panel o Costura —la costura son las fichas de API/edge sin las cuales una superficie no
> puede dejar de mentir—), su sesión, qué tests de censo toca, si necesita un token nuevo y si
> cambia algo que un test defiende hoy. Si un test de censo se pone rojo al ejecutarla, **el test
> casi siempre tiene razón**: se escribe por qué no antes de tocarlo.
>
> **Los cinco principios del §3 del prompt siguen vigentes en todas las fichas:** el movimiento
> nunca es el único portador de estado; ninguna animación retrasa la lectura de una alerta; la
> animación más valiosa es la que se detiene; cero peticiones externas en el panel; todo valor
> visual sale del token. **Ninguna ficha escribe un color, tamaño o espaciado con valor:** nombra
> el token que ya existe en `shared/design-tokens/tokens.json` o pide uno nuevo con su nombre
> semántico, y ese se añade al paquete, se regenera y se documenta.
>
> **Estimación en sesiones de Claude Code**, no en horas: una sesión = plan, tests primero, bucle
> hasta verde, y PR con los siete checks.

---

## 1 · La ruta a la primera exposición

`PLAN-V1-COMERCIAL.md §1` ya separó la ruta a la primera exposición de la ruta al primer cliente.
Esta auditoría añade lo que **la pantalla** hace mentir hoy delante de un prospecto, y de nuevo
**todo es software**:

```
EXPOSICIÓN-UI  =  T-6.17 ∧ T-6.19 ∧ T-6.01 ∧ T-6.02 ∧ T-6.04 ∧ T-6.03 ∧ T-6.20 ∧ T-6.27 ∧ T-6.28
```

Nueve fichas, ninguna espera a un humano ni a una ventana de AWS. Tres son de móvil, una de
costura, tres de consola y dos de panel. Lo que el prospecto vería sin ellas: un teléfono que
anuncia un simulacro que ningún edificio ejecuta, un brigadista que no sabe que es un ensayo, una
consola que en cinco de seis pantallas no dice que hay alerta, un distintivo de MFA sin dato, una
cola de incidentes que hace pasar por reales los sitios simulados, un alta de sitio que aterriza
en el tenant equivocado, un botón de emergencia de 29 dp, un panel cuyo PIN está bajo el pliegue y
una demo del gabinete que dice «SIRENA: SONANDO» con el relé en reposo.

---

## 2 · Las tres tandas

### Tanda 1 — lo que impide presentar · 11 fichas · 14 sesiones

Una pantalla que miente, un simulacro que no es lo que dice, o un rol que ve de más o de menos.

| Ficha | Qué cierra | Superficie | Sesiones |
|---|---|---|---|
| `T-6.17` | El rechazo y el aborto del simulacro no viajan; `active` es un reloj | Costura | 2 |
| `T-6.19` | La app anuncia simulacros inexistentes y el brigadista no ve nada | Móvil | 1 |
| `T-6.01` | Alerta, simulacro, mantenimiento y demo solo se ven en `/console` | Consola | 2 |
| `T-6.02` | «AUTH · MFA» sin dato; enlaces y botones que prometen de más | Consola | 1 |
| `T-6.03` | El alta de sitio ignora al cliente recién creado | Consola | 1 |
| `T-6.04` | La marca DEMO es parcial dentro de la misma pantalla | Consola | 1 |
| `T-6.05` | El gate del LOGIN DEV es una línea que nadie lee | Consola | 1 |
| `T-6.20` | Objetivos táctiles por debajo del mínimo en pantallas de vida | Móvil | 1 |
| `T-6.27` | La botonera del panel bajo el pliegue; carriles ilegibles en CAMPO | Panel | 1 |
| `T-6.28` | Escenas demo que afirman una sirena que no suena; checklist desfasado | Panel | 1 |
| `T-6.29` | El panel no puede pintar el aborto (condición inalcanzable) | Panel | 1 |

### Tanda 2 — lo que mejora la venta · 15 fichas · 19 sesiones

Lo que un cliente nota en la primera reunión, o lo que hará mentir una pantalla en la siguiente
fase (`T-2.89`).

| Ficha | Qué cierra | Superficie | Sesiones |
|---|---|---|---|
| `T-6.06` | Vacíos que culpan al tenant; cola sin `error`/`stale`; caja en blanco del modo demo | Consola | 1 |
| `T-6.07` | Arranque con tres silencios: sin pantalla, splash mudo, expiración muda | Consola | 1 |
| `T-6.08` | El login es la pantalla de fábrica de AWS | Consola (+ terraform) | 2 |
| `T-6.09` | 171 nodos sin contraste AA; `watch`/`normal` solo por tono | Consola | 2 |
| `T-6.10` | Movimiento honesto: reducción parcial, latido que no es de frescura, filas que aparecen sin aviso | Consola | 2 |
| `T-6.11` | El aviso de privacidad se lleva el mapa | Consola | 1 |
| `T-6.14` | El flujo alerta → dictamen pierde el contexto dos veces | Consola | 1 |
| `T-6.16` | El reporte de simulacro no es presentable ante Protección Civil | Costura | 1 |
| `T-6.18` | Dos arneses que ya no ejercen lo que prometen | Costura | 1 |
| `T-6.21` | 44 literales de color en las pantallas de crisis del móvil | Móvil | 1 |
| `T-6.22` | Pestañas del brigadista sin gate por acción | Móvil | 1 |
| `T-6.23` | Sin push, la crisis llega por sondeo de 30 s y volver del fondo no refresca | Móvil | 1 |
| `T-6.24` | El dato retenido del ocupante es una franja sobre el reloj de Android | Móvil | 1 |
| `T-6.30` | El pulso de vida del panel no se pinta y no se detiene | Panel | 1 |
| `T-6.31` | Dos variables CSS inexistentes; el nombre del relé ilegible en MURO | Panel | 1 |

### Tanda 3 — lo que es gusto · 5 fichas · 8 sesiones

Casi todo lo estético está aquí, y está bien que así sea.

| Ficha | Qué cierra | Superficie | Sesiones |
|---|---|---|---|
| `T-6.12` | El título gana al dato; 59 declaraciones bajo el piso tipográfico; KPI a dos tamaños | Consola | 2 |
| `T-6.13` | Sin primitivas de tabla, tarjeta ni botón | Consola | 3 |
| `T-6.15` | Fuentes y mapa desde internet; el cian con cinco significados | Consola | 1 |
| `T-6.25` | `reduceMotion` inexistente en el móvil; el hold de pánico sin portador; latido táctico | Móvil | 1 |
| `T-6.26` | Identificadores crudos en pantalla; el prompt cuenta 12 pantallas donde hay 21 | Móvil | 1 |

**Total: 31 fichas · 41 sesiones.** Los totales salen de sumar las columnas de las tres tablas;
un total tecleado a mano acaba divergiendo.

---

## 3 · Por qué el corte está donde está

**La tanda 1 no es «lo urgente»: es lo que hace que una superficie afirme algo falso.** Un
teléfono que dice «SIMULACRO EN CURSO» en un edificio que rechazó el simulacro (U-01) es la misma
familia de defecto que el «● LIVE» con el SOC mudo de `T-2.59`: una pantalla que dice «bien»
cuando quiere decir «no sé». Todo lo demás de la tanda es del mismo tipo: un distintivo de
seguridad sin dato, una cinta DEMO que falta justo donde el prospecto mira, un alta que escribe
en el cliente equivocado sin decirlo, y una demo del gabinete que se contradice a sí misma. La
única ficha de la tanda que no es de honestidad es `T-6.20`: un botón de 29 dp en la pantalla de
vida es un fallo de uso, no de estética.

**La tanda 2 es lo que un cliente nota o lo que mentirá pronto.** El login de fábrica de AWS
(`T-6.08`) y el aviso de privacidad de 170 px encima del mapa (`T-6.11`) son lo primero que se ve
en una demo; el contraste (`T-6.09`) es lo que un operador de turno largo sufre; y los vacíos que
culpan al tenant (`T-6.06`) mienten el día que `T-2.89` active el alcance —esa ficha va **antes**
del apply, nunca después.

**La tanda 3 es gusto, y se dice así.** Unificar tablas, tarjetas y botones, bajar títulos y
subir datos, alojar fuentes en local: mejoran el producto, no impiden enseñarlo ni venderlo. Van
al final y se hacen por bloque, con captura antes y después, porque `layoutInvariants.test.ts`
fija paddings y alturas que dependen de esos tamaños.

---

## 4 · Hallazgos que NO llevan ficha nueva

| Hallazgo | Dónde vive ya | Nota |
|---|---|---|
| **U-47** · el Pi sirve una release sin isotipo ni favicon | despliegue del edge (`deploy/edge/deploy.sh`), `PENDIENTES-MAURICIO.md §3` | No es defecto del panel: la release del 2026-08-30 es anterior a los commits de marca. Se despliega antes de una demo. |
| **U-17** en su mitad de fondo (qué cambia con el alcance) | `T-2.89` | La ficha `T-6.06` prepara los vacíos; activar el alcance sigue siendo `T-2.89`. |
| **U-18** en su mitad de identidad (gestión de usuarios) | `T-2.87` | El copy y el splash son `T-6.07`; los usuarios simulados no. |
| **U-36** en su mitad de push | `T-2.97` y altas administrativas (`PENDIENTES-MAURICIO §4`) | `T-6.23` acorta el sondeo; que llegue el push es alta de proveedor. |
| **U-29** en su mitad de tiempos y exportación | `T-5.14` (cerrada) | Los tiempos por sitio y el PDF ya existen; lo que queda (nombre, `stop_reason`, porqué) es `T-6.16`. |
| El rechazo del gabinete al comando de simulacro | regla de oro 8 y `command_enabled` apagada de fábrica | **Correcto y no se toca.** Lo que se ficha es que la superficie lo refleje (`T-6.17`, `T-6.19`). |
| El modo demostración que suprime comandos firmados | `D-27` | Correcto. La consola ya lo declara; `T-6.01` lo lleva a las demás pantallas. |
| La escala tipográfica del panel por debajo del piso | `ESPECIFICACION-PANEL-GABINETE.md §10.2` (deuda declarada) | Es decisión de producto ratificar o pagar; esta auditoría solo toca MURO (`T-6.31`). |

---

## 5 · Lo que se decide NO hacer

Un plan de rediseño sin lista de descartes es una lista de deseos.

1. **No sustituir el Hosted UI de Cognito por un formulario propio.** Prohibido por el encargo
   (§4.4, §10.2) y con razón técnica: la constancia de MFA de la regla de oro 8 se sostiene en el
   `iss` del pool; reimplementar el reto TOTP con `T-2.87` abierto es riesgo sin beneficio.
2. **No rediseñar el panel del gabinete.** Ni la jerarquía de banners (§9, invariante), ni los
   cinco rótulos de tier (congelados por test), ni la botonera, ni el veto de recursos externos, ni
   el PIN en memoria. Las fichas de panel corrigen lo que contradice **su propia** spec.
3. **No animar nada en el camino de lectura de una alerta.** `AlertBanner`, `#banner-alert` y
   `CrisisView` están limpios y ninguna ficha los toca. La única animación nueva en el panel es el
   latido que la spec ya declara, y solo si se detiene cuando el dato envejece.
4. **No migrar a Reanimated «porque está instalado».** Lo que falta en el móvil es el portador de
   estado y la consulta de `reduceMotion`, no una librería. Migrar es rendimiento, no diseño.
5. **No subir el alto de la tira de simulacro de la consola.** El e2e la fija por debajo del
   umbral por una regresión real («el botón ocupa 3/4 de pantalla»); lo que se mejore cabe en ancho.
6. **No añadir `is_demo` al contrato del servidor.** `datosDeDemostracion.ts` ya razonó que sería
   una segunda verdad; la cola y el detalle solo tienen que importar la función que existe.
7. **No saltar la landing y redirigir directo al Hosted UI.** Lo primero que vería el cliente sería
   la pantalla de AWS, el `returnTo` viaja en `location.state`, y con Cognito caído no habría
   dónde leer el error.
8. **No mover un valor anclado de `designTokens.test.ts`** (el cian operativo entre ellos). Donde
   hace falta un significado nuevo se añade un **nombre** nuevo, no se cambia el valor.
9. **No relabelar literales congelados por test** (`fail-safe fail_close`, los tiers, «DEMO · NO
   ES ESTADO REAL», «SIN ENLACE — PROTECCIÓN LOCAL ACTIVA»). Donde el test defiende lo contrario
   de una idea, gana el test.
10. **No reordenar los flujos de vida del móvil** (crisis → check-in → bloqueo de reingreso;
    pánico; acuse). Licencia MEDIA: se pule y se anima, no se reordena sin ficha propia.
11. **No rellenar `staleSince={null}` en los marcos incompletos** ni añadir excepciones a las
    listas vacías de `screenStateCensus`. Cada marco necesita su reloj y su umbral.
12. **No convertir el ámbar de la alarma del inmueble en el ámbar de estado del paquete sin
    más.** Cambiaría el color de una pantalla acreditada en el Pixel; lo correcto es añadir la
    familia al paquete con los valores actuales y consumirla.
13. **No poner `color-contrast` como regla bloqueante de golpe.** Primero se mide por pantalla con
    el reporte adjunto (ya se hizo: 171 nodos, una regla) y se sube la barra pantalla a pantalla.
14. **No crear tabla `drill_acks` ni convertir `stop_reason` en enum.** El acuse derivado por
    JOIN es una superficie menos que firmar; `stop_reason` es texto y `aborted`/`rejected` son
    valores aditivos.
15. **No unificar la escala tipográfica de la consola «a ojo».** Diecinueve tamaños distintos
    contra ocho escalones de token: se hace por bloque, con captura antes y después.

---

## 6 · Fichas · Costura (API + edge)

### [x] T-6.17 · **El rechazo y el aborto de un simulacro viajan a la nube y a las superficies** — `SOFTWARE`

> Hoy `active` es una ventana de reloj: un gabinete que rechaza o aborta el comando no cambia
> nada, y el móvil solo recibe `active`. Medido el 2026-09-06 con un simulacro real: dos rechazos
> honestos en la consola, franja «SIMULACRO EN CURSO» en el teléfono los tres minutos.

- **Superficie:** Costura · **Sesión:** X1 (dos sesiones: edge+API, luego contrato)
- **Componente:** edge (`drill`, `dispatch`, `cloud`) + api (`routers/drills.py`, `schemas/drills.py`, `ws/protocol.py`, `routers/mobile_site.py`) · **Depende de:** nada · **Prioridad: ALTA**
- **Cierra:** U-01 (mitad nube), U-03
- **Tests de censo que toca:** `web/src/serverFrameCensus.test.ts` (un frame WS nuevo debe enrutarse en el SDK y en la consola; el censo se pondrá rojo hasta que se cablee, y tiene razón); drift gate de OpenAPI y SDK (`make drift`).
- **Token nuevo:** no.
- **Cambia algo que un test defiende hoy:** sí — `edge/tests/test_local_api_panel.py:850-856` fabrica un estado (`active` y alerta a la vez) que el nuevo contrato hace imposible; se reescribe para leer `aborted`.
- **Objetivo:** que la nube sepa, por acuse del gabinete, si el simulacro está sonando, fue rechazado o fue abortado, y que `MobileDrillOut` y `DrillOut` lo expongan.
- **Criterios de aceptación:**
  - [x] `abort()` publica un acuse con `drill_id`, `aborted`, `abort_reason` y sello; el rechazo ya acusa y se conserva.
  - [x] La API cierra la fila con `stop_reason='aborted'` al recibirlo y expone `aborted`, `abort_reason` y el `command_status` por sitio en `DrillOut`; `MobileDrillOut` deja de ser solo `active`: declara cuántos gabinetes lo ejecutan.
  - [x] Un frame WS de drill llega a la consola sin esperar el sondeo de 10 s; `serverFrameCensus` en verde con el frame enrutado.
  - [x] Test de punta a punta: drill → aborto en el edge → la fila queda cerrada y `GET /drills/active` devuelve `null` antes de que venza la ventana.
  - [x] Un simulacro con todos los sitios en `rejected` no es `active` para el móvil.
- **Cómo se cerró (2026-09-06, SESIÓN 2):**
  - **Sin topic ni regla IoT nuevos.** El aborto viaja como un **segundo `CommandAck`** por
    `takab/acks` con `results.aborted`, `abort_reason`, `aborted_at` y `drill_id`, con el mismo
    `command_id`/`nonce` del `drill_start` (`edge/takab_edge/drill/__init__.py` recibe un
    `on_abort` y `edge/takab_edge/dispatch/__init__.py` lo cablea). Así no se toca terraform ni
    la política de flota, que es la trampa de la Fase 1.8.
  - **El aborto es por SITIO**, no por simulacro: `drill_sites.aborted_at/abort_reason`
    (migración `0062`). El simulacro solo se cierra con `stop_reason='aborted'` cuando ningún
    sitio sigue `pending` o `acked` sin abortar: el vecino que sigue sonando no se apaga en la
    consola por el rechazo de otro. La ingesta (`ingest/handlers.py`) lo reconoce aunque el
    comando ya esté `acked`, y aplica las dos cosas si el aborto llega ANTES que el acuse de
    arranque (SQS no ordena). Reentrega idempotente; auditoría `drill_site_aborted`.
  - **`DrillOut`** gana `aborted`, `abort_reason`, `executing` y `sites[].aborted_at/abort_reason`;
    **`MobileDrillOut`** gana `execution` (`executing`/`pending`/`rejected`/`expired`/`aborted`/
    `no_gateway`/`none`), `sites_total` y `sites_executing`, y `active` pasa a significar «el
    gabinete de ESTE sitio acusó y no abortó». Con dos gabinetes en `rejected`, la app ya no dice
    EN CURSO (`api/tests/api/test_mobile_core.py`).
  - **WS:** triggers `takab_notify_drill*` en `drills`, `drill_sites` y `commands` → frame
    `drill` (sin lectura en el hub, topic de incidentes). La consola lo enruta en
    `shared/sdk-ts/src/ws.ts`, `serverFrameCensus` lo censa y `useActiveDrill` invalida las tres
    consultas; el sondeo de 10 s se conserva como respaldo. Los suscriptores con alcance de sitio
    no lo reciben (el frame no lleva `site_id`, default-deny): siguen por sondeo.
  - **Consola:** estado `aborted` en `drill.ts` (rótulo «ABORTADO POR ALERTA REAL», cuenta como
    acusado Y abortado), el historial ya no rotula EJECUTADO a un simulacro cortado, y el banner
    dice rechazados y abortados en vez de esconderlos en el «0/2 ACUSADOS».
  - **Lo que NO se tocó, a propósito:** `edge/tests/test_local_api_panel.py:850-856` sigue igual —
    el panel del gabinete no se tocó en esta sesión (es `T-6.29`, la de la superficie panel);
    la ficha lo daba por reescrito aquí y no lo estaba: la app y la consola ya leen el aborto;
    el panel lo pintará cuando le toque su sesión. Y `T-6.19` (la app cuenta gabinetes) ya tiene
    el dato en el contrato.

### [x] T-6.16 · **El reporte de simulacro se puede entregar a Protección Civil** — `SOFTWARE`

> El PDF se titula con el UUID del cliente, no dice cómo terminó el simulacro y no explica por qué
> faltó cada acuse; la consola sí distingue `rejected` de `pending`. `T-5.14` ya puso tiempos y
> exportación; esto es lo que quedó.

- **Superficie:** Costura · **Sesión:** X2
- **Componente:** api (`drill_report.py`, `routers/drills.py`) + web (`DrillHistory.tsx`) · **Depende de:** ~~nada~~ `T-6.17` para imprimir `aborted` · **Prioridad: MEDIA**
- **Cierra:** U-29
- **Tests de censo que toca:** ninguno; se amplía `api/tests/api/test_drill_report.py` (el determinismo del sello no se toca).
- **Token nuevo:** no.
- **Cambia algo que un test defiende hoy:** no.
- **Objetivo:** cabecera con el nombre del cliente y del sitio, línea de cierre (`stop_reason` legible: manual, ventana cumplida, cancelado, abortado por alerta real) y, por cada sitio sin acuse, la causa que la consola ya conoce.
- **Criterios de aceptación:**
  - [x] El PDF nombra cliente y sitios; jamás imprime un UUID donde hay nombre.
  - [x] Imprime cómo terminó y, por sitio, `rechazado` / `sin gabinete comandable` / `sin acuse`.
  - [x] Dos PDFs del mismo modelo producen los mismos bytes (test existente sigue verde).
  - [x] La pestaña reservada al exportar muestra el documento o un error legible; nunca queda en blanco.
- **Cómo se cerró (2026-09-09, SESIÓN X2):**
  - **El documento lleva nombres.** La cabecera se titulaba con el uuid del cliente y cada sitio sin
    nombre salía como ocho caracteres de su uuid —que se leen como si fueran un nombre—. Ahora el
    nombre sale de `tenants`/`sites` y, si falta, se cae al **código** (lo que el operador teclea y
    reconoce); solo si no hay ninguno de los dos se rotula «SITIO SIN NOMBRE REGISTRADO (…)» con el
    identificador para poder buscarlo. La consulta del nombre del cliente va aparte y no como JOIN
    en `_DRILL_COLS`, que la comparten cinco endpoints que no lo necesitan.
  - **Dice cómo terminó.** Línea `CIERRE` con `stop_reason` en castellano —detenido por el
    operador, abortado por una alerta real (con su motivo), cancelado antes de ejecutarse, agenda
    ejecutada, cerrado sin motivo registrado— y, sin cerrar, la ventana que corre desde el inicio.
    **No mira el reloj**, y eso no es un detalle: decir «en curso» o «ventana cumplida» según la
    hora de quien exporta daría bytes distintos en dos exportaciones del mismo simulacro y el
    sha256 registrado dejaría de probar nada.
  - **Y dice por qué faltó cada acuse.** El documento colapsaba los tres casos en un guion mientras
    la consola sí los distinguía. Ahora: `RECHAZADO POR EL GABINETE — <la razón que él mismo dio>`
    (el `detail` del acuse: `command_enabled=false`, `demo_mode`…), `EXPIRADO — la orden venció`,
    `SIN ACUSE — la orden salió y el gabinete no contestó` y `SIN GABINETE COMANDABLE — no había a
    quién mandarle la orden`. Un rechazo es accionable y un silencio no: reaccionar igual a los dos
    es no haber leído el reporte.
  - **El sitio que acusó y luego abortó lo dice en su línea** (T-6.17): cuenta como acuse —lo fue— y
    debajo lleva `ABORTADO hh:mm:ss UTC — motivo`.
  - **La pestaña reservada ya no es un `about:blank`.** Se reserva dentro del gesto porque la URL
    presignada no existe todavía, y se quedaba en blanco los ~10 s que tarda el servidor en generar,
    sellar y firmar: una pestaña vacía que aparece sola no se distingue de un fallo y quien la ve la
    cierra. Ahora escribe la espera al reservarse y, si la petición falla, **esa misma pestaña
    declara el motivo** en vez de cerrarse de golpe. Vale para el reporte y para el dictamen, que
    tenían el mismo hueco.
  - **Medido:** PDF de ejemplo con los cinco casos (acuse, acuse+aborto, rechazo con razón, silencio
    y sin gabinete) rasterizado y revisado a ojo; de paso se corrigió un rótulo que no cabía en la
    columna de 52 mm y pegaba el número al texto («SITIOS SIN GABINETE COMANDABLE» → «SITIOS SIN
    GABINETE»; la categoría se explica entera en la línea de cada sitio).
  - **Verificación:** `tests/api/test_drill_report.py` con 29 (8 nuevos, incluido el del endpoint
    que intercepta el render para leer el MODELO — el texto del PDF no se puede raspar: va
    comprimido y por glifos); los 4 ficheros de simulacros del `api`, 77; web 2 170, con 7 nuevos
    de `download.test.ts`; `ruff` y `prettier` limpios.

### [x] T-6.18 · **Los dos arneses vuelven a ejercer lo que prometen** — `SOFTWARE`

> El sembrador de staging reutiliza el incidente `d4000000…` y ya no produce la toma de crisis;
> `make soc-local` emite un simulacro con «5 SIN COMANDO EMITIDO», así que el aborto no se puede
> ensayar en local.

- **Superficie:** Costura · **Sesión:** X3
- **Componente:** `infra/scripts/seed_staging_incident.sh`, `demo/soc_local.py` · **Depende de:** nada · **Prioridad: MEDIA**
- **Cierra:** U-37
- **Tests de censo que toca:** ninguno; `make demo-fase1` ya tiene la bajada por spool y sirve de modelo.
- **Token nuevo:** no.
- **Cambia algo que un test defiende hoy:** no.
- **Objetivo:** que cada corrida del sembrador use un incidente fresco (y limpie el anterior) y que el SOC local entregue los comandos firmados al gabinete simulado.
- **Criterios de aceptación:**
  - [x] `PHASE=crisis` produce `alert_active` en el teléfono aunque el incidente anterior tenga dictamen firmado.
  - [x] En `make soc-local`, un simulacro sobre el sitio simulado llega al panel `:8080` como `drill.active=true` y un `/quake` lo aborta de forma visible.
- **Cómo se cerró (2026-09-09, SESIÓN X3):**
  - **El sembrador abre un incidente FRESCO por corrida.** El id era una constante, así que
    `crisis` REABRÍA el mismo incidente; en cuanto una corrida pasaba por `reentry`, ese incidente
    se quedaba con un dictamen firmado —`dictamens` es append-only— y la derivación, que busca el
    dictamen POR INCIDENTE, devolvía `reentry_approved` para siempre. Ahora `crisis` cierra lo
    abierto del sitio y abre uno nuevo; los demás subcomandos resuelven el incidente abierto en vez
    de dar por hecho el suyo. `INCIDENT_ID=<uuid>` sigue permitiendo fijarlo.
  - **Y el sembrador entró en CI, que es lo que impide que se vuelva a pudrir.** Su SQL vive ahora
    en `infra/scripts/sql/staging-incident/*.sql` —una sola copia— y
    `api/tests/api/test_seed_staging_incident.py` corre ESOS ficheros contra la base de tests,
    comprobando la fase por el **endpoint real** que lee la app. La cadena del defecto
    (crisis → reentry → crisis ⇒ `alert_active`) es un test; con el id constante de antes se pone
    rojo, medido. Se compara además la réplica en SQL que el script imprime contra el endpoint en
    las cuatro fases: dos derivaciones de la misma regla que nadie comparaba.
  - **El SOC local ya entrega los comandos firmados al gabinete.** La API se levantaba tal cual y
    su publicador es el de AWS IoT Core: en una laptop sin credenciales cada comando moría al
    publicar y el simulacro salía con «SIN COMANDO EMITIDO». `demo/api_local.py` sustituye **solo**
    esa dependencia por el `SpoolCommandPublisher` que ya existía (T-5.29) y deja el envelope
    firmado en el buzón del thing; el gabinete lo recibe por `--downlink` y lo verifica su
    `CommandDispatcher` REAL. La firma no se salta: la clave sale del mismo sitio para las dos
    mitades, y el buzón también, porque si divergieran el comando iría a un directorio que nadie
    lee sin un solo error en ningún log. Un test estático en `demo/tests/` lo amarra.
  - **De paso quedó a la vista una defensa que funciona.** El primer intento acabó en
    `rejected · command_enabled=false`: el comando llegó, **la firma se verificó** y el gabinete lo
    rechazó porque de fábrica no ejecuta lo que le mande la nube. Ese default no se toca; el arnés
    lo enciende a propósito y lo DECLARA al arrancar (`--sin-comandos` devuelve el gabinete de
    fábrica).
  - **Ensayado de punta a punta en local** (2026-09-09): simulacro disparado por la API →
    `command_id` emitido → acuse `acked · «simulacro iniciado»` → el panel `:8080` pinta
    `drill.active=true` con `elapsed_s` → `POST :9100/quake` → `aborted:true`,
    `abort_reason: "tier instrumental restricted"`, `aborted_at` y `aborted_age_s`, y el aborto
    **vuelve a la nube** en el segundo acuse (`drill_sites.aborted_at`). Medido en Chromium: el
    banner ámbar «SIMULACRO ABORTADO — HUBO UNA ALERTA REAL (…)» visible, 53 px de alto bajo la
    cabecera, cero errores de página. Es la primera vez que el aborto de T-6.29 se ejerce entero
    fuera de los tests, y era justo lo que U-37 impedía.
  - **Lo que NO se ejerció:** el sembrador contra la nube de staging, porque su túnel SSM pide la
    ventana de AWS y el SSO estaba caducado. Lo que sí corre en cada PR es su SQL contra el mismo
    esquema, con la fase leída del endpoint real; lo único que queda sin cubrir es el túnel.
  - **Verificación:** suite `api` completa en verde (incluidos los 4 tests nuevos del sembrador) y
    `demo/tests` con 43; `ruff check` y `ruff format --check` limpios.

## 7 · Fichas · Consola SOC

### [x] T-6.01 · **La escena vive en el shell: alerta, simulacro, mantenimiento y demo en las seis pantallas** — `SOFTWARE`

> Los cuatro banners son hijos de `ConsolePage` con dos booleanos a mano; el shell solo monta el
> aviso de privacidad. En `/fleet`, `/triage`, `/tenants`, `/audit` y `/building` no hay rastro de
> que la nube no avisa a nadie ni de que el edificio vocea.

- **Superficie:** Consola · **Sesión:** C1 (dos sesiones: tabla y censo, luego las franjas)
- **Componente:** web (`shell/AppShell.tsx`, `components/`, `features/console/*Banner.tsx`) · **Depende de:** nada · **Prioridad: ALTA**
- **Cierra:** U-04, U-28, U-45
- **Tests de censo que toca:** `web/src/statePrecedenceCensus.test.ts` (bloque nuevo de ESCENA, hermano del de dato), `web/src/styles/layoutInvariants.test.ts` (el shell gana una fila; el test vigila las filas de `.soc-main` y **se pondrá rojo**: se actualiza con la razón escrita), `web/src/serverDataCensus.test.ts` (los banners cambian de dueño).
- **Token nuevo:** no (ámbar de simulacro, violeta de mantenimiento y cian discontinuo de demo ya existen).
- **Cambia algo que un test defiende hoy:** sí — `layoutInvariants` sobre las filas del shell; `DrillBanner.test.tsx` sobre la degradación por `hasLiveIncident`, que pasa a decidirse por la tabla.
- **Objetivo:** una tabla `SCENE_PRECEDENCE` (alerta real > simulacro > mantenimiento > demo > normal) en el mismo espíritu que `STATE_PRECEDENCE`, una franja de una línea en el shell que la pinta en las seis rutas, y un censo que impida a cualquier pantalla decidir la escena por su cuenta. La excepción escrita se conserva: el mantenimiento **no** se degrada bajo alerta.
- **Criterios de aceptación:**
  - [x] Con alerta real, simulacro, mantenimiento o modo demostración vivos, las seis rutas lo declaran en el primer frame y sin animación.
  - [x] El badge «LA ALERTA REAL DOMINA» solo aparece con un incidente que **autoriza** (SASMEX o cuórum), nunca con un aviso instrumental.
  - [x] En escena NORMAL no hay franjas que digan que no pasa nada: el estado normal es la ausencia de franja, con el botón de simulacro donde ya está.
  - [x] El censo de escena falla si un componente lee `drill`, `maintenance` o `demo_mode` para pintar escena fuera de la tabla.
- **Cómo se cerró (2026-09-07, SESIÓN C1, en una sola sesión):**
  - **La tabla:** `web/src/features/scene/scene.ts` — `SCENE_PRECEDENCE = alert > notice > drill >
    maintenance > demo` (NORMAL no está en la tabla: es la ausencia), `resolveScene` como único punto
    de decisión, `DEGRADES_UNDER_ALERT` con la excepción ESCRITA (solo el simulacro se degrada; el
    mantenimiento, la demo y el aviso, no), `authorizes` (SASMEX o cuórum, nada más) y `sceneAlert`
    (el crítico más relevante de la cola). `notice` es nuevo y necesario: un aviso instrumental o una
    activación manual se declaran, pero no mandan sobre nada.
  - **La franja:** `features/scene/SceneStrip.tsx`, montada por `AppShell` como PRIMER hijo del
    `<main>` (una alerta se lee antes que un aviso legal). Es el único componente que lee las cuatro
    fuentes; los tres banners se mudaron a `features/scene/` y reciben el dato por prop (ya no llaman
    hooks). La alerta viaja como una línea (`AlertLine`: titular honesto de `alertHeadline`, sitio,
    EVENT_ID, «IR AL MONITOREO»); `/console` conserva su tarjeta detallada. Cada fuente trae su marco
    con los cuatro estados; un fallo de lectura del simulacro no calla al mantenimiento.
  - **La ausencia mide cero:** `StateFrame` ganó `silentEmpty` — la ausencia FRESCA se materializa
    (`data-state="empty"`, los censos y `expectFourStates` la ven) pero va `hidden`; la ausencia VIEJA
    (`stale`+`empty`) se pinta siempre y fechada (T-2.79.d intacta). Con eso las dos franjas
    permanentes de U-45 desaparecen sin tocar la tabla de estados.
  - **El shell ganó su fila:** `privacy.css` pasa a `auto auto minmax(0, 1fr)`; `.soc-scene` clavada
    a la 1, el aviso de privacidad por auto-colocación en la 2, la página clavada a la 3.
    `layoutInvariants` y `AppShell.layout.test` se actualizaron con la razón; ahora fijan además que
    ninguna regla `.soc-scene*` anima y que `.soc-stateframe[hidden]` gana al `display: grid`.
  - **Lo que se quedó en `/console`:** `features/console/DrillControls.tsx` (INICIAR SIMULACRO,
    HISTORIAL, el modal; `drill-idle` < 60 px como mide el e2e de T-1.62). Y `AlertBanner` gana
    `data-authorizes` desde la tabla: un aviso ya no viste la carcasa roja ni la sombra de la alerta
    (`.soc-alert[data-authorizes="false"]` en ámbar) — la otra mitad de U-28.
  - **El censo:** `web/src/sceneCensus.test.ts`. Quién LEE (cierre de productores del censo de dato
    con las cuatro fuentes como únicos transportes, `soloPropios`) se compara por igualdad contra
    cuatro lectores con razón escrita (la franja, la cola del wall, los botones, la administración de
    ventanas); quién PINTA se deriva de los imports de valor que cruzan la frontera de
    `features/scene/` (solo `SceneStrip` al shell, `sceneAlert` a la consola y `authorizes` a la
    tarjeta). La franja cuelga del shell y no de la consola (`arbolDeLaPagina`), y el literal del
    badge existe en un solo fichero. `serverDataCensus` cuadró de nuevo (`DrillControls` y
    `SceneStrip` con su razón; `critical` dejó de pintarse fuera del marco del wall).
  - **Roles:** `/maintenance-windows` lo leen cuatro roles; a los demás la API contesta 403. En vez
    de duplicar la regla en el cliente, `useMaintenanceWindows` la modela como `forbidden` (sin
    reintento ni sondeo) y la franja no pinta un REINTENTAR imposible en seis pantallas.
  - **En el wall no hay eco de la alerta** (`WALL_ROUTE`): la tarjeta ya está anclada al escenario y
    el mapa manda. Medido en `make soc-local` a 1280×800 con un aviso abierto y el aviso de privacidad
    pendiente: la línea (42 px) dejaba el escenario en 265 px y los sobrepuestos del mapa se pisaban;
    sin ella, 307 px — lo mismo que `main`. `data-scene` sigue diciendo la escena en el wall.
  - **Verificación:** vitest (133 ficheros, 2 086 tests), eslint, prettier y `vite build` en verde;
    `SceneStrip.routes.test` monta el árbol real de rutas y exige la franja en las seis, y solo una.
    Playwright contra `make soc-local`: a 1280×800 fallan los mismos siete que fallan en `main` con la
    misma base local (aviso de privacidad pendiente + un incidente crítico que la auditoría dejó
    abierto el 2026-09-06: `layout:19/70/108`, `screens:508` y `573`×2, `smoke:50`), comprobado
    guardando los cambios con `git stash` y repitiendo esos tests sobre `main`; `screens:601` (01) pasa
    ahora y fallaba en la línea base. A 1920×1080, 16/17 con el mismo `layout:19` de `main`.

### [x] T-6.02 · **Ningún distintivo afirma lo que la consola no sabe; ningún enlace promete lo que el rol no tiene** — `SOFTWARE`

> «AUTH · MFA» es un literal del mockup pintado en verde junto al botón de acuse en toda sesión,
> incluida la de desarrollo. «IR A FLOTA EDGE» manda al inspector a «SIN ACCESO». Dos botones de
> `/tenants` están apagados sin decir por qué.

- **Superficie:** Consola · **Sesión:** C2
- **Componente:** web (`IncidentTable.tsx`, `TriageDetail.tsx`, `tenants/`) · **Depende de:** nada · **Prioridad: ALTA**
- **Cierra:** U-05, U-38
- **Tests de censo que toca:** `web/src/serverDataCensus.test.ts` solo si el distintivo pasa a leer un campo nuevo de `/me` (entonces es dato de servidor fuera del marco y el censo lo exigirá dentro, con razón).
- **Token nuevo:** no.
- **Cambia algo que un test defiende hoy:** sí — `IncidentTable.test.tsx` y `screens.spec.ts:573` (que hoy falla por los dos botones).
- **Objetivo:** retirar el distintivo o respaldarlo con un dato real del token (`iss` del pool); condicionar el enlace a `allowed_routes`; dar `title` a todo botón apagado.
- **Criterios de aceptación:**
  - [x] Ninguna sesión sin constancia real de MFA pinta «MFA»; una sesión de `/dev/token` no pinta nada.
  - [x] `inspector` y `building_admin` no ven un enlace a `/fleet`; ven el dato que el enlace prometía o su ausencia declarada.
  - [x] `screens.spec.ts` «los apagados dicen por qué» en verde en las seis pantallas.
- **Cómo se cerró (2026-09-07, SESIÓN C2):**
  - **El distintivo dice lo que se sabe, y sólo eso.** `web/src/auth/authEvidence.ts` sigue la
    doctrina que ya había escrito la API (`auth/mfa.py`, RO-8.c): el ID token de Cognito no lleva
    `amr` ni `acr` —ni un Lambda propio puede fabricarlos—, así que **no certifica que esta sesión
    presentó el factor**; certifica el POOL (`iss`), y el pool principal exige TOTP
    (`mfa_configuration = ON`, anclado en terraform). Por eso: sesión dev ⇒ nada; sesión del pool
    principal ⇒ «AUTH · POOL PRINCIPAL · MFA OBLIGATORIO» con la grieta que AWS documenta en el
    `title` (el primer inicio de una cuenta nueva sale sin TOTP); otro pool o token ilegible ⇒
    «AUTH · COGNITO» sin afirmar MFA. `IncidentTable` lo recibe como prop (`null` = nada) y
    `ConsolePage` lo alimenta desde el almacén de sesión. Verificado en `make soc-local`: con
    `/dev/token` la palabra MFA no aparece en la pantalla.
  - **El enlace obedece a `allowed_routes`.** `TriageDetail` gana `canOpenFleet`, que `TriagePage`
    deriva del `/me` como los guards. Sin la ruta, la nota del miniSEED declara la ausencia y a quién
    pedir la verificación («Su rol no accede a FLOTA EDGE: pida al operador de flota…»). No se le
    pinta el dato del enlace de la estación: sacarlo aquí exigiría una lectura más en la pantalla de
    firma, que el censo de frescura vigila panel a panel, y la ficha admite la ausencia declarada.
  - **Todo apagado dice por qué.** `ConfirmButton` gana `title` (el hueco que faltaba). FIRMAR
    DICTAMEN explica su gate (`sign_dictamen`; el superadmin no firma): era el botón mudo que tumbaba
    `screens.spec` en `/triage` con un incidente abierto. El pie de `/tenants` tiene un porqué por
    estado (`syncFooterTitles`, con su test), los interruptores de canales reciben el gate de edición
    (`edit_thresholds` o tenant ajeno), y las tiras transitorias (crear, guardar, volver, verificar,
    cargar más) también lo dicen.
  - **Verificación:** vitest (135 ficheros, 2 107 tests), eslint, prettier, tsc y `vite build` en
    verde. Playwright contra `make soc-local` con la misma base que ayer (incidente abierto):
    «los botones vivos responden y los apagados dicen por qué» **6/6 pantallas** a 1280×800, donde
    en `main` fallaban `03` y `04`.

### [x] T-6.03 · **Dar de alta un sitio dice y elige en qué cliente se escribe** — `SOFTWARE`

> El formulario de estación no tiene campo de cliente y la API resuelve el tenant del JWT: el
> sitio del cliente recién creado aterriza en el tenant del operador, sin aviso. La API ya acepta
> `tenant_id` para roles internos.

- **Superficie:** Consola · **Sesión:** C3
- **Componente:** web (`fleet/FleetAdmin.tsx`, `fleet/SiteForm.tsx`) · **Depende de:** nada · **Prioridad: ALTA**
- **Cierra:** U-06
- **Tests de censo que toca:** `web/src/serverDataCensus.test.ts` (`FleetAdminPanel` cambia su lista de identificadores fuera del marco si gana un selector de cliente).
- **Token nuevo:** no.
- **Cambia algo que un test defiende hoy:** sí — `FleetAdmin.test.tsx` sobre el cuerpo del `POST /sites`.
- **Objetivo:** para roles internos, un selector de cliente en el alta de estación con rótulo permanente «escribiendo en …»; para roles de tenant, el rótulo solo.
- **Criterios de aceptación:**
  - [x] Crear cliente → crear estación deja el sitio en el cliente nuevo, y `/console` lo muestra al elegir ese cliente.
  - [x] El formulario declara siempre en qué cliente escribe; un rol de tenant no puede elegir otro.
  - [x] El flujo completo (cliente → sitio → gabinete → mapa) tiene un test que recorre las tres pantallas.
- **Cómo se cerró (2026-09-07, SESIÓN C3):**
  - **El defecto era peor que «aterriza en el tenant del operador».** Medido en vivo contra
    `make soc-local`: el superadmin —el único rol que crea clientes— recibía del `POST /sites`
    un **400 «tenant_id es obligatorio para roles internos TAKAB»** (la API ya exigía nombrar el
    cliente), y la consola lo traducía con el mensaje del **retiro** («NO COINCIDE · el
    identificador que escribiste…»). No podía crear una estación, y nada le decía por qué. Para
    un `tenant_admin` sí aterrizaba en el suyo, sin rótulo.
  - **El servidor dice quién debe elegir.** `GET /me` publica `is_internal` (derivado de
    `auth/matrix.INTERNAL_ROLES`, que se movió allí desde `routers/_common` y ahora también lo
    usa el hub WS). La consola no adivina por el nombre del rol: `FleetAdmin` y `UsersCard` leen
    `me.is_internal`. El exportador de la matriz RBAC vuelca `internal_roles` al fixture
    compartido y `meFixtures.ts` deriva `is_internal` de ahí (test de igualdad en la API).
  - **El formulario declara SIEMPRE en qué cliente escribe.** `SiteForm` lleva un rótulo
    permanente «ESCRIBIENDO EN · <cliente>» («ESTACIÓN DE · …» al editar). Para un rol interno,
    un selector CLIENTE (`/tenants`, misma clave de caché que la pantalla Multi-Tenant, así el
    cliente recién creado aparece sin recargar) y el envío apagado hasta elegir uno **de la
    lista**, con el porqué en el `title`; para un rol de cliente, sólo el rótulo. El cuerpo
    lleva `tenant_id` únicamente cuando el rol pudo elegirlo. La tabla de estaciones del
    interno gana la columna CLIENTE y el 400 genérico ya no se disfraza de retiro: `unwrap`
    añade el `detail` del servidor al mensaje.
  - **El flujo se enlaza.** La ficha del cliente en `/tenants` ofrece «NUEVA ESTACIÓN AQUÍ»
    (gateada por `manage_fleet` **y** la ruta `/fleet`, como todo enlace desde T-6.02) hacia
    `/fleet?tenant=<id>&nueva=1`, que abre el alta ya apuntada a ese cliente; los parámetros se
    limpian al cerrar el formulario.
  - **Verificación.** `web/e2e/onboarding.spec.ts` recorre las tres pantallas contra el stack
    real: crea un cliente único, salta por el enlace, crea la estación (el `POST /sites` responde
    con el `tenant_id` del cliente nuevo), añade el gabinete (el acuse lleva ese tenant) y en
    `/console` el `map/state` trae el sitio en ese cliente y el semáforo lo cuenta. 6/6 en los
    tres viewports. Unitarios: `SiteForm.test` (10), `FleetAdmin.test` (+4: superadmin envía el
    `tenant_id` elegido, `?tenant=` preselecciona, el 400 trae el `detail`, `tenant_admin` sigue
    sin mandarlo), `TenantsPage.test` (+4 del enlace por rol), `meFixtures.test` (+1),
    `test_me.py` e `test_rbac_fixture_es_la_matriz.py` en la API. Censo `serverDataCensus`:
    `FleetAdminPanel` declara `writeTarget` con su razón.

### [x] T-6.04 · **La marca DEMO llega a todo lo que pinta un sitio** — `SOFTWARE`

> `esDeDemostracion` la consumen el mapa y la tarjeta de flota; la cola de incidentes, el triage,
> el detalle y los KPI pintan el sitio sin cinta. Un marcado a medias enseña la regla falsa «sin
> cinta ⇒ real».

- **Superficie:** Consola · **Sesión:** C4
- **Componente:** web (`IncidentTable.tsx`, `TriageTable.tsx`, `DetailPanel.tsx`, `KpiStrip`) · **Depende de:** nada · **Prioridad: ALTA**
- **Cierra:** U-07
- **Tests de censo que toca:** ninguno existente; se **añade** un censo hermano de `serverDataCensus` que exija que toda superficie que pinta `site.code` o `site.name` lo pase por `esDeDemostracion`.
- **Token nuevo:** no (el gris neutro que ya usa la capa `site-demo` del mapa).
- **Cambia algo que un test defiende hoy:** no.
- **Objetivo:** una sola función, consumida por todos: donde hay un sitio simulado hay cinta, con la misma forma en el mapa, la flota, la cola, el triage, el detalle y los KPI.
- **Criterios de aceptación:**
  - [x] Con el seed de demostración, ninguna fila ni tarjeta de un sitio `site-sim-*` aparece sin cinta.
  - [x] Los KPI que agregan sitios simulados lo declaran («de los cuales N simulados»).
  - [x] El censo nuevo falla al añadir una pantalla que pinte un sitio sin pasar por la función.
- **Cómo se cerró (2026-09-07, SESIÓN C4):**
  - **Un componente para pintar un sitio.** `web/src/components/SiteLabel.tsx` pinta el nombre y, si
    `esDeDemostracion` lo dice por el código (o el serial), la MISMA cinta gris y discontinua que el
    mapa y la tarjeta de flota (`.site-demo`; cero tokens). `siteLabelText` pega « · DEMO» en los
    contextos de texto plano (`<option>`, títulos de formulario, la marca del SVG de la comparativa).
    Lo consumen la cola de incidentes, la tarjeta y la línea de alerta, el detalle, el triage (tabla,
    detalle y matriz de inspección), el alta y el historial de simulacros, la reubicación del
    epicentro, el banner de mantenimiento, la flota (tabla, fantasmas, formularios, códigos de alta),
    la ficha del edificio y el alcance por sitio de los usuarios.
  - **El código viaja hasta quien pinta.** `IncidentSiteInfo`, `DetailSite`, `TriageRow` e
    `InspectionRow` ganan el código; `AlertBanner`, `AlertLine` y `EpicenterModal` lo reciben por prop.
    Donde el contrato no lo traía se añadió en la API: `DrillSiteOut.site_code` y
    `MaintenanceWindowOut.site_code` (opcionales), SDK regenerado. Se descartó derivar la marca del
    UUID: el sitio real `site-dev` comparte prefijo con los simulados, y `esDeDemostracion` ancla a
    propósito en el código del seed.
  - **KPI honesto:** `consoleKpis.simulados`; la tira dice «DE LAS CUALES N SIMULADAS» sólo si N > 0.
  - **El censo:** `web/src/siteDemoCensus.test.ts`. La población se DERIVA: todo fichero de
    producción cuyas expresiones JSX toquen un nombre o código de sitio (`site_name`, `siteName`,
    `site.name`, `s.name`…, fuera de comentarios y tipos) tiene que importar `SiteLabel`,
    `siteLabelText` o `esDeDemostracion`, o estar exento con razón (`ConsolePage` y `SceneStrip`
    reparten a hijos que pintan; `GatewayForm`/`GatewayAcuse` reciben el título ya rotulado). Por
    igualdad en las dos direcciones: una exención que ya pasa por la función sobra. El analizador va
    probado contra fuentes sintéticas (un `siteName` en una interfaz o un comentario no es pintar; un
    import sólo de tipo no es pasar por la función).
  - **Verificación:** vitest (137 ficheros, 2 134 tests), eslint, prettier, tsc, `vite build`; API:
    drills + ventanas de mantenimiento en verde, ruff limpio. En `make soc-local` con el seed
    simulado, un barrido del DOM en `/console`, `/fleet` y `/triage`: 2 + 25 + 3 menciones de
    `Sitio Sim NNN`, **cero sin cinta**, y la tira de KPI dice «DE LAS CUALES 20 SIMULADAS».

### [x] T-6.05 · **El gate del LOGIN DEV lo lee un test bloqueante** — `SOFTWARE`

> El servidor está cerrado con test; el cliente depende de una línea `ENV` del Dockerfile que
> ningún test bloqueante lee, y el e2e que se le parece corre por `workflow_dispatch` y comprueba
> el endpoint, no el panel. Hoy no es visible en producción; no está defendido.

- **Superficie:** Consola · **Sesión:** C5
- **Componente:** web (`consoleImageCensus.test.ts`, `e2e/deployed.spec.ts`) · **Depende de:** nada · **Prioridad: ALTA**
- **Cierra:** U-16
- **Tests de censo que toca:** `web/src/consoleImageCensus.test.ts` — se **amplía**, no se relaja.
- **Token nuevo:** no.
- **Cambia algo que un test defiende hoy:** no.
- **Objetivo:** que un `true` tecleado en el Dockerfile, o un `ARG` homónimo añadido de buena fe, pongan el job `web` en rojo; y que el e2e desplegado asercione la ausencia del texto «LOGIN DEV» en el DOM de la entrada.
- **Criterios de aceptación:**
  - [x] El censo exige `ENV VITE_DEV_TOKEN_ENABLED=false` en la etapa de build y la ausencia de un `ARG` con ese nombre.
  - [x] `deployed.spec.ts` comprueba el DOM de `/`, no solo el 404 del endpoint.
  - [x] Una mutación (`false` → `true`) pone rojo el job `web`.
- **Cómo se cerró (2026-09-07, SESIÓN C5):**
  - **El censo lee el Dockerfile como Docker, no con un regex.** `consoleImageCensus.test.ts`
    gana un analizador que pliega las continuaciones, separa las etapas (`FROM … AS`), entiende
    las dos formas de `ENV` y localiza la etapa de build por su `RUN … npm run build`.
    `auditarGateLoginDev` exige: el literal `false` fijado ANTES de ese `RUN` (Vite congela
    `import.meta.env` en el build; un `ENV` posterior no sirve), ningún `ARG` homónimo en ninguna
    etapa, ninguna interpolación `${VITE_DEV_TOKEN_ENABLED}`, y `.dockerignore` con `web/.env` y
    `web/.env.*` (el segundo cerrojo de T-1.62). Cada defecto se describe con su porqué.
  - **Las mutaciones se ejercen sobre el fichero REAL** dentro del propio test: `true` tecleado,
    línea borrada, `ARG` añadido de buena fe, `ENV X=${X}`, y el `ENV` movido detrás del build; las
    cinco ponen rojo. Trampa medida: la primera aparición de `VITE_DEV_TOKEN_ENABLED=false` en el
    Dockerfile es un COMENTARIO, así que una mutación ingenua solo cambiaba la prosa y el gate
    seguía (con razón) en verde; se muta la línea del `ENV`, la que lleva la continuación. La
    mutación en vivo también se hizo a mano: `sed` al Dockerfile ⇒ 3 tests rojos ⇒ `git checkout`.
  - **`deployed.spec.ts` mira el DOM antes que el endpoint.** Exige que la entrada MONTÓ (título
    «CONSOLA SOC»), que no hay «LOGIN DEV», ni selector ROL, ni botón ENTRAR COMO ROL, que SÍ está
    ENTRAR CON COGNITO, y por último el 404. Y gana su ESPEJO local: contra el stack local exige
    que las tres huellas existan, para que un cambio de copy no deje al test de producción pasando
    por vacuidad. Las huellas viven en una sola constante compartida por los dos.
  - **Evidencia.** Bundle tipo producción (`vite build` con la bandera en `false`, servido con
    `http.server`): el test de producción pasa. Servidor de desarrollo forzado como producción
    (`PW_BASE_URL=http://127.0.0.1:5173`): falla exactamente en `getByText('LOGIN DEV')`
    (esperado 0, recibido 1). Contra `localhost`: el espejo pasa. Web: 138 ficheros /
    2 163 tests, eslint, prettier, tsc. La consola desplegada no se re-midió en esta sesión (IP
    allowlist + SSO): el hallazgo U-16 ya la había medido limpia el 2026-09-06.

### [x] T-6.06 · **Los vacíos dicen la causa real; la cola declara `error` y `stale`; ninguna caja en blanco** — `SOFTWARE`

> Cuatro estados vacíos culpan al TENANT de lo que con `console_scope_enforced` será el ALCANCE;
> la cola de incidentes no declara `error` ni `stale`; `DemoModeBanner` pasa `emptyText=""` y hoy
> un e2e midió la caja en blanco resultante.

- **Superficie:** Consola · **Sesión:** C6
- **Componente:** web (`ConsolePage.tsx`, `FleetPage.tsx`, `ComparePanel.tsx`, `IncidentTable.tsx`, `DemoModeBanner.tsx`, `SiteCard.tsx`, `BuildingPage.tsx`) · **Depende de:** nada; **antes de `T-2.89`** · **Prioridad: MEDIA**
- **Cierra:** U-17, U-26
- **Tests de censo que toca:** `web/src/statePrecedenceCensus.test.ts` y `web/src/serverDataCensus.test.ts` — **ninguno se relaja**: cambia el texto y se pagan entradas de `MARCOS_INCOMPLETOS` borrando su línea (el test se pone rojo si se arregla y no se borra: es la conducta deseada).
- **Token nuevo:** no.
- **Cambia algo que un test defiende hoy:** sí — los literales de `emptyText` que algunos tests de pantalla afirman.
- **Objetivo:** que el vacío diga si es por tenant o por alcance, derivado de `useSiteScope()`; que la cola tenga sus cuatro estados; que ningún `emptyText` esté vacío.
- **Criterios de aceptación:**
  - [x] Con alcance vacío, `/console`, `/fleet`, la comparativa y la cola dicen «EN SU ALCANCE», no «EN EL TENANT».
  - [x] La cola de incidentes declara `error` con reintento y `stale` con su reloj.
  - [x] `DemoModeBanner` con lectura caída y modo apagado imprime una frase con sujeto; el e2e «nunca una caja en blanco» en verde.
  - [x] `SiteCard` y la cabecera de `/building` salen de `MARCOS_INCOMPLETOS`.
- **Cómo se cerró (2026-09-09, SESIÓN C6):**
  - **El ámbito del vacío se DERIVA, ya no se escribe en cada pantalla.** Tres decían «EN EL
    TENANT» y una «EN EL ALCANCE» porque cada una redactaba la frase entera. Ahora
    `vacioConCausa(base, scope)` la compone a partir del MISMO `useSiteScope()` del que sale la
    insignia de la barra superior —la única fuente que sabe si el servidor está acotando de
    verdad—, con tres desenlaces: sin alcance impuesto, «EN EL TENANT» (hoy es cierto); con
    alcance, «EN SU ALCANCE (N ESTACIONES)»; y **sin ninguna estación asignada deja de hablar de
    lo que no hay** y dice lo que pasa: «SU CUENTA NO TIENE ESTACIONES ASIGNADAS · SOLICITE EL
    ALTA A SU ADMINISTRADOR». Ese último es el caso de la ficha: el día del apply de `T-2.89`, un
    operador con cero sitios habría leído «sin sitios en el tenant» sobre un cliente con 21 — falso,
    y encima le mandaba a preguntar por su cliente en vez de a pedir su alta.
  - **La cola de incidentes tiene sus cuatro estados.** `error` y `stale` vivían en el marco del
    WALL, que envuelve mapa y cola juntos: una lectura de incidentes caída borraba también el
    mapa, y la cola no podía ofrecer reintentar lo suyo. Ahora el marco del wall se queda con el
    error del MAPA y la cola declara el suyo con su reintento y su propia edad — que las dos
    lecturas envejezcan a la vez es casualidad, no contrato.
  - **La caja en blanco ya no existe, y ahora hay quien lo vigile.** El `emptyText=""` que midió la
    auditoría (1264×120 px) lo cerró `T-6.01` al mover la franja al shell y darle `silentEmpty`;
    se comprobó corriendo el e2e **tal como está escrito**, sin relajarlo: **18/18** en las seis
    pantallas × tres viewports. Lo que faltaba era impedir que vuelva: `silentEmpty` es la única
    forma de que un marco pase ese e2e sin decir nada, así que el censo compara **por igualdad**
    quién puede usarlo — hoy, sólo las cuatro franjas de `features/scene/`. El día que alguien
    silencie el vacío de una tabla para quitarse un rojo de encima, el censo se pone rojo con él.
  - **Las tres deudas del censo, pagadas.** `HISTORIAL DEL SITIO` gana su `staleSince` (el hook de
    métricas no exponía la edad); la cabecera de `/building` y `SALUD DEL GABINETE` dejan de
    guardarse a mano y pasan por `StateFrame` —un `soh` de hace dos horas se pintaba idéntico a uno
    de hace un segundo, el defecto que RO-7.c cerró en el panel y aquí seguía abierto—; y `SiteCard`
    deja de ser el único dato de servidor de la flota **sin marco**: la máquina de fases del
    autodiagnóstico se TRADUCE a los cuatro estados (esperando el acuse = cargando, TTL y rechazo =
    error con el detalle del gabinete y su reintento, acuse sin censo de relés = vacío) en vez de
    correr en paralelo. Tres entradas menos en `FUERA_DEL_MARCO`, una en `MARCOS_INCOMPLETOS` y el
    recuento del censo baja de 3 a 2 marcos ausentes.
  - **Lo que NO se pagó, y por qué está escrito:** `SiteCard` sigue en la lista de los que no
    tienen prueba de los cuatro estados. `expectFourStates` exige los CUATRO y el `stale` de esa
    tarjeta no existe —el acuse de una orden que el operador acaba de dar no envejece en pantalla,
    se limpia— así que el marco lo declara (`staleSince={null}`) en vez de callarlo. Inventarle una
    edad para pasar el helper sería el defecto, no el arreglo.
  - **Verificación:** web 2 184 tests (14 nuevos), `eslint`, `prettier` y `vite build` limpios; e2e
    contra el stack local: `screens.spec.ts` «nunca una caja en blanco» 18/18 y 152 aserciones más
    en verde. Los 4 e2e que fallan (`layout.spec.ts:19`, `:70`, `:108` y `screens.spec.ts:508`)
    fallan IGUAL en `main` sin este cambio —se comprobó con el árbol limpio—: son U-35 (el aviso de
    privacidad se lleva el mapa, ficha `T-6.11`) y los sobrepuestos del escenario, ninguno de esta
    ficha.

### [x] T-6.07 · **El arranque no tiene silencios** — `SOFTWARE`

> Entre el HTML y el primer frame no hay pantalla; el splash es estático y mudo; la sesión expira
> y el operador vuelve a un login idéntico al de un arranque frío; el fallback nombra variables de
> build al cliente.

- **Superficie:** Consola · **Sesión:** C7
- **Componente:** web (`index.html`, `pages/StatusScreens.tsx`, `pages/LoginPage.tsx`, `auth/session.store.ts`) · **Depende de:** nada · **Prioridad: MEDIA**
- **Cierra:** U-18
- **Tests de censo que toca:** ninguno; `session.store.test.ts` censa los miembros de `SessionStatus` y exige productor real para cada uno: la causa de expiración va en un campo aparte, **no** como estado nuevo (el test tiene razón).
- **Token nuevo:** sí — una duración semántica para el umbral «esto está tardando» del splash (hoy `tokens.json` solo tiene duraciones de interacción).
- **Cambia algo que un test defiende hoy:** sí — `LoginPage.test.tsx` afirma el literal del fallback; copy y test cambian en el mismo commit.
- **Objetivo:** una marca de arranque en el HTML con la marca; un splash con `role="status"` que a partir del umbral dice qué espera; la landing que declara «su sesión expiró» cuando esa es la causa; cero texto de ingeniero.
- **Criterios de aceptación:**
  - [x] Con JavaScript lento, el usuario ve algo con marca antes del primer frame de React.
  - [x] Pasado el umbral, el splash dice qué espera (`/me`) y desde cuándo.
  - [x] Tras `handleUnauthorized`, la landing dice por qué se cerró la sesión.
  - [x] El fallback sin Cognito habla al operador, no al que despliega.
- **Cómo se cerró (2026-09-09, SESIÓN C7):**
  - **El paso 0 existe y vive DENTRO de `#root`.** `index.html` trae marca, «CONSOLA SOC ·
    INICIANDO…» y un `<style>` inline. Dentro de `#root` a propósito: React lo sustituye al montar,
    y fuera se quedaría pegado debajo de la consola para siempre. No depende de nada que todavía
    no haya llegado —ni hoja externa, ni fuente remota, ni `var(--tk-*)`: la hoja que declara esos
    tokens viaja en el bundle que aún no está—, así que los colores van escritos a mano y
    `bootMarker.test.ts` exige que sean **los del paquete** y que no haya ningún otro hex, la misma
    disciplina que el panel del gabinete.
  - **Medido en un navegador con el bundle cortado:** la marca se pinta al segundo, cian
    `--tk-cyan` sobre `--tk-surface-0`, y al llegar el bundle quedan **cero** marcadores de
    arranque en el DOM. Con el scripting apagado se pintaban **los dos bloques**: el de `#root`
    anunciando el arranque de una consola que no iba a arrancar, encima del texto que explica por
    qué. Una hoja inline dentro del propio `noscript` lo apaga (solo se aplica en ese caso, y
    `#root .boot` gana por especificidad de id) y queda el deslinde que de verdad importa: **el
    alertamiento del edificio NO depende de esta pantalla**.
  - **El splash dice qué espera y desde cuándo.** Umbral en token semántico nuevo
    (`--tk-wait-declare`, 3000 ms) porque la misma pregunta se la hacen otras pantallas; el número
    no se escribe en el componente ni en su test. Pasado el umbral: «ESTO ESTÁ TARDANDO · esperando
    la sesión del operador (/me) desde hace N s», con el contador corriendo —que es la diferencia
    entre lento y colgado— y `role="status"` + `aria-live="polite"` en el panel, porque quien usa
    lector de pantalla oía un rótulo y luego silencio. **Qué se espera lo declara cada sitio**:
    `RequireSession` la sesión, `AuthCallbackPage` la vuelta de Cognito. Confundirlas manda a mirar
    el sitio equivocado: la API propia y el proveedor de identidad son dos diagnósticos distintos.
    Verificado en el navegador con `/me` colgado: 0 s muda, el aviso a los 3 s, 6 s tres segundos
    después.
  - **La expiración deja de ser muda.** `handleUnauthorized` limpiaba y el operador reaparecía en
    un login idéntico al de un arranque en frío, sin una palabra: volvía a entrar sin enterarse de
    que el turno llevaba un rato sin consola. La causa viaja en un **campo** (`endedReason`) y no
    en un `SessionStatus` nuevo —el estado sigue siendo `anonymous`, que es lo que es, y el censo de
    `session.store.test.ts` exige productor real por cada miembro del union: **el test tenía razón**,
    como decía la ficha. La landing solo la LEE; quien la apaga es el `/me` de la sesión siguiente,
    para que «SU SESIÓN SE CERRÓ» no reaparezca meses después culpando de una expiración que ya
    nadie recuerda.
  - **No se inventa la causa.** Un 401 puede ser expiración o revocación y desde el navegador no se
    distinguen, así que el aviso dice «el servidor dejó de reconocerla (expiró o fue revocada)» y no
    «expiró por inactividad», que sería adivinar. Tono de aviso, no de error: aquí no falló nada de
    la consola.
  - **El fallback sin Cognito le habla a quien está de turno.** Decía «Cognito no configurado
    (VITE_COGNITO_*)»: nombra un proveedor de identidad y dos variables de build a alguien que solo
    quiere entrar, y no dice ni qué hacer ni si el edificio sigue protegido. Ahora dice que desde
    ahí no se entra, a quién avisar y que el alertamiento no depende de esta pantalla; el detalle
    técnico viaja en el `title`, donde lo busca quien desplegó. `LoginPage.test.tsx` afirmaba el
    literal viejo: **copy y test cambian en el mismo commit**, y lo que el test defiende ahora no es
    una frase sino las tres cosas que hacen falta, más que **ninguna** variable de build aparezca en
    el texto.
  - **Verificación:** web 2 201 tests (6 ficheros nuevos o tocados: `bootMarker`, `StatusScreens`,
    `LoginPage`, `session.store`), `tsc`, `eslint`, `prettier` y `vite build` limpios; los cuatro
    criterios ejercidos en un navegador real sobre el build de producción (bundle cortado, scripting
    apagado, `/me` colgado y `/me` en 401), con capturas.

### [x] T-6.08 · **El login se ve TAKAB** — `SOFTWARE` + `TERRAFORM`

> No existe `aws_cognito_user_pool_ui_customization`: el operador teclea contraseña y TOTP en la
> pantalla de fábrica de AWS, en inglés, entre dos pantallas con imagotipo TAKAB. **No se propone
> un formulario propio.**

- **Superficie:** Consola (+ terraform) · **Sesión:** C8 (dos sesiones: generador, luego apply)
- **Componente:** `infra/terraform/modules/identity/` + un generador en `shared/design-tokens/` · **Depende de:** nada; el `apply` es de Mauricio · **Prioridad: MEDIA**
- **Cierra:** U-19
- **Tests de censo que toca:** ninguno existente; se añade uno que exija que el CSS subido a Cognito se **derive** de `tokens.json` (Cognito no acepta custom properties, así que el generador resuelve tokens a literales en build: eso es un generador, no un hex a mano).
- **Token nuevo:** no (superficie, borde, cian y texto ya existen).
- **Cambia algo que un test defiende hoy:** no.
- **Objetivo:** logo del paquete de marca y hoja CSS generada desde los tokens para los dos pools (consola y ocupantes), sabiendo antes si el pool está en Hosted UI clásico o en «managed login» (el repo no lo declara).
- **Criterios de aceptación:**
  - [x] La pantalla de Cognito muestra el imagotipo y los colores de superficie, borde y acento del paquete.
  - [x] El CSS subido es salida de un generador; un test falla si diverge de `tokens.json`.
  - [x] Captura antes y después en el informe de la sesión; los textos siguen siendo los de Cognito (no se pueden cambiar) y se dice.
- **APLICADA Y VERIFICADA EN LA NUBE (2026-09-10).** `terraform apply` acotado a los cuatro recursos
  de esta ficha: **2 to add, 0 to change, 0 to destroy** — los dos dominios no traían diferencia, lo
  que confirma desde el estado lo que ya decía la pantalla: están en Hosted UI clásico. Medido
  después contra los DOS dominios reales, con un `client_id` de verdad y navegador:

  | | pool consola | pool ocupantes |
  |---|---|---|
  | fondo | `rgb(14, 35, 54)` | `rgb(14, 35, 54)` |
  | imagotipo presente | sí | sí |
  | botón `Sign in` | cian sobre navy | cian sobre navy |
  | CSS en el pool | 929 B · versión `20260910031042` | 929 B · misma versión |

  **Y la incógnita que quedaba se resolvió a favor.** La ficha salía con un riesgo declarado: si
  `redirect-customizable` estuviera en un contenedor, «Forgot your password?» se quedaría en 3.51:1.
  La pantalla real dice que **la clase está en el propio enlace** (`a.redirect-customizable`), así
  que la regla llega: el enlace mide `rgb(0, 191, 255)` — **7.54:1**. La previsualización local se
  había equivocado ahí, y por eso la comprobación tenía que ser contra la pantalla desplegada.
  **Cero fallos AA en el login**, y dos de los que había de fábrica (mensaje de error 4.24, aviso de
  contraseña válida 2.47) quedan cerrados.
  **Los textos siguen siendo los de Cognito y en inglés** —`Sign in with your email and password`,
  `Email`, `Password`, `Sign in`—: la API viste, no traduce. Cambiarlos exige el formulario propio
  que esta ficha decidió NO hacer.
- **Cómo se hizo (2026-09-09, SESIÓN C8 · generador y terraform):**
  - **La pregunta que la ficha dejaba abierta se contestó sin credenciales.** «Hosted UI clásico o
    managed login» decide qué API viste la pantalla: la v1 se viste con `SetUICustomization` (CSS +
    logo) y la v2 la ignora entera. Se resolvió pidiendo la propia pantalla de los dos dominios con
    `curl`: devuelven `<title>Signin</title>` y marcado con `banner-customizable`, que es el
    **clásico**. Y se deja de heredar: los dos dominios declaran ahora `managed_login_version = 1`,
    porque con la v2 esta hoja se ignoraría **en silencio** y el login volvería al gris.
  - **La lista de clases está MEDIDA, no copiada de la documentación.** `SetUICustomization` rechaza
    la hoja ENTERA si cita una clase que no conoce, y ese rechazo llegaría en la ventana de AWS de
    otra persona. La lista sale de la hoja que Cognito sirve
    (`.../css/cognito-login.css`): son **quince**. Casi se quedan en trece: un barrido con
    `\.[a-zA-Z]+-customizable` se deja fuera `passwordCheck-notValid` y `passwordCheck-valid` por el
    guion de en medio — y son justo las dos de la pantalla de contraseña nueva, la primera que ve un
    operador dado de alta.
  - **El generador, y por qué tiene que serlo.** Cognito no acepta custom properties, así que la
    hoja lleva los colores resueltos a literales. Escrita a mano son doce hexes en un fichero que
    nadie abre: el día que la marca cambie de navy, la consola se entera y el login no.
    `gen-cognito-css.mjs` los deriva de `tokens.json`, su `--check` entra en `npm run check` —o sea
    en `make drift` y en el paso de CI que ya existía— y `hosted_ui_branding.tftest.hcl` cruza la
    hoja contra el paquete **en los dos sentidos**: cada token tiene que aparecer, y cada `#rrggbb`
    de la hoja tiene que existir en `tokens.json`. Las dos direcciones comprobadas por mutación.
  - **La hoja sale SIN COMENTARIOS, y no es descuido.** No está verificado que la API los acepte, y
    quien hace el `apply` es una persona con una ventana abierta: un rechazo ahí le cuesta la
    ventana. La procedencia vive en el generador y en el terraform que la sube.
  - **Medido antes y después, en contraste (previsualización local con la hoja real de Cognito):**

    | Elemento | De fábrica | Con la hoja |
    |---|---|---|
    | texto del campo | 7.46 ✓ | **14.27** ✓ |
    | rótulo de campo | 7.46 ✓ | **8.87** ✓ |
    | botón `Sign in` | 4.56 ✓ | **7.54** ✓ |
    | mensaje de error | **4.24 ✗** | **7.01** ✓ |
    | contraseña válida | **2.47 ✗** | **9.59** ✓ |
    | contraseña NO válida | 4.55 ✓ | **7.01** ✓ |
    | descripción y texto legal | 7.46 ✓ | 5.69 ✓ |
    | «Forgot your password?» | 4.56 ✓ | **3.51 ✗** |

    **De dos fallos AA a uno**, y el que queda es el único que la API no deja alcanzar con una clase
    pelada: `redirect-customizable` vale sólo `text-align: center` en la hoja de Cognito y el color
    del enlace lo pone el `a` de Bootstrap. La regla se escribe igual —si la clase está en el propio
    enlace, lo arregla—; si no, hace falta `.redirect-customizable a`, y eso se prueba **en el
    `apply`**, donde un rechazo es barato porque hay alguien mirando. Está escrito en la ficha de
    pendientes como lo único que hay que mirar ese día.
  - **El logo se DERIVA, como el resto de la identidad.** `shared/brand/generar.py` emite el
    imagotipo negativo a 560 px (42 KB; el tope duro de la API son 100 KB, y el test lo vigila).
    Correr el generador entero no movió ningún otro byte: la derivación es determinista.
  - **Lo que la previsualización NO podía decir, y acertó en no afirmarlo.** Se montó con la hoja
    real de Cognito y el logo real, pero el MARCADO era una reconstrucción — y en el único punto en
    que se apartó del real (dónde cuelga `redirect-customizable`) la conclusión salía al revés. Una
    previsualización sirve para decidir antes de gastar la ventana; la pantalla desplegada es la que
    responde.

### [x] T-6.09 · **Contraste AA donde hay texto, y forma donde solo había color** — `SOFTWARE`

> axe sin filtrar: 171 nodos `color-contrast` (rojo crítico sobre la tarjeta crítica de flota a
> 11 px, 3.76:1; la meta del cliente en `/tenants`, 4.4:1). `color-contrast` no bloquea, `/building`
> no está en `axe.spec`, y en el mapa `watch` y `normal` difieren solo por tono.

- **Superficie:** Consola · **Sesión:** C9 (dos sesiones)
- **Componente:** web (`styles/soc.css`, `styles/soc-tabs.css`, `MapPanel.tsx`, `e2e/axe.spec.ts`) · **Depende de:** nada · **Prioridad: MEDIA**
- **Cierra:** U-20
- **Tests de censo que toca:** `web/src/designTokens.test.ts` (la guarda de contraste de los rótulos pequeños se amplía a los pares medidos; los hex duplicados del semáforo pasan a `var()`).
- **Token nuevo:** sí, semántico — un tono de texto para «crítico sobre superficie crítica» que pase AA; el rojo de estado no se mueve (está anclado).
- **Cambia algo que un test defiende hoy:** sí — las anclas de identidad no se tocan; los pares `fg×bg` medidos se añaden al test.
- **Objetivo:** cero nodos `color-contrast` en las seis pantallas con datos sembrados; un glifo propio para `watch` en el mapa; `/building` en `axe.spec`; `color-contrast` como regla observada por pantalla y bloqueante donde ya está en cero.
- **Criterios de aceptación:**
  - [x] axe sin filtrar reporta cero `color-contrast` en `/fleet` y `/tenants` con el seed de demostración.
  - [x] `watch` y `normal` se distinguen sin color (glifo o radio), verificado con un simulador de deuteranopía.
  - [x] `axe.spec.ts` cubre `/building` y bloquea por contraste en las pantallas que ya están limpias.
- **Cómo se cerró (2026-09-09, SESIÓN C9):**
  - **La medición primero, y salió más chica y más grave de lo fichado.** axe sin filtrar sobre las
    seis pantallas con el seed de demostración a 1440×900: **44 nodos** `color-contrast`, no 171 —
    aquella cifra sumaba 72 corridas (roles × viewports) y contaba el mismo nodo muchas veces. Pero
    los 44 se reparten en **cuatro** defectos, no cuarenta: **36 son el rojo anclado haciendo de
    tinta sobre su propio tinte** (3.35:1 en una fila seleccionada de `/triage`, 3.76 en la píldora
    de la tarjeta crítica de flota, 4.23 en sus enlaces), 6 son la cinta DEMO, 3 la selección y 1 el
    resto.
  - **Un ancla no se mueve: se le separa el oficio.** `--tk-status-critical` (`#FF5252`) es ancla de
    identidad y la defiende un test desde T-2.01. Sobre `--tk-surface-2` da 4.10:1 y sobre su propio
    tinte, 3.46 — no puede escribir. Se estrena **`--tk-status-critical-text`** (`#FF8A80`): el mismo
    rojo, más claro, con **4.69:1 en el peor fondo que la consola compone**. El ancla dibuja
    (bordes, barras, rellenos, el punto del mapa); la tinta escribe. Las 36 declaraciones `color:`
    cambiaron de token de una vez. Ámbar, verde y cian pasaban con holgura y **no** estrenan tinta:
    la simetría por la simetría serían tres tokens que nadie usa.
  - **El peor par del producto no lo había visto nunca nadie.** El censo nuevo —«una tira de estado
    SÓLIDA lleva tinta oscura»— sacó cuatro bloques que axe jamás alcanzó porque **ninguna corrida
    tenía una alerta en pantalla**: `.soc-alert__strip` pintaba `#fff` sobre el rojo, **2.85:1**, y
    ese es el texto más importante que escribe la consola («ALERTA SÍSMICA · PROTÉJASE»). Con él, el
    botón que BORRA, la píldora de estado del BMS y la franja de escena. La tira de AVISO ya lo hacía
    bien desde T-6.01 (navy sobre ámbar): ahora las cinco hablan igual. Medido en el navegador con un
    SASMEX real del gabinete simulado: **5.01:1**.
  - **El contrato medía tres fondos y la consola pinta ocho.** El bloque de contraste de
    `designTokens.test.ts` comparaba texto contra `--tk-surface-0/1/2`, planos. Encima de esos tres
    la consola compone un tinte por estado, y **es justo ahí donde va el texto de ese estado**. El
    contrato nuevo compone `tinte × superficie` y mide los ocho pares que se pintan de verdad.
  - **Dos defectos que solo existían por composición.** La cinta `DEMO` era transparente, así que su
    gris se medía contra lo que hubiera debajo: 3.88:1 sobre la franja de escena en ámbar, 4.41 sobre
    una fila seleccionada y, en una alerta, contra el rojo sólido. Ahora **lleva su propio fondo
    opaco** y da 8.87:1 se pinte donde se pinte, sin dejar de ser gris y discontinua (T-6.04). Y
    **seleccionar una fila la hacía más difícil de leer**: el tinte cian ACLARA el fondo y el gris
    terciario caía a 4.41 — la fila que el operador está leyendo era la única de la tabla por debajo
    de AA.
  - **La forma, verificada donde importa.** `watch` (#FFC107) y `normal` (#00E676) llevaban el mismo
    radio y solo se distinguían por tono. La banda estrena alfabeto propio en una capa aparte —
    `!!` disparo · `!` cautela · nada bajo umbral · `?` sin dato— que no reusa el del enlace
    (`⊘ ▲ ○`): un ▲ que según la capa signifique una cosa u otra no es un glifo, es una adivinanza.
    `unknown` gana marca porque «no reportó» no es «no se movió» (regla de oro 7). **Bajo el
    simulador de deuteranopía (matriz de Machado) los tres colores de la leyenda son el MISMO
    amarillo** y lo único que los separa es la columna de marcas — está en las capturas.
  - **Ningún tinte es seguro para el gris terciario, y eso ahora es un test.** Al subir la barra, el
    e2e a 1280×800 sacó dos nodos que el barrido a 1440 no veía: el encabezado del catálogo de
    triage **con el ratón encima** (4.02–4.41:1). La tentación es aclarar `--tk-fg-3`, y está
    medido que no se puede: para pasar sobre un tinte habría que llevarlo a `#98AABE`, y ahí el
    escalón fg-2/fg-3 cae de 1.56 a **1.32** — por debajo del 1.4 que ya exige el test de la
    jerarquía. Así que la regla es la contraria y se dejó derivada del paquete: **sobre cualquiera
    de los ocho tintes el terciario deja de ser seguro (3.20:1 en el peor fondo) y el secundario
    aguanta los 24 pares (4.99:1 el peor)**; donde hay tinte, la tinta sube.
  - **La barra sube con datos.** `color-contrast` pasa de adjunto a **bloqueante** en `axe.spec.ts`,
    que era la promesa escrita en su cabecera desde T-2.56, y el barrido estrena `/building` (no es
    pestaña: se llega por enlace profundo desde flota y desde triage). Comprobado en el navegador
    **44 → 0 nodos**, y **0 violaciones de cualquier regla** en las seis pantallas, con y sin alerta
    en pantalla.
  - **El e2e cierra en 216 pasados / 9 fallidos, y los 9 son de antes.** Seis son los dos conocidos
    (`layout.spec:19` y `screens.spec:508` × 3 viewports: la franja de alerta tapando los cuatro
    botones de capas). Los otros **tres son nuevos en la línea base, no en esta rama**: a 1440×900 el
    escenario mide **376 px** contra los 400 que exigen `layout.spec:70`, `:108` y `smoke.spec:50`,
    y los 24 px que faltan son la tira de simulacro en reposo. Verificado con un control A/B sobre
    **el mismo stack y en el mismo minuto** —`git stash` de todo `web/src` + el paquete de tokens—:
    **376 px con los cambios y 376 sin ellos**, y las mismas cuatro pruebas en rojo. Los tres siguen
    sin ficha, igual que los dos de siempre.

### [x] T-6.10 · **Movimiento honesto: se detiene, se declara y se apaga** — `SOFTWARE`

> `prefers-reduced-motion` apaga los dos keyframes y 2 de 18 transiciones; la barra del UPS anima
> un dato bajo reducción; el latido de `LinkPill` late por `kind`, no por frescura; una fila nueva
> en la cola aparece sin aviso; 10 `transition: all` y 14 literales de duración duplican un token.

- **Superficie:** Consola · **Sesión:** C10 (dos sesiones)
- **Componente:** web (`styles/soc.css`, `styles/soc-tabs.css`, `fleet/LinkPill.tsx`, `console/IncidentTable.tsx`, `components/ConfirmButton.tsx`) · **Depende de:** nada · **Prioridad: MEDIA**
- **Cierra:** U-22 (consola), U-23, U-39, S3 (consola)
- **Tests de censo que toca:** `web/src/styles/layoutInvariants.test.ts` («reglas muertas»: una `@media` no añade especificidad; el bloque de reducción ampliado debe declararse con la misma cautela que el actual), `web/src/statePrecedenceCensus.test.ts` (si el latido de `LinkPill` pasa a depender de frescura, el censo debe verlo).
- **Token nuevo:** sí — una duración semántica para la entrada de una fila de dato (no hereda la de hover) y el período de la trama del banner de simulacro.
- **Cambia algo que un test defiende hoy:** sí — `motion.spec.ts` gana casos (las transiciones bajo reducción) y `LinkPill` cambia su condición.
- **Objetivo:** bajo reducción no queda ninguna transición viva; todo latido late por edad del dato y se congela al envejecer; una fila nueva se anuncia con rótulo `NUEVO` (portador) y entrada del contenedor con el dato ya pintado; el banner de simulacro gana una trama de galones que deriva mientras la lectura es fresca y se congela al retenerse; `transition: all` enumera propiedades; las duraciones usan el token.
- **Criterios de aceptación:**
  - [x] Con `reduce`, `getComputedStyle(...).transitionDuration` es cero en los selectores hoy vivos y la barra del UPS salta al valor final.
  - [x] El latido de `LinkPill` se detiene cuando el último frame supera el umbral, con el texto de edad diciendo lo mismo.
  - [x] La fila nueva lleva `NUEVO` N segundos aunque no haya animación; `AlertBanner` no cambia ni una línea.
  - [x] Cero `transition: all` y cero literales de duración en las hojas de la consola.
- **Cómo se cerró (2026-09-09, SESIÓN C10):**
  - **El interruptor dejó de ser una lista.** La reducción apagaba dos selectores escritos a mano y
    por eso alcanzaba 2 de 18 transiciones: el que se queda fuera no rompe nada, simplemente sigue
    moviéndose. Ahora la duración de TODA transición de las hojas es un token y el bloque de
    `prefers-reduced-motion` **pone esos tokens a cero en un `:root`**, así que cubre también lo que
    nadie ha escrito todavía. Gana a `tokens.css` por ORDEN de import, no por especificidad —una
    `@media` no añade ninguna, lo aprendió T-2.59—, y hay un test que vigila justo eso.
  - **Medido en el navegador, que es donde vive:** a 1440×900, **15 transiciones vivas** en
    `/console` y **295** en `/fleet` sin la preferencia; con `reduce`, **0 y 0**. La barra del UPS
    —la única transición sobre un DATO— pasa de **0.24 s a 0 s**: el porcentaje de batería salta al
    valor en vez de llegar tarde a propósito.
  - **El latido mentía durante tres minutos, y ahora hay número.** Con el WAN del gabinete simulado
    cortado: el halo siguió latiendo hasta **t+75 s** (correcto: el frame aún era reciente), se paró
    en **t+90 s** escribiendo `ÚLTIMO FRAME · 2 min`, y el servidor no declaró `SIN ENLACE` hasta
    **t+286 s**. Esos ~3 minutos eran exactamente la ventana en la que dos halos latían sobre un
    enlace ya muerto. El umbral son **120 s** y no es un número redondo: más ancho que la cadencia
    del edge (`health_heartbeat_s = 60`, o parpadearía con cualquier jitter) y más estrecho que el
    del servidor (`sin_enlace_min = 5`, o no apagaría nunca nada).
  - **Y el latido ya no se puede escribir a fuego.** Un censo nuevo exige que `soc-dot--pulse` salga
    siempre de una condición: qué condición sea la correcta lo miden los tests del componente, pero
    escribirla pelada deja de pasar en verde. Comprobado por mutación.
  - **La fila que llega se anuncia con un RÓTULO, no con un destello.** `NUEVO` dura 10 s por RELOJ
    (no por render: un refresco del WebSocket a los 200 ms lo habría borrado) y el primer censo no
    marca nada —abrir la consola no es que lleguen doce incidentes—. En el navegador: 3 filas al
    abrir con **0 rótulos**, el rótulo aparece **366 ms** después del `/quake` y se retira solo a los
    11 s. Con `reduce` la entrada del contenedor computa `animation-name: none` y **el rótulo sigue
    ahí, en cian**: el portador sobrevive a la preferencia. `AlertBanner` no cambió ni una línea.
  - **El simulacro gana una trama que DICE si la lectura sigue viva** (S3, que estaba en rojo en las
    tres superficies). Galones ámbar sobre el mismo tinte de siempre: forma y color primero, el
    movimiento sólo confirma. Medido con el banner real: vivo ⇒ `soc-drill-weave 1.4s` y los píxeles
    cambian entre dos capturas a 700 ms; con la lectura de `/drills/active` cortada ⇒ la clase se
    cae, `animation: none`, **los píxeles son idénticos** y la franja escribe `DATOS RETENIDOS ·
    23:30:23 UTC` sin quitarle una palabra al aviso de simulacro.
  - **Diez `transition: all` enumeradas y quince literales de duración retirados.** `all` anima
    cualquier propiedad futura del selector, incluido un color de estado: el día que un rojo crítico
    entrara por hover, llegaría deslizándose. Cinco tokens nuevos, y los cuatro que no son de
    interacción se separan a propósito: `--tk-dur-data` va con `--tk-ease-data` (lineal, porque una
    curva de aceleración sobre un porcentaje real inventa un énfasis que el dato no tiene),
    `--tk-dur-row-in` no hereda la de hover, y `--tk-dur-pulse`/`--tk-dur-armed`/`--tk-dur-drill` son
    PERÍODOS: laten distinto porque dicen cosas distintas.
  - **`statePrecedenceCensus.test.ts` no hizo falta tocarlo** y conviene decir por qué: vigila el
    acoplamiento `empty`↔`staleSince` de los marcos, y la frescura del latido no pasa por
    `StateFrame` — viaja como prop del dato al componente.
  - **El e2e cierra en 223 pasados / 9 fallidos**, los nueve de la línea base que dejó T-6.09. La
    corrida trajo además dos rojos de `drill.spec` que **no eran de la rama**: un simulacro que
    arranqué a mano para ver la trama **sobrevivió al reinicio del stack** —`make soc-local` vuelve a
    sembrar la base, pero no la tira— y mientras estuvo vivo escondía el botón `INICIAR SIMULACRO`.
    Con el stack en reposo, `drill.spec` + `motion.spec` cierran **36/36** en los tres viewports.

### [x] T-6.11 · **El aviso de privacidad es una franja, no un panel** — `SOFTWARE`

> Ocupa unos 170 px en todas las pantallas hasta aceptarlo y a 1280×800 deja el mapa en su piso;
> dos e2e de layout lo miden y fallan hoy. Es lo primero que ve un cliente en la demo.

- **Superficie:** Consola · **Sesión:** C11
- **Componente:** web (`privacy/PrivacyConsentBanner.tsx`, `styles/privacy.css`) · **Depende de:** nada · **Prioridad: MEDIA**
- **Cierra:** U-35
- **Tests de censo que toca:** `web/src/styles/layoutInvariants.test.ts` (ya exige que el banner sea una franja: el arreglo lo pone en verde donde hoy la hoja miente por la cascada).
- **Token nuevo:** no.
- **Cambia algo que un test defiende hoy:** no; hace pasar dos e2e que hoy fallan (`layout.spec.ts:70`, `:108`).
- **Objetivo:** una sola línea con el rótulo, la versión y dos acciones; el texto largo en el modal que ya existe. Sigue siendo no bloqueante y no modal (`T-2.79`).
- **Criterios de aceptación:**
  - [x] A 1280×800 con el banner presente, el mapa mide más que su piso.
  - [x] El banner no crece más de una fila en ningún viewport de la matriz.
  - [x] `layout.spec.ts` «el banner de privacidad es una FRANJA» en verde.
- **Cómo se cerró (2026-09-09, SESIÓN C11):**
  - **Medido antes de tocar nada, que es de donde sale el diseño.** El bloque medía **164 px** y se
    los cobraba al mapa uno a uno: a 1280×800 el escenario pasaba de 445 px sin banner a **269**
    con él —por debajo de su piso de 280—, y a 1440×900 de 455 a 279. No era una impresión: la
    fila del aviso en la reja del shell medía 176.23 px en los tres viewports.
  - **La franja es una línea, y por construcción.** Se queda a la vista lo que hay que poder leer
    sin pulsar nada: el estado (el título ya distingue los cuatro), qué aviso y de quién, el sello
    de TEXTO PROVISIONAL cuando lo es, **que NO bloquea la operación** —esa promesa no se esconde—
    y las acciones. La explicación larga y el texto del aviso encabezan el cuerpo desplegable, que
    ya existía. `flex-wrap: nowrap` con el nombre del aviso recortándose con puntos suspensivos (y
    su `title` con el texto entero): que quepa no depende de que hoy los textos sean cortos.
  - **Resultado, medido en el navegador:** la franja pasa de 164 a **32 px** en los tres viewports
    y el mapa sube a **405 px a 1280×800** (era 269) y **415 a 1440×900** (era 279). El aviso le
    cuesta al mapa 40 px en vez de 176.
  - **Dos defectos que solo aparecieron al medir el rediseño.** El rótulo `TEXTO PROVISIONAL` se
    pasaba por dos píxeles del ancho de su propia caja y **se partía en dos líneas**: 32 px que se
    llevaban por delante la franja entera (por eso a 1280 medía 42 y a 1440, 32). Y con `nowrap` la
    caja medía **1376 px de ancho en una ventana de 1280**: un item de reja no baja de su contenido
    sin `min-width: 0`, así que la consola ganaba scroll horizontal — lo caza
    `layout.spec.ts` «sin desborde horizontal», que sigue en verde.
  - **Guardas.** `layoutInvariants.test.ts` gana el invariante de la línea única (la caja es `flex`
    con `nowrap`, y el nombre del aviso declara `min-width: 0` + `overflow: hidden` +
    `text-overflow: ellipsis`; sin lo primero el recorte no llega a pasar). El invariante del
    margen deja de clavar `12px` y pasa a exigir que la separación EXISTA y venga sólo por abajo:
    el hueco es parte de lo que la franja le cobra al mapa y esta ficha lo bajó a 8 px con esa
    cuenta delante; clavar el número convertía una medida de diseño en un contrato.
  - **Verificación:** web 2 185 tests, `tsc`, `eslint`, `prettier` y `build` limpios. En el
    navegador, `layout.spec.ts` **«el mapa conserva su alto»** y **«el banner de privacidad es una
    FRANJA»** en verde en los tres viewports —los dos que la auditoría midió fallando— y 138
    aserciones de `layout` + `screens` en verde.
  - **Lo que sigue rojo y NO es de esta ficha:** `layout.spec.ts:19` (la pila de alertas se solapa
    con las leyendas del mapa, 73 080 px²) y `screens.spec.ts:508` (la franja de alerta tapa los
    cuatro botones de capas del mapa). Los dos fallan igual en `main` sin este cambio —comprobado
    con el árbol limpio en la verificación de T-6.06— y ninguna ficha los nombra todavía: son dos
    solapamientos sobre el mapa, de la familia de esta ficha pero con causa propia.

### [x] T-6.14 · **El flujo alerta → dictamen no pierde el contexto** — `SOFTWARE`

> Solicitar el dictamen salta a `/triage` y tira el riel, el mapa y el filtro; con un sismo del
> catálogo seleccionado el mapa queda armado y el siguiente clic abre la comparativa sin aviso;
> `/building` cuelga de un único enlace del riel.

- **Superficie:** Consola · **Sesión:** C14
- **Componente:** web (`console/ConsolePage.tsx`, `console/DetailPanel.tsx`, `fleet/SiteCard.tsx`, `triage/TriageDetail.tsx`) · **Depende de:** nada · **Prioridad: MEDIA**
- **Cierra:** U-27, U-44
- **Tests de censo que toca:** `web/src/app/screenLabels.test.ts` (si `SiteCard` gana el enlace a la ficha del edificio, la numeración no cambia; si `NAV_PRESENTATION` gana el contrato con `routes.tsx`, es ahí).
- **Token nuevo:** no.
- **Cambia algo que un test defiende hoy:** sí — `ConsolePage.test.tsx` sobre la navegación tras solicitar.
- **Objetivo:** volver al riel al terminar en triage (o abrir el dictamen sin abandonar `/console`), desarmar la comparativa al apagar el histórico y declararla mientras está armada, y una entrada a la ficha del edificio desde `SiteCard` y desde el triage.
- **Criterios de aceptación:**
  - [x] Tras firmar o cancelar en triage, un solo clic devuelve al riel con el mismo sitio en foco.
  - [x] Con la comparativa armada, el mapa lo dice; al apagar el histórico se desarma.
  - [x] `inspector` llega a la ficha del edificio desde `/triage` sin pasar por `/console`.
- **Cómo se cerró (2026-09-09, SESIÓN C14):**
  - **El viaje de ida ya llevaba billete; faltaba el de vuelta.** Solicitar el dictamen navega a
    `/triage?incident=…`, y eso tiraba el riel, el mapa y el filtro. Ahora el salto se lleva puesto
    **de dónde se vino** (`&volver=<site_id>`, el sitio del incidente por el que se saltó, que es el
    que el operador estaba mirando) y el panel de triage encabeza con **◀ VOLVER A MONITOREO ·
    \<sitio\>**. Del otro lado, `/console?sitio=<id>` abre el riel enfocado en ese sitio. Es
    **estado inicial y no un efecto**: el deep-link es cómo se entró a la pantalla, no algo que la
    pantalla vaya aplicando después —un efecto reabriría el cajón cada vez que el operador lo
    cerrara—, y sin `?sitio=` el riel sigue naciendo cerrado, que es lo que protege los 380 px del
    mapa.
  - **Medido en el navegador, con la pila local viva:** el ciclo completo `SOLICITAR DICTAMEN` →
    `/triage?incident=…&volver=d1000000…` → `◀ VOLVER A MONITOREO` → `/console?sitio=d1000000…` con
    el riel abierto en *Sitio Sim 001 Puebla*, **un clic y 195 ms**.
  - **El mapa armado ya no es un secreto.** Con un sismo del catálogo elegido, el próximo clic en
    una estación abre la COMPARATIVA en vez del detalle. El aviso existía —el «PASO 2» de la tercera
    leyenda, abajo a la izquierda— pero además colgaba de `layers.catalog`: **apagar el histórico
    borraba el aviso y dejaba el mapa armado en silencio**. Ahora el aviso vive en la esquina de
    ESTADO DEL MAPA (arriba-izquierda, dueño único desde T-2.55), nombra el sismo con el mismo
    rótulo que su ◇ —función `catalogLabel`, una sola verdad: con trece diamantes iguales, dos
    rótulos distintos se leen como dos eventos—, trae su propio **CANCELAR**, y el cursor pasa a
    cruz. Medido: 593 × 25 px, una línea.
  - **Y apagar el histórico DESARMA**, por los dos mandos del mismo interruptor (la fila de CAPAS y
    el rótulo de la leyenda): que uno desarmara y el otro no sería peor que no desarmar ninguno. El
    desarmado se emite hacia el padre (`onSelectCatalog(null)`) en vez de tocarle el estado: el
    interruptor vive en el mapa, la selección sigue siendo suya.
  - **La ficha del edificio deja de colgar de un solo hilo.** `/building` se alcanzaba **solo** desde
    el riel de detalle de `/console`, y `inspector` y `building_admin` —que tienen la ruta concedida
    y NO tienen `/fleet`— dependían de ese riel para llegar al inmueble que están evaluando. Ahora
    hay entrada desde el panel de triage y desde cada tarjeta de flota, con la misma forma que el
    enlace del riel (tres formas distintas para un mismo destino se leen como tres destinos). El
    enlace se pinta desde `allowed_routes` (T-6.02): hoy lo tienen los siete roles web, y por eso
    mismo el gate tiene que existir antes de que deje de ser cierto.
  - **Ejercido con el rol real:** `inspector` entra, ve dos pestañas (MONITOREO · EVALUACIÓN), abre
    `/triage`, pulsa FICHA DEL EDIFICIO y aterriza en **DASHBOARD EDIFICIO** —no en SIN ACCESO—;
    y desde `/fleet`, la tarjeta lleva a la ficha del sitio de la tarjeta.
  - **Una trampa que se llevó por delante 42 tests:** montar un `<Link>` dentro de `SiteCard` puso en
    rojo `FleetPage.test` entero («Cannot destructure property 'basename'»), incluido el caso de los
    cuatro estados, que **construye su JSX aparte** y no pasa por el helper `render`. Y en
    `TriageDetail.test` había un caso que montaba el panel **a mano**, con la lista de props copiada
    y sin router: se reescribió sobre `arrange`, que es lo que evita que la próxima prop lo vuelva a
    romper.
  - **Verificación:** web 2 216 tests, `tsc`, `eslint`, `prettier` y `vite build` limpios; los tres
    criterios ejercidos en un navegador real contra `make soc-local`, con capturas.

### [x] T-6.12 · **El dato es lo más grande de cada pantalla** — `SOFTWARE`

> En `/triage`, `/tenants` y `/audit` el título gana al dato; los KPI miden 15 px en una pantalla y
> 28 en otra; 59 declaraciones bajo el piso tipográfico y cuatro tamaños inline que escapan a los
> censos; armado y en curso del simulacro se distinguen a distancia solo por el matiz.

- **Superficie:** Consola · **Sesión:** C12 (dos sesiones, por bloque)
- **Componente:** web (`styles/soc-tabs.css`, `styles/soc.css`, `console/KpiStrip`, `DetailPanel.tsx`, `QuorumNodes.tsx`, `IncidentTable.tsx`, `DrillBanner.tsx`) · **Depende de:** nada · **Prioridad: BAJA**
- **Cierra:** U-25, U-46
- **Tests de censo que toca:** `web/src/designTokens.test.ts` (el barrido de tamaños se amplía a los `fontSize` inline de TSX), `web/src/styles/layoutInvariants.test.ts` (paddings y alturas que dependen de esos tamaños).
- **Token nuevo:** sí — un escalón semántico de rótulo mínimo con piso declarado y auditable (hoy conviven tres pisos sin criterio).
- **Cambia algo que un test defiende hoy:** sí — alturas fijadas por `layoutInvariants` en los bloques que se toquen; se actualizan con captura antes y después.
- **Objetivo:** títulos de pantalla en un escalón menor que la métrica principal; el mismo KPI con el mismo token en todas las pantallas; ningún tamaño por debajo del piso ni escrito inline; el prefijo de estado del banner de simulacro (ARMADO / EN CURSO) en el escalón legible a distancia, sin robar alto al mapa.
- **Criterios de aceptación:**
  - [x] En las seis pantallas, el rótulo más grande es un dato o el estado, nunca el nombre de la pantalla. **Medido en navegador real** (`make soc-local`, 1920×1080, `takab_superadmin`), barriendo TODO elemento visible con texto propio y quedándose con el mayor:

    | pantalla | antes | después |
    |---|---|---|
    | `/console` | 28 px · `soc-alert__pga-value` (dato) pero el KPI en 15 | 28 px · `soc-alert__pga-value` |
    | `/fleet` | 28 px · `fleet__kpi-val` (título en 26) | 28 px · `fleet__kpi-val` (título en 22) |
    | `/triage` | **26 px · `h1.triage__title`** | 28 px · `soc-kpi__value` «4» |
    | `/tenants` | **26 px · `h1.mt__title`** | 28 px · `soc-kpi__value` «28» |
    | `/audit` | **26 px · `h1.audit__title`** (el segundo mayor medía 13) | 28 px · `soc-kpi__value` «50» |
    | `/building` | **20 px · `h1.bld__title`** | 28 px · nombre del sitio |

  - [x] Cero `fontSize` inline y cero declaraciones bajo el piso en `web/src`. Eran **64** declaraciones bajo el piso (47 de 9 px, 13 de 9.5 y 4 de 8.5 — la ficha decía 59 porque contaba con `font-size:` y no con el atajo `font:`) y **6** tamaños inline (cuatro `soc-pill` de 9 px, un objeto `style` de 11 y un `fontSize="8"` en el `<text>` de `TimeAxis`, que ningún censo de hoja podía ver). `typeScale.test.ts` barre ambas cosas.
  - [x] La tira de simulacro sigue por debajo del alto que fija `drill.spec.ts`: `drill-idle` mide **34 px** (tope 60) en los tres viewports, antes y después — el prefijo de estado sólo se monta cuando hay simulacro. **Ejercido con un simulacro real en `soc-local`** (1920×1080): ARMADO a T+2 min y luego EN CURSO sobre `Sitio Dev Puebla` (`POST /api/drills` → 201). Los dos banners miden **52 px**, con el estado en **16 px** sobre un detalle de 13 — se distinguen por CUERPO y no sólo por matiz —, la frase de seguridad viaja literal («🔶 SIMULACRO EN CURSO — ESTO NO ES UNA ALERTA REAL · 1 SITIO(S) · 0/0 ACUSADOS · 1 SIN COMANDO EMITIDO») y el mapa se queda en **476 px** con el banner en pantalla. Se cerró con TERMINAR (200) y se verificó que no queda nada armado ni en curso: un simulacro colgado sobrevive a `make soc-local` y ensucia los e2e de la sesión siguiente.
- **Cómo se cerró (2026-09-10, SESIÓN 2):**
  - **El piso tiene nombre: `--tk-text-min` (10 px).** No es un escalón nuevo: vale lo mismo que
    `--tk-text-2xs`, el más bajo de la escala, y el censo ancla esa igualdad. Lo que retira es la
    costumbre de inventar números — convivían **tres** pisos (8.5, 9 y 9.5 px) sin que ninguno
    estuviera declarado en ninguna parte. Mismo patrón que `--tk-touch-min` (T-6.20).
  - **Los títulos de pantalla bajan a `--tk-text-xl` (22 px)** —los cinco visibles; el de
    `/console` es de lector de pantalla (`.soc-vh`, 1×1) y nunca compitió— y la métrica principal
    sube a `--tk-text-2xl` (28 px), que es el escalón que la alerta ya usaba para el PGA.
  - **El KPI es UNA primitiva.** `.soc-kpi` (cifra + rótulo) pasa a pintar los contadores de
    `/triage`, `/tenants` y `/audit`, que hasta ahora eran rótulos de 10 px: el recuento de la
    bitácora vivía además **al pie de la página**. Los tres siguen DENTRO de su marco (o tras la
    puerta de T-2.59, en triage), así que `serverDataCensus` no gana una exención.
  - **La única excepción está medida y declarada.** La tira del wall no es la cifra grande de una
    pantalla: son once indicadores en una banda **sobre el mapa**. Con 28 px la banda se parte en
    filas y el mapa cae de 405 a 381 px en 1280×800, bajo el piso de 400 que defienden
    `layout.spec.ts:70` y `smoke.spec.ts:50`. Su cifra queda en `--tk-text-md` (16 px), que además
    retira el **15 px suelto** que había —15 no es ningún escalón de la escala—, y
    `typeScale.test.ts` la ancla como la única bajada permitida.
  - **`var(--f-ui)` NUNCA existió, y se citaba 15 veces en `soc-tabs.css`.** Un `font:` con una
    `var()` sin resolver es *invalid at computed-value time*: la declaración **entera** se cae,
    tamaño y peso incluidos. Medido en el navegador: `.soc-demo-mode__txt` pedía `700 12px/1` y
    pintaba **16 px / 400**, el heredado del `<body>`; igual `.notifychain__*` y `.triage-tasa__*`.
    La guarda vieja (`designTokens.test.ts:475`) sólo miraba las `var(--tk-*)`, así que este
    agujero le pasaba por debajo. `typeScale.test.ts` la cierra para **cualquier** prefijo.
  - **ARMADO / EN CURSO** salen a `.soc-drill__estado` en `--tk-text-md`: se distinguían a
    distancia sólo por el matiz —cian contra ámbar—, que es justo lo que un daltónico no tiene. La
    frase de seguridad («ESTO NO ES UNA ALERTA REAL») se conserva palabra por palabra.
  - **Trampa medida, y cara:** al añadir el token, el `tokens.css` que servía el dev server ya
    llevaba arriba media hora y **no lo recogió**. `--tk-text-min` resolvía a vacío en el
    navegador, así que las 64 declaraciones nuevas caían enteras y los rótulos heredaban 16 px: la
    banda del wall creció un 69 % y el mapa perdió hasta 71 px. La primera medición «después» era
    de una hoja rota. Se caza con una sonda de una línea
    (`getComputedStyle(document.documentElement).getPropertyValue('--tk-text-min')`), y se arregla
    reiniciando vite tras regenerar los tokens.
  - **Y quedaba una regresión real de 8 px** cuando la hoja ya se aplicaba: con el rótulo en 10 px,
    «MOSTRANDO 44 DE 44 · DE LAS CUALES 20 SIMULADAS» se partía en **cuatro líneas** dentro de un
    grupo de 156 px y fijaba el alto de la banda entera (405 → 397). No era la cifra: era que un
    rótulo de 10 px envuelve donde uno de 9.5 no lo hacía. Se resuelve como ya lo resuelve la
    banda bajo `max-height: 800px` —se desplaza, no se apila— y el mapa vuelve a 405 px, el mismo
    valor que en `main`.
  - **E2E: sin regresión, con control A/B.** Los 9 rojos de `npm run e2e` son **idénticos** a los
    de `main` en el mismo stack y el mismo minuto (`layout.spec:19` ×3, `layout.spec:70/108` y
    `smoke.spec:50` en 1440×900, `screens.spec:508` ×3). Los provoca la franja de alerta viva del
    seed (`AVISO SÍSMICO · UMBRAL INSTRUMENTAL`), que tapa los botones de capas del mapa y le
    quita alto: es un hallazgo previo a esta ficha y no se toca aquí.

### [x] T-6.13 · **Una tabla, una tarjeta, un botón** — `SOFTWARE`

> Tres sistemas de clases de tabla, dieciocho `soc-card` a mano en un fichero, 72 `soc-btn` sueltos
> en 30 ficheros, siete productores de pill, y la regla «conocido ⇒ stale» copiada en dos banners.

- **Superficie:** Consola · **Sesión:** C13 (tres sesiones: una por primitiva)
- **Componente:** web (`components/`, todas las pantallas) · **Depende de:** `T-6.12` · **Prioridad: BAJA**
- **Cierra:** U-24
- **Tests de censo que toca:** `web/src/styles/cssContract.test.ts` (se pondrá rojo por cada `className` que desaparezca, y ese rojo es correcto: se migra una tabla por ficha), `web/src/statePrecedenceCensus.test.ts` (si se extrae `staleDeLectura()`, el censo apunta al helper).
- **Token nuevo:** no.
- **Cambia algo que un test defiende hoy:** sí — tests de pantalla que afirman clases.
- **Objetivo:** `Table`, `Card` y `Button` en `components/` con contrato; las tres tablas fuera de `.soc-table` migradas una por sesión; el cálculo de stale extraído a una función única.
- **Criterios de aceptación:**
  - [x] Ninguna pantalla declara una tabla, tarjeta o botón fuera de la primitiva. Lo vigila `web/src/primitivasCensus.test.ts`, que barre TODO `.ts`/`.tsx` de producción y exige que `<table`, `soc-card` y `soc-btn` sólo aparezcan en su propio fichero de `components/`. Migradas: **6 tablas**, **21 tarjetas** y **72 botones en 30 ficheros**.
  - [x] `cssContract` en verde con las clases viejas retiradas de las hojas — y también `layoutInvariants`, cuya lista explícita de «clases que DEBEN tener regla» citaba `audit__table`. La entrada no se borró: se sustituyó por `audit__frame`, que es lo único de la bitácora que no era ni densidad ni cabecera fija (sus columnas no parten).
  - [x] `DrillBanner` y `MaintenanceBanner` consumen la misma función de stale — **y otros tres sitios más**. La ficha contaba dos; el censo, escrito para cazar la FORMA (`readError … ? updatedAt : null`) y no los nombres, encontró **cinco**: los tres banners de la franja de escena y las dos mitades de `ClassificationPanel`.
- **Cómo se cerró (2026-09-10, SESIÓN 2):**
  - **`components/Table.tsx`.** Seis `<table>` en el árbol y **tres sistemas de clases**: `fleet__admintable`, `bld__table` y `audit__table` redeclaraban `width`, `border-collapse`, el `th` y el `td` con valores casi iguales. *Casi*: los tres divergían en el cuerpo —11, 11 y 11.5 px— sin que nadie lo hubiera decidido, y ninguno heredaba el `tr:hover` ni el `tr:last-child` de la canónica. Lo que de verdad las distinguía cabe en dos modificadores: **`densa`** (la tabla que vive dentro de una tarjeta y no en una pantalla entera) y **`sticky`** (la bitácora, la única lista que no cabe nunca). Las tres hojas viejas se retiraron.
  - **`components/Card.tsx`.** Veintiuna tarjetas repetían la misma cabecera de tres niveles; las seis que llevan icono lo colocaban con un `style` en línea —una fila de flex escrita a mano, invisible a cualquier censo de la hoja, la misma familia que cazó T-6.12—. Ahora la fila es la clase `.soc-card__title` y el título, el icono, la procedencia y lo que va a la derecha entran por parámetro.
  - **`components/Button.tsx`.** 72 sitios escribían la variante a mano en el `className`. Dos exportaciones y no una prop, porque el producto tiene dos cosas distintas: el `<button>` que HACE algo y el `<Link>` que LLEVA a algún sitio —un enlace se abre en otra pestaña, se copia y entra en el historial; un botón no—. `type="button"` es el defecto **a propósito**: el de HTML es `submit`.
  - **`components/staleDeLectura.ts`.** «Si nunca supimos nada, el fallo ES el estado; si ya supimos algo, el fallo no lo borra: lo marca como RETENIDO con la hora de la última lectura buena» (regla de oro 7). Vive en `components/` y no en `features/scene/` porque no era de la escena: dos de sus cinco usos estaban en triage.
  - **Un defecto colateral de T-6.12, cazado con el navegador y no con un test:** en `/building` el código y las coordenadas quedaban pegados al nombre del sitio sin ni un espacio —«SITIO DEV PUEBLAsite-dev · 19.0414, -98.2063», el nombre acaba en x=262 y el código empieza en x=262—. `.bld__sub` es un `<span>`, así que su `margin-top` de 3 px no hacía nada; pasaba desapercibido mientras los dos medían lo mismo y se volvió ilegible al subir el nombre al escalón de la métrica. Un `display: block` y el margen escrito hace tiempo por fin se aplica.
  - **Trampa medida:** el codemod contaba `<div>` para encontrar el cierre de cada tarjeta y se descuadró en `QuorumNodes.tsx` — había un `<div className="soc-stateframe">` **citado dentro de un comentario**. Tercera vez que la misma trampa muerde en esta sesión (T-6.07 con `<style>`, T-6.22 con `<Tabs.Screen>`): **cualquier barrido estructural del marcado tiene que enmascarar los comentarios antes de contar.**
  - **E2E: sin regresión.** Los 9 rojos de `npm run e2e` son los mismos nueve que ya daba `main` (comprobado con un control A/B en T-6.12): los provoca la franja de alerta viva del seed. El árbol adelgazó: **534 líneas nuevas contra 609 retiradas** y el bundle bajó de 470,5 a 465,5 kB.

### [x] T-6.15 · **La consola no depende de internet para su fuente ni para su mapa** — `SOFTWARE`

> Dos familias desde Google Fonts y tiles y glifos desde `openfreemap` (los glifos dan 404 hoy).
> Un SOC con salida restringida pierde la fuente del dato y el mapa. Y el cian de marca transporta
> cinco significados.

- **Superficie:** Consola · **Sesión:** C15
- **Componente:** web (`styles/colors_and_type.css`, `console/MapPanel.tsx`) · **Depende de:** nada · **Prioridad: BAJA**
- **Cierra:** U-34, U-43
- **Tests de censo que toca:** `web/src/consoleImageCensus.test.ts` (los ficheros de fuente nuevos deben estar en el `COPY` del Dockerfile), `web/src/designTokens.test.ts` (nombre nuevo, valor anclado intacto).
- **Token nuevo:** sí — un nombre de acento de marca separado del cian operativo, con el **mismo valor** hoy.
- **Cambia algo que un test defiende hoy:** no.
- **Objetivo:** JetBrains Mono alojada como ya lo está Geist; un estado declarado del mapa cuando los tiles no llegan (nunca un lienzo vacío); un nombre de token para la marca distinto del cian de estado.
- **Criterios de aceptación:**
  - [x] Con `fonts.googleapis.com` bloqueado, la cola de incidentes y el PGA del banner siguen en la fuente del dato con cifras tabulares. **Medido con la red cortada en el navegador** (`page.route` abortando `fonts.googleapis.com` y `fonts.gstatic.com`): cero peticiones bloqueadas —porque ya no se hacen—, `JetBrains Mono` cargada, y `.soc-mono` de la cola, `.soc-alert__pga-value` y `.soc-kpi__value` los tres en `"JetBrains Mono"` con `font-variant-numeric: tabular-nums`.
  - [x] Con `openfreemap` bloqueado, el mapa declara su estado con los pins y leyendas intactos. **Medido**: `◐ SIN MAPA BASE · TILES NO DISPONIBLES · SITIOS EN VIVO`, tres leyendas en pie y, en la captura a zoom 14, los pins con su glifo de enlace (`⊘`), su glifo de sacudida (`?`) y las cintas DEMO. El rótulo que se conserva es el del producto —«SIN MAPA BASE»—, no el «SIN CARTOGRAFÍA» que proponía la ficha: dice lo mismo y ya estaba escrito, probado y traducido al vocabulario del operador.
  - [x] El frente P, el catálogo y el pill EDGE ya no comparten token con la marca: `--tk-brand` (mismo valor que `--tk-cyan` hoy, anclado por el censo) y su único consumidor con color es la hoja del Hosted UI de Cognito. Ninguna hoja de la consola lo cita, así que repintar la marca ya no toca nada del mapa.
- **Cómo se cerró (2026-09-10, SESIÓN 2):**
  - **El hallazgo era peor que el de la ficha, y más silencioso.** La ficha decía «dos familias desde Google Fonts». La medición dice que la consola **nunca las tuvo**: los dos `@import url(https://fonts.googleapis.com/…)` estaban escritos DESPUÉS del `@font-face` de Geist, y un `@import` sólo es válido al principio de la hoja. Medido contra `make soc-local`: **cero** peticiones a `googleapis`/`gstatic`, `document.fonts` con una sola cara (Geist), el bundle de producción sin un solo `@import` ni la cadena `googleapis`, y el ancho de «0123456789 ·» a `700 28px` **idéntico** pidiendo `'JetBrains Mono'` que pidiendo `'Saira Condensed'` (156,34 px las dos: el sustituto del sistema, no la familia). Con la fuente alojada pasa a 204 px. **Las cifras del SOC llevaban desde siempre en un monoespaciado cualquiera.**
  - **JetBrains Mono alojada, variable y en dos subsets.** `wght 100–800` en un solo fichero por subset (latin 40 kB, latin-ext 15 kB), con `unicode-range` para no cargar el extendido en la pantalla que no lo necesita. Variable y no tres estáticas porque los `700` del KPI y del PGA se estaban **sintetizando**: engorda los trazos sin cambiar los avances, y eso se nota justo en una columna de cifras. La licencia (SIL OFL 1.1) viaja con ella.
  - **Saira Condensed NO se aloja, y no es un olvido.** `--tk-font-brand` lo consume **una sola regla** de `colors_and_type.css` (`.tk-display, .tk-h1`) y **ningún marcado de la consola usa esas clases**. Alojar una familia entera para una regla que nadie alcanza sería pagar peso por nada; el token sigue para móvil y landing, que sí la usan y ya la alojan.
  - **Los glifos del mapa: tres 404 por sesión, y no eran cosméticos.** Ninguna capa declaraba `text-font`, así que MapLibre usaba su defecto de especificación (`Open Sans Regular, Arial Unicode MS Regular`) y `openfreemap` **no sirve ese par**. Fallaban los rangos `0-255`, `8704-8959` y `9472-9727` — el latín y los dos bloques donde viven `◐`, `◇` y `✳`, que son el rótulo del sitio, el glifo de enlace y el glifo de sacudida que T-6.09 y T-6.10 pusieron ahí **para que el daltónico no dependiera del matiz**. Las ocho capas de símbolo pasan a `Noto Sans Regular`, que openfreemap sí sirve: los tres rangos responden 200 y no queda un solo 404.
  - **El mapa sin tiles ya estaba resuelto, y se verificó en vez de rehacerlo.** `FALLBACK_STYLE` (T-1.50) es un fondo navy con las capas GeoJSON intactas; el badge lo declara. Con `openfreemap` abortado desde la primera petición, la captura a zoom 14 enseña los pins, sus dos glifos, las cintas DEMO y las tres leyendas.
  - **`--tk-brand` separa dos cosas que compartían nombre.** `--tk-cyan` es el acento **operativo** de la consola —57 selectores: pestañas, foco, selección, botones— y también era el cian de la marca, así que repintar la marca repintaba el frente P, el catálogo y el pill EDGE. El token nuevo vale lo mismo **hoy** (el censo lo ancla) y su único consumidor con color es la hoja del login de Cognito, que es la única superficie del repo donde el cian habla por la empresa y no por un estado. La hoja generada no cambió ni un byte: **no hace falta re-aplicar nada en AWS**.
  - **Censo nuevo:** `web/src/styles/sinInternet.test.ts` — ninguna hoja cita un host externo, **ningún `@import`** (que es la trampa que dejó muertas las dos importaciones), las dos familias que la consola pinta tienen `@font-face` con fichero local que existe en disco, la del dato es variable `100 800` y la licencia viaja con ella.

## 8 · Fichas · App móvil

### [x] T-6.19 · **La franja de simulacro dice la verdad, en todas las pestañas y para el brigadista** — `SOFTWARE`

> Medido con un simulacro real: dos gabinetes lo rechazaron y el teléfono anunció «SIMULACRO EN
> CURSO» tres minutos. El brigadista no ve el simulacro ni el modo demostración; el ocupante solo
> en INICIO; la franja de simulacro y la de reingreso son la misma forma con distinto matiz.

- **Superficie:** Móvil · **Sesión:** M1
- **Componente:** mobile (`features/home/HomeView.tsx`, `features/panel/PanelView.tsx`, `app/(occupant)/_layout.tsx`, `app/(brigadista)/_layout.tsx`) · **Depende de:** `T-6.17` (para saber cuántos gabinetes lo ejecutan) · **Prioridad: ALTA**
- **Cierra:** U-01 (mitad móvil), U-02, U-32
- **Tests de censo que toca:** `mobile/src/screenStateCensus.test.ts` — la franja es presentacional y no lee dato nuevo por su cuenta: consume el `mobile-state` que ya está en el marco; si se mueve al layout, el censo debe seguir viendo las cuatro entradas donde estaban.
- **Token nuevo:** no (`tokens.color.status.warning` para el simulacro, `tokens.color.fg.tertiary` con borde discontinuo para la demostración, como ya hace INICIO).
- **Cambia algo que un test defiende hoy:** sí — `HomeView.test.tsx` «drill activo: franja ámbar» gana la variante «anunciado sin gabinete que lo ejecute».
- **Objetivo:** la franja distingue «SIMULACRO EN CURSO» (al menos un gabinete acusó) de «SIMULACRO ANUNCIADO · ningún gabinete lo ejecuta» (todos rechazados o sin comando); vive en el layout de las dos pestañeras, no en INICIO; el brigadista la ve encima de su panel junto con el modo demostración; la forma la separa de la franja de reingreso (regla lateral gruesa y glifo, no relleno sólido) y ninguna de las dos depende del matiz. Sin bucles de animación: una entrada y una salida, ninguna si `reduceMotion`.
- **Criterios de aceptación:**
  - [x] Con los sitios en `rejected`, el teléfono no dice «EN CURSO».
  - [x] En RUTAS, DIRECTORIO, CUENTA, PANEL, TRIAGE, LISTA y SYNC la franja se ve igual que en INICIO.
  - [x] Un daltónico distingue simulacro de reingreso por la forma; verificado con simulador. **Cerrado el 2026-09-07 en el Pixel 8 Pro real:** se compiló un APK con los componentes reales (`SiteNoticeStrip` en curso / anunciado / demostración y `HomeView` en reingreso, con datos inyectados por un parche local no comiteado), se capturó en el teléfono y se simularon protanopia, deuteranopia, tritanopia y acromatopsia (Machado 2009, severidad 1.0, en RGB lineal) sobre la captura. En las cuatro, la regla lateral + altavoz, el borde discontinuo + ojo tachado y el relleno sólido + visto se distinguen sin matiz; en protanopia/deuteranopia el verde del reingreso y el ámbar del simulacro convergen al mismo amarillo, que es justo el caso que la forma resuelve. **Trampa medida:** el simulador de color de Android (`accessibility_display_daltonizer`) se activó en el aparato pero `screencap` NO lo incluye (captura idéntica byte a byte con y sin él): la simulación tiene que aplicarse sobre la captura. El teléfono quedó con el APK limpio de `main`.
  - [x] Un drill jamás abre `crisis.tsx` (test existente sigue verde).
- **Cómo se cerró (2026-09-06, SESIÓN 2):**
  - **La franja se deriva de `execution`** (T-6.17), no de la ventana: `features/notices/drillNotice.ts`
    es una función pura con cinco salidas — EN CURSO (solo si el gabinete de ESTE sitio acusó y no
    abortó), ANUNCIADO · AÚN NO CONFIRMA (`pending`), ANUNCIADO · NINGÚN GABINETE / SU GABINETE NO LO
    EJECUTA (`rejected`/`expired`/`no_gateway`, con la razón y el conteo «N de M gabinetes»),
    ABORTADO · ATENDIÓ UNA ALERTA REAL, y nada. Un valor desconocido cae en ANUNCIADO (default-deny).
    Una nube anterior a T-6.17 (sin `execution`) cae a `active`.
  - **Vive en el navegador:** `SiteNotices` se monta UNA vez en `(occupant)/_layout.tsx` y en
    `(brigadista)/_layout.tsx`, encima de `<Tabs>`; INICIO y las demás pestañas ya no la pintan. El
    brigadista la ve encima de su panel junto con el MODO DEMOSTRACIÓN, que se mudó a la misma
    franja. `tests/app/tab-layouts-notices.test.ts` lo deriva del sistema de ficheros: las dos
    pestañeras la montan, ninguna pestaña la monta por su cuenta, y todas reservan la banda de 64
    que la franja solapa (así no abre un hueco; lo que asoma bajo ella es el inset real).
  - **Forma, no matiz:** simulacro = regla lateral gruesa + glifo sobre fondo de tarjeta (nunca
    relleno sólido); demostración = borde discontinuo + ojo tachado; reingreso (en INICIO) =
    relleno sólido + visto. Tokens existentes; ninguno nuevo.
  - **Movimiento:** un fundido de entrada y uno de salida (`Animated`, sin Reanimated), ninguno con
    `reduceMotion` (`ui/useReduceMotion.ts`, observable). Un test exige que `Animated.loop` no se
    invoque y que un sondeo con el mismo aviso no re-anime.
  - **Censo:** `screenStateCensus` sigue en verde sin declarar nada nuevo — el contenedor está en
    `features/`, la pestaña sigue montando su `StateFrame` y JSX no es una llamada para el censo.

### [x] T-6.20 · **Todo objetivo táctil de una pantalla de vida cumple el mínimo** — `SOFTWARE`

> Medido en el Pixel: `REINTENTAR` ≈29 dp en las pantallas de crisis y alarma; «Ver directorio
> completo» 19 dp; el botón de pánico correcto (70 dp) pero al 35 % de la altura con el 60 %
> inferior vacío; `hitSlop` inexistente.

- **Superficie:** Móvil · **Sesión:** M2
- **Componente:** mobile (`ui/StateFrame.tsx`, `features/home/HomeView.tsx`, `app/panic.tsx`, `ui/theme.ts`) · **Depende de:** nada · **Prioridad: ALTA**
- **Cierra:** U-08, U-31
- **Tests de censo que toca:** ninguno existente; se **añade** un censo de objetivos táctiles hermano de `screenStateCensus` (todo `Pressable` en `src/app` y `features` con `minHeight` del token o `hitSlop`).
- **Token nuevo:** sí — altura mínima de objetivo táctil en `tokens.json`, consumida por `theme.ts` como los `space` y `radius`.
- **Cambia algo que un test defiende hoy:** no.
- **Objetivo:** ningún control por debajo del mínimo; el botón de pánico anclado al tercio inferior (cambio de posición, no de paso del flujo; si el revisor lo considera reordenamiento, va a ficha propia).
- **Criterios de aceptación:**
  - [x] `uiautomator` en el Pixel: todo control de crisis, check-in, alarma, pánico e inicio ≥ el mínimo en alto.
  - [x] El centro del botón de pánico queda en el tercio inferior de la pantalla.
  - [x] El censo táctil falla al añadir un `Pressable` sin altura del token ni `hitSlop`.
- **Cómo se cerró (2026-09-09, SESIÓN M2):**
  - **El mínimo es un token: `--tk-touch-min = 48 px`.** 48 dp es el mínimo de Android —la
    plataforma sobre la que se acredita esta app— y supera los 44 dp con los que la auditoría
    midió, así que no hay que elegir entre los dos números: el estricto cumple el otro. Vive en
    `@takab/design-tokens` (`tokens.touch.min`) y no en `theme.ts` para que la consola no pueda
    diverger; el tema lo consume como `touch.min` y expone `slopHasta(altoVisible)`, que calcula
    la holgura de un control que no puede crecer.
  - **Los 52 controles quedaron declarados.** 47 con `minHeight: touch.min` —entre ellos el
    `REINTENTAR` de las pantallas de vida (medía ≈29 dp) y los enlaces de texto que medían 19—;
    5 chips que viven DENTRO de una fila densa (LLAMAR y VERIFICAR del pase de lista, las
    severidades del reporte de daños) con `hitSlop` derivado del token, porque crecerlos hasta 48
    empujaría un pase de lista de 200 personas fuera de pantalla.
  - **Dos clases de control entraron por MEDIR, no por leer.** El censo de la ficha era de
    `Pressable`. En el aparato aparecieron el interruptor de GPS del aviso de privacidad (**27 dp**)
    y el campo del código de sitio (**46.7 dp**): ni `Switch` ni `TextInput` estaban censados.
    Ahora lo están.
  - **Y el arreglo del interruptor ERA INERTE, también medido.** Se le puso `hitSlop` y el teléfono
    dijo que no: un toque a 8 dp de su borde no lo movió. En Android el `hitSlop` solo lo honra una
    vista de React (`ReactHitSlopView`); sobre un control NATIVO se ignora **en silencio**. Así que
    el interruptor pasa a INDICADOR (`pointerEvents="none"`) y **la fila es el control**: 65 dp,
    con `accessibilityRole="switch"`, y responde tocando el rótulo a 20 dp del dibujo. El censo lo
    exige ahora por escrito: un `<Switch>` que reciba el dedo es un fallo.
  - **El botón de pánico, al alcance del pulgar.** El contenido crece (`flexGrow`) y el hueco
    sobrante se pone ENCIMA del botón (`marginTop:"auto"`): pasó del **35 %** de la altura al
    **92.4 %**. Anclarlo destapó lo siguiente, que solo se ve en el aparato: **la barra de gestos
    del sistema se comía su borde inferior**, y esa franja se queda con el toque. El hueco de abajo
    sale ahora del inset real del teléfono, no de un número inventado.
  - **Verificación en el Pixel 8 Pro** (`uiautomator`, 1344×2992 a 480 dpi ⇒ 1 dp = 3 px), con el
    APK compilado de este commit y sesión de ocupante real:

    | Pantalla | Medido |
    |---|---|
    | login | 67.7 y 59.3 dp · 0 por debajo |
    | privacidad (onboarding) | fila del GPS **65.3** (era un interruptor de 27) · CONTINUAR 48.0 |
    | enrolamiento | campo **48.0** (era 46.7) · VINCULAR 48.0 · continuar sin vincular 48.0 |
    | inicio | «Ver directorio completo →» **48.0** (era 19) · rutas 49.7 · alarma 49.7 · 4 pestañas 48.7 |
    | pánico | botón 70.7 dp, centro al **92.4 %** y por encima de la barra de gestos |
    | cuenta | 12 controles, todos ≥ 48 |
    | error sin conexión | **REINTENTAR 48.0** (era ≈29), con la red del teléfono apagada |

    El único nodo por debajo en cualquier captura es la superposición de LogBox (el visor de
    errores de desarrollo de React Native), que no es UI de la app.
  - **Lo que NO se ejerció en el aparato, y por qué:** los 5 chips con holgura —el directorio del
    sitio de staging no publica contactos y el resto vive tras una sesión táctica cuyo MFA lo teclea
    una persona— y las pantallas de crisis, check-in y alarma de inmueble, que redirigen sin
    incidente activo y sembrarlo pide la ventana de AWS (el SSO estaba caducado). Sus controles
    salen de los mismos estilos que sí se midieron, y el censo los cubre.
  - **Verificación:** móvil 566 tests + `tsc` + `expo lint` + `expo export`; web 2 163; gates de
    documentos 106. El paquete de tokens gana una variable y `css/tokens.css` se regeneró.

### [x] T-6.21 · **Las pantallas de crisis y alarma salen del token** — `SOFTWARE`

> 44 literales de color en cinco ficheros, con ámbares que no existen en el paquete, y un tamaño de
> instrucción entre dos escalones. `BuildingAlarmView` declara la excepción por escrito, y eso es
> honesto; pero deja las dos pantallas de vida fuera de cualquier drift gate.

- **Superficie:** Móvil · **Sesión:** M3
- **Componente:** `shared/design-tokens/tokens.json` + mobile (`features/alert/CrisisView.tsx`, `features/alarm/BuildingAlarmView.tsx`, `features/alarm/TacticalAckButton.tsx`, `app/camera.tsx`, `app/(brigadista)/panel.tsx`) · **Depende de:** nada · **Prioridad: MEDIA**
- **Cierra:** U-21 (mitad móvil)
- **Tests de censo que toca:** `web/src/designTokens.test.ts` (el paquete gana nombres, ningún valor anclado cambia); se **añade** un `designTokens.test` móvil que prohíba el literal de color y de tamaño en `mobile/src/**/*.tsx`.
- **Token nuevo:** sí — la familia semántica de la alarma del inmueble (fondo, franja, acento, texto sobre ámbar, error) y los escalones de la instrucción de crisis, con los **valores actuales** (la pantalla acreditada en el Pixel no cambia de color).
- **Cambia algo que un test defiende hoy:** no.
- **Objetivo:** cero literales en `mobile/src`; la paridad web ↔ móvil deja de ser cierta solo en `theme.ts`.
- **Criterios de aceptación:**
  - [x] `grep` de hex y `rgba(` en `mobile/src/**/*.tsx` (sin tests) devuelve cero.
  - [x] Captura antes y después de crisis, alarma y acuse: idénticas. **Probado por VALOR, byte a byte, que es más fuerte que dos capturas; las de la pantalla viva necesitan un incidente sembrado.**
  - [x] `make drift` cubre el paquete y el nuevo test móvil lo consume.
- **Cómo se cerró (2026-09-10, SESIÓN M3):**
  - **43 literales en cinco ficheros, y todos en las dos pantallas de VIDA.**
    `BuildingAlarmView` declaraba la excepción por escrito —y eso era honesto—, pero el efecto era
    que la crisis sísmica y la alarma del inmueble eran las ÚNICAS superficies fuera de cualquier
    drift gate: se podía cambiar la marca entera y no se enteraban.
  - **La familia se nombra por TONO, no por pantalla**, y no es un detalle: el ámbar lo comparten el
    repliegue sísmico y la alarma del inmueble, que son sucesos distintos con la misma piel.
    Llamarla `alarm` habría dejado al repliegue vistiéndose de algo que no es. Quedan
    `emergency.red.*` (siete pasos), `emergency.amber.*` (once), `onDark` (superficie y borde sobre
    piel oscura) y `veil` (tres pesos + su tinta).
  - **Las escalas `ink-1/2/3` son lo que ya había, ordenado:** un blanco cálido a tres opacidades
    —1 el dato, 2 el apoyo, 3 el pie— que estaba escrito seis veces con cuatro valores distintos.
  - **Los tres velos se conservan DISTINTOS** (0.4 · 0.55 · 0.6) aunque unificarlos habría sido más
    limpio: son tres usos medidos y la ficha exige que la pantalla acreditada en el Pixel no cambie
    de color. Unificar habría movido píxeles de una pantalla ya verificada; queda dicho en el test.
  - **«Idénticas» se prueba por VALOR y no por captura.** Dos capturas «que se ven iguales» dependen
    de la luz, del estado y del ojo; `ui/emergencyPalette.test.ts` ancla los **24 valores byte a
    byte** contra los literales que había antes de la ficha. Si alguien mueve uno, que sea un acto
    deliberado y no el efecto lateral de otra cosa — el mismo trato que las anclas de identidad de
    la consola.
  - **La guarda que faltaba:** `src/designTokens.test.ts` barre `mobile/src` entero y falla con
    cualquier `#rrggbb`/`rgba(` en producción. Los tests quedan fuera del barrido a propósito: ahí
    el literal ES el sujeto.
  - **Lo que NO se pudo capturar en el teléfono:** la crisis y la alarma en vivo. Las dos pantallas
    sólo se pintan con un incidente o una alarma ACTIVA —el enlace profundo a `/alarma-inmueble` sin
    alarma sale en negro—, y eso pide sembrar un incidente en la nube de desarrollo
    (`make cloud-staging-incident`), que es una acción hacia afuera y no se disparó por iniciativa
    propia.

### [x] T-6.22 · **Las pestañas del brigadista siguen a sus acciones** — `SOFTWARE`

> `inspector` ve LISTA sin `roster_read`, `building_admin` ve TRIAGE y cámara sin
> `damage_report_submit` ni `evidence_upload`; el táctico no tiene RUTAS ni DIRECTORIO, que RBAC
> le concede.

- **Superficie:** Móvil · **Sesión:** M4
- **Componente:** mobile (`app/(brigadista)/_layout.tsx`, `auth/profileGate.ts`) · **Depende de:** nada · **Prioridad: MEDIA**
- **Cierra:** U-30
- **Tests de censo que toca:** `mobile/src/screenStateCensus.test.ts` (añadir rutas al grupo táctico mete población nueva en `rutasConDato` y exige su prueba de cuatro estados).
- **Token nuevo:** no.
- **Cambia algo que un test defiende hoy:** no.
- **Objetivo:** pestañas derivadas de `allowed_actions`, nunca de una lista por rol; RUTAS y DIRECTORIO disponibles al táctico.
- **Criterios de aceptación:**
  - [x] `inspector` no ve LISTA; `building_admin` no ve TRIAGE; ambos ven RUTAS y DIRECTORIO.
  - [x] Un test cruza las pestañas visibles con la matriz de RBAC para los cuatro roles tácticos.
- **Cómo se cerró (2026-09-10, SESIÓN M4):**
  - **La pestaña cuelga de la acción, y cada una DECLARA de cuál.** El layout enumeraba cinco
    pantallas iguales para los cuatro roles y el reparto no era el de RBAC. Ahora sale de
    `auth/pestanasTacticas.ts`, donde `requiere: null` no significa «sin gate» sino «de todo el
    perfil, y alguien lo escribió» — sin esa obligación, la pestaña siguiente entra sin gate y nadie
    lo nota, que es justo como llegaron aquí LISTA y TRIAGE. Default-deny: sin `allowed_actions` sólo
    quedan las incondicionales, porque lo contrario es la pestaña que aparece cuando llega `/me` y
    para entonces el táctico ya pulsó.
  - **El cruce con RBAC no copia la matriz: la lee.** `tabs-tacticas-rbac.test.ts` carga
    `shared/fixtures/rbac-matrix.json` —que `export_rbac_matrix.py` genera de `auth/matrix.py` y
    `make drift` vigila— y compara pestaña a pestaña para los cuatro roles. Si mañana el inspector
    gana `roster_read` en el servidor, la pestaña aparece y el test sigue verde sin tocar nada.
  - **RUTAS y DIRECTORIO son EL MISMO módulo que los del ocupante**, no una copia:
    `export { default } from "../(occupant)/rutas"`. Se probó primero a extraerlos a `@/features/…`
    y **se revirtió con razón medida**: `screenStateCensus` decide si una ruta «posee dato de
    servidor» mirando sólo el fichero de la ruta, así que mover el cuerpo fuera hacía desaparecer la
    exigencia de declarar los cuatro estados — un agujero silencioso en una guarda compartida. Un
    test nuevo exige que esos dos ficheros sigan siendo **una sola línea**.
  - **Y el agujero queda escrito, no cerrado a medias.** Enseñarle al censo que renderizar una
    productora es invocarla es correcto, pero arrastra a la población `_layout.tsx` (excluible: un
    layout es marco, no pantalla) **y CUENTA**, que lleva `empty={false}` a fuego porque una sesión
    autenticada siempre tiene perfil. Probarle un vacío que no puede tener sería fabricarlo: es otra
    ficha.
  - **Medido en el Pixel 8 Pro, y tres veces, porque las dos primeras me dieron la razón equivocada.**
    Con siete pestañas cada hueco mide **64 dp** (448 dp de ancho). `uiautomator dump` decía que
    «DIRECTORIO» ocupaba 54 dp y cabía; **la captura decía «DIRECTO…»** — el volcado devuelve el
    texto, no lo pintado. Bajar sólo el tracking a 0.4 tampoco bastó. Entra con el cuerpo al `2xs`
    (10 px) que **ya existía en el paquete** y el tema móvil no exponía: no es un token nuevo. El
    objetivo táctil no se toca — **64 × 48.7 dp** por pestaña, sobre el mínimo de 48 de T-6.20.
  - **Ejercido con sesión real:** brigadista dentro (TOTP tecleado por una persona; Maestro no lo
    genera), las siete pestañas a la vista, y RUTAS y DIRECTORIO abriendo y **declarando su vacío**
    («Su edificio aún no publica rutas ni manuales.») en vez de una pantalla en blanco.
  - **Lo que NO se pudo ejercer en el teléfono, y por qué:** el reparto por rol. El único usuario
    táctico sembrado es **brigadista**, que tiene las dos acciones; `inspector` y `building_admin` no
    existen todavía ([`PENDIENTES-MAURICIO §2.6`](../PENDIENTES-MAURICIO.md)). Esa mitad la sostiene
    el cruce con la matriz, no una captura.

### [x] T-6.23 · **Volver del fondo refresca; la crisis no espera al tic** — `SOFTWARE`

> Sin push (está en simulado), la toma de crisis llega por sondeo de 30 s —medido: 8.5 s— y volver
> del segundo plano no fuerza el refetch porque `AppState` no está atado al `focusManager`.

- **Superficie:** Móvil · **Sesión:** M5
- **Componente:** mobile (`app/_layout.tsx`, `features/alert/useAlertState.ts`, `features/alert/CrisisView.tsx`) · **Depende de:** nada · **Prioridad: MEDIA**
- **Cierra:** U-36
- **Tests de censo que toca:** ninguno.
- **Token nuevo:** no.
- **Cambia algo que un test defiende hoy:** no.
- **Objetivo:** `AppState` → `focusManager` para que traer la app al frente refresque al instante; entrada del **contenedor** de crisis con el dato pintado en el primer frame (permitido por el principio 2), sin transición bajo `reduceMotion`.
- **Criterios de aceptación:**
  - [x] App en segundo plano cinco minutos → al frente → `mobile-state` refetch en menos de un segundo. **Probado con `QueryClient` y `focusManager` reales; la medición EN EL TELÉFONO no se pudo cerrar — abajo el porqué.**
  - [x] La instrucción, la zona, la fuente y el T+ están pintados en el primer frame del contenedor.
- **Cómo se cerró (2026-09-10, SESIÓN M5):**
  - **El defecto es de una línea que no estaba.** `refetchOnWindowFocus` viene puesto por defecto en
    TanStack Query y en React Native **no se dispara nunca**: no hay ventana de la que recuperar el
    foco. Sin atar `AppState` al `focusManager`, traer la app al frente no pedía nada — y con la push
    en simulado, quien abre la app porque el edificio está sonando esperaba al sondeo (30 s en
    reposo). El cable vive en `services/appFocus.ts`, con las dependencias por parámetro para poder
    probarlo sin simular React Native entero.
  - **`inactive` NO cuenta como fondo**, y es una decisión: en iOS es la app tapada por el centro de
    control o por una llamada entrante, así que tratarlo como fondo haría que descartar cualquier
    aviso provocara un ciclo foco→refetch de todas las consultas vivas. Y Android emite `active` más
    de una vez al volver: sin la guarda de «no repetir», cada repetición sería otro refetch.
  - **Se prueba la CONSECUENCIA, no sólo la traducción.** Un segundo test monta un `QueryClient` y el
    `focusManager` de verdad —lo único falso es el `AppState`—, sin sondeo, y exige que el evento
    `active` vuelva a pedir el dato. **Con control negativo**: sin el cable, el mismo evento no pide
    nada. Sin esa segunda mitad, el archivo pasaría igual si `focusManager` refrescara por su cuenta,
    que es justo lo que no hace.
  - **Los cuatro datos de la crisis salen de PROPS**, no de un efecto, y en el camino de lectura no
    hay ni una animación: `CrisisView` es presentacional puro. Se ata por los dos lados —render sin
    `act` ni temporizadores, y barrido de la fuente contra `Animated`/`withTiming`/`entering=`—
    porque el primero solo mira el árbol y no los fotogramas. **No se le añade entrada de contenedor**
    a propósito: el movimiento móvil es de `T-6.25`, y meterlo aquí lo dejaría medio hecho en dos
    fichas.
  - **⚠️ Lo que NO se pudo medir en el Pixel, con los cuatro intentos escritos** —porque el siguiente
    que lo intente merece no repetirlos:
    1. `logcat` no delata las peticiones en un build de **release**;
    2. el valor visible que se eligió de testigo (RTT del panel) **no cambió** en 35 s, así que no
       discrimina;
    3. los contadores de tráfico **por UID** ya no están expuestos en este Android (`xt_qtaguid` no
       existe y `dumpsys netstats` no da la app);
    4. y la premisa del criterio no se sostiene tal cual: **Android mantuvo vivos los temporizadores
       del sondeo durante los cinco minutos en segundo plano**, así que el dato nunca llegó a
       envejecer y no había nada que ver limpiarse. Cortar la red para forzarlo tampoco cerró: al
       restaurarla antes de traer la app al frente, el sondeo ya la había refrescado.

    El cable es el que documenta TanStack para React Native y su efecto está probado arriba; lo que
    queda sin número es el milisegundo en el teléfono.

### [x] T-6.24 · **El dato retenido del ocupante se ve** — `SOFTWARE`

> Con WiFi y datos apagados 105 s, la única señal fue una franja fina dibujada encima de la barra
> de estado de Android mientras «SEGURO» seguía verde e intacto. El umbral (tres sondeos perdidos)
> es correcto; la jerarquía no.

- **Superficie:** Móvil · **Sesión:** M6
- **Componente:** mobile (`ui/StateFrame.tsx`, `features/home/HomeView.tsx`) · **Depende de:** nada · **Prioridad: MEDIA**
- **Cierra:** U-33
- **Tests de censo que toca:** `mobile/src/screenStateCensus.test.ts` (el estado `stale` sigue viniendo del reloj; solo cambia cómo se pinta).
- **Token nuevo:** no (`tokens.color.status.warning` y las superficies existentes).
- **Cambia algo que un test defiende hoy:** sí — los tests de estados de las pantallas que afirman el literal de la franja.
- **Objetivo:** la franja retenida respeta el área segura; la tarjeta de estado retenida cambia de tono (borde y rótulo en retenido, no verde vivo) y dice desde cuándo; el texto sigue siendo el portador.
- **Criterios de aceptación:**
  - [x] Sin red 105 s, «SEGURO» no se ve verde vivo: la tarjeta declara retenido con su hora.
  - [x] La franja no se superpone al reloj ni a los iconos del sistema.
- **Cómo se cerró (2026-09-10, SESIÓN M6):**
  - **La franja se dibujaba en y=0, o sea encima del reloj de Android**, porque es el primer hijo del
    marco y el marco es la raíz de la pantalla. Ahora consulta el inset seguro. Verificado en el
    Pixel con la red cortada: la franja arranca bajo la barra de estado y el reloj, la batería y los
    iconos se leen enteros.
  - **La tarjeta pintaba SIEMPRE el tono de `site_health`**, que describe el gabinete y no sabe nada
    de si esta lectura llegó hace un segundo o hace diez minutos. Con dato retenido pasa a ámbar
    —borde y rótulo— y añade su línea. **El rótulo sigue diciendo SEGURO**: el edificio está bien, y
    lo que no se puede afirmar es que eso sea de ahora; cambiarlo sería inventar un estado del
    inmueble. El tono acompaña; el texto es el portador.
  - **Y la captura destapó un defecto que el arreglo mismo introducía.** La primera versión ponía
    «DATO RETENIDO · hace segundos» mientras la franja de arriba decía «hace 1 min»: dos edades del
    mismo hecho, y la de la tarjeta siempre la más corta — porque su `nowMs` es el instante de la
    CONSULTA, que ya es viejo justo cuando el dato lo está. Se cambia a **desde cuándo** (hora fija,
    que es lo que pedía el criterio): una hora no puede envejecer mal. Medido después: franja «hace
    1 min», tarjeta «desde 10:59 p.m.», reloj del teléfono 11:01. Concuerdan.
  - **⚠️ Consultar el inset rompió 115 pruebas de golpe**: `react-native-safe-area-context` lanza si
    nadie montó su provider, y desde que el marco lo consulta eso alcanza a todo test que renderice
    una pantalla. Se simula el módulo en el arranque de jest —lo que recomienda la propia librería—
    con `top: 42`, que es lo que devuelve el Pixel 8 Pro de verdad: así un test que mida posiciones
    mide algo parecido a lo que se ve.

### [x] T-6.25 · **Movimiento móvil: se consulta la preferencia, el hold tiene portador, el panel late y se detiene** — `SOFTWARE`

> `AccessibilityInfo.isReduceMotionEnabled` no se consulta en ninguna parte; el relleno del hold
> de pánico es el único estado que vive solo en el movimiento; el panel táctico ya dice «Frame
> recibido hace X» y no late.

- **Superficie:** Móvil · **Sesión:** M7
- **Componente:** mobile (`ui/useReduceMotion` nuevo, `features/panic/PanicButton.tsx`, `features/panel/PanelView.tsx`) · **Depende de:** nada · **Prioridad: BAJA**
- **Cierra:** U-22 (mitad móvil), inventario M7
- **Tests de censo que toca:** ninguno.
- **Token nuevo:** sí — una duración semántica de latido, análoga a la del paquete para la consola.
- **Cambia algo que un test defiende hoy:** no.
- **Objetivo:** un hook de movimiento reducido equivalente al de la consola; el hold de pánico cuenta en texto («MANTENGA · 2 · 1 · CONFIRMADO»); el panel táctico late mientras llegan frames y se congela cuando envejecen, con el pill LIVE / SIN CANAL como portador. Nada en `CrisisView`.
- **Criterios de aceptación:**
  - [x] Con movimiento reducido activo, el hold sigue siendo usable por su cuenta textual.
  - [x] El latido del panel se detiene al superar el umbral de edad y el pill lo dice.
  - [x] Cero animaciones nuevas en `crisis.tsx` ni `CrisisView.tsx`.
- **Cómo se cerró (2026-09-10, SESIÓN M7):**
  - **Dos premisas de la ficha habían caducado, y conviene decirlo.** `useReduceMotion` ya existía
    —lo trajo `T-6.19`—, sólo que lo miraba una sola superficie; y el token de latido tampoco hay
    que estrenarlo: `--tk-dur-pulse` entró con `T-6.10` para el halo de la consola, y el latido del
    panel táctico es el MISMO hecho en la otra superficie. Dos tokens para el mismo período serían
    dos ritmos que divergen.
  - **El hold de pánico tenía un defecto más grave que el que la ficha fichaba.** No es sólo que el
    relleno fuera el único portador: **la confirmación colgaba del callback de la animación**. Una
    animación no es un reloj —el sistema puede recortarla, y con la reducción puesta lo correcto es
    no animar— así que el voto de pánico dependía de la decoración. Ahora manda un temporizador, la
    barra acompaña, y el texto cuenta: `MANTENGA · 2 · 1 · CONFIRMADO`. Con reducción activa el hold
    **tarda exactamente lo mismo** (la protección anti-accidente no se acorta) y la cuenta sigue.
  - **El pill del panel afirmaba «LIVE» sobre un canal mudo.** Salía del estado del socket y nada
    más, mientras la misma pantalla imprimía «Frame recibido hace X» dos tarjetas más abajo: dos
    afirmaciones sobre el mismo hecho, y la grande era la optimista. Ahora la lectura vive en
    `livePill.ts` y depende de la EDAD del último frame — con el umbral en **5 s**, que son cinco
    frames de 1 s: bastante para no parpadear con el jitter de una red móvil y poco para que «LIVE»
    siga queriendo decir algo. Y distingue lo que no es lo mismo: `CANAL ABIERTO · SIN FRAMES`
    (jamás llegó uno) frente a `LIVE · SIN FRAMES RECIENTES` (llegó y envejeció).
  - **Con movimiento reducido el punto se queda quieto y ENCENDIDO.** Apagarlo sería perder el
    estado, no respetarlo; el portador es el rótulo del pill.
  - **La crisis no se toca, y hay guarda.** El barrido de `T-6.23` sobre `CrisisView.tsx` se extiende
    a `crisis.tsx`: es la única pantalla de la app donde una animación puede costarle segundos de
    lectura a alguien que tiene que salir del edificio.
  - **Ejercido en el Pixel:** el hold, con sesión de ocupante real — a mitad del mantenido la
    pantalla escribe `MANTENGA · 1` bajo el rótulo, con el relleno por la mitad. El latido del panel
    queda probado en tests (`livePill` + `LatidoPunto`) y **no se capturó en el teléfono**: vive en
    el perfil táctico, cuyo login exige un TOTP que teclea una persona.

### [x] T-6.26 · **Ningún identificador crudo en pantalla; el prompt cuenta lo que hay** — `SOFTWARE`

> La línea de tiempo del ocupante imprime `inhabit_monitor` tras el check-in; el prompt de esta
> auditoría cuenta 12 pantallas donde la spec declara 21.

- **Superficie:** Móvil · **Sesión:** M8
- **Componente:** mobile (`features/reentry/`, `features/alert/`) + `takab-docs/PROMPT-auditoria-uiux.md` · **Depende de:** nada · **Prioridad: BAJA**
- **Cierra:** U-40 (mitad móvil), U-41
- **Tests de censo que toca:** ninguno.
- **Token nuevo:** no.
- **Cambia algo que un test defiende hoy:** no.
- **Objetivo:** un diccionario de veredictos legibles compartido con la consola (que ya los rotula); el prompt corregido a 21.
- **Criterios de aceptación:**
  - [x] Ningún valor de enum del dictamen llega al ocupante sin traducir.
  - [x] El prompt y la spec coinciden en el número de pantallas.
- **Cómo se cerró (2026-09-10, SESIÓN M8):**
  - **Había TRES juegos de rótulos para los mismos cuatro valores**, y uno de ellos era el valor
    crudo: la consola tenía el suyo (`OPERACIÓN NORMAL`, `HABITAR · MONITOREO`…), el certificado del
    ocupante otro (`EDIFICIO APROBADO PARA REINGRESO`…) y la línea de tiempo imprimía
    `Firmado (inhabit_monitor)` a quien sólo quiere saber si puede volver a su casa.
  - **Los dos registros son legítimos y por eso el glosario trae los dos.** El operador conoce el
    vocabulario técnico y necesita el veredicto tal cual; el ocupante no. Lo que no es legítimo es
    que cada pantalla se invente el suyo — `shared/glossary/dictamen.json` los declara juntos, con
    su tono y si es habitable.
  - **Copia por superficie, comprobada por igualdad EN LOS DOS SENTIDOS.** `web/` y `mobile/` son dos
    builds distintos y ninguno puede importar el módulo del otro; es el mismo patrón —y la misma
    razón física— que `estadoGlosario` con `estados.json`. La dirección «el glosario no trae ninguno
    que aquí falte» es la que importa: sin ella, añadir un quinto veredicto dejaría a la app
    enseñando el texto de reserva para siempre y en silencio.
  - **Un status desconocido no se degrada NI se imprime crudo.** Las dos formas de fallar aquí son
    inventarle un significado a lo que no entendemos —`normal_operation` por defecto— y enseñar el
    identificador; la segunda era la que había. Ahora dice «DICTAMEN TÉCNICO EMITIDO», que no promete
    nada.
  - **Y el prompt de la auditoría contaba 12 pantallas donde la spec declara 21** desde que se
    escribió: un encargo que cuenta mal el alcance produce una auditoría que se cree completa. Queda
    corregido, con la razón al lado.

## 9 · Fichas · Panel LAN del gabinete

### [x] T-6.27 · **CONSOLA sin pliegue a 1080p; CAMPO con ondas legibles** — `SOFTWARE`

> Medido: a 1920×1080 el documento mide 1347 px y la botonera con el PIN nace fuera de pantalla;
> la spec fija «sin scroll vertical en 1080p» y el perfil «10 segundos con el PIN en la mano». En
> CAMPO cada carril de onda mide 35 px y los rótulos se pisan. Ningún test lo defiende.

- **Superficie:** Panel · **Sesión:** P1
- **Componente:** edge (`local_api/index.html`, solo CSS de `#bitacora`, `#col-der` y `body.mode-campo`) · **Depende de:** nada · **Prioridad: ALTA**
- **Cierra:** U-09, U-10
- **Tests de censo que toca:** `edge/tests/test_local_api_panel.py` — se **añade** un invariante de layout: `#actionbar` dentro de la altura objetivo en CONSOLA, y altura mínima de `.lane` en CAMPO.
- **Token nuevo:** no (la escala de espaciado de la spec §10.2).
- **Cambia algo que un test defiende hoy:** no.
- **Objetivo:** acotar la bitácora y las filas de la columna derecha para que el documento quepa en la resolución objetivo; en CAMPO, subir el mínimo de la fila de ondas o mover la nota al rótulo superior cuando el carril no dé para las dos. Ni un cambio de jerarquía, color ni texto.
- **Criterios de aceptación:**
  - [x] A 1920×1080 en CONSOLA, la botonera y el PIN están dentro de pantalla sin scroll.
  - [x] En CAMPO los rótulos de cada carril no se superponen y un hueco de señal es visible.
  - [x] El nuevo invariante del arnés falla si alguien vuelve a empujar la botonera fuera.
- **Cómo se cerró (2026-09-07, SESIÓN P1, en una sola sesión):**
  - **La causa raíz no era la bitácora: era que nada acotaba la página.** `body` declaraba
    `min-height:100vh` (no `height`), así que la página crecía con el contenido y el `#actionbar`
    —hermano posterior de `#grid` dentro de `#main`, que es quien tenía el `overflow`— se iba con
    él bajo el pliegue. Medido con Chromium sobre `?demo=reposo&mode=consola`: documento 1347 px
    sobre un viewport de 1080, botonera de 1230 a 1347, **entera fuera**.
  - **Y `#col-der` era quien estiraba:** seis tarjetas (brújula, salud, evidencia, LoRa, prueba,
    bitácora = 1124 px) contra **tres** filas declaradas, `minmax(300px,1fr) auto auto`. Las otras
    tres caían en filas implícitas `auto`, que no encogen. `#col-izq` medía lo mismo sólo porque
    el grid la estiraba: no era ella la que mandaba.
  - **El arreglo:** `body{height:100vh}`, el scroll baja de `#main` a `#grid` (así el `#actionbar`
    queda fijo por construcción, no por aritmética), y `#col-der` gana una fila por tarjeta más
    scroll propio. **No se recortó ninguna tarjeta:** sería perder la densidad que usa el técnico
    de pie. Resultado medido: **1080 px de documento, `scrollV=no`, botonera 963→1080 DENTRO, PIN
    en 1070**. A 1280×800 (el ancho mínimo declarado) también cabe, y antes no cabía (1480 px).
  - **Dos defectos que el propio arreglo destapó, y que no se dejaron pasar:**
    - La bitácora tiene `overflow:hidden auto`, así que su `min-content` es ~30 px y el grid le
      descontaba a **ella** todo el déficit de la columna: pasó de 96 px a 30, una línea de evento.
      Su fila es ahora `max-content`; quien scrollea es la columna.
    - Al acotar la página, un viewport bajo comprimía las pistas de onda a 34 px y el rótulo del
      canal (7–20) volvía a pisar la nota (18–28): **el solape de U-10, pero en CONSOLA, y lo
      habría introducido esta ficha**. `#waves-wrap` gana `min-height:240px`.
  - **CAMPO:** la fila de ondas pasa de la horquilla `minmax(220px,300px)` a `auto` con
    `#waves-wrap{min-height:216px}` (mismo patrón que `#rose-wrap` en T-2.30, y por la misma razón:
    el `overflow:hidden` de la tarjeta recorta el mínimo del wrap), y la nota deja el suelo de la
    pista para colocarse bajo el rótulo. Medido a 412×915: pistas de **31.5 → 54 px** y **solape 6 px
    → 0**. CAMPO revierte el acotado de la página (`height:auto`, `overflow:visible`): en un teléfono
    la página SÍ debe scrollear.
  - **El número que gobierna no es 4, es 6.** `laneGrow()` reparte `[1,3,1,1]` en la variante B, así
    que la pista más pequeña se lleva **1/6** del alto, no 1/4. Los dos suelos (216 en campo, 240 en
    consola) salen de esa división, y el test la **deriva** de la hoja y del propio `laneGrow()` en
    vez de teclearla: si mañana sube la tipografía del canal o entra una quinta pista, lo caza.
  - **El arnés no puede medir esto** (`panel_harness.js` es un mini-DOM sin motor de layout: su
    `clientHeight` es la constante 420). Los cuatro invariantes nuevos leen la **hoja** y comprueban
    la *mecánica* que hace el defecto imposible, igual que `layoutInvariants.test.ts` en la consola
    web porque jsdom tampoco mide. Las mediciones de arriba son de Chromium, a mano, y quedan aquí.
  - **Dos fallos propios que el ciclo cazó, y que valen para el siguiente:** `_regla("body")` sin
    ancla engancha con `html,body{margin:0}` —la primera coincidencia del fichero—, y
    `min-height:100vh` **contiene** la subcadena `height:100vh`, así que la guarda del acotado
    pasaba en verde contra la hoja vieja. Un test de CSS por subcadena miente si no ancla el
    separador de declaración.
  - **Alcance:** la ficha lo acotaba a `#bitacora`, `#col-der` y `body.mode-campo`. Hizo falta
    tocar además `body`, `#main`, `#grid` y `#waves-wrap`: dentro de aquellos tres selectores la
    única salida era un `max-height` en `vh` con la altura de la botonera y de la pila de banners
    tecleada a mano, que es exactamente el tipo de número que se desvía. Ni jerarquía, ni color,
    ni texto cambiaron.
  - **Verificación:** `pytest edge/tests/` completo en verde — **1461 pasados**, incluidos los 5
    del gate #3 contra el Shake real; `ruff check` y `ruff format --check` limpios.

### [x] T-6.28 · **Las escenas de demostración no afirman lo que el gabinete no puede hacer; el checklist dice lo que hay** — `SOFTWARE`

> `simulacro` y `prueba_actuadores` fuerzan `siren_sounding:true` con el relé en reposo; la cuenta
> del simulacro usa campos que el gabinete nunca emite; `?mode=` acepta cualquier cadena; el
> checklist enumera 10 escenas de 13 y describe `prueba_actuadores` como ya no es.

- **Superficie:** Panel · **Sesión:** P2
- **Componente:** edge (`local_api/index.html`: `SCENES`, `:2537`) + `takab-docs/design/edge-panel/VERIFICACION-T-2-23.md` · **Depende de:** nada · **Prioridad: ALTA**
- **Cierra:** U-11, U-12, U-42
- **Tests de censo que toca:** `edge/tests/test_local_api.py:800-817` (congela las escenas: si se añade `prueba_actuadores_en_curso`, se declara ahí), `edge/tests/test_local_api_panel.py` (la escena `simulacro` deja de tener sirena).
- **Token nuevo:** no.
- **Cambia algo que un test defiende hoy:** sí — la lista congelada de escenas, por adición.
- **Objetivo:** `simulacro` sin `siren_sounding`; `prueba_actuadores` se conserva como prueba terminada y gana una hermana `_en_curso` con `siren_reason:'test'` para el banner cian; la escena demo del simulacro deja de usar `elapsed_s`/`total_s`; `?mode=` valida contra las tres densidades; el checklist se extiende a las 13 escenas y describe la tarjeta de resultado. **Decisión de producto pendiente** (registrar en `DECISIONES-MAURICIO.md`): si un voceo por jack debe reflejarse en la línea de estado y con qué palabra, porque hoy «SONANDO» significa relé.
- **Criterios de aceptación:**
  - [x] En `?demo=simulacro` la línea de estado y la tarjeta del relé de sirena dicen lo mismo.
  - [x] Existe una escena que enseña el banner cian con relés en cian y otra que enseña la tarjeta de resultado; el checklist describe las dos.
  - [x] `?mode=lo-que-sea` cae a la densidad automática y lo declara.
  - [x] El checklist enumera las 13 escenas con su criterio (hoy son 15: entraron `simulacro_abortado` de T-6.29 y `prueba_actuadores_en_curso` de esta ficha).
- **Cómo se cerró (2026-09-07, SESIÓN P2):**
  - **Las escenas dejan de afirmar lo que el hardware no produce.** `simulacro` y
    `prueba_actuadores` ya no fuerzan `siren_sounding:true` sobre un relé en reposo: el booleano
    se deriva de la energización del relé y el simulacro es voceo por jack con cero relés. La
    prueba de actuadores se parte en dos escenas honestas: `prueba_actuadores_en_curso` (banner
    cian, relés `ACTIVADO` en cian, `SIRENA: SONANDO · PRUEBA` porque ahí sí suena por el relé,
    tarjeta `EN CURSO`) y `prueba_actuadores` (terminada: banner oculto, relés en reposo, tarjeta
    de resultado con `1 RELÉ SIN CONFIRMAR`). La lista congelada de escenas gana las dos nuevas.
  - **La cuenta del simulacro usa lo que el controlador emite.** `DrillController.status()` deriva
    `elapsed_s` de `started_at` con el reloj del Pi (misma familia que `aborted_age_s`), y el
    banner pinta `DRILL-… · 4 m / 8 m · INICIADO hh:mm:ss UTC`; `elapsed_s`/`total_s` de demo, que
    el gabinete real nunca mandó, desaparecen. La sub del banner afirma el voceo solo si
    `audio.will_sound` lo dice; sin asset dice `SIN VOCEO · <motivo>`.
  - **`?mode=` valida contra las tres densidades.** Otra cadena cae a AUTO y la cabecera lo
    declara: `?mode=xyz NO EXISTE → DENSIDAD AUTO`. Antes dejaba `body.mode-xyz`, ningún CSS
    aplicaba y nada lo decía.
  - **D-29, decidida por Mauricio en esta sesión:** el voceo por jack se declara APARTE en la
    línea de estado, `SIRENA: EN REPOSO · VOCEO: SIMULACRO|PRUEBA|ACTIVO`, solo cuando el jack
    suena y el relé está en reposo; `SIRENA` sigue siendo el relé y si suena, `SONANDO` ya lo dice.
    Registrada con su razón en `DECISIONES-MAURICIO.md` (cabecera, índice y sección) y anotada
    en la spec §9.2. Medido en MURO: la línea mide 845 px y no desborda.
  - **El checklist se ata al código.** `VERIFICACION-T-2-23.md §1` enumera las 15 escenas con su
    criterio y describe `prueba_actuadores` como la prueba terminada; un test nuevo compara por
    IGUALDAD los `?demo=` del documento con la lista congelada. Y **destapó un tercer defecto de
    la misma clase**: `aviso` (T-2.32) existía en el código desde julio y NUNCA estuvo en la lista
    congelada, porque aquel test solo comprobaba contención. Desde hoy la lista congelada y las
    claves de `SCENES` en el HTML también se comparan por igualdad.
  - **Censo de render:** la escena `simulacro` pasa a la forma real del estado (atada al
    controlador por un test de contrato start → status, como la del aborto), gana la hermana
    `simulacro_sin_voceo` que hace observable `audio.reason`, y se borran cuatro excepciones
    (`drill.started_at`, `drill.duration_s`, `drill.audio.will_sound`, `drill.audio.reason`) y una
    quinta (`audio.sounding`) que ahora tienen camino de render.
  - **Verificación.** Panel + censo + servidor local: 267 tests en verde; `pytest edge/tests/`
    completo en verde en modo simulado antes del último cambio de copy, y las tres suites que
    ejercitan el HTML repetidas después; docs (consistencia, mediciones, matriz regenerada):
    106 en verde; ruff limpio. Chromium sobre las tres escenas y `?mode=xyz`: textos exactos,
    relés en cian en la prueba en curso, cero errores de página.

### [x] T-6.29 · **El panel pinta el aborto cuando ocurre** — `SOFTWARE`

> El texto «SIMULACRO ABORTADO — ALERTA REAL EN CURSO» existe pero su condición exige
> `drill.active` y alerta a la vez, combinación que `abort()` hace imposible; `aborted` y
> `abort_reason` no se leen en ninguna línea.

- **Superficie:** Panel · **Sesión:** P3
- **Componente:** edge (`local_api/index.html:984`, `:999-1003`) · **Depende de:** `T-6.17` (el contrato de `status()` gana `aborted`; hoy ya lo emite) · **Prioridad: ALTA**
- **Cierra:** U-03 (mitad panel)
- **Tests de censo que toca:** `edge/tests/test_local_api_panel.py:850-856` — el test fabrica un estado imposible y se reescribe para leer `aborted`; `edge/tests/test_panel_render_census.py` (todo campo de `status()` tiene camino de render: `aborted` y `abort_reason` lo ganan).
- **Token nuevo:** no.
- **Cambia algo que un test defiende hoy:** sí — el test del aborto, por la razón escrita.
- **Objetivo:** leer `st.drill.aborted` y `abort_reason`; el banner ámbar pasa a «SIMULACRO ABORTADO — …» con la razón y se mantiene un tiempo declarado bajo la alerta real, sin tapar nada de la precedencia §9.1. Sin animación.
- **Criterios de aceptación:**
  - [x] Con `aborted:true` en el status, el panel lo pinta aunque `active` sea falso.
  - [x] Bajo alerta real el banner de alerta sigue arriba y el aborto se lee debajo.
  - [x] Test que recorre `DrillController.abort()` → `status()` → render, sin fabricar el estado.
- **Cómo se cerró (2026-09-07, SESIÓN P3):**
  - **El aborto es un estado propio, no la coincidencia «activo y alerta».** `render()` lee
    `st.drill.aborted` y pinta el banner ámbar «SIMULACRO ABORTADO — ALERTA REAL EN CURSO (motivo)»
    bajo la alerta (el orden físico de la pila es la precedencia de §9.1) o «— HUBO UNA ALERTA
    REAL (motivo)» cuando la alerta ya cerró. La condición vieja `drill && alert` era inalcanzable
    y, peor, con un simulacro vivo y una alerta de red encima habría rotulado «ABORTADO» sin que
    nadie abortara; ahora esa combinación sigue la regla 2 de §9.1 (el simulacro vivo solo se
    anuncia sin alerta real) y hay un test que lo fija.
  - **La ventana se declara y la edad la deriva el gabinete.** `DRILL_ABORT_VISIBLE_S = 1800` en
    el panel (30 min: cubre la ventana del simulacro y la de la alerta que lo cortó); `abort()`
    guarda `aborted_at` EN EL ESTADO (antes solo viajaba en el aviso a la nube) y `status()` añade
    `aborted_age_s` resuelto en el Pi, como toda edad de dato de este panel. Sin edad conocida el
    aviso no se esconde: esconder por un dato ausente sería inventarlo. El test lee la constante de
    la hoja en vez de teclearla.
  - **La meta dice cuándo:** `DRILL-… · ABORTADO 09:58:12 UTC · hace 42 s`. La sub declara que el
    voceo se cortó y que el aviso se retira solo. Ni animación ni color nuevos.
  - **Tests.** `test_local_api_panel.py`: el test que fabricaba el estado imposible se reescribe
    en cinco (aborto con `active:false`; alerta arriba y aborto debajo, midiendo el ORDEN en el
    árbol renderizado; caducidad en el límite, en el límite+1 y con edad desconocida; simulacro
    vivo bajo alerta real ⇒ ámbar oculto) más el del criterio 3, que corre
    `supervisor.drill.start_drill()` → `abort("SASMEX real")` → `local_api.status()` → render.
    `test_panel_render_census.py` gana la escena `simulacro_abortado` con la forma REAL del
    estado, atada al controlador por un test de contrato clave a clave (start → abort → status),
    y ocho excepciones escritas (`started_at`, `duration_s`, `ended_reason`, `audio.*`), dos de
    ellas con fecha de caducidad: T-6.28 les dará camino al corregir la cuenta del simulacro vivo.
    La escena demo `?demo=simulacro_abortado` entra en `_DEMO_SCENES_EXTRA`.
  - **Medido en Chromium** (`?demo=simulacro_abortado&mode=consola`, 1440×900): banner rojo de
    121 a 183 px, ámbar de 183 a 236 px justo debajo, cian oculto, cero errores de página.
  - **Verificación:** `pytest edge/tests/` completo en verde en modo simulado (el gate #3 no se
    ejerce); `ruff check` y `ruff format --check` limpios. El Pi de Puebla NO se redesplegó en
    esta sesión: el cambio llega con el siguiente despliegue del edge.

### [x] T-6.30 · **El pulso de vida se pinta y se detiene** — `SOFTWARE`

> El halo anima opacidad y escala de una caja sin fondo (`setPill` colorea el punto, nunca el halo)
> y late incondicionalmente: seguiría latiendo con «DATO RETENIDO» y con «SIN CONEXIÓN».

- **Superficie:** Panel · **Sesión:** P4
- **Componente:** edge (`local_api/index.html:73`, `:948-951`) · **Depende de:** nada · **Prioridad: MEDIA**
- **Cierra:** U-13
- **Tests de censo que toca:** ninguno existente; se **añade** al arnés un caso: con `S.failures > 0` el punto no late.
- **Token nuevo:** no (el color que `setPill` ya calcula).
- **Cambia algo que un test defiende hoy:** no.
- **Objetivo:** dar fondo al halo con el color del punto y aplicar `tk-pulse` solo con `conn.kind === 'live'`. Sin keyframes nuevos; `prefers-reduced-motion` ya lo apaga; el texto «PANEL EN VIVO» / «DATO RETENIDO DESDE …» porta el mismo estado.
- **Criterios de aceptación:**
  - [x] En vivo, el punto late y se ve; con dato retenido o sin conexión, está quieto.
  - [x] Bajo `reduce`, quieto siempre y el texto dice lo mismo.
  - [x] Cero `transition` y ningún keyframe nuevo en el fichero.
- **Cómo se cerró (2026-09-07, SESIÓN P4):**
  - **El halo tiene fondo, así que ahora hay algo que mirar.** `tk-pulse` anima opacidad y escala;
    el halo era una caja `position:absolute;inset:0` **sin color** —`setPill()` colorea el punto,
    nunca el halo—, de modo que la animación llevaba desde el primer día moviendo lo invisible.
    El halo hereda el fondo del punto (`background:inherit`): el color sigue saliendo del único
    sitio que ya lo calcula, el estado de conexión, sin un segundo lugar donde equivocarse.
  - **Y late solo cuando el dato es de ahora.** La animación pasa de `.dot .halo` a
    `.dot.pulse .halo`, y `render()` pone la clase con `classList.toggle('pulse', conn.kind ===
    'live')`. Antes latía incondicionalmente: con el fondo puesto habría seguido latiendo bajo
    `DATO RETENIDO` y bajo `SIN CONEXIÓN`, que es la regla de oro 7 contada al revés —un dato
    congelado con aspecto de vivo—. La spec §10.4 ya lo pedía así («variante con pulso animado
    para en vivo»); lo que faltaba era decirlo en §9.3, que es la sección que se sigue al
    implementar los cuatro estados: ahora lo dice.
  - **Tests.** Seis en `test_local_api_panel.py`: el pulso armado en vivo y quieto en los otros dos
    estados de conexión (por el árbol renderizado, con el contador de fallos real del arnés, no con
    un estado fabricado); el halo con fondo y sin animación en reposo, y la regla armada como
    único sitio donde se enciende; y dos guardas de movimiento —el inventario del panel es
    exactamente `tk-blink` y `tk-pulse`, no hay ninguna `transition`, y la defensa de
    `prefers-reduced-motion` sigue siendo el `*` global, que es lo que la hace cubrir todo—.
  - **Medido en Chromium** (1440×900, servido en local, cero errores de página):
    en vivo el halo es `rgb(0,230,118)` con `animation-name: tk-pulse` de 1 s y se le pilla a
    13.5 px de los 8 px del punto; con `reduced-motion: reduce` el rótulo sigue diciendo `PANEL EN
    VIVO` y el halo se queda en 8 px con `animation-name: none`; `?demo=dato_retenido` lo deja
    quieto en ámbar y, con la API apagada, quieto en rojo.
  - **Verificación:** `pytest edge/tests/` completo en verde en modo simulado (el gate #3 no se
    ejerce); `ruff check` y `ruff format --check` limpios. El Pi de Puebla NO se redesplegó: el
    cambio llega con el siguiente despliegue del edge, junto con T-6.27, T-6.28 y T-6.29.

### [x] T-6.31 · **Variables que existen; MURO que se lee entero** — `SOFTWARE`

> `--f-mono` y `--warn` no están definidas: la comparativa pierde la fuente del dato y las cifras
> tabulares, y la advertencia de banda de fábrica no se pinta ámbar. En MURO el estado del relé
> mide 28 px y su nombre 10 px.

- **Superficie:** Panel · **Sesión:** P5
- **Componente:** edge (`local_api/index.html:168`, `:225`, `:1188`, reglas `body.mode-muro`) · **Depende de:** nada · **Prioridad: MEDIA**
- **Cierra:** U-14, U-15
- **Tests de censo que toca:** ninguno existente; se **añade** una guarda al arnés que extraiga todos los `var(--x)` del CSS y falle si alguno no está declarado.
- **Token nuevo:** no (`--f-data` y `--tk-warn` ya existen; los escalones de la spec §10.2 para el nombre del relé en muro).
- **Cambia algo que un test defiende hoy:** no.
- **Objetivo:** usar los tokens que existen; en `:1188` conmutar la clase con `classList.toggle` en vez de reasignar `className`; en `body.mode-muro`, dos reglas para `.relay .rl` y `.relay .re`, sin tocar CONSOLA ni CAMPO.
- **Criterios de aceptación:**
  - [x] La guarda de `var()` está en verde y falla al introducir una variable inexistente.
  - [x] La comparativa muestra cifras tabulares en la fuente del dato; la advertencia de banda se ve ámbar.
  - [x] En MURO a cinco metros se lee de qué relé es cada «ACTIVADO».
- **Cómo se cerró (2026-09-07, SESIÓN P5):**
  - **Las dos variables fantasma resultaron ser tres defectos, no dos.** `--f-mono` (la
    comparativa) traía fallback, así que sus cifras se pintaban en la monoespaciada del sistema y
    nada se veía roto; y el atajo `font:` **reinicia** `font-variant-numeric` y gana por
    especificidad a la clase `.mono` que el JS pone en cada valor, así que las columnas bailaban
    horizontalmente a cada repintado — lo contrario de lo que pide §10.2. `--warn` (la advertencia
    de banda de fábrica) no traía fallback: la declaración entera se descartaba y el aviso heredaba
    el color de su padre, es decir, se leía igual que una banda elegida. Los nombres del panel son
    `--f-data` y `--tk-warn`; ninguno de los dos es un token nuevo.
  - **El tercero salió al tirar del hilo:** `$('prox-profile').className = …` reasignaba la clase
    **entera** y borraba el `meta` con el que nace el rótulo en el esqueleto, en las tres ramas
    —incluida la de «umbrales S/D (motor caído)»—. Desde el primer repintado la línea de umbrales
    se pintaba con la tipografía heredada del contenedor, no con la de una meta. Se conmuta con
    `classList.toggle`, que es lo único que esa línea decide.
  - **MURO: el `ACTIVADO` ya tiene dueño.** El estado del relé crecía a 28 px y el nombre se
    quedaba en 10: a cinco metros se leía que algo está accionado y no si era la sirena, el gas,
    los ascensores o los retenedores — justo la mitad que hace falta para actuar. Dos reglas
    nuevas en `body.mode-muro` (nombre 18 px, detalle 14 px, escalones de §10.2). CONSOLA y CAMPO
    no se tocan, y hay un test que lo exige.
  - **La guarda que faltaba.** El arnés extrae todo `var(--x)` del fichero —también el que se
    escribe desde JS— y lo compara contra lo declarado en el `:root`: 27 declaradas, 23 usadas,
    cero huérfanas. **El fallback no exime**, porque el fallback es precisamente lo que hizo que
    `--f-mono` sobreviviera meses. Y una guarda de la guarda: se le inyecta una variable
    inexistente —con fallback y sin él— y se exige que la cace, midiendo la DIFERENCIA contra la
    hoja real para que el test siga diciendo la verdad el día que el panel llegue sucio.
  - **Medido en Chromium** (cero errores de página): MURO a 1920×1080 con los cinco relés
    accionados → `18 / 28 / 14 px` en las cinco filas, sin desbordes y sin scroll horizontal de
    página; la comparativa resuelve a `"JetBrains Mono", ui-monospace…` de 12 px con
    `font-variant-numeric: tabular-nums`; y la línea de umbrales conserva `meta` en los dos
    orígenes, pasando de `rgb(138,156,177)` (`--tk-fg-3`) a `rgb(255,193,7)` (`--tk-warn`) cuando
    la banda es de fábrica.
  - **Verificación:** `pytest edge/tests/` completo en verde en modo simulado (el gate #3 no se
    ejerce); `ruff check` y `ruff format --check` limpios. El Pi de Puebla NO se redesplegó: el
    cambio llega con el siguiente despliegue del edge, junto con T-6.27…T-6.30.
