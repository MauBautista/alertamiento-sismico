# Plan del prototipo funcional — de lo desplegado a lo que se enseña

> **De dónde sale.** Del encargo de Mauricio del **2026-09-11**, con la reforma visual cerrada
> ([`design/PLAN-REFORMA-VISUAL.md § 10`](design/PLAN-REFORMA-VISUAL.md)) y la nube dev corriendo
> `main` (`/api/health` → `build e68a89e`, esquema `0062_simulacro_aborto_por_sitio` al día,
> verificado ese mismo día). El encargo: **un prototipo funcional y profesional para presentar a
> un cliente**, planificado por fases de la más crítica a la menos, cada fase con un objetivo
> medible que se ejecuta en `/loop` hasta alcanzarlo, con subagentes donde convenga, y todo
> listo para que otra sesión lo empiece.
>
> **Bloque de numeración `T-7.xx`, y no colisiona con nada.** Verificado antes de escribirlo:
> `TASKS.md` no contenía ninguna ocurrencia de `T-7.`; las 28 fichas van de `T-7.01` a `T-7.28` y
> viven en el `## BLOQUE VIII · PROTOTIPO FUNCIONAL` de [`TASKS.md`](TASKS.md), insertadas en el
> mismo commit que este plan con la cabecera recontada (un test la verifica). **Aquí está el
> diseño, el objetivo ejecutable y la plantilla de cada fase; allí, los criterios de aceptación.**
>
> **Cómo se ejecuta.** `/goal`, `/write-plan` y `/execute-plan` **no están instaladas** en esta
> máquina (se comprobó con `find` sobre `~/.claude` y `.claude`); `/loop` sí. Por eso el objetivo
> de cada fase es **un bloque de comandos que devuelve 0**, y la instrucción es «corre el bloque en
> `/loop` (modo dinámico) hasta que pase; si tras tres iteraciones un criterio sigue en rojo, para
> y resume el bloqueo» (regla de detención de `CLAUDE.md §6`). Si alguna sesión futura tuviera
> `/goal`, el bloque es su argumento.
>
> **Cuatro decisiones lo gobiernan** — `D-30` a `D-33` de
> [`DECISIONES-MAURICIO.md`](DECISIONES-MAURICIO.md) — y se tomaron el mismo día con sus razones;
> §3 las resume. **Los cinco principios de la reforma visual siguen vigentes** salvo en lo que
> `D-30` revoca expresamente: el movimiento nunca es el único portador de estado, ninguna
> animación retrasa la lectura de una alerta, la animación más valiosa es la que se detiene, cero
> peticiones externas en el panel, todo valor visual sale del token.
>
> **Estimación en sesiones de Claude Code**, no en horas: unas **21** en total.

---

## 1 · La ruta a la presentación

`PLAN-V1-COMERCIAL.md §1` separó la ruta al primer cliente de la ruta a poder enseñar el producto,
y la reforma visual añadió `EXPOSICIÓN-UI`. Este plan añade la tercera y última capa: **que el
guion entero corra con hardware real y que lo que se ve sea memorable**.

```
PROTOTIPO  =  F0 (conformidad)  ∧  F1 (el guion corre hoy)  ∧  F2 (datos demo)  ∧  F3 (la vida del sismo)
              ∧  F4 (papel oficial)  ∧  [F5 (sismología visual) ∥ F6 (IA asesora)]  ∧  F7 (ensayo general)
```

Las tres primeras son las que **impiden presentar** si faltan: sin F0 la evidencia no llega y el
teléfono no vibra; sin F1 nadie ha visto el guion entero con el radio de verdad; sin F2 la
consola enseña las pruebas de julio. F3 es **lo que vende**: la alerta que late, las ondas que
llegan a cada estación, el epicentro y la tabla por estación. F4 a F6 son lo que el cliente **se
lleva** (el papel) y lo que hace que el producto parezca de otra liga (el sismógrafo, el mapa de
intensidad, la redacción asistida). F7 es el ensayo con cronómetro.

---

## 2 · Lo que se midió antes de planificar

Tres barridos del repositorio y uno de diseño (unas 280 llamadas a herramientas). Estos son los
hechos que **cambiaron las premisas** del encargo; sin ellos el plan habría construido cosas que ya
existen o cosas que no se pueden construir así.

