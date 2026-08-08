# Matriz requisito → test — TAKAB Ailert

> **Generado, no escrito a mano.** Lo produce `api/tests/test_matriz_trazabilidad.py` a partir de tres fuentes (`CLAUDE.md §2`, `BLUEPRINT §14`, `RUNBOOK-auditoria-cierre §10`) y de la resolución por AST de cada test citado. Para regenerarlo:
>
>     python api/tests/test_matriz_trazabilidad.py --escribir
>
> El `archivo:línea` es **derivado**: el ancla de cada cita es el NOMBRE del test y la línea se recalcula en cada corrida. Si un test citado desaparece o se renombra, la suite del `api` se pone en rojo y este documento deja de poder generarse.

## Cómo leer los veredictos

- **`CUBIERTO`** — hay al menos un test que (a) existe, (b) **no** puede saltarse, (c) ejercita el código en vez de sólo cruzar documentos y (d) corre en un job que bloquea el merge.
- **`PARCIAL`** — el requisito se parte en varias afirmaciones y sólo algunas están cubiertas. Las que no, salen listadas debajo de su tabla con lo que implican.
- **`SIN COBERTURA`** — ninguna afirmación tiene prueba que valga. **Éste es el contenido con valor del documento.** Una matriz sin huecos es una matriz que miente.

**Un test que se salta no es cobertura.** Es la lección de `T-2.63` (cinco tests de hardware saltándose en silencio con el job en verde) y de `T-2.58` (67 tests del panel saltados por falta de `node`). Aquí un `skipif` en un test citado degrada su fila automáticamente. Lo mismo vale para la matriz de Playwright de `web/e2e/`: es `workflow_dispatch` y `continue-on-error` **a propósito**, así que su verde informa pero no acredita.

La única excepción es el sello 🔒: un test que *puede* saltarse pero cuyo salto el workflow hace imposible con un paso propio y citado (el `node --version` que `T-2.58` añadió). Si ese paso desaparece del workflow, la suite se pone en rojo y la fila cae sola a `SIN COBERTURA`.

## Resumen

| Requisitos de software | Requisitos | Afirmaciones |
|---|---:|---:|
| `CUBIERTO` | 6 | 48 |
| `PARCIAL` | 8 | — |
| `SIN COBERTURA` | 3 | 18 |
| **Total** | **17** | **66** |

Y **10 gates físicos / de despliegue** que ningún test de software puede cerrar: piden hardware en sitio o una cuenta AWS. Se listan al final para que el documento de entrega no dé la impresión de que no queda nada por acreditar presencialmente.

## Reglas de oro (`CLAUDE.md §2`)

### RO-1 · El camino crítico de activación es 100% determinista.

**Fuente:** `CLAUDE.md §2` · **Veredicto:** `PARCIAL`

> El reflejo SASMEX→sirena se prueba con la nube explícitamente caída, no con la nube ausente por casualidad. La afirmación `d` es la que no se sostiene: el proceso mínimo que estas pruebas ejercitan **no es** el que corre hoy en el gabinete (ver `RO-4.f`).

| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |
|---|---|---|---|---|
| RO-1.a | Con la nube caída, el contacto SASMEX energiza la sirena. | `CUBIERTO` | `edge/tests/test_supervisor.py:192`<br>`test_sasmex_actuates_with_cloud_offline`<br>`edge/tests/test_e2e.py:231`<br>`test_sasmex_reflex_and_sequence_cloud_off` | `cloud.online is False` y aun así el relé de sirena queda energizado; `cloud.sent == 0`.<br>E2E con la nube apagada: `siren_sounding` inmediato y 1 evento encolado (no enviado). |
| RO-1.b | Ningún estado de la nube (config viva, ventana de mantenimiento) desarma ni calla el reflejo. | `CUBIERTO` | `edge/tests/test_supervisor.py:206`<br>`test_la_config_viva_de_la_nube_jamas_se_cablea_al_reflejo`<br>`edge/tests/test_supervisor.py:358`<br>`test_una_ventana_de_mantenimiento_DE_LA_NUBE_no_calla_la_sirena` | La config publicada desde la nube no llega al camino del reflejo.<br>Una ventana de mantenimiento remota no silencia la sirena. |
| RO-1.c | El proceso mínimo `takab-gpio` —el que toca sirena, gas y puertas— no carga ninguna dependencia fuera de una lista blanca cerrada (IA incluida). | `CUBIERTO` | `edge/tests/test_gpio_process.py:464`<br>`test_el_proceso_minimo_no_carga_ninguna_dependencia_no_autorizada` | Lista blanca *fail-closed* sobre el grafo de importación real, en tres montajes de arranque. |
| RO-1.d | El proceso que corre en el gabinete desplegado ES ese proceso mínimo. | `SIN COBERTURA`<br><sub>sin test</sub> | — | — |
| RO-1.e | La latencia contacto WR-1 → los cinco relés se mide y cabe en el presupuesto (<100 ms). | `CUBIERTO` | `edge/tests/test_e2e.py:100`<br>`test_latencia_contacto_wr1_a_los_cinco_reles_bajo_presupuesto` | Mide contacto→nivel físico de los 5 pines y exige <0.100 s, con guarda anti-teatro de que el tramo medido contiene el reflejo. |
| RO-1.f | La detección instrumental de una sola estación es SOLO AVISO: no mueve relés (política ratificada en T-2.32). | `CUBIERTO` | `edge/tests/test_e2e.py:32`<br>`test_instrumental_quake_visual_only_no_actuation` | Sismo simulado completo: el tier sube y los 5 relés siguen en `activated is False`. |
| RO-1.g | El opt-in por sitio `instrumental_actuation` restaura la actuación autónoma. | `CUBIERTO` | `edge/tests/test_e2e.py:52`<br>`test_instrumental_actuation_optin_restores_sequence` | Mismo sismo con el opt-in activo: los 5 relés vuelven a actuar. |
| RO-1.h | La IA asesora y jamás emite un veredicto: la capa narrativa no puede invocar al motor de reglas ni colocar un dictamen. | `CUBIERTO` | `api/tests/narrative/test_contract.py:34`<br>`test_la_capa_narrativa_no_puede_invocar_al_motor_de_reglas`<br>`api/tests/narrative/test_contract.py:57`<br>`test_el_veredicto_del_pdf_no_depende_de_la_prosa` | Escaneo AST de `narrative/**`: no importa `dictamen.rules|service`.<br>El veredicto del PDF es el mismo con y sin prosa generada. |

