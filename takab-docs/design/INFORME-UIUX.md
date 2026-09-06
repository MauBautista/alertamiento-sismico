# Informe UI/UX — las tres superficies, medidas antes de tocarlas

> **Qué es esto.** La SESIÓN 1 del encargo `takab-docs/PROMPT-auditoria-uiux.md`, ejecutada el
> **2026-09-06** sobre `main` en `2e0c02d`. **No arregló nada**: cada hallazgo salió como ficha de
> [`PLAN-REFORMA-VISUAL.md`](PLAN-REFORMA-VISUAL.md), y las mejoras se ejecutan después, una
> superficie por sesión. Ningún fichero de código cambió en esta sesión.
>
> **El estado VIVO de cada hallazgo será su ficha, no este documento.** Aquí se congela lo que se
> vio el 2026-09-06 en tres superficies con **licencia distinta**: consola SOC (`web/`, AMPLIA),
> app móvil (`mobile/`, MEDIA) y panel LAN del gabinete (`edge/takab_edge/local_api/`, ESTRECHA:
> se audita contra su especificación, no se reimagina).
>
> **Cómo se leyó cada ítem.** 🟢 exige tres cosas: implementado, con test, **y ejercido al menos
> una vez fuera de los tests**. 🟡 es que falta una de las tres, o que el código cumple y el
> documento que lo describe quedó desfasado. 🔴 es que no existe, o que existe algo que no hace lo
> que su nombre dice. Severidad **ALTA** solo si una pantalla miente, un simulacro es confundible
> con una alerta real, un rol ve de más, o un atajo de desarrollo es visible.
>
> **Lo que este informe midió contra el sistema vivo, no contra el repositorio:** el stack local
> completo (`make soc-local`: consola, API, gabinete simulado) recorrido con Playwright y axe;
> el panel del gabinete en sus 13 escenas × 3 densidades × 2 estados de `prefers-reduced-motion`
> (78 recorridos); el **Pixel 8 Pro real** con el APK de release compilado desde `2e0c02d` (login
> Cognito, pánico, crisis, check-in, offline con WiFi y datos apagados, medidas táctiles con
> `uiautomator`); la consola **desplegada** (`/api/health` declara `1e7bf0f`) en solo lectura hasta
> el Hosted UI de Cognito; el gabinete **real de Puebla** (release `20260830T222850Z-71ac7df`) por
> SSH y HTTP solo GET; y **un simulacro real de 3 min** disparado por Mauricio desde la consola dev
> a sus dos gabinetes. Los ocho hallazgos ALTA se re-verificaron abriendo el fichero antes de
> escribirlos. Lo que no se pudo ejercer está en §7.

---

## 1 · Resumen ejecutivo

**Lo que está bien, y conviene no tocar:** la honestidad de dato de las tres superficies (`S/D`,
`<0.001 g`, «DATO RETENIDO», «SIN ENLACE» en ámbar, los tres estados por relé, el `StateFrame` con
sus cuatro estados y su censo), la separación por forma, color y texto entre simulacro y alerta
real en cada superficie tomada por separado, el camino de lectura de la alerta **sin una sola
animación** en las tres, el panel del gabinete sin red externa ni `localStorage`, la degradación de
la consola cuando cae la identidad, y una batería de tests de censo que se puso roja tres veces
durante esta auditoría **con razón**.

**Lo que hace hoy peligrosa una exposición, en orden:** (1) la app móvil anuncia
«SIMULACRO EN CURSO» aunque **ningún gabinete lo esté ejecutando** — medido hoy con un simulacro
real: los dos gabinetes lo rechazaron y el teléfono lo anunció tres minutos; (2) el **brigadista
no ve nada** durante un simulacro ni en modo demostración: su panel dice «SIN INCIDENTE ABIERTO»
mientras el edificio vocea; (3) la alerta real, el simulacro, el mantenimiento y el modo
demostración **solo se ven en `/console`**: en las otras cinco pantallas de la consola no hay
rastro; (4) un distintivo verde **«AUTH · MFA»** junto al botón de acuse es un literal del mockup,
se pinta también en la sesión de desarrollo y ningún dato lo respalda; (5) la marca **DEMO** se
aplica al mapa y a la flota pero **no a la cola de incidentes** de la misma pantalla; (6) el
aborto de un simulacro por sismo real **no viaja a ninguna superficie**; (7) dar de alta un sitio
para un cliente recién creado lo deja **en el tenant del operador**, sin aviso; (8) el botón
de reintento de las pantallas de vida del móvil mide **29 dp**.

**Lo que se ve mal en una demo** está en §3, pantalla por pantalla. **El inventario de movimiento**
(lo que hay, lo que falta, lo que sobra) está en §5: la animación más valiosa del producto —el
latido que se detiene cuando el dato envejece— **existe en la consola en dos sitios**, en el panel
del gabinete **está declarada y no se pinta**, y en el móvil no existe.

**47 ítems: 9 verdes · 29 amarillos · 9 rojos.** 47 hallazgos numerados: 8 ALTA, 30 MEDIA,
9 BAJA. Lo estético es la minoría y casi todo cae en la tercera tanda del plan, que es donde
debe estar.

---

## 2 · Hallazgos

### ALTA

| # | Hallazgo | Dónde | Ítem |
|---|---|---|---|
| **U-01** | **La app anuncia un simulacro que ningún edificio está ejecutando.** `active` se deriva del reloj en SQL (`started_at + duration_s`, sin cierre por acuse) y el móvil solo recibe `active`; un gabinete que **rechaza** o **aborta** el comando no cambia nada. Medido hoy: simulacro real de 3 min a dos gabinetes → historial «0/2 ACUSADOS · 2 RECHAZADO(S) · RECHAZADO POR EL GABINETE» en los dos; el panel de Puebla nunca salió de `drill.active=false`; el Pixel pintó «SIMULACRO EN CURSO — ESTO NO ES UNA ALERTA REAL» la ventana entera. El rechazo es correcto (`command_enabled` apagada de fábrica, regla de oro 8); la mentira es la franja. *(Verificado a mano.)* | `api/src/takab_api/routers/drills.py:112-118`; `api/src/takab_api/queries/mobile.py:201-206`; `api/src/takab_api/routers/mobile_site.py:283-288`; `mobile/src/features/home/HomeView.tsx:81-87` | S1, S2, M5 |
| **U-02** | **El brigadista no ve el simulacro ni el modo demostración.** `PanelView` no recibe `drill` ni `demo_mode` (cero ocurrencias en `features/panel/` y en `(brigadista)/panel.tsx`); con la sirena voceando, su panel dice «SIN INCIDENTE ABIERTO». La persona que manda en el edificio es la única sin la etiqueta que dice que es un ensayo. *(Verificado a mano.)* | `mobile/src/features/panel/PanelView.tsx:37`; `mobile/src/features/home/HomeView.tsx:81` (solo el ocupante) | M5, S2 |
| **U-03** | **El aborto de un simulacro por sismo real es invisible en las tres superficies.** `abort()` pone `active=False, aborted=True` y **no publica nada** a la nube; la consola y el móvil siguen derivando `active` del reloj; el texto del panel «SIMULACRO ABORTADO — ALERTA REAL EN CURSO» exige `drill && alert` con `drill = st.drill.active`, condición **inalcanzable** porque el aborto pone `active=false`; `aborted`/`abort_reason` no se leen en ninguna línea del panel. El único test que lo «cubre» fabrica el estado a mano. *(Verificado a mano.)* | `edge/takab_edge/drill/__init__.py:161-178`; `edge/takab_edge/local_api/index.html:984`, `:999-1003`; `edge/tests/test_local_api_panel.py:850-856`; `web/src/features/console/useActiveDrill.ts:83` | S5 |
| **U-04** | **Alerta real, simulacro, mantenimiento y modo demostración solo existen en `/console`.** El shell solo monta el aviso de privacidad; los cuatro banners viven dentro de `ConsolePage` como props ad-hoc (`hasLiveIncident`). En `/fleet`, `/triage`, `/tenants`, `/audit` y `/building` no hay rastro de que la nube no avisa a nadie, de que el edificio vocea, ni de que hay una alerta. No hay tabla de precedencia de escena ni censo que la vigile (`statePrecedenceCensus` censa la precedencia de DATO). *(Verificado a mano.)* | `web/src/shell/AppShell.tsx:7-20`; `web/src/features/console/ConsolePage.tsx:192-198`; `web/src/features/console/DrillBanner.tsx:70-73` | W5 |
| **U-05** | **El distintivo «AUTH · MFA» es un literal heredado del mockup.** Se pinta en verde (`soc-pill--ok`) junto al botón de acuse en **toda** sesión, incluida la de `POST /dev/token` que jamás pasó un reto de MFA (capturado hoy en `make soc-local`); `/me` no expone `amr` ni nada de MFA y la cadena `mfa` no aparece en ningún otro fichero de `web/src`. Una consola de alertamiento afirmando un hecho de seguridad que no puede conocer. *(Verificado a mano.)* | `web/src/features/console/IncidentTable.tsx:259-261`; `takab-docs/design/jsx/IncidentTable.jsx:83` | W3 |
| **U-06** | **Dar de alta un sitio para un cliente nuevo lo escribe en el tenant del operador.** El formulario de estación no tiene campo de cliente (comprobado en vivo: CÓDIGO, NOMBRE, CRITICIDAD, DIRECCIÓN, TIPO, LATITUD, LONGITUD) y `FleetAdmin` arma el cuerpo sin `tenant_id`; la API lo resuelve del JWT. La API **sí** acepta `tenant_id` para roles internos: el hueco es de la consola. El flujo «alta de cliente → alta de sitio → gabinete → mapa» está roto en su segundo paso y nada lo dice. *(Verificado a mano.)* | `web/src/features/fleet/FleetAdmin.tsx:96-104`; `api/src/takab_api/routers/sites.py:114`; `api/src/takab_api/schemas/sites.py:77-89` | W2 |
| **U-07** | **La marca DEMO es parcial dentro de una misma pantalla.** `esDeDemostracion`/`ROTULO_DEMO` solo los consumen el mapa y la tarjeta de flota; la cola de incidentes, el triage, el detalle y los KPI pintan el sitio sin marca. Un marcado a medias enseña la regla falsa «sin cinta ⇒ real» al prospecto que mira la fila debajo del pin rotulado. *(Verificado a mano.)* | `web/src/features/console/MapPanel.tsx:165-166`; `web/src/features/fleet/SiteCard.tsx:159-165`; `web/src/features/console/IncidentTable.tsx:218`; `web/src/features/fleet/datosDeDemostracion.ts:41` | W10 |
| **U-08** | **El botón `REINTENTAR` de las pantallas de vida del móvil mide ≈29 dp.** `paddingVertical: space[2]` (8) más texto de 13 sobre un objetivo mínimo de 44 dp; es el botón que aparece cuando el ocupante **no pudo consultar si tiene que evacuar**. `hitSlop` no existe en toda la app y solo `TacticalAckButton` declara `minHeight`. *(Verificado a mano y medido en el Pixel.)* | `mobile/src/ui/StateFrame.tsx:102-106`; `mobile/src/features/alarm/TacticalAckButton.tsx:103` | M8 |