| Hecho | Consecuencia para el plan | Evidencia |
|---|---|---|
| **La IA ya existe, lista y apagada.** Proveedor OpenRouter con guardrail, cuota mensual por tenant, redacción de PII y respaldo determinista; único consumidor: el PDF del dictamen | F6 **enciende y amplía**, no construye | `api/src/takab_api/narrative/openrouter.py`, `settings.py` (`openrouter_*`, `ai_monthly_cap_usd`), `routers/reports.py` |
| **Nada cierra un incidente en producción.** `transition_incident`/`close_resolved` no tienen llamador; no hay TTL; el ACK no quita el banner; la clasificación no cambia el estado | F3 construye la máquina de fases (`T-7.13`) | `incident/lifecycle.py`, `routers/incidents_ack.py`, `web/src/features/console/useLiveIncidents.ts` |
| **No existe «analizando» en ninguna superficie**; `in_review` solo se pinta en la tabla de triage; el móvil deriva `shaking_concluded` sin persistirlo; la tabla de escenas está clavada por un censo | La revisión se **deriva** de `alertKind`, no se añade a `SCENE_PRECEDENCE` (`T-7.16`) | `schemas/mobile.py`, `routers/mobile_site.py`, `web/src/features/scene/scene.ts`, `web/src/sceneCensus.test.ts` |
| **El mapa YA anima frentes P/S** desde un epicentro localizado y el faro del edificio que disparó — pero **rechaza los epicentros `external`/`manual`** | F3 añade una rama explícita `reproduccion` y la ráfaga por estación (`T-7.18`) | `web/src/features/console/MapPanel.tsx`, `wavefront.ts` |
| **El motor de cuórum clusteriza desde `incidents` y, al confirmar, manda comando firmado a los gabinetes miembro.** Un simulador que publique `LocalEvent` abre incidentes ⇒ cuórum fabricado ⇒ comando al gabinete real | Los simuladores publican **features y latido, jamás eventos** (`T-7.11`, `T-7.15`) | `api/src/takab_api/incident/engine.py`, `edge/simulators/fleet.py` |
| **No hay tabla por estación**; las features por segundo sí existen por sensor | `T-7.17` la construye de **picos medidos** | `db/schema.sql` (`waveform_features_1s`, `quorum_votes`), `web/src/features/triage/QuorumNodes.tsx` |
| **El worker de backfill NO corre en la nube** (`T-3.11.c` abierta): sin miniSEED en S3, el espectrograma del dictamen sale vacío en la nube | F0 lo despliega (`T-7.02`) | `deploy/cloud/docker-compose.yml`, `deploy/cloud/deploy.sh` |
| **El push está SIMULADO en la nube.** `deploy.sh` no exporta el ARN; la cuenta de servicio de Firebase no está en `local.auto.tfvars`; la app no tiene `google-services.json`; el teléfono se entera por sondeo (30 s en reposo, 5 s en crisis) | F0 lo cablea con respaldo declarado (`T-7.03`) | `api/src/takab_api/notify/push.py`, `infra/terraform/modules/push/main.tf`, `mobile/src/features/alert/useAlertState.ts` |
| **El modo prueba del WR-1 suprime la nube.** Un pulso real con el modo desarmado abre incidente real, dispara push y **la cascada de notificaciones del tenant** | El runbook lo comprueba antes de tocar el radio (`T-7.07`) | `edge/takab_edge/supervisor.py`, `rules/__init__.py` |
| **El catálogo de 13 sismos reales está sembrado sin ingesta viva y con procedencia NULL** ⇒ hoy ninguna fila pinta cifra | F2 consulta USGS y lo graba (`T-7.12`); F5 lo automatiza (`T-7.25`) | `db/seeds/reference_earthquakes.sql`, `api/src/takab_api/procedencia.py` |
| **Hay un simulador de flota que habla mTLS con la nube real** y un script de aprovisionamiento de gateways | F2 lo parametriza y lo deja corriendo (`T-7.11`) | `edge/simulators/fleet.py`, `infra/scripts/provision_gateway.sh`, `runbooks/RUNBOOK-load-test-ingesta.md` |
| **DEMO se deriva del prefijo del código**; un censo afirma exactamente lo que genera `sim_fleet.sql` | La red demo usa prefijos `site-sim-`/`gw-sim-`/`SIM` y el censo declara el segundo seed | `web/src/features/fleet/datosDeDemostracion.ts`, `web/src/siteDemoCensus.test.ts` |
| **Hay precedente de purga** con superusuario que conserva `audit_log`; las tablas de evidencia son append-only por trigger; las features retienen 24 meses | `T-7.10` lo calca; **no se fabrica historial** con fechas falsas | `db/maintenance/2026-07-10_purge_sim_fleet_and_test_incidents.sql`, `db/schema.sql` |
| **`TakabPDF` es el membrete de facto** y el dictamen ya trae croquis, trazas, espectrograma (FFT en numpy, dibujo vectorial) y duración; **la API no tiene matplotlib**, el edge sí tiene scipy | F4 promociona el membrete; el shakemap del PDF se dibuja vectorial (`T-7.21`, `T-7.24`) | `api/src/takab_api/dictamen/layout.py`, `espectrograma.py`, `api/pyproject.toml`, `edge/pyproject.toml` |
| **El panel del gabinete no tiene FFT ni filtros** y sirve 60 s decimados; su banner de alerta **ya parpadea** | El sismógrafo vive en el panel (`T-7.23`); `D-30` en el panel es verificar, no añadir | `edge/takab_edge/signal/waveform.py`, `local_api/index.html` |
| `T-3.09` tiene arquitectura decidida (`D-08`) | `T-7.24` la ejecuta tal cual | `TASKS.md` § T-3.09, `design/BLOQUE-IV-ARQUITECTURA.md` |
| USGS (dominio público) tiene los eventos exactos; OpenRouter sirve `anthropic/claude-sonnet-5` con herramientas y visión a 2/10 USD por millón de tokens | Fuente viva = USGS; modelo recomendado = `sonnet-5` | consultas de la sesión de planificación |

**Arribos calculados** para el 19-S-2017 (18.5499, −98.4887, 48 km de profundidad; S a 4 km/s,
P a 7 km/s): Puebla +19.6 s · Tlaxcala +25.3 s · CDMX +32.1 s · Toluca +38.7 s. Es la coreografía
que el mapa tiene que enseñar, y el valor de referencia del test de `T-7.14`.

---

## 3 · Las decisiones que gobiernan el plan

| Decisión | Qué fija | Quién |
|---|---|---|
| **`D-30`** | Se anima el camino de lectura de la alerta (muro, panel, móvil) **con condiciones**: texto legible desde el primer frame, portador no-movimiento, se detiene por estado, respeta `reduced-motion`. Revoca el §5.3 del plan de reforma visual | Mauricio |
| **`D-31`** | Red de demostración en la nube dev —Puebla real + Tlaxcala, CDMX y Toluca simuladas—, excepción **temporal** a «solo la flota real en la nube» (`T-1.47`), con retirada escrita; la reproducción histórica se arma solo en tenants con sitios DEMO | Mauricio |
| **`D-32`** | La IA ve datos estructurados sin PII **y las fotos del brigadista** (modelo con visión); aviso en la cámara forense, adenda de residencia de datos, consentimiento contractual pendiente | Mauricio |
| **`D-33`** | El incidente tiene fases: `open/acked` = alerta, `in_review` = analizando, `closed` = fuera. La alerta se apaga **por estado**, nunca por cronómetro del cliente; se cierra por clasificación, dictamen firmado o TTL de horas. `reproduccion` es clasificación y atributo del evento, no un estado de procedencia | delegada |