- **`SIN COBERTURA` · RO-1.d** (sin test) — Nada lo comprueba, y el valor por defecto va en contra: `edge/takab_edge/config/settings.py` declara `gpio_owner = "edge"` por defecto, así que salvo que `/etc/takab/edge.env` diga `TAKAB_EDGE_GPIO_OWNER=gpio` quien abre los pines es el supervisor de 16 módulos (`EdgeSupervisor`, vía `edge_owns_pins`). Ese archivo no está en el repo y ningún test lee su contenido. **Consecuencia: `RO-1.c` acredita un proceso que puede no ser el que sostiene la sirena.** Mismo hueco que `RO-4.f`.

### RO-2 · El edge opera sin nube.

**Fuente:** `CLAUDE.md §2` · **Veredicto:** `CUBIERTO`

| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |
|---|---|---|---|---|
| RO-2.a | Sin nube, el gabinete sigue detectando y accionando. | `CUBIERTO` | `edge/tests/test_supervisor.py:192`<br>`test_sasmex_actuates_with_cloud_offline` | Nube caída: tier + sirena energizada + 5 acks encolados localmente. |
| RO-2.b | Dos horas sin enlace y al reconectar no se pierde ni se duplica un evento. | `CUBIERTO` | `edge/tests/test_cloud.py:65`<br>`test_offline_two_hours_then_reconnect_zero_loss_zero_dup` | Los eventos encolados se drenan en orden y sin `event_id` repetido. |
| RO-2.c | La cola durable sobrevive al reinicio del proceso. | `CUBIERTO` | `edge/tests/test_cloud.py:81`<br>`test_durable_queue_survives_restart` | Un `CloudConnector` nuevo sobre el mismo spool recupera el atraso. |
| RO-2.d | La evidencia miniSEED encolada offline se sube al reconectar. | `CUBIERTO` | `edge/tests/test_backfill.py:226`<br>`test_offline_event_evidence_uploads_on_reconnect` | Cero PUT mientras está offline; al volver, sube con su sha256. |

### RO-3 · Idempotencia en todo dato que cruza el edge→nube.

**Fuente:** `CLAUDE.md §2` · **Veredicto:** `CUBIERTO`

| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |
|---|---|---|---|---|
| RO-3.a | El mismo `event_id` recorrido dos veces por el camino completo (SQS→consumidor→DB) produce un solo incidente. | `CUBIERTO` | `api/tests/test_ingest_e2e.py:277`<br>`test_local_event_escalates_into_single_incident` | Dos mensajes con el mismo `event_id` ⇒ una fila en `incidents`, DLQ vacía. |
| RO-3.b | La idempotencia está en la DB, no sólo en el código de aplicación. | `CUBIERTO` | `api/tests/test_idempotency.py:34`<br>`test_incident_event_uuid_idempotent` | `ON CONFLICT (event_uuid) DO NOTHING`: rowcount 1 y luego 0. |
| RO-3.c | La superficie de escritura HTTP tolera el reintento del cliente offline. | `CUBIERTO` | `api/tests/api/test_mobile_core.py:522`<br>`test_checkin_replay_offline_es_idempotente` | Reenviar el mismo `checkin_id` devuelve la fila idéntica; otro portador con el mismo id recibe 409. |
| RO-3.d | El nonce de intención emitido por el servidor es de un solo uso. | `CUBIERTO` | `api/tests/api/test_command_intent.py:163`<br>`test_intencion_firmada_feliz_y_replay_rechazado` | Primera llamada 201; el replay exacto del intento firmado, 409. |
| RO-3.e | El anti-replay de configuración firmada sobrevive a un reinicio del edge. | `CUBIERTO` | `edge/tests/test_config.py:240`<br>`test_replay_rejected_across_restart` | Un `ConfigStore` nuevo sobre la misma caché sigue rechazando la versión ya vista. |

### RO-4 · El proceso GPIO/actuadores es mínimo y auditable.

**Fuente:** `CLAUDE.md §2` · **Veredicto:** `PARCIAL`

> «Mínimo» está bien cubierto; **«auditable» no lo está en el edge**, y la pregunta de qué proceso corre de verdad en el gabinete no la responde ningún test.

| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |
|---|---|---|---|---|
| RO-4.a | El proceso GPIO no carga dependencias pesadas (NumPy/SciPy/ObsPy). | `CUBIERTO` | `edge/tests/test_gpio_process.py:545`<br>`test_gpio_process_does_not_import_heavy_deps`<br>`edge/tests/test_gpio_process.py:464`<br>`test_el_proceso_minimo_no_carga_ninguna_dependencia_no_autorizada` | Ninguna de numpy/obspy/scipy/pandas/matplotlib en `sys.modules` del hijo.<br>Y la versión *fail-closed*: lista blanca en vez de lista negra. |
| RO-4.b | Arranca en menos de un segundo. | `CUBIERTO` | `edge/tests/test_gpio_process.py:561`<br>`test_gpio_process_starts_under_one_second` | Mide de la primera importación al retorno de `run_gpio_process`. |
| RO-4.c | La propiedad de los pines es exclusiva: un segundo dueño no toca un pin. | `CUBIERTO` | `edge/tests/test_gpio_ownership.py:160`<br>`test_un_segundo_dueno_no_toca_un_solo_pin_y_lo_grita`<br>`edge/tests/test_gpio_traspaso.py:323`<br>`test_los_dos_servicios_a_la_vez_no_mueven_un_solo_pin` | El segundo `GpioController` muere antes de abrir un pin y grita el PID del dueño.<br>Seis rondas de crash-loop cruzado: cero transiciones eléctricas de más en gas y retenedor. |
| RO-4.d | Un arranque fallido deja los relés en seguro ANTES de soltar el cerrojo. | `CUBIERTO` | `edge/tests/test_gpio_ownership.py:448`<br>`test_un_arranque_fallido_deja_los_reles_EN_SEGURO_antes_de_soltar_el_cerrojo` | Fotografía el nivel y la función de los 5 pines en el instante exacto de liberar el cerrojo. |
| RO-4.e | «Auditable»: toda acción de actuador queda registrada en el edge con quién la ordenó y cuándo. | `SIN COBERTURA`<br><sub>sin test</sub> | — | — |
| RO-4.f | El gabinete desplegado corre el proceso mínimo como dueño de los pines. | `SIN COBERTURA`<br><sub>sin test</sub> | — | — |

- **`SIN COBERTURA` · RO-4.e** (sin test) — No hay bitácora de actuación en el gabinete. `ActuatorAck` (`edge/takab_edge/contracts.py`) lleva canal, acción, `event_id`, éxito y latencia — **no lleva actor**, y `GpioController.set_relay` no emite ni una línea de registro. El único `audit_log` vive en la nube (`api/src/takab_api/audit.py`), o sea que **una actuación ejecutada con el enlace caído —el caso para el que existe el gabinete— no deja rastro auditable en ninguna parte.** Es la mitad no construida de la regla 4.
- **`SIN COBERTURA` · RO-4.f** (sin test) — Ningún test lee qué unidad queda habilitada ni qué dice `/etc/takab/edge.env`, y `deploy/edge/deploy.sh` no ejecuta ningún `systemctl enable`. Los tests de despliegue van a propósito en la dirección contraria: `edge/tests/test_deploy_sh.py::test_la_verificacion_no_esta_anclada_al_nombre_takab_edge` exige que la comprobación sea agnóstica del nombre. Con `gpio_owner = "edge"` por defecto, **el estado de fábrica es el que la regla 4 prohíbe** y sólo un archivo fuera del repo lo corrige. Es la otra cara de `RO-1.d`.

### RO-5 · Multi-tenant por diseño:

**Fuente:** `CLAUDE.md §2` · **Veredicto:** `PARCIAL`

| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |
|---|---|---|---|---|
| RO-5.a | Toda tabla de negocio lleva `tenant_id`, comprobado DERIVANDO la lista del catálogo y no de una lista escrita a mano. | `SIN COBERTURA`<br><sub>sin test</sub> | — | — |
| RO-5.b | Toda tabla con `tenant_id` tiene RLS activa y con políticas, derivado del catálogo de Postgres. | `CUBIERTO` | `api/tests/ops/test_restore_check.py:83`<br>`test_la_base_migrada_pasa_entera` | `verify()` recorre `pg_catalog` y falla cualquier tabla con `tenant_id` sin `relrowsecurity`, y cualquier tabla con RLS y cero políticas. |
| RO-5.c | Una lectura cruzada entre tenants no devuelve nada. | `CUBIERTO` | `api/tests/test_rls_isolation.py:36`<br>`test_app_cannot_read_other_tenant` | Como `takab_app` con `app.tenant_id=B`, contar filas de A da 0. |
| RO-5.d | Una escritura cruzada entre tenants es rechazada por la DB. | `CUBIERTO` | `api/tests/test_rls_isolation.py:51`<br>`test_app_cannot_write_other_tenant` | El `INSERT` etiquetado con otro tenant levanta `InsufficientPrivilege` (WITH CHECK). |
| RO-5.e | La API rechaza el cruce con un JWT real, no sólo la DB. | `CUBIERTO` | `api/tests/auth/test_guc_propagation.py:43`<br>`test_gucs_propagate_and_no_cross_tenant_read` | Petición HTTP real: el token de A ve el incidente de A y no el de B, y simétrico. |
| RO-5.f | La función de alcance, invocada con el filtro puesto, deja cero sitios ante un claim vacío. | `CUBIERTO` | `api/tests/auth/test_console_scope.py:85`<br>`test_fase_B_un_claim_vacio_significa_cero_sitios` | Unidad pura con `enforced=True`: claim vacío ⇒ cero sitios. |
| RO-5.g | El servidor filtra de verdad por sitio en el despliegue real. | `SIN COBERTURA`<br><sub>sin test</sub> | — | — |