### MEDIA

| # | Hallazgo | Dónde | Ítem |
|---|---|---|---|
| **U-09** | **En CONSOLA a 1920×1080 la botonera y el PIN nacen fuera de pantalla.** Medido: documento de 1347 px, `#actionbar` en y=1230; a 1280×800, 6 de 11 tarjetas bajo el pliegue. La spec fija «sin scroll vertical en 1080p» y el perfil «10 segundos con el PIN en la mano». Ningún test lo defiende. | `edge/takab_edge/local_api/index.html:122`; `takab-docs/design/edge-panel/ESPECIFICACION-PANEL-GABINETE.md:141` | E2 |
| **U-10** | **En CAMPO los carriles de onda miden 35 px** y sus rótulos (`.top` a 7 px del borde superior, `.note` a 6 px del inferior) se pisan; cuatro canales en 140 px no permiten ver un hueco de señal. | `edge/takab_edge/local_api/index.html:136-142`, `:193` | E2 |
| **U-11** | **Las escenas demo `simulacro` y `prueba_actuadores` afirman «SIRENA: SONANDO» con el relé de sirena en REPOSO.** Fuerzan `siren_sounding:true`, pero en el gabinete real ese booleano **se deriva de la energización del relé** y el `DrillController` es observador sin relés: es un estado que el hardware no puede producir. Se enseña en la demo, con la cinta «NO ES ESTADO REAL» encima; por eso no es ALTA. | `edge/takab_edge/local_api/index.html:754`, `:756`, `:1037-1041`; `edge/takab_edge/gpio/__init__.py:1446-1448`; `edge/takab_edge/drill/__init__.py:67` | E1 |
| **U-12** | **El checklist de verificación del panel quedó desfasado:** enumera 10 escenas y el código tiene 13 (`aviso`, `retirado`, `gpio_caido`); dice que `prueba_actuadores` es «banner cian, relés en cian» y hoy es una prueba **terminada** que enseña la tarjeta de resultado (decisión de T-2.85.a). El documento manda mal a quien lo obedezca. | `takab-docs/design/edge-panel/VERIFICACION-T-2-23.md:50`; `edge/takab_edge/local_api/index.html:738-807`, `:756-766` | E1 |
| **U-13** | **El pulso «en vivo» del panel está declarado, consume una animación y no pinta nada.** `.halo` anima opacidad y escala de una caja **sin fondo** (`setPill` colorea el punto, nunca el halo), y late incondicionalmente: seguiría latiendo con «DATO RETENIDO» y con «SIN CONEXIÓN». Es el principio 3 al revés. | `edge/takab_edge/local_api/index.html:73`, `:261`, `:948-951` | E9 |
| **U-14** | **Dos variables CSS usadas no existen:** `--f-mono` (la comparativa cae a `monospace` genérica y pierde las cifras tabulares) y `--warn` (la advertencia de banda de fábrica no se pinta ámbar). Ninguna guarda comprueba que cada `var()` esté definida. | `edge/takab_edge/local_api/index.html:168`, `:225` | E7 |
| **U-15** | **En MURO el estado del relé mide 28 px y su nombre 10 px:** a cinco metros se lee «ACTIVADO» pero no de qué relé. Solo `#tier-label`, `.rs`, `.ch`, `.peak` y el reloj crecen en muro. | `edge/takab_edge/local_api/index.html:129`, `:131`, `:185` | E8 |
| **U-16** | **El único gate del panel LOGIN DEV en producción es una línea `ENV` del Dockerfile que ningún test bloqueante lee.** El servidor sí está cerrado con test (sin JWKS inline no se monta `/dev/token`; verificado hoy: `/api/dev/token` → 404 y sin «LOGIN DEV» en el DOM desplegado). El cliente no: `consoleImageCensus` solo parsea los `COPY`; el e2e que lo mira corre por `workflow_dispatch` con `continue-on-error` y comprueba el endpoint, no el panel. Hoy no es visible; no está defendido. | `deploy/cloud/console.Dockerfile:69`; `web/src/consoleImageCensus.test.ts:55`; `web/e2e/deployed.spec.ts:94`; `.github/workflows/e2e.yml:101` | W21 |
| **U-17** | **Cuatro estados vacíos atribuyen al TENANT lo que con `console_scope_enforced` será el ALCANCE.** El día del apply, un operador con cero sitios asignados leerá «SIN SITIOS VISIBLES EN EL TENANT» sobre un cliente con 21. Solo la cola dice «EN EL ALCANCE». Sube a ALTA con `T-2.89`. | `web/src/features/console/ConsolePage.tsx:209`; `web/src/features/fleet/FleetPage.tsx:293`; `web/src/features/console/ComparePanel.tsx:81`; `web/src/features/console/IncidentTable.tsx:195` | W22 |
| **U-18** | **El arranque tiene tres silencios:** entre el HTML y el primer frame no hay pantalla (`index.html` sin `<noscript>` ni marca de arranque); el splash es estático y mudo (sin `role=status`, no distingue «tardando» de «colgado»); y **la sesión expira en silencio** (`signinSilent` falla → `handleUnauthorized` → login idéntico al de un arranque frío, sin una palabra). El fallback «Cognito no configurado (VITE_COGNITO_*)» es texto de ingeniero servido al cliente. Medido hoy: 0.5 s hasta pantalla con login dev; 1.3 s hasta la landing desplegada y 1.8 s más hasta el Hosted UI. | `web/index.html:18`; `web/src/pages/StatusScreens.tsx:3-12`; `web/src/auth/session.store.ts:119`, `:223-231`; `web/src/pages/LoginPage.tsx:131` | W16, W19, W20 |
| **U-19** | **El login real que ve el cliente es el genérico de AWS.** No existe `aws_cognito_user_pool_ui_customization` en todo `infra/terraform`; capturado hoy: bloque gris donde iría el logo, «Sign in with your email and password» en inglés, botón azul de fábrica, entre dos pantallas con imagotipo TAKAB. | `infra/terraform/modules/identity/main.tf:95`, `:549` | W17 |
| **U-20** | **Contraste: axe sin filtrar reportó 171 nodos `color-contrast` en 15 de 72 corridas.** El peor: rojo crítico sobre la tarjeta crítica de flota a 11 px en negrita (3.76:1). `color-contrast` no está entre las reglas bloqueantes de `axe.spec`, `/building` no está en su lista, y en el mapa `watch` y `normal` difieren **solo por tono** con el mismo radio. | `web/e2e/axe.spec.ts:21-26`, `:36`; `web/src/features/console/MapPanel.tsx:104`, `:526`; `web/src/styles/soc.css:1097`, `:1102` | W9 |
| **U-21** | **Valores fuera del token.** Consola: 20 hex y 16 `rgba()` en `soc.css`, 28 hex en TSX, 14 literales `120ms` frente a 3 usos de `--tk-dur-fast` (que vale exactamente eso), ~900 líneas con px crudo. Móvil: 44 literales de color en cinco `.tsx` de crisis y alarma, con ámbares que no existen en `tokens.json`, y `fontSize: 64` entre dos escalones del paquete. Ningún drift gate lo ve: `designTokens.test.ts` valida que las `var()` citadas existan, no que los literales usen tokens; el móvil no tiene equivalente. | `web/src/styles/soc.css:1016`, `:1097`, `:1102`; `shared/design-tokens/tokens.json:88`; `mobile/src/features/alert/CrisisView.tsx:31`, `:110`; `mobile/src/features/alarm/BuildingAlarmView.tsx:102` | W6–W8, S2, M9 |
| **U-22** | **`prefers-reduced-motion` cubre los dos keyframes y 2 de 18 transiciones**; la única transición que transporta un dato (la barra de carga del UPS) sigue animando bajo reducción. En el móvil `AccessibilityInfo.isReduceMotionEnabled` **no se consulta en ninguna parte** y el hold de pánico es el único estado que vive solo en el movimiento. | `web/src/styles/soc.css:1338-1351`; `web/src/styles/soc-tabs.css:451`; `mobile/src/features/panic/PanicButton.tsx:21-24` | W15, M7 |
| **U-23** | **El latido de `LinkPill` no es un latido de frescura:** late mientras el servidor diga `ok`, sin mirar la edad del último frame. El de `DetailPanel` sí está atado a `liveFresh` y se detiene. | `web/src/features/fleet/LinkPill.tsx:19`; `web/src/features/console/DetailPanel.tsx:301` | W13 |
| **U-24** | **Sin primitivas compartidas de tabla, tarjeta ni botón:** tres sistemas de clases de tabla, 18 `soc-card` a mano en un solo fichero, 72 `soc-btn` sueltos en 30 ficheros y siete productores de pill; la regla «conocido ⇒ stale, desconocido ⇒ error» está copiada literalmente en dos banners. | `web/src/features/console/IncidentTable.tsx:197`; `web/src/features/audit/AuditPage.tsx:132`; `web/src/features/fleet/FleetAdmin.tsx:205`; `web/src/features/building/BuildingPage.tsx:179`; `web/src/features/console/DrillBanner.tsx:55`; `web/src/features/console/MaintenanceBanner.tsx:42` | W8 |
| **U-25** | **En `/triage`, `/tenants` y `/audit` el título de la pantalla (26 px) gana a cualquier dato**; los KPI de `/console` van a 15 px y los de `/fleet` a 28; hay 59 declaraciones por debajo de 10 px (piso 8.5) y cuatro `fontSize: 9` inline que escapan a los censos. | `web/src/styles/soc-tabs.css:562`, `:832`, `:2415`; `web/src/styles/soc.css:1237`, `:1242`; `web/src/features/console/IncidentTable.tsx:259` | W6, W7 |
| **U-26** | **La cola de incidentes no declara `error` ni `stale`, y `DemoModeBanner` pasa `emptyText=""`:** con el modo apagado y la lectura caída, el marco produce una caja vacía (el e2e la midió hoy: «un panel vacío de 1264×120 px no dice nada»). `SiteCard` no tiene `StateFrame`, y `/building` guarda cabecera y salud a mano sin `stale`. | `web/src/features/console/IncidentTable.tsx:191`; `web/src/features/console/DemoModeBanner.tsx:52`; `web/src/serverDataCensus.test.ts:419` | W4 |
| **U-27** | **El flujo alerta → dictamen pierde el contexto dos veces:** solicitar el dictamen salta a `/triage` y tira el riel, el mapa y el filtro; y con un sismo del catálogo seleccionado el mapa queda **armado**: el siguiente clic en una estación abre la comparativa en vez del detalle, sin aviso. Medido hoy: 3 clics hasta solicitar, 4 más como inspector hasta el PDF. | `web/src/features/console/ConsolePage.tsx:88-97`, `:170`; `web/src/features/triage/TriageDetail.tsx:362`, `:407` | W2 |
| **U-28** | **Ante un AVISO instrumental, la consola dice «LA ALERTA REAL DOMINA» y viste la tarjeta con la carcasa roja de la alerta.** El badge del simulacro se degrada por `critical !== null`, y `.soc-alert` es una sola clase: la tarjeta de hoy decía «AVISO SÍSMICO · SOLO AVISO, SIN ACTUACIÓN» en rojo crítico con la fila «CRÍTICO» debajo. El titular es honesto desde `T-5.03`; el color y el badge no. | `web/src/features/console/DrillBanner.tsx:70-73`; `web/src/features/console/ConsolePage.tsx:193`; `web/src/features/console/AlertBanner.tsx:31` | S2, W5 |
| **U-29** | **El reporte de simulacro se titula con el UUID del cliente, no imprime cómo terminó (`stop_reason`) y no dice por qué faltó cada acuse** (la consola sí distingue `rejected` de `pending`). Hoy la API respondió 201 al exportar y la pestaña reservada se quedó en blanco durante 10 s en el stack local. | `api/src/takab_api/routers/drills.py:789`, `:797`; `api/src/takab_api/drill_report.py:143-147` | S6 |
| **U-30** | **Las pestañas del táctico no están gateadas por `allowed_actions`:** `inspector` ve LISTA sin `roster_read`, `building_admin` ve TRIAGE sin `damage_report_submit`; y el táctico no tiene RUTAS ni DIRECTORIO, que RBAC le concede. | `mobile/src/app/(brigadista)/_layout.tsx:31-61`; `takab-docs/RBAC-TAKAB.md:321` | M2 |
| **U-31** | **Objetivos táctiles medidos en el Pixel:** «Ver directorio completo →» **382×19 dp**; el botón de pánico (416×70 dp, correcto) vive al **35 %** de la altura con el 60 % inferior vacío, fuera del alcance del pulgar en un teléfono de 2992 px. | `mobile/src/features/home/HomeView.tsx:179`; `mobile/src/features/panic/PanicButton.tsx:62`; `mobile/src/app/panic.tsx:164` | M8 |
| **U-32** | **En el móvil, el simulacro y el modo demostración viven solo en INICIO** (en RUTAS, DIRECTORIO y CUENTA no hay rastro), y la franja de simulacro y la de reingreso autorizado son **la misma forma** con distinto matiz (ámbar / verde). | `mobile/src/features/home/HomeView.tsx:81-87`, `:242-247` | M5, S2 |
| **U-33** | **El dato retenido del ocupante es una franja fina que se dibuja encima de la barra de estado de Android** mientras la tarjeta «SEGURO» sigue verde e intacta. Medido hoy con WiFi y datos apagados 105 s: «DATOS RETENIDOS · hace 1 min · sin conexión» sobre el reloj del sistema. El umbral (tres sondeos perdidos) es correcto; la jerarquía no. | `mobile/src/ui/StateFrame.tsx:81`; `mobile/src/ui/useStaleSince.ts:22` | M6 |
| **U-34** | **La consola pide dos familias a Google Fonts y el mapa, tiles y glifos a `openfreemap`** (hoy los glifos dan 404). Un SOC con salida a internet restringida pierde JetBrains Mono —la fuente del dato— y el mapa entero. No lo prohíbe el principio 4, que es del gabinete; sí lo hace la naturaleza de un SOC. | `web/src/styles/colors_and_type.css:20`, `:25`; `web/src/features/console/MapPanel.tsx:63` | W11 |
| **U-35** | **El aviso de privacidad ocupa ~170 px en TODAS las pantallas hasta aceptarlo y a 1280×800 deja el mapa en su piso**; dos e2e de layout lo miden y fallan hoy («el escenario está en su piso de 280 px con el banner presente: se lo comió él»). Es lo primero que ve un cliente en la demo. | `web/src/shell/AppShell.tsx:14`; `web/e2e/layout.spec.ts:70`, `:108` | W7, W10 |
| **U-36** | **Sin push, la toma de crisis llega por sondeo:** `IDLE_POLL_MS` de 30 s y sin `focusManager` atado a `AppState`. Medido hoy: 8.5 s desde que el sembrador confirmó el incidente hasta la pantalla de crisis (dentro de la ventana); volver del segundo plano no fuerza el refetch. El push está en simulado (`H-09`), así que hoy este ES el camino. | `mobile/src/features/alert/useAlertState.ts:21`, `:60-61` | M4 |
| **U-37** | **Dos arneses de prueba ya no ejercen lo que prometen:** el sembrador de staging reutiliza siempre el incidente `d4000000…` y **ya no produce la toma de crisis** (hoy hizo falta un id fresco); y en `make soc-local` un simulacro sale con «5 SIN COMANDO EMITIDO», así que el aborto por sismo real no se puede ensayar en local. | `infra/scripts/seed_staging_incident.sh:46`; `Makefile:109` | M4, S5 |
| **U-38** | **Botones apagados sin explicación e enlaces sin gate:** en `/tenants`, `RESTAURAR` y `APLICAR Y SINCRONIZAR` deshabilitados sin `title` (e2e falla hoy); «IR A FLOTA EDGE» en el triage manda al `inspector` a «SIN ACCESO». La regla «sin stubs silenciosos» se cumple en lo grueso: cero `TODO`, cero `console.log`, cero `href="#"`. | `web/src/features/triage/TriageDetail.tsx:295`; `web/e2e/screens.spec.ts:573` | W3 |