Y los supuestos que se fijan sin ser decisión (revocables al leerlos):

- **La purga de la nube dev es operativa, no total** (respuesta de Mauricio): se van incidentes
  y su familia, eventos, telemetría, notificaciones, simulacros, check-ins y daños; se quedan
  `audit_log`, `actuation_records`, clientes, sitios, gabinetes, sensores y usuarios.
- **La fuente viva es USGS.** El SSN sigue bloqueado por atribución (`D-06`, `T-2.149`); SASMEX
  no publica epicentros. El reporte lo dice con esas palabras.
- **Solo se deroga la viñeta `[DIFERIDO · mini-ShakeMap]`** de `BLUEPRINT §14`, dentro de
  `T-7.24`; las cinco viñetas `[INVARIANTE · …]` no se tocan.

---

## 4 · Las ocho fases

> **El ciclo de cada ficha** (el mismo del Bloque VII): rama desde `main` → tests primero → gates
> verdes de su componente → **ejercer los criterios fuera de los tests** (navegador real, Pi real,
> Pixel real) → `[x]` con «Cómo se cerró» → memoria → `graphify update .` → regenerar
> `MATRIZ-REQUISITO-TEST.md` → commit con rutas explícitas, Conventional Commits, sin footers de
> IA → PR → CI → merge. **Subagentes** según `TRASPASO-SESION.md §2`: dos por lote, una base de
> tests por agente (`takab_test_a`, `takab_test_b`), ficheros disjuntos como límite duro, **un solo
> agente crea migraciones**, y el `.output` de un subagente es un symlink (`stat -L`).

### F0 · Conformidad — «lo que está en código está en el sistema» · 3 sesiones

**Objetivo.** Un informe con veredicto por pieza, derivado de comandos, y **cero rojos** que
bloqueen la demo. Las dos brechas ya conocidas —evidencia que nunca llega, push simulado— se
cierran aquí porque sin ellas los actos 3 y 4 del guion no existen. Y «nada se encima» solo se
puede afirmar **con la alerta en pantalla**, no con la consola en reposo.

| Ficha | Qué cierra | Lote |
|---|---|---|
| `T-7.01` | `deploy/cloud/conformidad.sh` + `make cloud-conformidad` + test que deriva los workers ejecutables y exige servicio en compose; `INFORME-CONFORMIDAD-DEMO.md` | A |
| `T-7.02` | Servicio `backfill` en la nube; ejecuta y cierra `T-3.11.c`; prueba viva con miniSEED en S3 | A |
| `T-7.03` | Push real por FCM con respaldo medido si no hay credenciales | integrador |
| `T-7.04` | Censo de solapes con `alert` y `review` forzadas (consola, panel, Pixel) y conteo de clics | B |
| `T-7.05` | Correcciones del censo, un criterio por hallazgo | según hallazgos |
| `T-7.06` | `console_scope_enforced` encendido; ejecuta y cierra `T-2.89` | integrador |

**Goal F0** (exit 0 ⇒ fase cerrada):

```bash
set -e; cd "$(git rev-parse --show-toplevel)"
make verify
bash deploy/cloud/conformidad.sh          # build==HEAD · esquema al día · compose cubre workers · env completo · backfill vacío · Pi · APK
( cd web && PW_BASE_URL=https://16-58-11-196.sslip.io npx playwright test e2e/deployed.spec.ts && npx playwright test e2e/layout.spec.ts )
! grep -q '🔴' takab-docs/INFORME-CONFORMIDAD-DEMO.md
```

**Subagentes.** Tres `Explore` previos con contrato fijo por pieza (`PIEZA · VEREDICTO · EVIDENCIA
ruta:línea · EJERCIDO_FUERA_DE_TESTS · RAZON`): nube y compose · edge y release del Pi · móvil, APK
y push. Después lote A (`deploy/`, `api/tests/test_compose_cubre_los_workers.py`) en paralelo con
lote B (`web/e2e`, guion `panel_walk` en el scratchpad). `T-7.03` y `T-7.06` los ejecuta el
integrador porque tocan `deploy.sh` y despliegan.

**Aporta Mauricio.** La cuenta de servicio de Firebase y `google-services.json` (pendientes §4.4);
SSO fresco justo antes de construir imágenes (`aws sso logout && aws sso login`; el build tarda
unos 40 minutos y el token caduca a mitad); el Pixel por USB; la decisión de encender el alcance
por rol para la demo.

### F1 · El guion corre de punta a punta HOY · 2 sesiones

**Objetivo.** Ejecutar los cuatro actos con el WR-1 real, el gabinete de Puebla y el Pixel, con
evidencia por acto, y dejar escrito el runbook de la demostración **antes** de añadir nada. Lo que
se rompa aquí se arregla aquí.

| Acto | Qué se ve | Ficha |
|---|---|---|
| 1 · SOC en reposo | mapa con las estaciones vivas, KPIs, cola vacía | `T-7.07` (precondiciones) |
| 2 · Movimiento aislado sin WR-1 | tier en el panel, escena `notice` en consola, evento en nube, **relés quietos** | `T-7.08` |
| 3 · Pulso del WR-1 | sirena, incidente `sasmex`, push y pantalla de crisis en el Pixel | `T-7.07`, `T-7.09` |
| 4 · Después de la sacudida | dictamen preliminar, brigadista en el táctico, inspector firma, reporte PDF con evidencia | `T-7.09` (Maestro `03`) |

**Goal F1:**