- **`SIN COBERTURA` · RO-5.a** (sin test) — El único cruce contra el catálogo corre en la dirección opuesta —las tablas que YA tienen `tenant_id` deben tener RLS (`RO-5.b`)—, así que **una tabla de negocio nueva que nazca sin `tenant_id` no es vista por nadie**: no tiene la columna, luego no entra en el censo, luego no se le exige RLS. El punto ciego se cierra solo. La lista más parecida a un censo, `api/tests/test_timescale_jobs.py::test_business_tables_have_force`, es una tupla de cuatro nombres escrita a mano.
- **`SIN COBERTURA` · RO-5.g** (sin test) — La conducta impuesta sólo se prueba como unidad pura pasando `enforced=True` a mano; **ningún test recorre el HTTP con el filtro puesto**. En producción la perilla está en `False` (`api/src/takab_api/settings.py`) y es la única brecha multi-tenant viva, la que `T-2.89` existe para cerrar. Y hay algo peor que el hueco: dos tests HTTP fijan la conducta NO impuesta —`api/tests/api/test_console_scope.py::test_fase_A_sin_claim_la_consola_NO_se_queda_en_blanco` y `::test_me_dice_si_el_servidor_esta_filtrando_de_verdad`—, así que **encender la perilla pondrá la suite en rojo**. Quien ejecute `T-2.89` tiene que contar con eso.

### RO-6 · Nada de secretos hardcodeados.

**Fuente:** `CLAUDE.md §2` · **Veredicto:** `PARCIAL`

| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |
|---|---|---|---|---|
| RO-6.a | Ningún secreto vive en el árbol: alguien barre el repo buscándolos. | `SIN COBERTURA`<br><sub>sin test</sub> | — | — |
| RO-6.b | Sin secreto configurado, la superficie que lo necesita se cierra en vez de seguir sirviendo. | `CUBIERTO` | `api/tests/api/test_command_intent.py:324`<br>`test_sin_secreto_configurado_es_503_fail_closed`<br>`api/tests/commands/test_keys.py:93`<br>`test_build_key_provider_precedence_and_fail_closed` | Borrado `TAKAB_API_COMMAND_INTENT_SECRET`, los endpoints tácticos devuelven 503.<br>Precedencia env → Secrets Manager, y sin ninguno `key_for()` devuelve `None` (cierra, no inventa). |
| RO-6.c | En producción, un secreto ausente hace ruido en el arranque en vez de caer al valor por defecto de desarrollo. | `SIN COBERTURA`<br><sub>sin test</sub> | — | — |

- **`SIN COBERTURA` · RO-6.a** (sin test) — **No existe barrido de secretos en ninguna parte.** Ni test, ni paso de CI, ni `.pre-commit-config.yaml` (no hay), ni `gitleaks`/`trufflehog`/`detect-secrets` en todo el repo. La regla 6 se sostiene hoy sólo sobre la disciplina de quien escribe el diff — que es exactamente la clase de garantía que este proyecto no acepta en ninguna otra regla.
- **`SIN COBERTURA` · RO-6.c** (sin test) — `Settings` no tiene ningún validador de entorno: sus valores por defecto **son credenciales de desarrollo**, así que una variable que falte en producción no truena — se resuelve silenciosamente al default de dev. Lo cubierto en `RO-6.b` es *fail-closed por endpoint* para dos secretos concretos; no hay guarda de arranque para el resto.

### RO-7 · Estados de UI obligatorios:

**Fuente:** `CLAUDE.md §2` · **Veredicto:** `PARCIAL`

> Cobertura por muestreo, no sistemática: cada superficie tiene su prueba ejemplar, y **no hay nada que obligue a la número 28**.

| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |
|---|---|---|---|---|
| RO-7.a | Un censo DERIVADO obliga a que todo componente que pinte dato de servidor declare sus cuatro estados. | `SIN COBERTURA`<br><sub>sólo tests que no corren (suite no bloqueante (e2e.yml))</sub> | `web/e2e/screens.spec.ts:601`<br>`declara los estados obligatorios: nunca una caja en blanco`<br>⚠️ *no corre: suite no bloqueante (e2e.yml)* | Por pantalla, exige ≥1 `[data-state]` con valor del conjunto permitido; nunca exige que exista `stale`. |
| RO-7.b | La consola SOC rotula el dato viejo en vez de pintarlo como fresco. | `CUBIERTO` | `web/src/features/console/DetailPanel.test.tsx:276`<br>`M-6: flota vieja se rotula stale, no se pinta como fresca` | Flota de hace 10 min ⇒ la tarjeta dice DATOS RETENIDOS. |
| RO-7.c | El panel del gabinete no pinta una medición de hace dos horas como viva. | `CUBIERTO` | `edge/tests/test_local_api_panel.py:691`<br>`test_feature_vieja_no_se_pinta_como_medicion_viva`<br>🔒 *lleva `skipif`, pero el CI lo impide con `run: node --version`* | Con `age_s=7200` las barras dicen S/D y la brújula estampa SIN SEÑAL DEL SENSOR. |
| RO-7.d | La app móvil sirve la copia vieja con su edad, nunca como dato fresco. | `CUBIERTO` | `mobile/src/ui/StateFrame.test.tsx:42`<br>`stale: contenido VIEJO con banner DATOS RETENIDOS + edad honesta` | El contenido viejo se pinta bajo `state-stale` con la edad real. |
| RO-7.e | La tira de KPI de `/fleet` dice S/D cuando no hay dato, jamás cero. | `CUBIERTO` | `web/src/features/fleet/FleetPage.test.tsx:279`<br>`sin dato (%s) los KPI dicen S/D, no CERO` | Con la consulta en error 503 o cargando, los cuatro KPI dicen S/D. |