### BAJA

| # | Hallazgo | Dónde | Ítem |
|---|---|---|---|
| **U-39** | **Movimiento sobrante y duplicado:** 10 `transition: all` (animan cualquier propiedad futura, incluido un color de estado); 14 literales `120ms` que duplican `--tk-dur-fast`. | `web/src/styles/soc.css:212`, `:617`; `web/src/styles/soc-tabs.css:81` | W14 |
| **U-40** | **Identificadores crudos en pantallas que se leen de pie:** `fail-safe fail_close` en el panel (con `NO`/`NC` sí abreviados) e `inhabit_monitor` en la línea de tiempo del ocupante tras el check-in (visto hoy). El literal del panel lo congela un test de contrato, con razón. | `edge/takab_edge/local_api/index.html:591`; `edge/tests/test_local_api_panel.py:943` | E4, M4 |
| **U-41** | **El prompt de esta auditoría cuenta 12 pantallas móviles donde la spec declara 21**; tres (REPLIÉGUESE, bloqueo de reingreso, control de 2 pasos) viven dentro de otra ruta por decisión escrita. | `takab-docs/design/app/ESPECIFICACION-APP-MOVIL.md:403`; `takab-docs/PROMPT-auditoria-uiux.md:176` | M1 |
| **U-42** | **`?mode=` acepta cualquier cadena** y deja `body.mode-<lo-que-sea>`; y la cuenta de la escena demo de simulacro (`elapsed_s`/`total_s`) usa campos que `DrillController.status()` nunca emite: en un gabinete real el meta solo muestra el `drill_id`. | `edge/takab_edge/local_api/index.html:2537`, `:1007`; `edge/takab_edge/drill/__init__.py:79-83` | E2, E1 |
| **U-43** | **El cian de marca transporta cinco significados:** acento, pill EDGE, catálogo histórico, frente P y modo demostración; `--tk-font-brand` es un sustituto declarado de la tipografía de marca. | `web/src/styles/soc.css:292`; `web/src/features/console/MapPanel.tsx:113`, `:116`; `web/src/features/console/DemoModeBanner.tsx:8` | W11 |
| **U-44** | **`/building` cuelga de un único enlace en el riel de detalle de `/console`;** para `inspector` y `building_admin` —sin `/fleet`— es el único camino a la ficha del inmueble. `NAV_PRESENTATION` no tiene contrato directo con `routes.tsx` (lo sostiene una tabla copiada a mano en un test). | `web/src/features/console/DetailPanel.tsx:190`; `web/src/shell/navItems.ts:12` | W1 |
| **U-45** | **En la escena NORMAL la consola dedica dos franjas permanentes** a «SIN SIMULACRO EN CURSO» y «SIN VENTANA DE MANTENIMIENTO», y `/triage` vacío apila dos mensajes de vacío en el mismo marco con el 70 % de la pantalla en blanco. | `web/src/features/console/DrillBanner.tsx:99`; `web/src/features/triage/TriagePage.tsx:183` | W7 |
| **U-46** | **Armado y en curso del simulacro se distinguen a distancia solo por el matiz** (cian / ámbar): el texto que los desambigua va a `--tk-text-xs` en una tira de menos de 60 px, altura que un e2e fija con razón. | `web/src/features/console/DrillBanner.tsx:206-209`; `web/e2e/drill.spec.ts:23` | S4 |
| **U-47** | **El Pi corre una release anterior a la marca:** `/favicon.png` e `/isotipo.png` dan 404 en `192.168.3.91:8080` (release del 2026-08-30; los ficheros entraron el 5 y el 6 de septiembre). No es defecto del panel: es despliegue pendiente antes de una demo. | `edge/takab_edge/local_api/__init__.py:217-218` | E7 |