```bash
bash deploy/demo/guion.sh --preflight      # modo prueba desarmado · modo demo apagado · destinatarios propios · red 192.168.1.0/24 · Pixel enrolado
bash deploy/demo/guion.sh --check          # espera el pulso: incidente sasmex · phase alert_active · relés reported · PDF con ≥1 imagen
mobile/.maestro/run.sh 01a-crisis.yaml && mobile/.maestro/run.sh 03-dictamen-liberacion.yaml
# y a mano: Registro del runbook con los cuatro actos, captura por acto, último incidente de site-dev clasificado `prueba` y cerrado
```

**Subagentes.** Ninguno: es físico y secuencial. **Aporta Mauricio.** La sesión con el WR-1 (la
sirena suena de verdad y la cascada notifica de verdad: avisar a quien esté cerca y comprobar que
los destinatarios del tenant son propios), el Pixel, y un segundo dispositivo como brigadista si
lo hay.

### F2 · Datos demo · 2 sesiones

**Objetivo.** Que la consola enseñe una red presentable y nada de las pruebas de julio a
septiembre, sin fabricar historia.

| Ficha | Qué cierra | Lote |
|---|---|---|
| `T-7.10` | Purga operativa con respaldo y huella; test sobre base efímera; conteos en el Registro | A |
| `T-7.11` | `demo_red.sql` (Tlaxcala, CDMX, Toluca con nombres ficticios presentables), `make cloud-demo-red[-down]`, tres cosas IoT, `fleet.py --stations-file --tenant --no-events` como unidad systemd | B |
| `T-7.12` | Catálogo con procedencia real: consulta viva a USGS grabada como fixture; entra el 2023-12-07 M5.7 | A |

**Goal F2:**

```bash
psql "$NUBE" -Atc "select count(*) from incidents" | grep -qx 0
psql "$NUBE" -Atc "select count(*) from audit_log" | awk '{exit !($1>0)}'
psql "$NUBE" -Atc "select count(*) from sites where code ~ '^site-sim-1[0-9]{2}$'" | grep -qx 3
psql "$NUBE" -Atc "select count(*) from reference_earthquakes where review_status='confirmado'" | awk '{exit !($1>=6)}'
curl -s -H "Authorization: Bearer $JWT" "https://16-58-11-196.sslip.io/api/telemetry/map/state" | jq -e '[.sites[]|select(.link_down==false)]|length==4'
ssh takab-pi5 systemctl is-active takab-fleet-sim      # o el host que se haya elegido tras medir
( cd edge && uv run pytest -q tests/test_fleet_sim.py ) && ( cd demo && uv run pytest -q tests/test_purge_demo.py ) && ( cd web && npx vitest run src/siteDemoCensus.test.ts )
```

**Subagentes.** Lote A (SQL de purga, semilla, tests de `demo/`, fixture de USGS) en paralelo con
lote B (`fleet.py`, unidad systemd, aprovisionamiento). La ejecución contra la nube la hace el
integrador y en este orden: respaldo → purga → semilla → aprovisionar → arrancar el simulador.
**Aporta Mauricio.** SSO; los nombres si quiere otros; el apply de las tres cosas IoT.

### F3 · La vida del sismo en el SOC · 5 sesiones

**Objetivo.** Que un pulso del WR-1 desencadene, con honestidad, toda la coreografía: la alerta que
persiste y late, las ondas que llegan a cada estación, «ANALIZANDO», el epicentro con su
procedencia y la tabla de cómo detectó cada estación; y que todo **se detenga** al clasificar.

| Ficha | Qué cierra | Lote |
|---|---|---|
| `T-7.13` | `run_lifecycle_pass`: `open/acked → in_review` (tier normal + settle + `alert_hold_min_s`) y `→ closed` por clasificación, dictamen firmado o `incident_review_ttl_s` | 1-A |
| `T-7.14` | Reproducción armada en la nube (`demo_replay`, migración `0063`, `EVT-REP` `external` con `meta.reproduccion`, plan de arribos puro con espejo) | 1-B |
| `T-7.15` | `fleet.py --replay --armar`: features en rampa por arribo, anclado al panel del gabinete real, **nunca eventos** | 2-A |
| `T-7.16` | Escena `review` derivada de `alertKind` + banner ANALIZANDO con contador de texto | 2-B |
| `T-7.18` | `MapEpicenter.reproduccion`, rama en `isLocalized`, ráfaga de arribo por estación (`--tk-dur-arrival`) | 2-B |
| `T-7.19` | La alerta se anima y se detiene (`D-30`): halo del muro (`--tk-dur-alerta`), panel verificado, `CrisisView` re-acreditado en el Pixel | 2-B (web) · 3-B (móvil) |
| `T-7.17` | `GET /incidents/{id}/estaciones` + `EstacionesTable` + sección del PDF | 3-A |
| `T-7.20` | Epicentro y estaciones en el muro + `vida_del_sismo.spec.ts` sobre `soc-local` | integrador |

**Goal F3:**

```bash
( cd api && DATABASE_URL=postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab_test uv run pytest -q tests/incident/test_lifecycle_pass.py tests/api/test_classification_cierra.py tests/replay tests/api/test_estaciones.py )
( cd edge && uv run pytest -q tests/test_fleet_replay.py tests/test_cloud_streaming_crudo.py )
( cd web && npx vitest run src/sceneCensus.test.ts src/styles/motionInvariants.test.ts src/features/console/wavefront.test.ts src/serverDataCensus.test.ts src/siteDemoCensus.test.ts && npm run e2e )
( cd mobile && npm test -- CrisisView )
bash deploy/demo/guion.sh --check-f3       # open→in_review en ≤ settle+hold+15 s tras tier normal · epicentro reproduccion=true con procedencia confirmado · 4 filas por estación con t_arribo y pico · cierre por clasificación
# fuera de tests: capturas del muro en alert (halo vivo) → review (contador) → epicentro y tabla; alerta detenida tras clasificar; Pixel con y sin reduce-motion
```