- **`SIN COBERTURA` · RO-7.a** (sólo tests que no corren (suite no bloqueante (e2e.yml))) — No existe censo derivado. La guarda real es el ayudante opt-in `web/src/test-utils/states.ts::expectFourStates()`, que cada test tiene que acordarse de llamar. Medido el 2026-08-08: **27** componentes de `web/src` usan `StateFrame` y sólo **14** tienen la prueba de los cuatro estados; y hay **al menos 12 componentes que pintan dato de servidor FUERA de `StateFrame`** (`KpiStrip`, `MapPanel`, `Topbar`, `SiteCard`, `UpsGauge`, `SyncBadge`…), cada uno con su propio `S/D` a mano. El bug de `T-2.59` fue exactamente eso. La única cita posible vive en la matriz de Playwright, que **no bloquea un merge** — y aun así nunca exige un estado `stale`.

### RO-8 · Control de actuadores por nube = superficie más sensible.

**Fuente:** `CLAUDE.md §2` · **Veredicto:** `PARCIAL`

> Cinco controles en una sola frase, y hay que puntuarlos por separado: firma, MFA, rate-limit, nonce y ack. **El MFA es el único de los cinco sin una sola línea de prueba en ninguna capa.**

| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |
|---|---|---|---|---|
| RO-8.a | Una firma inválida ni ejecuta ni ackea. | `CUBIERTO` | `edge/tests/test_dispatch.py:230`<br>`test_bad_signature_neither_executes_nor_acks` | Payload manipulado sin refirmar: ni ack ni actuador. |
| RO-8.b | La nube firma con la clave del gabinete concreto, no con una compartida. | `CUBIERTO` | `api/tests/api/test_commands_router.py:236`<br>`test_each_gateway_signs_with_its_own_key` | La firma queda atada a la clave del gateway destinatario. |
| RO-8.c | El endpoint de comando exige MFA. | `SIN COBERTURA`<br><sub>sin test</sub> | — | — |
| RO-8.d | Hay rate-limit por usuario y sitio. | `CUBIERTO` | `api/tests/api/test_commands_router.py:154`<br>`test_rate_limit_user_site_429` | Con el límite en 2/min, el tercer POST es 429 y no se publica. |
| RO-8.e | Hay rate-limit por sitio, independiente del usuario. | `SIN COBERTURA`<br><sub>sin test</sub> | — | — |
| RO-8.f | Un nonce ya visto se rechaza, en el edge y en la nube. | `CUBIERTO` | `edge/tests/test_dispatch.py:240`<br>`test_replayed_nonce_rejected_silently`<br>`api/tests/api/test_command_intent.py:163`<br>`test_intencion_firmada_feliz_y_replay_rechazado` | El comando byte-idéntico reenviado produce un solo ack.<br>En la nube, el replay exacto del intento es 409. |
| RO-8.g | El rechazo por replay queda AUDITADO. | `SIN COBERTURA`<br><sub>sin test</sub> | — | — |
| RO-8.h | Hay ack de ejecución y un comando sin ack nunca se reporta como ejecutado. | `CUBIERTO` | `api/tests/commands/test_sync.py:548`<br>`test_expires_stale_pending_commands`<br>`api/tests/commands/test_ack_ingest.py:128`<br>`test_late_ack_does_not_revive_expired` | Pasado el TTL, `pending` pasa a `expired` con «sin ack dentro del TTL».<br>Un ack que llega tarde no resucita el comando vencido. |
| RO-8.i | Un comando viejo con firma válida se rechaza (TTL de la firma). | `CUBIERTO` | `edge/tests/test_dispatch.py:248`<br>`test_expired_command_rejected_silently` | Firmado con `ts = ahora-120 s` y TTL de 30 s: cero acks. |
| RO-8.j | La emisión de un comando queda auditada. | `CUBIERTO` | `api/tests/api/test_commands_router.py:116`<br>`test_issue_command_signs_publishes_and_persists` | El verbo `command_issued` aparece en `audit_log` del tenant. |
| RO-8.k | Un comando DENEGADO (403/409/429/503) queda auditado. | `SIN COBERTURA`<br><sub>sin test</sub> | — | — |

- **`SIN COBERTURA` · RO-8.c** (sin test) — **Cero cobertura en cualquier capa.** No hay comprobación de claim `acr`/`amr`/`auth_time` en la petición: el docstring de `api/src/takab_api/routers/commands.py` documenta el control como *delegado* al pool de Cognito (`mfa_configuration = "ON"`, `infra/terraform/modules/identity/main.tf`). Eso es una **suposición, no un control**: el módulo `identity` es el único de los cuatro sin `.tftest.hcl`, así que una deriva de la configuración del pool a `OPTIONAL` no la detecta nadie, y un token emitido por cualquier camino que no pase por TOTP entra sin que la aplicación lo note. Es el hueco más grave de la matriz: la regla de oro 8 dice «sin excepción» sobre la superficie que abre válvulas de gas.
- **`SIN COBERTURA` · RO-8.e** (sin test) — `command_rate_site_per_min` está implementado (`api/src/takab_api/commands/service.py`) y **no lo prueba nadie**: sólo se prueba el límite usuario+sitio. Dos operadores coordinados agotan el presupuesto del sitio sin que ningún test lo vea.
- **`SIN COBERTURA` · RO-8.g** (sin test) — Se rechaza pero no se apunta. En el edge el camino de replay sólo emite `log.warning` (no hay sumidero de auditoría); en la nube el 409 sale sin llamada a auditoría y el test comprueba únicamente el código de estado. **Un atacante que sondee con comandos repetidos es invisible en el `audit_log`** — que es donde se investigaría el incidente. `api/tests/commands/test_ack_ingest.py::test_wrong_gateway_is_rejected_with_audit` sí audita, pero un *ack* falsificado, no un replay de comando: no cuenta.
- **`SIN COBERTURA` · RO-8.k** (sin test) — Sólo se audita el camino feliz. Ningún test cubre la auditoría de una denegación, y para el 429 y el 409 no hay ni siquiera llamada a auditoría en el código. Junto con `RO-8.g`: **la bitácora de la superficie más sensible del sistema registra lo que salió bien y calla lo que se intentó.**

