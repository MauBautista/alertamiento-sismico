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
| `CUBIERTO` | 11 | 60 |
| `PARCIAL` | 5 | — |
| `SIN COBERTURA` | 1 | 6 |
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
| RO-1.c | El proceso mínimo `takab-gpio` —el que toca sirena, gas y puertas— no carga ninguna dependencia fuera de una lista blanca cerrada (IA incluida). | `CUBIERTO` | `edge/tests/test_gpio_process.py:473`<br>`test_el_proceso_minimo_no_carga_ninguna_dependencia_no_autorizada` | Lista blanca *fail-closed* sobre el grafo de importación real, en tres montajes de arranque. |
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
| RO-3.c | La superficie de escritura HTTP tolera el reintento del cliente offline. | `CUBIERTO` | `api/tests/api/test_mobile_core.py:671`<br>`test_checkin_replay_offline_es_idempotente` | Reenviar el mismo `checkin_id` devuelve la fila idéntica; otro portador con el mismo id recibe 409. |
| RO-3.d | El nonce de intención emitido por el servidor es de un solo uso. | `CUBIERTO` | `api/tests/api/test_command_intent.py:163`<br>`test_intencion_firmada_feliz_y_replay_rechazado` | Primera llamada 201; el replay exacto del intento firmado, 409. |
| RO-3.e | El anti-replay de configuración firmada sobrevive a un reinicio del edge. | `CUBIERTO` | `edge/tests/test_config.py:240`<br>`test_replay_rejected_across_restart` | Un `ConfigStore` nuevo sobre la misma caché sigue rechazando la versión ya vista. |

### RO-4 · El proceso GPIO/actuadores es mínimo y auditable.

**Fuente:** `CLAUDE.md §2` · **Veredicto:** `PARCIAL`

> «Mínimo» está bien cubierto; **«auditable» no lo está en el edge**, y la pregunta de qué proceso corre de verdad en el gabinete no la responde ningún test.

| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |
|---|---|---|---|---|
| RO-4.a | El proceso GPIO no carga dependencias pesadas (NumPy/SciPy/ObsPy). | `CUBIERTO` | `edge/tests/test_gpio_process.py:564`<br>`test_gpio_process_does_not_import_heavy_deps`<br>`edge/tests/test_gpio_process.py:473`<br>`test_el_proceso_minimo_no_carga_ninguna_dependencia_no_autorizada` | Ninguna de numpy/obspy/scipy/pandas/matplotlib en `sys.modules` del hijo.<br>Y la versión *fail-closed*: lista blanca en vez de lista negra. |
| RO-4.b | Arranca en menos de un segundo. | `CUBIERTO` | `edge/tests/test_gpio_process.py:580`<br>`test_gpio_process_starts_under_one_second` | Mide de la primera importación al retorno de `run_gpio_process`. |
| RO-4.c | La propiedad de los pines es exclusiva: un segundo dueño no toca un pin. | `CUBIERTO` | `edge/tests/test_gpio_ownership.py:160`<br>`test_un_segundo_dueno_no_toca_un_solo_pin_y_lo_grita`<br>`edge/tests/test_gpio_traspaso.py:323`<br>`test_los_dos_servicios_a_la_vez_no_mueven_un_solo_pin` | El segundo `GpioController` muere antes de abrir un pin y grita el PID del dueño.<br>Seis rondas de crash-loop cruzado: cero transiciones eléctricas de más en gas y retenedor. |
| RO-4.d | Un arranque fallido deja los relés en seguro ANTES de soltar el cerrojo. | `CUBIERTO` | `edge/tests/test_gpio_ownership.py:448`<br>`test_un_arranque_fallido_deja_los_reles_EN_SEGURO_antes_de_soltar_el_cerrojo` | Fotografía el nivel y la función de los 5 pines en el instante exacto de liberar el cerrojo. |
| RO-4.e | «Auditable»: toda acción de actuador queda registrada en el edge con quién la ordenó y cuándo. | `CUBIERTO` | `edge/tests/test_actuation_ledger.py:138`<br>`test_una_actuacion_con_la_nube_caida_deja_constancia_que_nombra_la_causa`<br>`edge/tests/test_actuation_ledger.py:256`<br>`test_con_el_registro_averiado_la_sirena_suena_igual`<br>`edge/tests/test_actuation_ledger.py:190`<br>`test_sin_cloud_spool_dir_el_directorio_sigue_siendo_EL_MISMO` | La bitácora vive en `ActuatorManager._record`, por donde pasan `execute` y `execute_sequence`: el embudo es estructural, no disciplinario. Las causas se DERIVAN de `AlertSource` y de la lista blanca `GPIO_ACTIONS`, con mapeos totales — quitar una acción del mapeo pone el build en rojo nombrándola.<br>Ni el constructor ni `record()` lanzan jamás: con el directorio imposible, el WR-1 energiza sirena y cierra gas igual. Pero no calla — cuenta los fallos y los grita.<br>No cae en la trampa de T-2.67.b: el directorio se deriva, nunca es un `mkdtemp` — que es por lo que la evidencia se evapora en cada arranque del Pi real. **Reserva declarada:** la SUBIDA a la nube está construida y probada pero su `sink` va a `None` a propósito: publicar en un topic no autorizado desconecta al gabinete en cada publish (visto en producción el 2026-07-12), así que la copia permanente sigue pendiente de las cuatro piezas de nube que ficha `T-2.86.a`. Y el reflejo SASMEX→sirena no pasa por aquí: vive dentro de `gpio` y no cruza la costura (gate #6). |
| RO-4.f | El gabinete desplegado corre el proceso mínimo como dueño de los pines. | `SIN COBERTURA`<br><sub>sin test</sub> | — | — |

- **`SIN COBERTURA` · RO-4.f** (sin test) — Ningún test lee qué unidad queda habilitada ni qué dice `/etc/takab/edge.env`, y `deploy/edge/deploy.sh` no ejecuta ningún `systemctl enable`. Los tests de despliegue van a propósito en la dirección contraria: `edge/tests/test_deploy_sh.py::test_la_verificacion_no_esta_anclada_al_nombre_takab_edge` exige que la comprobación sea agnóstica del nombre. Con `gpio_owner = "edge"` por defecto, **el estado de fábrica es el que la regla 4 prohíbe** y sólo un archivo fuera del repo lo corrige. Es la otra cara de `RO-1.d`.

### RO-5 · Multi-tenant por diseño:

**Fuente:** `CLAUDE.md §2` · **Veredicto:** `PARCIAL`

| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |
|---|---|---|---|---|
| RO-5.a | Toda tabla de negocio lleva `tenant_id`, comprobado DERIVANDO la lista del catálogo y no de una lista escrita a mano. | `CUBIERTO` | `api/tests/test_censo_multitenancy.py:340`<br>`test_toda_tabla_de_negocio_lleva_tenant_id`<br>`api/tests/test_censo_multitenancy.py:359`<br>`test_toda_tabla_de_negocio_esta_aislada`<br>`api/tests/test_censo_multitenancy.py:412`<br>`test_una_vista_barrera_sobre_una_base_legible_no_aisla_nada` | El criterio de «tabla de negocio» es INCLUSIVO a propósito —toda relación ordinaria de `public` que no sea miembro de una extensión—, y la razón está medida: los criterios sustantivos («tiene FK a `tenants`», «la crea el migrador») reintroducen el defecto, porque eximen a la tabla infractora justo por lo que la hace sospechosa. El único criterio seguro es el que una tabla nueva no puede dejar de cumplir: existir.<br>Tres formas de cumplir, no una: RLS propia, o vista `security_barrier` con la base REVOCADA al rol de la API y anclada en una tabla con RLS. Las tres condiciones juntas o no cuenta.<br>No es sello de goma: devolver el `SELECT` sobre la base dentro de una transacción tira `waveform_features_1s` a «sin aislamiento», nombrada. |
| RO-5.b | Toda tabla con `tenant_id` tiene RLS activa y con políticas, derivado del catálogo de Postgres. | `CUBIERTO` | `api/tests/ops/test_restore_check.py:84`<br>`test_la_base_migrada_pasa_entera` | `verify()` recorre `pg_catalog` y falla cualquier tabla con `tenant_id` sin `relrowsecurity`, y cualquier tabla con RLS y cero políticas. |
| RO-5.c | Una lectura cruzada entre tenants no devuelve nada. | `CUBIERTO` | `api/tests/test_rls_isolation.py:36`<br>`test_app_cannot_read_other_tenant` | Como `takab_app` con `app.tenant_id=B`, contar filas de A da 0. |
| RO-5.d | Una escritura cruzada entre tenants es rechazada por la DB. | `CUBIERTO` | `api/tests/test_rls_isolation.py:51`<br>`test_app_cannot_write_other_tenant` | El `INSERT` etiquetado con otro tenant levanta `InsufficientPrivilege` (WITH CHECK). |
| RO-5.e | La API rechaza el cruce con un JWT real, no sólo la DB. | `CUBIERTO` | `api/tests/auth/test_guc_propagation.py:43`<br>`test_gucs_propagate_and_no_cross_tenant_read` | Petición HTTP real: el token de A ve el incidente de A y no el de B, y simétrico. |
| RO-5.f | La función de alcance, invocada con el filtro puesto, deja cero sitios ante un claim vacío. | `CUBIERTO` | `api/tests/auth/test_console_scope.py:85`<br>`test_fase_B_un_claim_vacio_significa_cero_sitios` | Unidad pura con `enforced=True`: claim vacío ⇒ cero sitios. |
| RO-5.g | El servidor filtra de verdad por sitio en el despliegue real. | `SIN COBERTURA`<br><sub>sin test</sub> | — | — |

- **`SIN COBERTURA` · RO-5.g** (sin test) — **El hueco que queda es el despliegue, y solo ése.** En producción la perilla sigue en `False` (`api/src/takab_api/settings.py`): el servidor desplegado NO filtra, y es la única brecha multi-tenant viva — la que `T-2.89` existe para cerrar, con su secuencia obligada (recorrer los `scope_gap` → asignar alcance → **encender al final**). Esta fila no sube a `CUBIERTO` por tests: lo que afirma es una conducta *del despliegue*, y eso lo acredita el `apply`, no la suite.

  > ### ✅ Lo que SÍ cambió el 2026-08-22 ([`D-18`](DECISIONES-MAURICIO.md#d-18))
  > Hasta esa fecha esta nota decía que **ningún test recorría el HTTP con el filtro puesto**, y ya no es cierto: los tres tests de `api/tests/api/test_console_scope.py` están **parametrizados por la perilla** y fijan la conducta a los dos lados —con el filtro puesto, un claim vacío no ve ningún sitio, `/me` lo declara y el `scope_gap` deja de escribirse—.
  >
  > **Y decía algo peor, que era un error de conteo con precio.** Afirmaba que **dos** tests HTTP fijaban la conducta no impuesta y que encender la perilla pondría la suite en rojo. **Eran TRES**: faltaba `::test_fase_A_el_hueco_queda_auditado_una_sola_vez`, que con la perilla encendida no ve ninguna fila `scope_gap` porque `auth/scope.py` devuelve `gap=False`. Un aviso que enumeraba a mano enumeró de menos, y el que faltaba habría saltado **en mitad de la ventana AWS** — exactamente lo que `D-18` mandó evitar. **Hoy no hay rojo que esperar por ninguno de los tres:** la perilla se enciende con la suite verde antes y después.

### RO-6 · Nada de secretos hardcodeados.

**Fuente:** `CLAUDE.md §2` · **Veredicto:** `CUBIERTO`

| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |
|---|---|---|---|---|
| RO-6.a | Ningún secreto vive en el árbol: alguien barre el repo buscándolos. | `CUBIERTO` | `infra/scripts/tests/test_secret_scan.sh:66`<br>`test_el_arbol_de_trabajo_no_tiene_secretos` | Barre el árbol ENTERO —rastreados y no-rastreados-no-ignorados— con 14 reglas ancladas a la forma del emisor, y falla el gate si encuentra uno. No es teatro: la misma corrida prueba que cada regla caza su secreto sintético, que 12 valores legítimos del repo NO se marcan, y que las exclusiones declaradas siguen haciendo falta. Corre en el job `secretos` de `ci.yml` y está espejado en `make test`. |
| RO-6.b | Sin secreto configurado, la superficie que lo necesita se cierra en vez de seguir sirviendo. | `CUBIERTO` | `api/tests/api/test_command_intent.py:324`<br>`test_sin_secreto_configurado_es_503_fail_closed`<br>`api/tests/commands/test_keys.py:93`<br>`test_build_key_provider_precedence_and_fail_closed` | Borrado `TAKAB_API_COMMAND_INTENT_SECRET`, los endpoints tácticos devuelven 503.<br>Precedencia env → Secrets Manager, y sin ninguno `key_for()` devuelve `None` (cierra, no inventa). |
| RO-6.c | En producción, un secreto ausente hace ruido en el arranque en vez de caer al valor por defecto de desarrollo. | `CUBIERTO` | `api/tests/test_settings_produccion.py:169`<br>`test_un_secreto_retirado_impide_arrancar`<br>`api/tests/test_settings_produccion.py:181`<br>`test_el_dsn_por_defecto_no_cuenta_como_configurado`<br>`api/tests/test_settings_produccion.py:195`<br>`test_una_credencial_de_dev_presente_en_produccion_impide_arrancar`<br>`api/tests/test_settings_produccion.py:409`<br>`test_el_deploy_real_inyecta_la_senal_de_produccion` | Parametrizado sobre `REQUERIDOS_EN_PRODUCCION`: retirar cualquiera levanta `ConfiguracionInvalida` nombrando la variable que falta.<br>El caso exacto del hueco: el DSN igual al default de dev se rechaza en vez de arrancar contra la base equivocada.<br>La mitad simétrica: un `PROHIBIDO_EN_PRODUCCION` presente (llave de `/dev/token`, JWKS inline, mapa HMAC inline) también impide arrancar.<br>Anclaje anti-fail-open: si `deploy/cloud/deploy.sh` dejara de poner `TAKAB_API_BUILD_SHA`, el guardia se apagaría en la nube — y esto se pone rojo antes. |

### RO-7 · Estados de UI obligatorios:

**Fuente:** `CLAUDE.md §2` · **Veredicto:** `CUBIERTO`

> Desde `T-2.84.c` la consola web ya no depende del muestreo: un censo derivado del árbol obliga al componente siguiente a tener su prueba o a aparecer en una lista de deuda comparada **por igualdad**. Lo que el censo mide hoy es deuda real y con nombre —21 componentes con dato de servidor, 12 con la prueba de los cuatro estados, 11 `<StateFrame>` que se callan una entrada—, no ausencia de guarda. Fuera de `web/src` (panel del gabinete, móvil) sigue siendo muestreo.

| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |
|---|---|---|---|---|
| RO-7.a | Un censo DERIVADO obliga a que todo componente que pinte dato de servidor declare sus cuatro estados. | `CUBIERTO` | `web/src/serverDataCensus.test.ts:469`<br>``expectFourStates` cubre a todos los censados`<br>`web/src/serverDataCensus.test.ts:362`<br>`el censo cuadra con la deuda declarada, identificador a identificador`<br>`web/src/serverDataCensus.test.ts:419`<br>`ninguno se calla una`<br>`web/e2e/screens.spec.ts:601`<br>`declara los estados obligatorios: nunca una caja en blanco`<br>⚠️ *no corre: suite no bloqueante (e2e.yml)* | Cierre transitivo por AST desde los transportes (hooks de lectura + `useLiveSocket`): quién POSEE dato de servidor se deriva, y se cruza contra quién tiene la prueba de los cuatro estados. Comparación por IGUALDAD contra la deuda declarada — el componente 22 tiene que escribir su prueba o ponerse en la lista a la vista de todos.<br>Y la otra mitad, la del bug de `T-2.59`: quien pinte dato de servidor FUERA de `StateFrame` sale nombrado con fichero y línea.<br>Un `<StateFrame>` sin `staleSince` AFIRMA que el dato no puede envejecer: los marcos que se callan una entrada están censados uno a uno y uno nuevo sale rojo.<br>Por pantalla, exige ≥1 `[data-state]` con valor del conjunto permitido; nunca exige que exista `stale`. |
| RO-7.b | La consola SOC rotula el dato viejo en vez de pintarlo como fresco. | `CUBIERTO` | `web/src/features/console/DetailPanel.test.tsx:347`<br>`M-6: flota vieja se rotula stale, no se pinta como fresca` | Flota de hace 10 min ⇒ la tarjeta dice DATOS RETENIDOS. |
| RO-7.c | El panel del gabinete no pinta una medición de hace dos horas como viva. | `CUBIERTO` | `edge/tests/test_local_api_panel.py:1014`<br>`test_feature_vieja_no_se_pinta_como_medicion_viva`<br>🔒 *lleva `skipif`, pero el CI lo impide con `run: node --version`* | Con `age_s=7200` las barras dicen S/D y la brújula estampa SIN SEÑAL DEL SENSOR. |
| RO-7.d | La app móvil sirve la copia vieja con su edad, nunca como dato fresco. | `CUBIERTO` | `mobile/src/ui/StateFrame.test.tsx:42`<br>`stale: contenido VIEJO con banner DATOS RETENIDOS + edad honesta` | El contenido viejo se pinta bajo `state-stale` con la edad real. |
| RO-7.e | La tira de KPI de `/fleet` dice S/D cuando no hay dato, jamás cero. | `CUBIERTO` | `web/src/features/fleet/FleetPage.test.tsx:282`<br>`sin dato (%s) los KPI dicen S/D, no CERO` | Con la consulta en error 503 o cargando, los cuatro KPI dicen S/D. |

### RO-8 · Control de actuadores por nube = superficie más sensible.

**Fuente:** `CLAUDE.md §2` · **Veredicto:** `CUBIERTO`

> Cinco controles en una sola frase, y hay que puntuarlos por separado: firma, MFA, rate-limit, nonce y ack. **El MFA es el único de los cinco sin una sola línea de prueba en ninguna capa.**

| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |
|---|---|---|---|---|
| RO-8.a | Una firma inválida ni ejecuta ni ackea. | `CUBIERTO` | `edge/tests/test_dispatch.py:233`<br>`test_bad_signature_neither_executes_nor_acks` | Payload manipulado sin refirmar: ni ack ni actuador. |
| RO-8.b | La nube firma con la clave del gabinete concreto, no con una compartida. | `CUBIERTO` | `api/tests/api/test_commands_router.py:236`<br>`test_each_gateway_signs_with_its_own_key` | La firma queda atada a la clave del gateway destinatario. |
| RO-8.c | El endpoint de comando exige MFA. | `CUBIERTO` | `api/tests/api/test_command_mfa.py:165`<br>`test_el_camino_de_comando_rechaza_por_falta_de_constancia_de_MFA`<br>`api/tests/api/test_command_mfa.py:190`<br>`test_un_amr_forjado_no_compra_la_constancia_de_MFA`<br>`api/tests/api/test_command_mfa.py:217`<br>`test_el_token_real_de_cognito_sin_amr_ni_acr_sigue_comandando`<br>`api/tests/api/test_command_mfa.py:240`<br>`test_el_camino_de_vida_del_ocupante_no_queda_exigido_de_MFA`<br>`api/tests/api/test_command_mfa.py:376`<br>`test_todo_handler_que_firma_un_comando_declara_su_postura_de_MFA` | **El ID token de Cognito NO lleva `amr` ni `acr`** —son claims reservados que ni un pre-token-generation Lambda puede poner, verificado contra la documentación de AWS—, así que un test sobre `amr` habría sido ficción. Lo único que el token certifica es la PROCEDENCIA, firmada; y el escenario de «dos pools» es HOY: principal `ON`, ocupantes `OPTIONAL`.<br>Un `amr`/`acr` escrito a mano no compra acceso: la constancia no se lee de claims que el emisor no emite.<br>Guarda anti-teatro: el token REAL —sin `amr` ni `acr`— sí comanda.<br>El alcance está acotado: el quórum de pánico del `occupant` sigue disparando la sirena. Exigir MFA ahí rompería el camino de vida, que es lo contrario de lo que la regla persigue.<br>Censo AST por igualdad: todo handler que llame a `issue_signed_command` lleva guarda o está declarado. La guarda va DEBAJO de la de rol — compuesta al revés, un rol sin acciones de comando se cae por el rol y la guarda no corre nunca. |
| RO-8.d | Hay rate-limit por usuario y sitio. | `CUBIERTO` | `api/tests/api/test_commands_router.py:154`<br>`test_rate_limit_user_site_429` | Con el límite en 2/min, el tercer POST es 429 y no se publica. |
| RO-8.e | Hay rate-limit por sitio, independiente del usuario. | `CUBIERTO` | `api/tests/api/test_command_rate_limit_site.py:135`<br>`test_dos_operadores_coordinados_agotan_el_presupuesto_del_sitio`<br>`api/tests/api/test_command_rate_limit_site.py:149`<br>`test_un_tercer_operador_con_su_cuota_intacta_tambien_queda_fuera`<br>`api/tests/api/test_command_rate_limit_site.py:162`<br>`test_el_429_del_sitio_se_distingue_del_429_del_usuario_en_la_bitacora`<br>`api/tests/api/test_command_rate_limit_site.py:177`<br>`test_agotar_un_sitio_no_derrama_al_vecino` | Cuota de usuario ANCHA (10/min) y de sitio estrecha (3/min): dos operadores, ninguno rebasa la suya, el cuarto comando es 429 y no sale al gabinete.<br>El presupuesto es del edificio: un operador que nunca comandó se topa igual con el techo del sitio.<br>Dos techos, dos motivos: `rate_limit_user_site` y `rate_limit_site` en `audit_log`, no un 429 mudo.<br>Y no prohíbe de más: agotado el sitio A, el sitio B sigue comandable. |
| RO-8.f | Un nonce ya visto se rechaza, en el edge y en la nube. | `CUBIERTO` | `edge/tests/test_dispatch.py:243`<br>`test_replayed_nonce_rejected_silently`<br>`api/tests/api/test_command_intent.py:163`<br>`test_intencion_firmada_feliz_y_replay_rechazado` | El comando byte-idéntico reenviado produce un solo ack.<br>En la nube, el replay exacto del intento es 409. |
| RO-8.g | El rechazo por replay queda AUDITADO. | `CUBIERTO` | `api/tests/api/test_command_rejection_audit.py:215`<br>`test_replay_rechazado_queda_auditado_con_su_motivo`<br>`api/tests/api/test_command_rejection_audit.py:248`<br>`test_el_replay_no_archiva_el_nonce_ni_la_firma_en_claro`<br>`api/tests/api/test_command_rejection_audit.py:391`<br>`test_el_sondeo_repetido_no_puede_inflar_la_bitacora_sin_techo`<br>`api/tests/api/test_command_rejection_audit.py:463`<br>`test_el_rechazo_se_archiva_bajo_el_tenant_TOCADO_no_el_del_operador` | El camino feliz no ensucia la bitácora; el replay deja UNA fila con `reason=nonce_replay`, status 409, el sitio tocado y el actor — y el comando jamás sale al gabinete.<br>Se archiva el HECHO, no la credencial: ni nonce ni firma en claro, sólo un `nonce_sha256` para correlacionar sondeos.<br>Auditar el rechazo no puede ser el vector: `audit_log` es append-only y nunca se poda (regla 11), así que hay presupuesto por (tenant, actor, ventana) y la última fila MARCA el agotamiento.<br>Quien pregunta «¿quién intentó abrir MI válvula?» es el dueño del edificio: la fila vive en su bitácora, no en la del operador. |
| RO-8.h | Hay ack de ejecución y un comando sin ack nunca se reporta como ejecutado. | `CUBIERTO` | `api/tests/commands/test_sync.py:548`<br>`test_expires_stale_pending_commands`<br>`api/tests/commands/test_ack_ingest.py:128`<br>`test_late_ack_does_not_revive_expired` | Pasado el TTL, `pending` pasa a `expired` con «sin ack dentro del TTL».<br>Un ack que llega tarde no resucita el comando vencido. |
| RO-8.i | Un comando viejo con firma válida se rechaza (TTL de la firma). | `CUBIERTO` | `edge/tests/test_dispatch.py:251`<br>`test_expired_command_rejected_silently` | Firmado con `ts = ahora-120 s` y TTL de 30 s: cero acks. |
| RO-8.j | La emisión de un comando queda auditada. | `CUBIERTO` | `api/tests/api/test_commands_router.py:116`<br>`test_issue_command_signs_publishes_and_persists` | El verbo `command_issued` aparece en `audit_log` del tenant. |
| RO-8.k | Un comando DENEGADO (403/409/429/503) queda auditado. | `CUBIERTO` | `api/tests/api/test_command_rejection_audit.py:265`<br>`test_firma_de_intencion_invalida_queda_auditada_sin_creerse_el_dispositivo`<br>`api/tests/api/test_command_rejection_audit.py:293`<br>`test_llave_de_dispositivo_desconocida_queda_auditada`<br>`api/tests/api/test_command_rejection_audit.py:370`<br>`test_rate_limit_por_usuario_queda_auditado`<br>`api/tests/api/test_command_rejection_audit.py:349`<br>`test_sin_clave_hmac_el_503_queda_auditado`<br>`api/tests/api/test_command_rejection_audit.py:447`<br>`test_un_intento_rechazado_escribe_exactamente_una_fila` | 403 auditado con `intent_signature_invalid`, y el `key_id` de una firma que NO verifica se archiva como *reclamado*: un rechazo no asciende a hecho lo que no se probó.<br>403 por llave ajena al operador, con su motivo `device_key_unknown`.<br>429 auditado con `rate_limit_user_site` y el sitio como objeto.<br>503 fail-closed por gabinete: el comando que NO ocurrió se ve en la bitácora del edificio, no sólo en un log de servidor.<br>Una denegación = una fila: ni cero ni duplicada. |

### RO-9 · Sin streaming de forma de onda cruda.

**Fuente:** `CLAUDE.md §2` · **Veredicto:** `CUBIERTO`

> Era la regla con la brecha más limpia entre lo declarado y lo verificado —tres documentos, ni un test— y desde `T-2.84.a` la sostiene una propiedad DERIVADA del esquema, no una lista de nombres: un payload sólo es publicable en continuo si su tamaño está acotado por su propio esquema, y una serie de muestras no lo está. Queda declarado en el propio fichero lo que la guarda no ve: los campos `dict` libres (censados y anclados) y la ruta S3 pre-firmada, cuyo control es `RO-9.b`.

| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |
|---|---|---|---|---|
| RO-9.a | El enlace edge→nube nunca publica forma de onda cruda en continuo. | `CUBIERTO` | `edge/tests/test_cloud_streaming_crudo.py:458`<br>`test_ningun_publicador_del_edge_pasa_una_serie_de_muestras`<br>`edge/tests/test_cloud_streaming_crudo.py:501`<br>`test_el_conector_rechaza_una_serie_de_muestras_en_la_puerta`<br>`edge/tests/test_cloud_streaming_crudo.py:420`<br>`test_el_clasificador_distingue_serie_de_muestras_de_payload_acotado`<br>`edge/tests/test_cloud_streaming_crudo.py:524`<br>`test_el_camino_legitimo_sigue_publicando` | Censo por AST de TODO `takab_edge/**`: cada `.publish(...)` tiene que enseñar un payload de tipo resoluble y acotado por su esquema. *Fail-closed* — un publicador nuevo entra solo y, sin tipo, sale rojo.<br>El invariante se IMPONE, no sólo se observa: `publish` y `publish_direct` devuelven `False`, nada alcanza el transporte y nada queda en el spool (un rechazo no es un aplazamiento).<br>No-vacuidad: el clasificador ve la serie de `WaveformPacket.samples` y no confunde con ella a `FeatureBatch`/`HealthSnapshot`; tampoco se rodea envolviendo, aplanando ni mandando `bytes`.<br>Y no prohíbe de más: salud y eventos siguen encolándose con cero rechazos, que es la diferencia entre una guarda y un gabinete mudo. |
| RO-9.b | El miniSEED crudo sube a S3 SÓLO en eventos confirmados. | `CUBIERTO` | `edge/tests/test_cloud_streaming_crudo.py:607`<br>`test_el_miniseed_crudo_solo_se_encola_en_tiers_que_comandan_actuacion` | Barre los tiers y exige IGUALDAD contra el conjunto que comanda actuación, leído de `rules.TIER_ACTUATION` — «confirmado» no es un literal copiado: bajar el umbral (meter `watch`) se pone rojo solo, y perder evidencia de un evento real también. |

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
| RO-11.a | Una regla de retención que borre filas de una tabla de compliance se rechaza, y se rechaza ANTES de borrar nada. | `CUBIERTO` | `api/tests/test_privacy_retention.py:546`<br>`test_una_regla_que_borra_filas_de_una_tabla_protegida_es_rechazada`<br>`api/tests/test_privacy_retention.py:560`<br>`test_el_rechazo_ocurre_en_el_preflight_antes_de_cualquier_conteo` | Parametrizado sobre las cinco tablas protegidas: `RetentionUnsafe` y conteo idéntico antes/después.<br>El plan entero aborta en el preflight. |
| RO-11.b | Ni saltándose el guard puede el job borrar evidencia: lo impide la propia base. | `CUBIERTO` | `api/tests/test_privacy_retention.py:571`<br>`test_ni_saltandose_el_guard_puede_el_job_borrar_evidencia` | `DELETE` crudo en la sesión del job ⇒ 42501 o P0001 (trigger append-only). |
| RO-11.c | ARCO anonimiza al titular sin perder una sola fila. | `CUBIERTO` | `api/tests/test_privacy_erasure.py:373`<br>`test_arco_anonimiza_al_titular_sin_perder_una_sola_fila` | Censo de filas sobre 9 tablas idéntico antes y después. |
| RO-11.d | El hecho sobrevive a la anonimización: el check-in sigue contando. | `CUBIERTO` | `api/tests/test_privacy_erasure.py:415`<br>`test_el_checkin_anonimizado_sigue_contando_para_el_incidente` | El conteo del incidente no cambia; la geometría precisa sí se anula. |

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

**Fuente:** `BLUEPRINT §14` · **Veredicto:** `CUBIERTO`

> Es la regla de oro 9 vista desde el blueprint. Su estado es el de `RO-9`.

| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |
|---|---|---|---|---|
| INV-streaming.a | No se sube forma de onda cruda en continuo a la nube. | `CUBIERTO` | `edge/tests/test_cloud_streaming_crudo.py:458`<br>`test_ningun_publicador_del_edge_pasa_una_serie_de_muestras`<br>`edge/tests/test_cloud_streaming_crudo.py:501`<br>`test_el_conector_rechaza_una_serie_de_muestras_en_la_puerta`<br>`edge/tests/test_cloud_streaming_crudo.py:547`<br>`test_los_topics_del_gabinete_son_un_conjunto_cerrado_y_declarado` | Mismo censo derivado que `RO-9.a`: la viñeta `[INVARIANTE]` deja de ser una prohibición sólo escrita y pasa a romper el build.<br>Y la puerta que la impone en tiempo de ejecución.<br>El topic que necesitaría un publicador de waveform entra solo en el censo y sale rojo hasta que alguien lo declare con su razón. |

### INV-IA en la ruta de disparo · **IA en la ruta determinista de seguridad** (P4) — regla de oro 1.

**Fuente:** `BLUEPRINT §14` · **Veredicto:** `PARCIAL`

| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |
|---|---|---|---|---|
| INV-IA.a | El proceso que dispara actuadores no puede cargar una dependencia de IA. | `CUBIERTO` | `edge/tests/test_gpio_process.py:473`<br>`test_el_proceso_minimo_no_carga_ninguna_dependencia_no_autorizada` | Lista blanca *fail-closed* sobre el grafo real de importación del proceso de la sirena. |
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