**Subagentes.** Lote 1: A = `T-7.13` (`api/incident`) en paralelo con B = `T-7.14` (`api/replay`,
**única migración `0063`**). Lote 2: A = `T-7.15` (edge) en paralelo con B = `T-7.16`+`T-7.18`+la
parte web de `T-7.19`. Lote 3: A = `T-7.17` (router + web) en paralelo con B = la parte móvil de
`T-7.19` (Pixel). `T-7.20` lo integra el integrador. **Aporta Mauricio.** El Pixel; el sismo a
reproducir (recomendado 19-09-2017 M7.1, el que más cerca pasó de las cuatro estaciones); los
valores de `alert_hold_min_s` e `incident_review_ttl_s`.

### F4 · Papel oficial · 2 sesiones

**Objetivo.** Que todo papel que sale del sistema comparta cabecera, pie e identidad, y que el
informe del evento sea el documento que el cliente se lleva.

| Ficha | Qué cierra |
|---|---|
| `T-7.21` | `MembretePDF` (tipo, folio, fecha, `build`, página x/y, sha256, «EVIDENCIA INMUTABLE», positivo sobre blanco, Carta); censo de subclases de `FPDF`; hoja en blanco en `shared/brand/membrete/` |
| `T-7.22` | Informe del evento: red de estaciones (mapa vectorial + arribos), epicentro con procedencia, cronología, daños del brigadista con fotos; huecos declarados para F5 y F6 |

**Goal F4:**

```bash
( cd api && DATABASE_URL=postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab_test uv run pytest -q tests/documentos tests/dictamen tests/api/test_reports.py )
python shared/brand/generar.py && git diff --exit-code shared/brand/membrete
# un reporte de la nube de un incidente de reproducción: pypdf cuenta ≥ 4 imágenes; pdftotext encuentra «REPRODUCCIÓN» y el folio; los tres PDFs comparten cabecera y pie (espía del render)
```

**Subagentes.** `T-7.21` primero y `T-7.22` después (hereda del membrete). **Aporta Mauricio.**
Razón social, domicilio, clasificación del documento y firmante (pendientes §4.8).

### F5 · Sismología visual · 4 sesiones (puede solaparse con F6)

**Objetivo.** El sismógrafo propio en el panel, el mapa de intensidad por evento y la consulta viva
a la fuente. Todo determinista, todo declarado cuando falta el dato.

| Ficha | Qué cierra | Lote |
|---|---|---|
| `T-7.23` | Panel SISMÓGRAFO: spec primero, `/api/spectrogram` y `/api/helicorder`, tarjeta de estación, coste medido en el Pi 4 | A |
| `T-7.24` | Mini-ShakeMap (`T-3.09`, `D-08`): derogación de la única viñeta diferida, tres capas, `SIN COBERTURA`, GeoJSON con procedencia, PDF vectorial, matriz regenerada | solo |
| `T-7.25` | Consulta FDSN de USGS al entrar en revisión; procedencia viva; SSN declarado como no consultado | B |

**Goal F5:**

```bash
( cd edge && uv run ruff check . && uv run pytest -q tests/test_local_api_sismografo.py )
( cd api && DATABASE_URL=postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab_test uv run pytest -q tests/shakemap tests/forensics/test_usgs.py tests/test_docs_consistency.py tests/test_matriz_trazabilidad.py )
git diff --exit-code takab-docs/MATRIZ-REQUISITO-TEST.md        # tras regenerarla
( cd web && npx vitest run MapPanel )
# y a mano: coste del sismógrafo escrito en la spec del panel (medido en el Pi real); captura del SISMÓGRAFO en el Pi y del mapa de intensidad en consola con un incidente de reproducción
```

**Subagentes.** A = `T-7.23` (edge) en paralelo con B = `T-7.25` (api); `T-7.24` solo, porque toca
documentos de gobierno, web y la matriz a la vez. **Aporta Mauricio.** Nada (USGS es público);
acceso al Pi para medir.

### F6 · IA asesora por OpenRouter · 2 sesiones

**Objetivo.** Encender lo que existe, medir su latencia real, contar su coste, registrar su
procedencia, y ampliar lo que ve (`D-32`) sin que toque jamás el veredicto.

| Ficha | Qué cierra |
|---|---|
| `T-7.26` | OpenRouter encendido en la nube: secreto, env, timeout medido, tope, `audit_log` con modelo y hash, control negativo con la clave revocada |
| `T-7.27` | Prompts v2 con estaciones, reproducción, cronología, daños **y fotos** (multimodal, ≤ 6, 1024 px); comprobación de visión al arrancar; redacción ampliada; adenda de residencia y aviso en la cámara forense |

**Goal F6:**

```bash
( cd api && DATABASE_URL=postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab_test uv run pytest -q tests/narrative )
# en la nube: POST /incidents/{id}/report → pdftotext contiene «Narrativa: openrouter» y la sección de daños observados;
#   ai_spend tiene fila del mes con calls ≥ 1 y coste > 0; audit_log tiene narrative_generated con modelo y hash
# control negativo: con la clave revocada el reporte dice «NARRATIVA DEGRADADA»
```

**Subagentes.** Uno de implementación y uno verificador (contrato y redacción), en paralelo.
**Aporta Mauricio.** Cuenta de OpenRouter, clave en Secrets Manager (`takab/dev/openrouter`, con
`!`, nunca en el chat), tope mensual en su panel, el modelo (recomendado `anthropic/claude-sonnet-5`;
`anthropic/claude-haiku-4.5` si el coste manda), y la cláusula de consentimiento (pendientes §2.13
y §4.7).

### F7 · Ensayo general · 1–2 sesiones