### RO-9 · Sin streaming de forma de onda cruda.

**Fuente:** `CLAUDE.md §2` · **Veredicto:** `SIN COBERTURA`

> Es la regla de oro con la brecha más limpia entre lo declarado y lo verificado: está escrita en tres documentos, clasificada como invariante permanente en `BLUEPRINT §14`… y **no la sostiene ni un test**.

| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |
|---|---|---|---|---|
| RO-9.a | El enlace edge→nube nunca publica forma de onda cruda en continuo. | `SIN COBERTURA`<br><sub>sin test</sub> | — | — |
| RO-9.b | El miniSEED crudo sube a S3 SÓLO en eventos confirmados. | `SIN COBERTURA`<br><sub>sin test</sub> | — | — |

- **`SIN COBERTURA` · RO-9.a** (sin test) — **Nada lo impide ni lo detecta.** No hay assert sobre un conjunto CERRADO de topics publicados, ninguno sobre volumen o tasa, y ninguno que diga que un `WaveformPacket` jamás se entrega a `CloudConnector.publish`. Añadir hoy un publicador continuo de crudo **no rompería un solo test**. Lo más parecido que existe protege la superficie del cliente (`web/src/features/triage/model.test.ts`, `mobile/.../panel.test.tsx`: no se ofrece pedir el crudo), no el enlace. Como la regla es una restricción de costo y de red, su violación se descubriría en la factura.
- **`SIN COBERTURA` · RO-9.b** (sin test) — La compuerta existe en el código (`EdgeSupervisor` sólo encola evidencia con tier `RESTRICTED`/`EVACUATE_OR_HOLD`) y **la dirección «sólo» no la prueba nadie**: todos los tests de evidencia recorren el camino del evento confirmado hacia adelante y comprueban que funciona. Ninguno comprueba que un tier `normal` produce cero PUT. Bajar el umbral por accidente convierte esto en el streaming continuo que la regla 9 prohíbe, sin rojo.

### RO-10 · Logging por evento, no por intervalo.

**Fuente:** `CLAUDE.md §2` · **Veredicto:** `PARCIAL`

| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |
|---|---|---|---|---|
| RO-10.a | El motor de reglas registra una vez por transición de tier, no por evaluación. | `CUBIERTO` | `edge/tests/test_rules.py:205`<br>`test_tier_transition_logged_once_per_change` | Tres evaluaciones con una repetida producen exactamente 2 registros. |
| RO-10.b | La salud registra por cambio discreto, no por deriva continua. | `CUBIERTO` | `edge/tests/test_health.py:187`<br>`test_transition_logged_only_on_discrete_change` | La deriva de 25→30 °C bajo umbral no emite; los dos cambios de estado sí. |
| RO-10.c | La salud del dispositivo llega por latido periódico y etiquetado como tal. | `CUBIERTO` | `edge/tests/test_health.py:200`<br>`test_heartbeat_thread_emits_periodic_snapshots`<br>`api/tests/test_ingest_handlers.py:440`<br>`test_health_default_reason_is_heartbeat` | Con `heartbeat_s=0.05` salen ≥3 instantáneas por temporizador.<br>En la nube, una salud sin motivo se persiste como `heartbeat`. |
| RO-10.d | En la nube, `rule_evaluations` no gana filas en estado estable. | `SIN COBERTURA`<br><sub>sin test</sub> | — | — |

- **`SIN COBERTURA` · RO-10.d** (sin test) — La propiedad se prueba en el edge al nivel del registro, nunca al nivel de la tabla. De hecho **no hay escritor de `rule_evaluations` en `api/src`** —sólo lectores en `queries/mobile.py` y `ws/hub.py`—, así que hoy la regla se cumple por ausencia de código, no por una guarda. El día que se escriba el ingestor, nada avisará si escribe por intervalo.

### RO-11 · Compliance como restricción dura.

**Fuente:** `CLAUDE.md §2` · **Veredicto:** `CUBIERTO`

| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |
|---|---|---|---|---|
| RO-11.a | Una regla de retención que borre filas de una tabla de compliance se rechaza, y se rechaza ANTES de borrar nada. | `CUBIERTO` | `api/tests/test_privacy_retention.py:299`<br>`test_una_regla_que_borra_filas_de_una_tabla_protegida_es_rechazada`<br>`api/tests/test_privacy_retention.py:313`<br>`test_el_rechazo_ocurre_en_el_preflight_antes_de_cualquier_conteo` | Parametrizado sobre las cinco tablas protegidas: `RetentionUnsafe` y conteo idéntico antes/después.<br>El plan entero aborta en el preflight. |
| RO-11.b | Ni saltándose el guard puede el job borrar evidencia: lo impide la propia base. | `CUBIERTO` | `api/tests/test_privacy_retention.py:324`<br>`test_ni_saltandose_el_guard_puede_el_job_borrar_evidencia` | `DELETE` crudo en la sesión del job ⇒ 42501 o P0001 (trigger append-only). |
| RO-11.c | ARCO anonimiza al titular sin perder una sola fila. | `CUBIERTO` | `api/tests/test_privacy_erasure.py:367`<br>`test_arco_anonimiza_al_titular_sin_perder_una_sola_fila` | Censo de filas sobre 9 tablas idéntico antes y después. |
| RO-11.d | El hecho sobrevive a la anonimización: el check-in sigue contando. | `CUBIERTO` | `api/tests/test_privacy_erasure.py:409`<br>`test_el_checkin_anonimizado_sigue_contando_para_el_incidente` | El conteo del incidente no cambia; la geometría precisa sí se anula. |