---

## 3 · Lo que se ve mal en una demo

Pantalla por pantalla, con el stack de demostración (`make soc-local`) y el Pixel real. Lo que
está entre paréntesis es el hallazgo que lo cierra.

**Consola · `/console` (la primera pantalla que ve un cliente).** Lo primero no es el mapa: es un
aviso de privacidad de 170 px con el rótulo «TEXTO PROVISIONAL · pendiente de revisión jurídica»
que ocupa el ancho entero hasta que alguien pulsa ACEPTO (U-35). Debajo, dos franjas permanentes
dicen que **no** hay simulacro y que **no** hay mantenimiento (U-45). El mapa está bien —pins con
la cinta DEMO, leyenda honesta, «NÚCLEO HUECO Y APAGADO = EL COLOR NO ES UNA LECTURA VIVA»— pero
los once pins simulados están apilados sobre Cholula y sus rótulos DEMO se pisan. La cola de
incidentes debajo pinta esos mismos sitios **sin** cinta (U-07). Al pie, junto al operador, un
distintivo verde «AUTH · MFA» que no significa nada (U-05). Los rótulos de la tira de KPI van a
8.5 px (U-25). Si durante la demo se inyecta un sismo simulado con un simulacro corriendo, la
tarjeta que aparece es roja, la fila dice CRÍTICO y el simulacro pasa a «LA ALERTA REAL DOMINA»
mientras la propia tarjeta dice «SOLO AVISO, SIN ACTUACIÓN» (U-28). **Vende**: el wall completo,
la honestidad de los rótulos y los tres banners de escena son mejores que la media del sector.
Lo que lo estropea es lo que hay encima y lo que falta debajo.

**Consola · `/fleet`.** Cinco tarjetas, cuatro en rojo «SIN ENLACE» y una degradada: en el stack
local es lo esperado, pero la tira de KPI dice «0 OPERATIVOS» en el momento más comercial. El rojo
crítico sobre la tarjeta crítica a 11 px no pasa AA (U-20). Las tarjetas DEMO llevan su cinta
discontinua, correctamente.

**Consola · `/triage`.** Con cero incidentes es una pantalla vacía en un 70 %: el título de 26 px
es lo más grande que hay, y el marco apila «SIN INCIDENTES QUE COINCIDAN CON EL FILTRO» y «SIN
INCIDENTES EN LA VENTANA» uno debajo del otro (U-45, U-25). El catálogo de referencia SSN/USGS va
plegado. Con un incidente, la firma del dictamen funciona en cuatro clics como `inspector` y el
resumen post-evento es honesto («NO APLICA · el incidente no vino de SASMEX»).

**Consola · `/tenants` y `/audit`.** El título gana al dato; en `/tenants` la meta del cliente va
a 10.5 px con 4.4:1 de contraste y dos botones apagados no dicen por qué (U-38). Crear un cliente
funciona en dos clics; crear su primer sitio **no llega a su tenant** (U-06).

**Consola · entrada.** La landing propia tiene imagotipo, «CONSOLA SOC» y un botón. Un clic
después el cliente está en una pantalla gris de AWS en inglés (U-19). Al expirar la sesión vuelve
a la landing sin saber por qué (U-18).

**Panel del gabinete.** En MURO se lee desde el fondo de la sala: tier a 72 px, cinco relés a 28 px,
sin acciones. En CONSOLA a 1080p la botonera y el PIN están **debajo del pliegue** (U-09). Las
escenas `simulacro` y `prueba_actuadores` dicen «SIRENA: SONANDO» dos centímetros encima de un
relé de sirena en REPOSO (U-11). En CAMPO las ondas son cuatro líneas de 35 px con los rótulos
encimados (U-10). El punto verde «PANEL EN VIVO» no late aunque el código diga que sí (U-13). En
el Pi real falta el isotipo hasta que se despliegue (U-47).

**App móvil · ocupante.** La pantalla de inicio es limpia y honesta («SEGURO · SASMEX WR-1 ·
GABINETE ENLAZADO»), con el tercio inferior vacío. La toma de crisis es ejemplar: instrucción
gigante en el primer frame, sin magnitud, T+ ascendente, fuente declarada. Pero **si el demo
incluye un simulacro y el gabinete lo rechaza, el teléfono lo anuncia igual** (U-01); si el
teléfono pierde la red, la única señal es una franja fina que se dibuja sobre el reloj de Android
mientras «SEGURO» sigue verde (U-33); el botón de pánico está en el tercio superior (U-31); y tras
el check-in la línea de tiempo imprime `inhabit_monitor` (U-40).

**App móvil · brigadista.** Durante un simulacro, su panel dice «SIN INCIDENTE ABIERTO» (U-02).
No se capturó su primera pantalla en esta sesión (§7).

**Lo que NO debe decirse en una demo hoy:** «la app le avisa del simulacro» (solo al ocupante, y
aunque el edificio no lo esté haciendo); «el operador tiene MFA» señalando el distintivo; «esto es
un cliente real» sobre la cola de incidentes; «el login es TAKAB»; «si el gabinete aborta el
simulacro, la consola lo refleja».

---

## 4 · Tabla de veredictos

Un renglón por ítem del encargo. **Evidencia** = dónde se lee; la razón dice qué falta para el
verde. «Ejercido» significa fuera de los tests, hoy o con fecha citada.

### W · Consola SOC

