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

### [ ] T-6.16 · **El reporte de simulacro se puede entregar a Protección Civil** — `SOFTWARE`

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
  - [ ] El PDF nombra cliente y sitios; jamás imprime un UUID donde hay nombre.
  - [ ] Imprime cómo terminó y, por sitio, `rechazado` / `sin gabinete comandable` / `sin acuse`.
  - [ ] Dos PDFs del mismo modelo producen los mismos bytes (test existente sigue verde).
  - [ ] La pestaña reservada al exportar muestra el documento o un error legible; nunca queda en blanco.

### [ ] T-6.18 · **Los dos arneses vuelven a ejercer lo que prometen** — `SOFTWARE`

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
  - [ ] `PHASE=crisis` produce `alert_active` en el teléfono aunque el incidente anterior tenga dictamen firmado.
  - [ ] En `make soc-local`, un simulacro sobre el sitio simulado llega al panel `:8080` como `drill.active=true` y un `/quake` lo aborta de forma visible.

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

### [ ] T-6.06 · **Los vacíos dicen la causa real; la cola declara `error` y `stale`; ninguna caja en blanco** — `SOFTWARE`

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
  - [ ] Con alcance vacío, `/console`, `/fleet`, la comparativa y la cola dicen «EN SU ALCANCE», no «EN EL TENANT».
  - [ ] La cola de incidentes declara `error` con reintento y `stale` con su reloj.
  - [ ] `DemoModeBanner` con lectura caída y modo apagado imprime una frase con sujeto; el e2e «nunca una caja en blanco» en verde.
  - [ ] `SiteCard` y la cabecera de `/building` salen de `MARCOS_INCOMPLETOS`.

### [ ] T-6.07 · **El arranque no tiene silencios** — `SOFTWARE`

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
  - [ ] Con JavaScript lento, el usuario ve algo con marca antes del primer frame de React.
  - [ ] Pasado el umbral, el splash dice qué espera (`/me`) y desde cuándo.
  - [ ] Tras `handleUnauthorized`, la landing dice por qué se cerró la sesión.
  - [ ] El fallback sin Cognito habla al operador, no al que despliega.

### [ ] T-6.08 · **El login se ve TAKAB** — `SOFTWARE` + `TERRAFORM`

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
  - [ ] La pantalla de Cognito muestra el imagotipo y los colores de superficie, borde y acento del paquete.
  - [ ] El CSS subido es salida de un generador; un test falla si diverge de `tokens.json`.
  - [ ] Captura antes y después en el informe de la sesión; los textos siguen siendo los de Cognito (no se pueden cambiar) y se dice.

### [ ] T-6.09 · **Contraste AA donde hay texto, y forma donde solo había color** — `SOFTWARE`

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
  - [ ] axe sin filtrar reporta cero `color-contrast` en `/fleet` y `/tenants` con el seed de demostración.
  - [ ] `watch` y `normal` se distinguen sin color (glifo o radio), verificado con un simulador de deuteranopía.
  - [ ] `axe.spec.ts` cubre `/building` y bloquea por contraste en las pantallas que ya están limpias.

### [ ] T-6.10 · **Movimiento honesto: se detiene, se declara y se apaga** — `SOFTWARE`

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
  - [ ] Con `reduce`, `getComputedStyle(...).transitionDuration` es cero en los selectores hoy vivos y la barra del UPS salta al valor final.
  - [ ] El latido de `LinkPill` se detiene cuando el último frame supera el umbral, con el texto de edad diciendo lo mismo.
  - [ ] La fila nueva lleva `NUEVO` N segundos aunque no haya animación; `AlertBanner` no cambia ni una línea.
  - [ ] Cero `transition: all` y cero literales de duración en las hojas de la consola.

### [ ] T-6.11 · **El aviso de privacidad es una franja, no un panel** — `SOFTWARE`

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
  - [ ] A 1280×800 con el banner presente, el mapa mide más que su piso.
  - [ ] El banner no crece más de una fila en ningún viewport de la matriz.
  - [ ] `layout.spec.ts` «el banner de privacidad es una FRANJA» en verde.

### [ ] T-6.14 · **El flujo alerta → dictamen no pierde el contexto** — `SOFTWARE`

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
  - [ ] Tras firmar o cancelar en triage, un solo clic devuelve al riel con el mismo sitio en foco.
  - [ ] Con la comparativa armada, el mapa lo dice; al apagar el histórico se desarma.
  - [ ] `inspector` llega a la ficha del edificio desde `/triage` sin pasar por `/console`.

### [ ] T-6.12 · **El dato es lo más grande de cada pantalla** — `SOFTWARE`

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
  - [ ] En las seis pantallas, el rótulo más grande es un dato o el estado, nunca el nombre de la pantalla.
  - [ ] Cero `fontSize` inline y cero declaraciones bajo el piso en `web/src`.
  - [ ] La tira de simulacro sigue por debajo del alto que fija `drill.spec.ts`.