**Objetivo.** Dos corridas enteras con cronómetro antes de tener un cliente delante, y un plan B
por cada cosa que puede fallar.

| Ficha | Qué cierra |
|---|---|
| `T-7.28` | Dos ensayos cronometrados (cada uno clasificado `reproduccion`), plan B escrito, lista «lo que NO debe decirse» actualizada, paquete de capturas y vídeo, informe de conformidad re-corrido, veredicto de flujos con Mauricio delante |

**Goal F7:**

```bash
for i in 1 2; do bash deploy/demo/guion.sh --full || exit 1; done
mobile/.maestro/run.sh 01a-crisis.yaml && mobile/.maestro/run.sh 01b-checkin-sync.yaml && mobile/.maestro/run.sh 02-tactico-foto-danos.yaml && mobile/.maestro/run.sh 03-dictamen-liberacion.yaml
( cd web && PW_BASE_URL=https://16-58-11-196.sslip.io npx playwright test e2e/deployed.spec.ts e2e/screens.spec.ts )
! grep -q '🔴' takab-docs/INFORME-CONFORMIDAD-DEMO.md
```

---

## 5 · Lo que se decide NO hacer

Un plan sin lista de descartes es una lista de deseos.

1. **No meter la IA en disparo, tier, veredicto ni cierre** (regla de oro 1). La garantía es de
   tipos y la defiende `api/tests/narrative/test_contract.py`; la IA redacta, el determinista decide.
2. **No publicar `takab/events` desde simuladores.** Un `LocalEvent` simulado abre incidentes, el
   motor forma cuórum con estaciones que no midieron nada y la nube manda un comando firmado al
   gabinete real. La reproducción son features y latido (reglas de oro 1, 7 y 9 intactas).
3. **No subir forma de onda cruda en continuo** (regla de oro 9). La vista viva del sismógrafo
   vive en el panel del gabinete, en la LAN; la nube ve features y el miniSEED de eventos
   confirmados.
4. **No embeber el visor de Raspberry Shake** (logo ajeno, internet y dato ajeno). Se construye
   propio y offline.
5. **No cerrar por cronómetro del cliente ni extender la edad máxima del frente de onda.** El
   estado manda (`D-33`); la animación más valiosa sigue siendo la que se detiene.
6. **No añadir un estado de procedencia «reproducción».** La procedencia dice quién publicó la
   cifra, y la cifra reproducida es la del catálogo; un sexto estado tocaría seis pines y el JSON
   que lee el panel sin build. La reproducción es un atributo del evento.
7. **No añadir `is_demo`, no relabelar `DEMO`** (literal congelado por test), no marcar como real un
   sitio simulado.
8. **No fabricar historial con fechas falsas.** Las features retienen 24 meses y un incidente de
   2017 sería una mentira con reloj; el historial son las corridas reales clasificadas
   `reproduccion` y la capa `◇ HISTÓRICO` del catálogo.
9. **No atribuir a SASMEX o al SSN lo que no publicaron.** Epicentros de USGS o «reproducción».
10. **No derogar la §14 entera**: solo `[DIFERIDO · mini-ShakeMap]`, en `T-7.24`.
11. **No usar emuladores**: móvil solo en el Pixel 8 Pro real; sin Pixel, la ficha móvil no se cierra.
12. **No animar la línea de escena de las cinco rutas secundarias** (la defiende
    `layoutInvariants`); la alerta se anima en el muro, el mapa, el panel y el móvil.
13. **No poner matplotlib en la API**: el mapa de intensidad del PDF se dibuja vectorial con fpdf,
    como el espectrograma.
14. **No sembrar los veinte sitios de `sim_fleet.sql` en la nube**: tres con nombre y latido
    propios, y se retiran con `make cloud-demo-red-down` antes del primer cliente de pago (`D-31`).
15. **No tocar `SCENE_PRECEDENCE`**: la revisión se deriva de `alertKind`.

---

## 6 · Riesgos que cuestan una corrida (y su cinturón)

| Riesgo | Cinturón |
|---|---|
| El modo prueba del WR-1 está armado o el modo demostración encendido ⇒ ni incidente ni push, sin ningún error visible | `guion.sh --preflight` los comprueba antes de desarmar el radio |
| El pulso real dispara la cascada de notificaciones a terceros | El preflight verifica que los destinatarios del tenant son propios |
| La reproducción forma cuórum ⇒ comando firmado al gabinete real | `--no-events` por construcción y un test que lo fija; `command_enabled` apagado en el Pi salvo decisión escrita |
| La purga toca `audit_log`/`actuation_records` o un chunk de hypertable con el trigger copiado | Ensayo sobre un dump local + test de lo conservado; `session_replication_role=replica` como el precedente |
| `--armar` no ve el pulso porque el equipo no está en `192.168.1.0/24` (al planificar estaba en `192.168.3.88`) | `ip -4 addr` en el preflight |
| `isLocalized` rechaza epicentros `external` ⇒ sin ondas | Rama explícita `reproduccion` (`T-7.18`) |
| El catálogo con procedencia NULL no pinta la magnitud | Consulta real a USGS grabada (`T-7.12`) **antes** de F3 |
| `sceneCensus`, `motionInvariants` o `siteDemoCensus` en rojo | Se actualizan en el mismo commit con la razón escrita; en la duda, gana el test |
| `MapEpicenter` o la clasificación cambian el contrato ⇒ `make drift` en rojo | Regenerar SDK y openapi y comitearlos en la misma rama |
| El timeout de 8 s de OpenRouter deja siempre la narrativa determinista y parece «la IA no funciona» | Medir la latencia del modelo antes de decidir; el respaldo ya se declara en el PDF |
| Derogar la viñeta de la §14 rompe la matriz de trazabilidad | `python api/tests/test_matriz_trazabilidad.py --escribir` en el mismo commit |
| Dos agentes crean migraciones a la vez | Solo `T-7.14` crea la `0063` |
| `make soc-local` deja procesos que tiran suites ajenas | `pkill -f takab_api.incident; pkill -9 -f soc_local.py; fuser -v /tmp/takab-gpio-*.lock` antes de cada suite |
| Un token nuevo no llega a un vite que ya estaba arriba | `pkill -f vite; rm -rf web/node_modules/.vite/deps` y sondear `--tk-*` con `getComputedStyle` antes de medir |
| El push real exige un apply de terraform y credenciales que hoy no existen | `T-7.03` lleva el respaldo medido y declarado; la demo no depende de él |
| Un barrido estructural del marcado cuenta etiquetas dentro de comentarios | Enmascarar `/* */` y `//` antes de contar (mordió tres veces en el Bloque VII) |