| # | Veredicto | Evidencia | Razón |
|---|---|---|---|
| **W1** | 🟡 | `web/src/app/routes.tsx:17-79`; `web/src/shell/navItems.ts:12`; `api/src/takab_api/auth/matrix.py:61`; `web/src/app/routes.guards.test.tsx:28-40` | Seis pantallas, seis `routeKey`, matriz 10 roles × 6 rutas probada celda a celda y **recorrida hoy en vivo** (la matriz medida coincide con RBAC: `soc_operator` sin `/tenants` ni `/audit`; `inspector` y `building_admin` sin `/fleet`; tres roles móviles caen en «SIN SUPERFICIE WEB»). Ninguna ruta huérfana en sentido estricto; `/building` solo es alcanzable desde el riel de detalle (U-44). |
| **W2** | 🔴 | `web/src/features/fleet/FleetAdmin.tsx:96-104`; `api/src/takab_api/routers/sites.py:114`; `web/src/features/console/ConsolePage.tsx:170`, `:88-97` | Medidos hoy: simulacro 3 clics y 2.7 s hasta el banner (el mejor de los tres); alerta → dictamen → firma → PDF 3 + 4 clics con un salto de pantalla que tira el riel y un mapa que queda armado (U-27); alta de cliente → sitio **roto en el segundo paso** (U-06). Ningún test recorre dos pantallas seguidas. |
| **W3** | 🟡 | `web/src/features/console/IncidentTable.tsx:259-261`; `web/src/features/triage/TriageDetail.tsx:295`; `web/e2e/screens.spec.ts:573` | Cero `TODO`, `console.log`, `href="#"` u `onClick` vacío en producción, y cada `disabled` de la consola lleva `title` salvo dos en `/tenants` (U-38). Lo que falla no es un botón mudo sino una etiqueta que afirma un hecho de seguridad sin dato (U-05). |
| **W4** | 🟡 | `web/src/components/StateFrame.tsx:76`, `:92`; `web/src/serverDataCensus.test.ts:419`; `web/src/features/console/IncidentTable.tsx:191`; `web/src/features/console/DemoModeBanner.tsx:52` | 43 marcos, ninguno dice «sin datos» a secas; la precedencia es una tabla única con dos censos por igualdad. La deuda está escrita con nombre: cola sin `error`/`stale`, `SiteCard` sin marco, `/building` sin `stale`, un `emptyText=""` que hoy produjo una caja en blanco medible (U-26). |
| **W5** | 🔴 | `web/src/shell/AppShell.tsx:7-20`; `web/src/features/console/ConsolePage.tsx:192-198`; `web/src/features/console/MaintenanceBanner.tsx:8-14` | La precedencia de ESCENA está bien razonada (el simulacro se degrada bajo alerta; el mantenimiento **no**, por decisión escrita) pero solo dentro de `/console` y como dos booleanos a mano; en las otras cinco pantallas no se ve nada y no hay censo (U-04). |
| **W6** | 🟡 | `web/src/styles/soc-tabs.css:562`, `:832`, `:2415`; `web/src/styles/soc.css:1237` | `/console` y `/fleet` ponen el dato arriba (PGA y KPI a 28 px); `/triage`, `/tenants` y `/audit` ponen el título a 26 px sobre datos de 24, 22 y ~12; el mismo KPI mide 15 px en una pantalla y 28 en otra (U-25). |
| **W7** | 🟡 | `web/src/styles/layoutInvariants.test.ts:306`, `:460`, `:590`; `web/src/styles/soc.css:1242`; `web/e2e/layout.spec.ts:70` | El amontonamiento **geométrico** está defendido por test (clipping, scroll recuperado, `minmax(0,…)`); el **tipográfico** no: 59 declaraciones bajo 10 px. Y el aviso de privacidad se lleva el alto del mapa a 1280×800 (U-35). |
| **W8** | 🟡 | `web/src/features/console/IncidentTable.tsx:197`; `web/src/features/audit/AuditPage.tsx:132`; `web/src/features/fleet/FleetAdmin.tsx:205`; `web/src/features/building/BuildingPage.tsx:179`; `web/src/styles/cssContract.test.ts:249` | Hay una capa de componentes con contrato (`SevTag`, `ScopeBadge`, `StateFrame`, `ConfirmButton`, `Modal`) que no cubre tabla, tarjeta ni botón (U-24). `cssContract` defiende que nada quede sin estilo, no que el componente sea el mismo. |
| **W9** | 🟡 | `web/src/designTokens.test.ts:124-156`; `web/e2e/axe.spec.ts:36`; `web/src/features/console/MapPanel.tsx:526`; medición axe de hoy (`171` nodos `color-contrast`) | El semáforo lleva etiqueta donde hay pill; en el mapa `watch`/`normal` difieren solo por tono. El guardia de contraste vive en un test de unidad sobre tres grises; axe nunca pone rojo por contraste (U-20). |
| **W10** | 🟡 | `web/src/features/console/ConsolePage.tsx:185-240`; `web/src/features/console/MapPanel.tsx:165`; `web/src/features/console/IncidentTable.tsx:218`; `web/src/shell/AppShell.tsx:14` | Sí vende: wall, leyendas honestas, tres banners de escena. Lo estropean el aviso de privacidad encima (U-35), la marca DEMO a medias (U-07) y el distintivo de MFA (U-05). Descripción completa en §3. |
| **W11** | 🟢 | `web/src/shell/Topbar.tsx:73-74`; `web/src/pages/LoginPage.tsx:114`; `web/src/brandAssets.test.ts:44-80`; commit `5f69e3c` | Presente, coherente y no invasiva: el isotipo va `aria-hidden`, la marca cede ancho antes que tapar navegación, y un test cruza marcado y fichero. Dos costuras de política, no de identidad: fuentes externas (U-34) y el cian con cinco significados (U-43). |
| **W12** | 🟢 | `web/src/styles/soc.css:300-306`; `web/src/styles/soc-tabs.css:147-152`; `web/src/features/console/wavefront.ts:134`; `web/e2e/motion.spec.ts:63-113` | Inventario cerrado y con propósito: dos keyframes (latido de dato vivo, botón armado), 18 transiciones de hover/foco, frentes P/S en MapLibre con sustituto quieto, dos chevrones. Ninguna decorativa. Detalle en §5. |
| **W13** | 🟡 | `web/src/features/console/DetailPanel.tsx:301`; `web/src/features/fleet/LinkPill.tsx:19`; `web/src/features/console/IncidentTable.tsx:197`; `web/src/styles/soc-tabs.css:154` | El principio 3 existe y está bien hecho en `DetailPanel` (halo y texto gobernados por `liveFresh`). Falta en la llegada de fila, en el cambio de banda, en el progreso de exportación y en la confirmación firmada; y el latido de `LinkPill` no mira la frescura (U-23). |
| **W14** | 🟢 | `web/src/features/console/AlertBanner.tsx:31-33`; `web/src/styles/soc.css:430-437`; `web/e2e/motion.spec.ts:101` | El camino de lectura de la alerta está limpio: el banner se monta con el dato pintado y no anima nada. Lo único sobrante son 10 `transition: all` fuera de ese camino (U-39). |
| **W15** | 🟡 | `web/src/lib/useReducedMotion.ts:25`; `web/src/features/console/MapPanel.tsx:328`, `:911`; `web/src/styles/soc.css:1338-1351`; `web/e2e/motion.spec.ts:110-121` | La mitad hecha incluye control negativo (lo que separa un interruptor de un placebo) y el mapa **declara** en la leyenda que está en movimiento reducido. La cobertura es parcial: 16 de 18 transiciones siguen vivas, incluida la barra del UPS (U-22). |
| **W16** | 🟡 | `web/index.html:18`; `web/src/pages/StatusScreens.tsx:8`; `web/src/auth/session.store.ts:124-147`; `web/src/app/landing.ts:6` | Doce pasos nombrados (§ de U-18): HTML → splash → landing → Hosted UI → callback → `/me` → destino → shell → datos. Medido hoy: dev-token 0.5 s hasta pantalla y 0.7 s hasta el primer dato; desplegado 1.3 s hasta la landing y 1.8 s más hasta el Hosted UI. El paso 0 no tiene pantalla (U-18). |
| **W17** | 🔴 | `infra/terraform/modules/identity/main.tf:95`, `:549`; captura `deployed--hostedui.png` | Cero personalización: la pantalla donde el operador teclea contraseña y TOTP es la de fábrica de AWS (U-19). Cognito Hosted UI clásico admite logo por pool/cliente y una hoja CSS acotada; textos y tipografía no. Si el pool estuviera en «managed login» el mecanismo es otro: el repo no lo declara (§7). |
| **W18** | 🟡 | `web/src/pages/LoginPage.tsx:111-137`; `web/src/styles/app.css:59`; `web/e2e/deployed.spec.ts:69` | La landing existe y conviene tenerla (es donde debe declararse la sesión expirada y donde vive el error si Cognito cae). Falla en el copy de ingeniero del fallback y en un `220px` a mano en la pantalla más comercial (U-18, U-21). |
| **W19** | 🟡 | `web/src/pages/AuthCallbackPage.tsx:43`; `web/src/app/RequireSession.tsx:16`; `web/src/components/StateFrame.tsx:155-157` | No hay pantalla en blanco: callback ⇒ splash, y `/console` monta con `StateFrame` en `loading` y `aria-busy`. El splash es estático y mudo (U-18). |
| **W20** | 🟡 | `web/src/app/DegradedSessionScreen.tsx:107-142`; `web/src/auth/session.store.ts:119`, `:223-231`; captura `w20--degradado.png` | La pantalla degradada es de lo mejor de la superficie: explica qué falta, por qué no muestra datos y que el alertamiento no depende de ella; reintenta sola. Verificado hoy bloqueando `/me`. La expiración, en cambio, es silenciosa; el logout vuelve a `/` con `sessionStorage` vacío en 3.2 s (U-18). |
| **W21** | 🟡 | `deploy/cloud/console.Dockerfile:69`; `api/src/takab_api/main.py:196`; `web/src/consoleImageCensus.test.ts:55`; medición de hoy (`/api/dev/token` → 404, sin «LOGIN DEV» en el DOM) | **No aparece en producción**, verificado. La mitad del servidor está cerrada con gate bloqueante; la del cliente depende de una línea `ENV` que ningún test bloqueante lee (U-16). |
| **W22** | 🟡 | `api/src/takab_api/settings.py:426`; `web/src/auth/useSiteScope.ts:30`, `:49`; `web/src/shell/Topbar.tsx:112`; `web/e2e/scope.spec.ts:51` | La insignia de alcance está pensada y probada. Lo que no está preparado son los vacíos, que hoy culpan al tenant (U-17), el mapa recortado sin mensaje propio, y `scope_gap`, que se audita y no tiene superficie. |