## Invariantes y diferido (`BLUEPRINT §14`)

### INV-T-MINUS · **T-MINUS countdown** — WR-1 es boolean; no hay dato de ETA.

**Fuente:** `BLUEPRINT §14` · **Veredicto:** `CUBIERTO`

> Sólo el test móvil escanea el árbol completo; el resto son asertos sobre elementos concretos. Un componente nuevo con cuenta regresiva pasaría todo menos el móvil.

| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |
|---|---|---|---|---|
| INV-T-MINUS.a | Ninguna superficie muestra una cuenta regresiva. | `CUBIERTO` | `mobile/src/features/alert/CrisisView.test.tsx:16`<br>`sasmex: SIN magnitud, SIN ETA, SIN cuenta regresiva (test que FALLA si aparecen)`<br>`edge/tests/test_local_api.py:564`<br>`test_index_has_no_external_resources` | Serializa el árbol renderizado entero y exige que no case `/T-[0-9]/`; el cronómetro visible es ascendente.<br>El HTML del panel no contiene `T-MINUS` ni `countdown`. |

### INV-magnitud preliminar · **Magnitud preliminar** en UI — WR-1 no provee magnitud.

**Fuente:** `BLUEPRINT §14` · **Veredicto:** `CUBIERTO`

| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |
|---|---|---|---|---|
| INV-magnitud.a | Ninguna superficie muestra una magnitud preliminar; el banner MVP dice PROTÉJASE y nada más. | `CUBIERTO` | `web/src/features/console/AlertBanner.test.tsx:27`<br>`banner MVP: PROTÉJASE + sitio + EVENT_ID + PGA MAX; sin magnitud ni T-MINUS`<br>`mobile/src/features/alert/CrisisView.test.tsx:16`<br>`sasmex: SIN magnitud, SIN ETA, SIN cuenta regresiva (test que FALLA si aparecen)` | El banner dice exactamente «ALERTA SÍSMICA · PROTÉJASE» y no case `/M\s*\d\.\d/` ni `T-MINUS`.<br>Mismo escaneo de árbol completo contra `/magnitud/i`. |

### INV-streaming crudo continuo · **Streaming continuo de forma de onda cruda** a la nube (P6) — regla de oro 9.

**Fuente:** `BLUEPRINT §14` · **Veredicto:** `SIN COBERTURA`

> Es la regla de oro 9 vista desde el blueprint. Su estado es el de `RO-9`.

| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |
|---|---|---|---|---|
| INV-streaming.a | No se sube forma de onda cruda en continuo a la nube. | `SIN COBERTURA`<br><sub>sin test</sub> | — | — |

- **`SIN COBERTURA` · INV-streaming.a** (sin test) — Igual que `RO-9.a`: la prohibición está declarada en tres documentos y **no la sostiene ningún test**. Que sea `[INVARIANTE]` —una tarea futura que lo proponga «se rechaza sin discusión»— hace la ausencia más llamativa, no menos: es la única viñeta de `§14` cuya violación sería silenciosa en el CI.

### INV-IA en la ruta de disparo · **IA en la ruta determinista de seguridad** (P4) — regla de oro 1.

**Fuente:** `BLUEPRINT §14` · **Veredicto:** `PARCIAL`

| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |
|---|---|---|---|---|
| INV-IA.a | El proceso que dispara actuadores no puede cargar una dependencia de IA. | `CUBIERTO` | `edge/tests/test_gpio_process.py:464`<br>`test_el_proceso_minimo_no_carga_ninguna_dependencia_no_autorizada` | Lista blanca *fail-closed* sobre el grafo real de importación del proceso de la sirena. |
| INV-IA.b | El motor de decisión de tier (`edge/takab_edge/rules/`) tampoco puede. | `SIN COBERTURA`<br><sub>sin test</sub> | — | — |

- **`SIN COBERTURA` · INV-IA.b** (sin test) — La guarda de importación existe sólo para el proceso `gpio`. `rules/` —el código que decide el tier y, con el opt-in de `RO-1.g`, dispara— no tiene lista blanca equivalente. Es un hueco de alcance, no de intención: el mecanismo ya está escrito y le falta el segundo objetivo.

### DIF-mini-ShakeMap · **Microservicio "mini-ShakeMap"** (scipy/pykrige, PostGIS, MapLibre) — fase futura; **es la única viñeta que una tarea puede derogar**, y la tarea que lo haría es `T-3.09`.

**Fuente:** `BLUEPRINT §14` · **Veredicto:** `CUBIERTO`

> Único DIFERIDO de `§14`: no es una prohibición permanente sino trabajo aplazado a `T-3.09`. Se lista para que el documento de entrega pueda decir qué NO hace el sistema.

| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |
|---|---|---|---|---|
| DIF-shakemap.a | La consola no promete una escala de intensidad que no existe. | `CUBIERTO` | `web/src/features/console/MapPanel.test.tsx:358`<br>`NO pinta bandas de intensidad: ni capas MMI ni una leyenda que prometa una escala inexistente` | Ninguna capa de MapLibre empieza por `mmi` ni hay leyenda «INTENSIDAD MMI». |

### INV-Shake OS · **Modificar el Shake OS** — el RS4D es solo sensor (P3).

**Fuente:** `BLUEPRINT §14` · **Veredicto:** `SIN COBERTURA`

| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |
|---|---|---|---|---|
| INV-shakeos.a | No se despliega nada al Shake ni se asume que corra código nuestro: la relación es leer SeedLink y nada más. | `SIN COBERTURA`<br><sub>sin test</sub> | — | — |