---

## 7 · Lo que solo Mauricio puede dar

| Fase | Qué | Dónde queda registrado |
|---|---|---|
| F0 | Cuenta de servicio de Firebase en `local.auto.tfvars` + `google-services.json` en `mobile/` (ambos gitignored) + apply del módulo `push`; SSO fresco; Pixel por USB; decisión de encender el alcance por rol | `PENDIENTES §4.4`, `§2.5` |
| F1 | Sesión con el WR-1 y el Pixel; destinatarios propios en la cascada; `audio_siren_enabled` decidido | `PENDIENTES §3.7` |
| F2 | SSO; apply de las tres cosas IoT; nombres de las estaciones si quiere otros | `PENDIENTES §3.7` |
| F3 | Pixel; sismo a reproducir; `alert_hold_min_s` e `incident_review_ttl_s` | `D-33` |
| F4 | Razón social, domicilio, clasificación y firmante del membrete | `PENDIENTES §4.8` |
| F5 | Acceso al Pi para medir el coste del sismógrafo | — |
| F6 | Cuenta y clave de OpenRouter en Secrets Manager, tope mensual, modelo, cláusula de consentimiento | `PENDIENTES §2.13`, `§4.7` |
| F7 | Los dos ensayos con él delante y el veredicto de flujos | — |

---

## 8 · Plantillas de sesión — pegar tal cual

> Una fase por sesión larga o una ficha por sesión corta. Cada plantilla lleva la regla de la
> casa: **si un test de censo se pone rojo, no lo modifiques sin escribir antes por qué el test se
> equivoca; en la duda, gana el test.**

### Plantilla general (cualquier ficha)

```
Ejecuta <T-7.xx> de takab-docs/TASKS.md (Bloque VIII), con el diseño de
takab-docs/PLAN-PROTOTIPO-FUNCIONAL.md §4.

Antes de escribir código:
- Lee la ficha completa, su fila del §4 del plan y las decisiones D-30…D-33 que cite.
- Lee takab-docs/TRASPASO-SESION.md §0 y §2 (la nube va por detrás del repo; método de subagentes).
- graphify query "<lo que vas a tocar>" antes de leer ficheros.
- Enumera qué tests de censo pueden romperse y por qué; escribe los tests nuevos PRIMERO.

Reglas de la sesión:
- Nada de emuladores: el móvil se prueba en el Pixel 8 Pro real (pide que lo conecten y para hasta que esté).
- Ningún valor visual fuera de shared/design-tokens/tokens.json.
- Los simuladores jamás publican takab/events. La reproducción se rotula como reproducción.
- Captura antes y después de cada pantalla tocada; ejerce los criterios fuera de los tests.
- make lint && make test && make drift en verde; graphify update .; regenerar MATRIZ-REQUISITO-TEST.md.
- Rama + PR con los checks; commits de Mauricio, Conventional Commits, sin footers de IA.
- Al cerrar: [x] con «Cómo se cerró», memoria, y si la ficha ejecuta otra de otro bloque, márcala [x] en el mismo commit.
```

### F0 — pegar para abrir la fase

```
Ejecuta la Fase F0 (T-7.01 → T-7.06) de takab-docs/PLAN-PROTOTIPO-FUNCIONAL.md.

Primero, tres subagentes Explore en paralelo, con este contrato de salida por pieza y prohibido
proponer arreglos: PIEZA · VEREDICTO (VERDE|AMARILLO|ROJO) · EVIDENCIA (ruta:línea o comando+salida)
· EJERCIDO_FUERA_DE_TESTS (sí/no/cómo) · RAZON (una línea).
  - Agente nube: deploy/cloud/docker-compose.yml vs módulos ejecutables de api/src/takab_api;
    variables que Settings exige vs heredoc de deploy.sh; /api/health; alarmas; console_scope_enforced;
    proveedor de push; OpenRouter.
  - Agente edge: release activa en el Pi vs HEAD (deploy/edge/deploy.sh); /api/status: test_mode,
    command_enabled, audio_*; red 192.168.1.0/24.
  - Agente móvil: APK instalado en el Pixel vs HEAD; google-services.json; token de push registrado;
    flujos Maestro y su último acreditado.
Después, lote A (T-7.01 + T-7.02: deploy/, api/tests/test_compose_cubre_los_workers.py) en paralelo
con lote B (T-7.04: web/e2e/layout.spec.ts, panel_walk en el scratchpad). T-7.03 y T-7.06 los haces
tú al final porque despliegan. Escribe takab-docs/INFORME-CONFORMIDAD-DEMO.md con la evidencia.

Objetivo de la fase: el bloque «Goal F0» del §4 del plan devuelve 0. Córrelo en /loop (modo dinámico)
hasta que pase; si tras tres iteraciones un criterio sigue en rojo, para y resume el bloqueo.
```

### F1 — pegar para abrir la fase