### E · Panel LAN del gabinete

| # | Veredicto | Evidencia | Razón |
|---|---|---|---|
| **E1** | 🟡 | `edge/takab_edge/local_api/index.html:738-807`, `:754`, `:756`; `takab-docs/design/edge-panel/VERIFICACION-T-2-23.md:46-55`; 78 recorridos de hoy | Las 13 escenas pintan y 11 cumplen su fila del checklist. `simulacro` y `prueba_actuadores` afirman una sirena que sus propios relés desmienten (U-11); el checklist enumera 10 y describe `prueba_actuadores` como ya no es (U-12). En `alerta` las marcas SASMEX/TIER viven en una ventana del ciclo de 48 s: la línea plana de la captura es fase, no ausencia. |
| **E2** | 🔴 | `edge/takab_edge/local_api/index.html:2533`, `:2537`, `:122`, `:193`; `takab-docs/design/edge-panel/ESPECIFICACION-PANEL-GABINETE.md:141`; `edge/tests/test_local_api_panel.py:803` | Breakpoints exactos (medido: 1023 → CAMPO, 1024 → CONSOLA, MURO solo manual, cero desbordamiento horizontal). Pero el objetivo escrito «sin scroll vertical en 1080p» no se cumple: botonera y PIN bajo el pliegue (U-09); en CAMPO los carriles miden 35 px (U-10). |
| **E3** | 🟢 | `edge/takab_edge/local_api/index.html:561`, `:937`, `:980`, `:1411`, `:2112`; `edge/tests/test_local_api.py:829`; `edge/tests/test_local_api_panel.py:1136`, `:1436` | Las seis honestidades de las notas de diseño verificadas en vivo hoy: `S/D`, `<0.001 g`, edad del diagnóstico, carril vacío con razón en vez de línea plana, «SIN ENLACE» en ámbar, «DATO RETENIDO DESDE …». `liveChannels` es la puerta única que impide el verde congelado. |
| **E4** | 🟢 | `edge/takab_edge/local_api/index.html:1051`, `:1054`, `:591`, `:689`; `edge/tests/test_local_api_panel.py:936-943` | Tres estados por relé en la misma tarjeta; `fail_close` y `NC` ENERGIZADO en reposo y DESENERGIZADO en alerta, correctamente opuestos a `NO` (medido hoy). Único reparo: `fail_close` se imprime crudo (U-40), y un test lo congela con razón. |
| **E5** | 🟢 | `edge/takab_edge/local_api/index.html:276`, `:1000`, `:1009`, `:1011`, `:1020`; `edge/tests/test_local_api_panel.py:860`, `:870`; `takab-docs/design/edge-panel/VERIFICACION-T-2-23.md:26-31` | Precedencia por construcción (orden en el DOM) más un guard `&& !alert` por banner; el WR-1 «SIEMPRE visible aun bajo alerta» está probado y se ejerció con el receptor físico el 2026-07-31. No hay ruta en la que un simulacro o una prueba tapen la alerta. |
| **E6** | 🟢 | `edge/takab_edge/local_api/index.html:14`, `:283`, `:495`; `edge/tests/test_local_api.py:604-628` | Cero cuenta regresiva, cero magnitud preliminar, cero `localStorage` (medido: `localStorage.length` = 0 en 78 recorridos), y un test que rompe el build si aparecen. El único descuento («87 s RESTANTES») es la ventana de prueba WR-1 que la spec pide. |
| **E7** | 🟡 | `edge/takab_edge/local_api/index.html:24`, `:53`, `:168`, `:225`; `edge/takab_edge/local_api/__init__.py:215`, `:284`; medición en el Pi | Geist y JetBrains Mono servidas desde el Pi (200, `max-age=86400`), con caída declarada, `document.fonts.check` verdadero, cero peticiones externas en 78 recorridos. Dos `var()` no existen (U-14) y el Pi sirve una release sin isotipo (U-47). |
| **E8** | 🟡 | `edge/takab_edge/local_api/index.html:179`, `:183`, `:185`, `:129`, `:131`; medición MURO 1920×1080 | Tier 72 px, relés 28 px, sin acciones, sin PIN, cabe en 1080: los cuatro requisitos literales se cumplen. El nombre del relé y su estado eléctrico se quedan en 10 px (U-15). |
| **E9** | 🔴 | `edge/takab_edge/local_api/index.html:73`, `:261`, `:948-951`, `:57` | El único movimiento admisible aquí —el latido de frescura— está declarado y no se pinta; y aunque se pintara, no se detiene (U-13). `prefers-reduced-motion` lo apaga (medido). Coste: cero en el Pi (el render es del cliente) y un elemento de 8 px en el compositor del navegador. |
| **E10** | 🟡 | medición SSH del 2026-09-06 (`top`, `curl`); `edge/takab_edge/local_api/index.html:2496`, `:2515`, `:854` | **Servir** el panel medido en el Pi 4 real: `takab-edge` ≈1–2 % CPU en reposo y ≈4–8 % con un cliente sondeando `/api/status` (17 KB) + `/api/waveform` (100 KB) a 1 Hz; `curl` 8–10 ms el status, 16–22 ms la onda, 13–19 ms el HTML (200 KB). **Render en el Pi: NO MEDIDO** — no hay navegador kiosco en el gabinete. `frame()` repinta dos canvas a la cadencia del compositor aunque el dato cambie a 1 Hz: es lo primero a mirar el día que se monte un kiosco. |

### M · App móvil