- **`SIN COBERTURA` · INV-shakeos.a** (sin test) — Cero enforcement ejecutable. «No se toca el Shake OS» aparece en cinco documentos y en ningún test: nada comprueba que el despliegue no escriba en el Shake ni que el edge sólo hable con él por SeedLink. El riesgo es de garantía con el proveedor, y el aviso llegaría en el sitio del cliente.

## Gates físicos y de despliegue (`RUNBOOK-auditoria-cierre §10`)

### G-01 · Restart en frío del Pi (L1)

**Fuente:** `RUNBOOK-auditoria-cierre §10` · **Veredicto:** `SIN COBERTURA`

> **No lo cierra ningún test:** Pide `sudo reboot` en un Pi físico con el gabinete armado y leer el journal.

### G-02 · SPOF-02 ruta hardware (L2)

**Fuente:** `RUNBOOK-auditoria-cierre §10` · **Veredicto:** `SIN COBERTURA`

> **No lo cierra ningún test:** Pide cortar la energía del Pi y comprobar que la sirena suena por la ruta eléctrica. Por definición mide lo que pasa cuando el software no está.

### G-03 · Soak 24 h + restart físico del Shake (L3/T-1.5)

**Fuente:** `RUNBOOK-auditoria-cierre §10` · **Veredicto:** `SIN COBERTURA`

> **No lo cierra ningún test:** Pide 24 h de SeedLink continuo y un power-cycle físico del Shake.

| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |
|---|---|---|---|---|
| G-03.a | El Shake entrega 100 sps y el stream se sostiene sin reconectar. | `SIN COBERTURA`<br><sub>sólo tests que no corren (skipif)</sub> | `edge/tests/test_seedlink_hardware.py:104`<br>`test_real_shake_streams_100sps`<br>⚠️ *no corre: skipif* | Contra el Shake real. |
| G-03.b | El resume por número de secuencia da cero pérdida tras un hueco. | `SIN COBERTURA`<br><sub>sólo tests que no corren (skipif)</sub> | `edge/tests/test_seedlink_hardware.py:154`<br>`test_real_shake_backfills_via_seqnum_resume`<br>⚠️ *no corre: skipif* | Contra el Shake real. |

- **`SIN COBERTURA` · G-03.a** (sólo tests que no corren (skipif)) — El test existe y **en CI nunca corre**: su `pytestmark` es un `skipif` de alcanzabilidad por socket al Shake, que un runner de GitHub jamás cumple. Está censado en `edge/tests/test_hardware_gates.py::GATES_HARDWARE` justo para que el verde del job no se lea como acreditación (T-2.63).
- **`SIN COBERTURA` · G-03.b** (sólo tests que no corren (skipif)) — Mismo `skipif` de socket: no acredita nada en CI.

### G-04 · Radio WR-1 real (L3/T-1.42)

**Fuente:** `RUNBOOK-auditoria-cierre §10` · **Veredicto:** `SIN COBERTURA`

> **No lo cierra ningún test:** Pide recepción SASMEX real (o prueba CIRES) con el radio WR-1 conectado.

### G-05 · Config firmada aplicada (B4)

**Fuente:** `RUNBOOK-auditoria-cierre §10` · **Veredicto:** `SIN COBERTURA`

> **No lo cierra ningún test:** Pide un publish desde el SOC a un gabinete físico y ver `in_sync`.

### G-06 · Simulacro E2E por sitio real (E1)

**Fuente:** `RUNBOOK-auditoria-cierre §10` · **Veredicto:** `SIN COBERTURA`

> **No lo cierra ningún test:** Pide un simulacro en un sitio real con cascada de notificación real.

### G-07 · Replay HMAC en hardware (S2)

**Fuente:** `RUNBOOK-auditoria-cierre §10` · **Veredicto:** `SIN COBERTURA`

> **No lo cierra ningún test:** Pide re-emitir un comando capturado contra el gabinete físico.

### G-08 · Load-test a escala objetivo (O2)

**Fuente:** `RUNBOOK-auditoria-cierre §10` · **Veredicto:** `SIN COBERTURA`

> **No lo cierra ningún test:** Pide una flota comercial y una ventana de carga contra AWS.

### G-09 · Restore de backup (O3)

**Fuente:** `RUNBOOK-auditoria-cierre §10` · **Veredicto:** `SIN COBERTURA`

> **No lo cierra ningún test:** Pide ejecutar los procedimientos A, B y C contra AWS y medir el RTO real (ventana `T-2.74`, bloqueada por `T-2.73.a`).

### G-10 · Panel LAN + PIN + MFA runtime (T-1.43/T-1.53/S4)

**Fuente:** `RUNBOOK-auditoria-cierre §10` · **Veredicto:** `SIN COBERTURA`

> **No lo cierra ningún test:** Pide el panel LAN del Pi real y un login por rol contra el pool de Cognito.

---

## Qué NO garantiza esta matriz

Está entera en el archivo que la genera (`api/tests/test_matriz_trazabilidad.py`, sección final). En corto:

- **La semántica la decide un humano.** El generador comprueba que el test exista, que no se salte y que un job bloqueante lo corra; que además *demuestre* lo que la fila dice, no lo comprueba nadie automáticamente.
- **La descomposición en afirmaciones es un juicio editorial.** Las once reglas, los seis invariantes y los diez gates se derivan de su fuente; partirlos en `a`/`b`/`c` no. Una afirmación que nadie escribió no aparece como hueco.
- **`CUBIERTO` no dice «bien cubierto».** Dice que hay al menos una prueba viva. Un requisito con una prueba superficial sale igual de verde que uno con quince.