```
Ejecuta la Fase F1 (T-7.07 → T-7.09) de takab-docs/PLAN-PROTOTIPO-FUNCIONAL.md. Sin subagentes:
es físico y secuencial.

1. Escribe deploy/demo/guion.sh (--preflight, --check) con tests de su parser, y
   takab-docs/runbooks/RUNBOOK-demo-cliente.md con los cuatro actos y la tabla Registro.
2. Antes de tocar el radio: guion.sh --preflight en verde. Si el modo prueba del WR-1 está armado o el
   modo demostración encendido, la demo no produce ni incidente ni push y nadie ve el error.
3. Con Mauricio: acto 2 (sensor movido a mano, relés quietos), acto 3 (pulso del WR-1: sirena,
   incidente sasmex, push, crisis en el Pixel con screenrecord), acto 4 (dictamen, táctico, firma,
   reporte). Captura por acto en el scratchpad; filtra los volcados del teléfono a rótulos de la app.
4. Limpieza: /api/reset, clasificar prueba, cierre por SQL hasta T-7.13.

Objetivo de la fase: el bloque «Goal F1» del §4 del plan, más el Registro relleno. /loop hasta verde.
```

### F2 — pegar para abrir la fase

```
Ejecuta la Fase F2 (T-7.10 → T-7.12) de takab-docs/PLAN-PROTOTIPO-FUNCIONAL.md.

Lote A (db/maintenance/, db/seeds/, demo/tests/, api/tests/incident/fixtures/) en paralelo con lote B
(edge/simulators/fleet.py, unidad systemd, infra/scripts/provision_gateway.sh). Bases de tests
takab_test_a y takab_test_b. Ficheros disjuntos.

Contra la nube, solo tú y en este orden: respaldo con huella → purga (conserva audit_log y
actuation_records) → make cloud-demo-red → aprovisionar tres cosas IoT → arrancar takab-fleet-sim.
Los simuladores publican latido y features; jamás takab/events. Los nombres de las estaciones son
ficticios y presentables, y ninguna usurpa una institución real. Nada de historial con fechas falsas.

Objetivo de la fase: el bloque «Goal F2» del §4 del plan devuelve 0. /loop hasta verde.
```

### F3 — pegar para abrir la fase

```
Ejecuta la Fase F3 (T-7.13 → T-7.20) de takab-docs/PLAN-PROTOTIPO-FUNCIONAL.md, en tres lotes de dos
agentes (takab_test_a / takab_test_b, ficheros disjuntos declarados en el brief):
  Lote 1: A = T-7.13 (api/src/takab_api/incident, tests/incident) ∥ B = T-7.14 (api/src/takab_api/replay,
          routers/demo_mode.py, migración 0063 — el ÚNICO agente que crea migraciones).
  Lote 2: A = T-7.15 (edge/simulators) ∥ B = T-7.16 + T-7.18 + parte web de T-7.19 (web/src/features/scene,
          console, styles; tokens nuevos --tk-dur-arrival y --tk-dur-alerta en shared/design-tokens).
  Lote 3: A = T-7.17 (api/src/takab_api/routers, web/src/features/triage y console) ∥ B = parte móvil
          de T-7.19 (mobile/src/features/alert/CrisisView.tsx, Pixel real).
Tú integras T-7.20 y escribes web/e2e/vida_del_sismo.spec.ts sobre make soc-local.

Invariantes: no tocar SCENE_PRECEDENCE (la revisión se deriva de alertKind); el banner de alerta sigue
legible desde el primer frame; toda animación nueva entra en el grupo animation: none del bloque
prefers-reduced-motion; nada cierra un incidente por cronómetro del cliente.

Objetivo de la fase: el bloque «Goal F3» del §4 del plan devuelve 0. /loop hasta verde.
```

### F4, F5, F6, F7 — pegar para abrir cada fase

```
Ejecuta la Fase <F4|F5|F6|F7> de takab-docs/PLAN-PROTOTIPO-FUNCIONAL.md con sus fichas, sus lotes y su
bloque «Goal» del §4. Reglas de la plantilla general. Particularidades:
  F4: T-7.21 primero (todo FPDF hereda de MembretePDF; tamaño Carta; positivo sobre blanco), T-7.22 después.
  F5: A = T-7.23 (edge; escribe la sección de la spec del panel ANTES del código; mide el coste en el Pi
      real y escríbelo) ∥ B = T-7.25 (api; respuestas grabadas, sin red en CI). T-7.24 solo, y su primer
      commit es la derogación de la viñeta [DIFERIDO · mini-ShakeMap] —esa y ninguna otra— con la matriz
      regenerada.
  F6: T-7.26 mide la latencia real del modelo antes de tocar el timeout; T-7.27 comprueba al arrancar que
      el modelo admite imágenes y cae al determinista si no. La prosa jamás toca el veredicto.
  F7: dos corridas de guion.sh --full con Mauricio delante; plan B escrito; paquete de capturas.
/loop hasta que el bloque «Goal» de la fase devuelva 0.
```

---

## 9 · Cómo se cierra una fase, y cómo se cierra el plan

Una fase está cerrada cuando **su bloque «Goal» devuelve 0 en una corrida limpia**, todas sus fichas
están en `[x]` con «Cómo se cerró», la cabecera de `TASKS.md` cuadra, la memoria tiene la nota de
la fase y `main` contiene el merge. El orden de las fases es de criticidad: **no se abre F3 con un
🔴 en el informe de conformidad**, y no se abre F7 sin F3 y F4.

El plan está cerrado cuando F7 tiene sus dos corridas en el Registro. Entonces se escribe aquí un
`## 10 · Cierre — cómo terminó`, como hizo el plan de la reforma visual: qué encontró la ejecución
que la planificación no vio, qué quedó fuera y de quién es, y la trampa que más veces mordió. Este
plan **no se reescribe**: es un documento de decisión, no una hoja de estado; el estado vivo de cada
ficha es su ficha.