| # | Veredicto | Evidencia | Razón |
|---|---|---|---|
| **M1** | 🟡 | `takab-docs/design/app/ESPECIFICACION-APP-MOVIL.md:403`; `mobile/src/features/alert/CrisisView.tsx:30`; `mobile/src/app/checkin.tsx:131`; `mobile/src/screenStateCensus.test.ts:91` | La spec declara **21** pantallas (el prompt dice 12: U-41). Las 21 existen; tres no son ruta propia por decisión escrita; cinco rutas construidas no están en §7 de la spec (`alarma-inmueble`, `denied`, `callback`, `index`, layouts). Ningún test compara spec ↔ construido. |
| **M2** | 🟡 | `mobile/src/app/(occupant)/_layout.tsx:12`; `mobile/src/app/(brigadista)/_layout.tsx:31-61`; `mobile/src/auth/profileGate.ts:18`; `takab-docs/RBAC-TAKAB.md:321` | Se nota al abrir (4 pestañas y tarjeta de edificio vs 5 pestañas y rejilla de métricas). El reparto por rol no es el de RBAC (U-30). La primera pantalla del táctico no se capturó hoy (§7). |
| **M3** | 🟢 | `mobile/src/screenStateCensus.test.ts:82`, `:260`, `:302`, `:339`, `:359`, `:389`; `mobile/src/test-utils/expectFourStates.tsx:29` | Población derivada del sistema de ficheros, cuatro listas de deuda **vacías**, frescura por reloj y no por `isError`, `panic.tsx` excluido con razón medida; 528 tests en verde hoy. No cubre precedencia de escena, contraste ni tamaño táctil: no es su trabajo, y nadie más lo hace. |
| **M4** | 🟡 | `mobile/src/features/alert/useAlertState.ts:21`, `:60-61`; `mobile/src/features/alert/CrisisWatcher.tsx:38`; `mobile/src/features/alert/CrisisView.tsx:53-86`; medición en el Pixel | **Medido hoy en el Pixel:** incidente sembrado → toma de crisis en **8.5 s** sin push (sondeo de 30 s); instrucción, zona, fuente y T+ pintados en el primer frame mientras el contenedor entra deslizando; sacudida concluida → check-in visible en ≤ 6 s; **1 toque** («ESTOY BIEN») → línea de tiempo «Recibido por el servidor». El eslabón push → apertura **no es medible hoy**: el push está en simulado. El acuse táctico exige una alarma de inmueble con dos votos: no ejercido (§7). |
| **M5** | 🔴 | `mobile/src/features/home/HomeView.tsx:81-87`; `mobile/src/features/panel/PanelView.tsx:37`; `mobile/src/features/home/HomeView.test.tsx:92`; simulacro real de hoy | Para el ocupante el simulacro es inconfundible con la alerta (franja ámbar sólida sobre contenido normal; jamás abre crisis). Pero la franja se pinta aunque **ningún gabinete lo ejecute** (U-01), solo en INICIO (U-32), y el brigadista no ve nada (U-02). |
| **M6** | 🟢 | `mobile/src/app/(brigadista)/sync.tsx:91-94`; `mobile/src/offline/useCachedQuery.ts:63`; `mobile/src/ui/useStaleSince.ts:22`; medición en el Pixel | Medido hoy con WiFi **y datos** apagados 105 s: «DATOS RETENIDOS · hace 1 min · sin conexión» en inicio; «SIN CONEXIÓN CON EL SERVIDOR · No hay copia local» en rutas; red restaurada sin secuelas. Los flujos 05a/b/c se acreditaron con red cortada el 2026-08-09. La franja retenida merece más peso (U-33). Trampa medida: apagar solo el WiFi **no** deja al Pixel sin red (LTE). |
| **M7** | 🟡 | `mobile/package.json:40-41`; `mobile/src/features/panic/PanicButton.tsx:21-24`; `mobile/src/features/control/ControlSheet.tsx:65`; `mobile/src/app/(brigadista)/panel.tsx:227` | Dos movimientos propios (relleno del hold de pánico, knob de deslizar) con `Animated` clásico y `useNativeDriver:false`; Reanimated y gesture-handler instalados y sin un solo import. `reduceMotion` no se consulta (U-22). El hold es el único estado que vive solo en el movimiento. |
| **M8** | 🔴 | `mobile/src/ui/StateFrame.tsx:102-106`; `mobile/src/features/home/HomeView.tsx:179`; `mobile/src/app/panic.tsx:164`; medición `uiautomator` en el Pixel | Medido, no inferido: `REINTENTAR` ≈29 dp (U-08), enlace del directorio 19 dp, pánico al 35 % de la altura (U-31). Los CTA de inicio (49 dp), el pánico (70 dp) y las pestañas (48 dp) cumplen. Ningún test de tamaño táctil ni de contraste en `mobile/`. |
| **M9** | 🟡 | `mobile/src/ui/theme.ts:3`; `shared/design-tokens/tokens.json:18`, `:55`; `mobile/src/features/alarm/BuildingAlarmView.tsx:102`; `mobile/src/features/alert/CrisisView.tsx:110` | `theme.ts` deriva del paquete y la paridad de los cinco valores comparados es exacta. La paridad se rompe donde más se ve: 44 literales de color y 13 tamaños a mano en crisis y alarma, sin drift gate móvil (U-21). |

### S · Simulacros, revisión transversal

| # | Veredicto | Evidencia | Razón |
|---|---|---|---|
| **S1** | 🟡 | `api/src/takab_api/routers/drills.py:112-118`, `:415`, `:529-546`, `:661`, `:712`, `:760`; `edge/takab_edge/drill/__init__.py:67`, `:161`; `api/src/takab_api/commands/service.py:88-93` | Inventario completo en la ficha `T-6.15` del plan: un verbo con tres modos, `active` derivado del reloj sin worker, acuse por JOIN, `commandable` al leer, best-effort por sitio, observador puro en el edge que falla cerrado y aborta con SASMEX o tier. Muy testeado; **hoy se ejerció por primera vez un simulacro real** y el resultado (dos rechazos honestos en la consola, franja falsa en el móvil) es U-01. |
| **S2** | 🟡 | `web/src/features/console/DrillBanner.tsx:169`; `mobile/src/features/home/HomeView.tsx:84`, `:215`; `edge/takab_edge/local_api/index.html:297`; capturas de hoy en las tres | Simulacro y alerta real **no se parecen** en ninguna superficie tomada por separado: tira ámbar vs tarjeta roja; franja ámbar vs pantalla completa; banner ámbar sin parpadeo vs rojo parpadeante. La costura falla en otro sitio: el móvil anuncia simulacros inexistentes (U-01), el badge de la consola llama alerta real a un aviso (U-28) y la franja móvil comparte forma con la de reingreso (U-32). |
| **S3** | 🔴 | `web/src/styles/soc.css:1332-1342`; `web/src/features/console/DrillBanner.tsx:166`; `mobile/src/features/home/HomeView.tsx:82` | La animación diferenciada de simulacro **no existe** en ninguna superficie. Propuesta en `T-6.16`/`T-6.10`: consola con trama de galones que **deriva mientras la lectura es fresca y se congela** al retenerse; móvil sin bucle (regla izquierda gruesa y glifo, una sola entrada); panel **ninguna**, por spec. Forma y color primero; el movimiento solo confirma. |
| **S4** | 🟡 | `web/src/features/console/DrillBanner.tsx:206-209`, `:220`; `web/src/features/console/drill.ts:14`; `web/e2e/drill.spec.ts:23`, `:71` | Armado (cian, `CalendarClock`, EJECUTAR AHORA inerte hasta T−0, CANCELAR) y en curso (ámbar, TERMINAR) se distinguen por color, icono, texto y botón; a 5 m solo por el matiz (U-46). No existe ejecutor automático, y eso es correcto (regla de oro 8). |
| **S5** | 🔴 | `edge/takab_edge/drill/__init__.py:161-178`; `edge/takab_edge/local_api/index.html:984`, `:999-1003`; `api/src/takab_api/routers/drills.py:112-118`; `edge/tests/test_local_api_panel.py:850-856` | El aborto ocurre y queda en la memoria del gabinete, y **no se pinta en ninguna superficie** (U-03). No se pudo ensayar en local porque `make soc-local` no emite los comandos (U-37); en Puebla no se provocó, por decisión. |
| **S6** | 🟡 | `api/src/takab_api/drill_report.py:9-12`, `:124-129`, `:143-147`; `api/src/takab_api/routers/drills.py:789`, `:797`; `web/src/features/console/DrillHistory.tsx:41-51`, `:140-143` | Disciplina de honestidad ejemplar (tres categorías sin colapsar, mediana solo sobre los que acusaron, `null` que no se pinta como 0). Como pieza para Protección Civil está a medias: UUID en la cabecera, sin `stop_reason`, sin el porqué del no-acuse (U-29). Hoy el historial mostró el simulacro real con «0/2 ACUSADOS · 2 RECHAZADO(S)»: la consola sí lo cuenta bien. |

---

## 5 · Inventario de movimiento

### Lo que hay

| Superficie | Qué se mueve | Propósito | Se detiene cuando… |
|---|---|---|---|
| Consola | halo de `.soc-dot--pulse::after` (`soc.css:300-306`) | dato vivo en el riel de detalle y en la tarjeta de flota | en `DetailPanel` cuando `liveFresh` cae (`:301`); en `LinkPill` **nunca** por frescura, solo por `kind` (U-23) |
| Consola | `soc-armed-pulse` en `.soc-confirm--armed` (`soc-tabs.css:147-152`) | «el siguiente clic ejecuta» | al confirmar o al vencer el temporizador |
| Consola | frentes P/S sobre MapLibre (`wavefront.ts:134`) | dónde va la onda ahora | `isAnimatable` apaga; bajo reducción, anillos quietos declarados en la leyenda |
| Consola | `width` de `.fleet-ups__fill` (`soc-tabs.css:451`) | carga del UPS; única transición sobre un dato | no se apaga bajo reducción (U-22) |
| Consola | 18 `transition` de hover/foco (10 son `transition: all`) | realimentación de puntero | no aplica; 16 siguen vivas bajo reducción |
| Panel | `tk-blink` en `#banner-alert` (`edge/takab_edge/local_api/index.html:96`) | alerta real, exigido por la spec §9.1 | `prefers-reduced-motion` lo apaga (medido) |
| Panel | `tk-pulse` en `.dot .halo` (`edge/takab_edge/local_api/index.html:73`) | punto «en vivo» | **no se pinta** y no se detiene (U-13) |
| Móvil | relleno del hold de pánico (`PanicButton.tsx:21-39`) | impedir el disparo accidental | al soltar; es el único estado que vive solo en el movimiento |
| Móvil | knob de deslizar-para-confirmar (`ControlSheet.tsx:44-84`) | paso 2 del control | se queda al final por decisión escrita |
| Móvil | `animationType="slide"` del modal de control y del stack de crisis | transición de sistema | — |

### Lo que falta y aportaría (principio 1: siempre con un portador no-movimiento)