### [ ] T-6.13 · **Una tabla, una tarjeta, un botón** — `SOFTWARE`

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
  - [ ] Ninguna pantalla declara una tabla, tarjeta o botón fuera de la primitiva.
  - [ ] `cssContract` en verde con las clases viejas retiradas de las hojas.
  - [ ] `DrillBanner` y `MaintenanceBanner` consumen la misma función de stale.

### [ ] T-6.15 · **La consola no depende de internet para su fuente ni para su mapa** — `SOFTWARE`

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
  - [ ] Con `fonts.googleapis.com` bloqueado, la cola de incidentes y el PGA del banner siguen en la fuente del dato con cifras tabulares.
  - [ ] Con `openfreemap` bloqueado, el mapa declara «SIN CARTOGRAFÍA» con los pins y leyendas intactos.
  - [ ] El frente P, el catálogo y el pill EDGE ya no comparten token con la marca.

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

### [ ] T-6.20 · **Todo objetivo táctil de una pantalla de vida cumple el mínimo** — `SOFTWARE`

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
  - [ ] `uiautomator` en el Pixel: todo control de crisis, check-in, alarma, pánico e inicio ≥ el mínimo en alto.
  - [ ] El centro del botón de pánico queda en el tercio inferior de la pantalla.
  - [ ] El censo táctil falla al añadir un `Pressable` sin altura del token ni `hitSlop`.

### [ ] T-6.21 · **Las pantallas de crisis y alarma salen del token** — `SOFTWARE`

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
  - [ ] `grep` de hex y `rgba(` en `mobile/src/**/*.tsx` (sin tests) devuelve cero.
  - [ ] Captura antes y después de crisis, alarma y acuse: idénticas.
  - [ ] `make drift` cubre el paquete y el nuevo test móvil lo consume.

### [ ] T-6.22 · **Las pestañas del brigadista siguen a sus acciones** — `SOFTWARE`

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
  - [ ] `inspector` no ve LISTA; `building_admin` no ve TRIAGE; ambos ven RUTAS y DIRECTORIO.
  - [ ] Un test cruza las pestañas visibles con la matriz de RBAC para los cuatro roles tácticos.

### [ ] T-6.23 · **Volver del fondo refresca; la crisis no espera al tic** — `SOFTWARE`

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
  - [ ] App en segundo plano cinco minutos → al frente → `mobile-state` refetch en menos de un segundo.
  - [ ] La instrucción, la zona, la fuente y el T+ están pintados en el primer frame del contenedor.

### [ ] T-6.24 · **El dato retenido del ocupante se ve** — `SOFTWARE`

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
  - [ ] Sin red 105 s, «SEGURO» no se ve verde vivo: la tarjeta declara retenido con su hora.
  - [ ] La franja no se superpone al reloj ni a los iconos del sistema.

### [ ] T-6.25 · **Movimiento móvil: se consulta la preferencia, el hold tiene portador, el panel late y se detiene** — `SOFTWARE`

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
  - [ ] Con movimiento reducido activo, el hold sigue siendo usable por su cuenta textual.
  - [ ] El latido del panel se detiene al superar el umbral de edad y el pill lo dice.
  - [ ] Cero animaciones nuevas en `crisis.tsx` ni `CrisisView.tsx`.

### [ ] T-6.26 · **Ningún identificador crudo en pantalla; el prompt cuenta lo que hay** — `SOFTWARE`

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
  - [ ] Ningún valor de enum del dictamen llega al ocupante sin traducir.
  - [ ] El prompt y la spec coinciden en el número de pantallas.

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

### [ ] T-6.28 · **Las escenas de demostración no afirman lo que el gabinete no puede hacer; el checklist dice lo que hay** — `SOFTWARE`

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
  - [ ] En `?demo=simulacro` la línea de estado y la tarjeta del relé de sirena dicen lo mismo.
  - [ ] Existe una escena que enseña el banner cian con relés en cian y otra que enseña la tarjeta de resultado; el checklist describe las dos.
  - [ ] `?mode=lo-que-sea` cae a la densidad automática y lo declara.
  - [ ] El checklist enumera las 13 escenas con su criterio.

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

### [ ] T-6.30 · **El pulso de vida se pinta y se detiene** — `SOFTWARE`

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
  - [ ] En vivo, el punto late y se ve; con dato retenido o sin conexión, está quieto.
  - [ ] Bajo `reduce`, quieto siempre y el texto dice lo mismo.
  - [ ] Cero `transition` y ningún keyframe nuevo en el fichero.

### [ ] T-6.31 · **Variables que existen; MURO que se lee entero** — `SOFTWARE`

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
  - [ ] La guarda de `var()` está en verde y falla al introducir una variable inexistente.
  - [ ] La comparativa muestra cifras tabulares en la fuente del dato; la advertencia de banda se ve ámbar.
  - [ ] En MURO a cinco metros se lee de qué relé es cada «ACTIVADO».