- **Consola · llegada de una fila nueva a la cola:** hoy aparece sin aviso. Rótulo `NUEVO` que persiste N segundos (portador) + entrada del contenedor; el dato ya pintado en el primer frame. `T-6.10`.
- **Consola · latido de `LinkPill` atado a la edad del frame** en vez de a `kind === "ok"`. El texto de edad es el portador. `T-6.10`.
- **Consola · progreso de exportación y acuse de acción firmada:** porcentaje o «PREPARANDO…» textual en el propio botón; hoy solo cambia el color. `T-6.10`.
- **Consola · trama de galones que deriva** en el banner de simulacro, congelada al retenerse la lectura: la forma distingue, el movimiento confirma. `T-6.16` (costura) y `T-6.10`.
- **Panel · el pulso de vida que se pinta y se detiene:** dar fondo al halo con el color que `setPill` ya calcula y animar solo con `conn.kind === 'live'`. Cero keyframes nuevos. `T-6.25`.
- **Móvil · latido de frescura del panel táctico**, con el pill LIVE / SIN CANAL y la edad del frame como portadores (ya existen). `T-6.20`.
- **Móvil · portador textual del hold de pánico** («MANTENGA · 2 · 1 · CONFIRMADO»). `T-6.20`.
- **Móvil · entrada del contenedor de crisis** (opacidad del `View` raíz), jamás de la instrucción ni del T+. `T-6.21`.

### Lo que sobra

- 10 `transition: all` (`soc.css:212`, `:617`, `:690`, `:1173`; `soc-tabs.css:81`, `:533`, `:623`, `:889`, `:1088`, `:1139`): animan cualquier propiedad futura del selector, incluido un color de estado. `T-6.10`.
- 14 literales `120ms` que duplican `--tk-dur-fast` (`tokens.json:88`). `T-6.10`.
- **Nada en el camino de lectura de una alerta.** `AlertBanner`, `#banner-alert` y `CrisisView` están limpios y se quedan así. Ninguna ficha del plan los toca.

---

## 6 · Conflictos con decisiones e invariantes

Donde un ítem del encargo choca con una decisión escrita, gana la decisión.

1. **W17 ↔ §4.4 y §10.2 del prompt.** La única mejora admisible del login es la personalización del Hosted UI; **no** se propone un formulario propio. Razón técnica añadida: el ID token no lleva `amr`/`acr` y la constancia de MFA de la regla de oro 8 se sostiene en el `iss` del pool (`api/src/takab_api/auth/mfa.py`). Reimplementar el reto TOTP con `T-2.87` abierto es riesgo sin beneficio.
2. **U-01 ↔ regla de oro 8 y `D-27`.** El rechazo del gabinete es **correcto**: `command_enabled` viene apagada de fábrica y el modo demostración suprime comandos firmados. Ninguna ficha propone relajar ninguno de los dos. Lo que se ficha es que la superficie **refleje** el rechazo.
3. **W2 ↔ «el superadmin no firma dictámenes»** (`api/src/takab_api/auth/matrix.py:29-31`). Decisión de seguridad; el flujo se mejora sin tocar quién firma.
4. **S3 ↔ licencia ESTRECHA del panel y `ESPECIFICACION-PANEL-GABINETE.md:688`** («Ámbar, sin parpadeo»). El panel no recibe animación de simulacro. Solo el latido de E9, que la spec ya declara.
5. **W6/W7 ↔ escala tipográfica del panel.** La spec §10.2 deja la deuda «<11 px» declarada y no ratificada; hoy son 43 de 113 declaraciones. Reformarla entera es rediseño, no auditoría: solo se toca MURO (U-15), donde la spec lo prohíbe explícitamente.
6. **W5 ↔ `MaintenanceBanner` que NO se degrada bajo alerta** (`MaintenanceBanner.tsx:8-14`, precedente del banner WR-1 del panel). La tabla de escena que propone `T-6.01` **conserva** esa excepción.
7. **U-28 ↔ `T-2.32` (instrumental = solo aviso).** El titular ya cumple; se propone que color y badge cumplan también, sin tocar la política.
8. **Anclas de identidad visual** (`web/src/designTokens.test.ts:52`). Ninguna propuesta mueve un valor anclado; donde hace falta un significado nuevo se añade un **nombre** nuevo.

---

## 7 · Lo que esta auditoría NO comprobó

- **El coste de render del panel en el Pi:** no hay navegador kiosco en el gabinete. Se midió el coste de **servir** el panel; el heap plano de 9.5 MB citado en `VERIFICACION-T-2-23.md:16` es de Chromium en una laptop.
- **El eslabón push → apertura en el móvil:** el push está en simulado. La apertura medida (8.5 s) es por sondeo.
- **El acuse táctico en vivo** («ESTOY ATENDIENDO»): exige una alarma de inmueble con dos votos desde dos dispositivos. Se contó desde el código: 1 toque.
- **La primera pantalla del brigadista en el Pixel** y su comportamiento con `inspector`/`building_admin`: no se capturó.
- **El aborto de un simulacro por sismo real:** no se provocó en Puebla y no se pudo ensayar en local (U-37). El análisis es de código.
- **El simulacro real en el gabinete de Puebla:** los dos gabinetes lo **rechazaron** (esperado con `command_enabled` apagada), así que el panel real nunca mostró el banner ámbar; lo que sí se midió es el efecto en el móvil (U-01). `audio.enabled` es `false` en el Pi: aunque hubiera aceptado, no habría voceado.
- **El SOC desplegado durante el simulacro:** lo vio Mauricio; el historial que transcribió es la evidencia.
- **Si el pool de Cognito está en Hosted UI clásico o en «managed login»:** el repo no lo declara; decide el mecanismo de `T-6.08`.
- **`console_scope_enforced` en vivo:** nadie ha visto la consola con el alcance activado; el hallazgo U-17 es de lectura.
- **El PDF del simulacro y del dictamen abiertos:** la API respondió 201 y la pestaña reservada quedó en blanco 10 s en el stack local; puede ser el endpoint de MinIO local. No se afirma nada sobre producción.
- **Contraste en el móvil:** no hay axe para React Native; los pares candidatos están en `CrisisView.tsx:104` y `TacticalAckButton.tsx:108` y no se midieron.
- **Las marcas SASMEX/TIER sobre las trazas en `?demo=alerta`:** viven en una ventana del ciclo de 48 s y la captura cayó fuera; no se afirma ni se niega.
- **Los 5 e2e que fallaron hoy** (`layout.spec.ts:70`, `:108`; `screens.spec.ts:573`, `:601`; `smoke.spec.ts:50`) se anotan como evidencia de U-26, U-35 y U-38; no se investigó si son estables o dependen del stack local.

---

## 8 · Mediciones de la sesión

| Qué | Valor | Dónde/cómo |
|---|---|---|
| Panel · recorridos | 13 escenas × 3 modos × 2 (`reduced-motion`) = 78; 0 peticiones externas; 0 errores de consola; `localStorage.length` = 0 | Playwright contra `127.0.0.1:8080` de `make soc-local` |
| Panel · MURO 1920×1080 | tier 72 px · relé 28 px · sin acciones · sin PIN · documento 1080 px | `getComputedStyle` |
| Panel · CONSOLA 1920×1080 / 1280×800 | documento 1347 / 1480 px · `#actionbar` en y=1230 / 1269 | id. |
| Panel · CAMPO 800×1280 | `.lane` 35 px · botón 56 px · PIN 48 px · 9 de 11 tarjetas bajo el pliegue | id. |
| Pi real · servir el panel | `takab-edge` 1–2 % CPU reposo → 4–8 % con 1 cliente a 1 Hz; status 8–10 ms (17 KB); waveform 16–22 ms (100 KB); HTML 13–19 ms (200 KB); fuentes 200 con `max-age=86400` | `ssh takab-pi5 top -bn3`; `curl -w time_total` |
| Consola · axe sin filtrar | 72 corridas (4 roles × 3 viewports × 6 pantallas), 15 con violaciones, 171 nodos, una sola regla: `color-contrast` | `@axe-core/playwright`, tags `wcag2a/2aa/21a/21aa` |
| Consola · arranque dev-token | 521 ms hasta `[data-screen-label]`; 710 ms hasta el primer `data-state="ready"` | `soc_walk` |
| Consola desplegada | 1282 ms hasta la landing; +1849 ms hasta el Hosted UI (3 saltos); `/api/dev/token` → 404; `build 1e7bf0f` | Playwright, solo lectura |
| Consola · flujos | simulacro 3 clics / 2.7 s hasta banner; alerta → solicitar dictamen 3 clics; inspector firma + PDF 4 clics; cliente 2 clics; estación 2 clics más (sin cliente) | `soc_flows` |
| Consola · e2e existentes | 66 pasados · 5 fallidos · 1 omitido (viewport 1280×800) | `npx playwright test` |
| Pixel 8 Pro | crisis a **8.5 s** del incidente (sondeo 30 s, sin push); check-in ≤ 6 s tras concluir; 1 toque; offline real 105 s → «DATOS RETENIDOS · hace 1 min»; `panic-hold` 416×70 dp al 35 %; CTA 416×49 dp; enlace 382×19 dp; pestañas 112×48 dp | `adb`, `uiautomator`, `screencap` |
| Simulacro real (Mauricio, 3 MIN, 2 gabinetes) | historial «0/2 ACUSADOS · 2 RECHAZADO(S)»; panel de Puebla `drill.active=false` durante 10 min de vigilancia; Pixel con franja «SIMULACRO EN CURSO» | consola dev; `GET /api/status`; `screencap` |
| Móvil · jest | 64 suites · 528 tests en verde | `npm test` |
| Docs · baseline | 106 tests de consistencia en verde antes de escribir una línea | `pytest api/tests/test_docs_consistency.py …` |
