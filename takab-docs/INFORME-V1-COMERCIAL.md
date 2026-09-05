# Informe V1-COMERCIAL — qué se puede afirmar hoy delante de un cliente

> **Qué es esto.** La auditoría encargada por `PROMPT-auditoria-v1-comercial.md`, ejecutada el
> **2026-09-02** sobre `main` en `df13599`. **No arregló nada**: cada hallazgo salió como ficha,
> no como commit. El plan que las contiene es [`PLAN-V1-COMERCIAL.md`](PLAN-V1-COMERCIAL.md).
>
> **Alcance (V1-DEMO):** el sistema que se puede enseñar y vender **sin que ninguna pantalla
> afirme algo que no se ha acreditado**. No es "el producto terminado".
>
> **Cómo se leyó cada ítem.** VERDE exige tres cosas: implementado, con test, **y ejercido al
> menos una vez fuera de los tests**. AMARILLO es código sin una de las tres. ROJO es que no
> existe, o que existe algo que **no hace lo que su nombre dice**.
>
> **Lo que este informe midió contra el sistema vivo, no contra el repositorio:** el gabinete
> `gw-dev-0001` por SSH (`/api/status`, 2026-09-02 15:46 UTC), la nube (`/api/health`), la
> landing pública y el aviso de privacidad publicado. Cuatro de los hallazgos ALTA se
> re-verificaron a mano abriendo el archivo antes de escribirlos.

---

## 1 · Resumen ejecutivo

**Se puede afirmar hoy:** que el gabinete **actúa solo, sin internet y sin IA**, y lo declara en
pantalla cuando queda aislado; que **no inventa cuenta atrás ni magnitud**, con una prueba en cada
superficie que se pone roja si aparecen; que **la evidencia no se puede reescribir ni borrar**, con
dos capas que paran hasta al rol más privilegiado; que **un cliente no ve los datos de otro**,
impuesto por la base; y que el dictamen **se firma, se sella y se verifica por su huella**.

**No se puede afirmar:** que el sistema **cierre el gas, retorne ascensores o libere puertas** —
ningún gabinete los tiene cableados—; que la **sirena suene con el gabinete apagado** — esa ruta
eléctrica no está construida—; que **avise por SMS, WhatsApp o teléfono** — los tres en simulado—;
que exista un **tiempo de recuperación** medido; ni que el sistema **sepa de qué sismo se trata**.

**Y tres cosas hacen hoy peligrosa una exposición:** el **modo demo del panel dispara relés de
verdad** mientras la pantalla dice que nada es real; **no existe un modo demostración** que impida
despertar teléfonos; y el **banner del SOC llama "alerta sísmica" a un botón de pánico**,
contradiciendo a la app móvil delante del mismo cliente.

**52 ítems: 10 verdes · 23 amarillos · 19 rojos.** Lo que importa es la forma: **casi todo lo rojo
de la primera tanda es software**, y eso sí se compra con capacidad de desarrollo.

---

## 2 · Hallazgos

Severidad según el encargo: **ALTA** = una pantalla que miente, un dato personal que se fuga, o
una afirmación comercial no acreditable.

### ALTA

| # | Hallazgo | Dónde | Ítem |
|---|---|---|---|
| **H-01** | **El modo demo del panel del gabinete dispara actuadores reales.** `doAction()` hace el `POST` sin comprobar `DEMO`; el único `if (!DEMO)` del flujo solo se salta el refetch de estado. Y `renderActions()` pinta `PROBAR ACTUADORES` —*"sostiene sirena+estrobo · pulso en gas, ascensores, puertas"*— **incondicionalmente**, decidiendo qué botones aparecen a partir del **estado falso de la escena**. Mientras tanto la cinta afirma `DEMO · NO ES ESTADO REAL`. Es el escenario exacto de una exposición. *(Verificado a mano.)* | `edge/takab_edge/local_api/index.html:1831`, `:1837`, `:1880`, `:220` | G5 |
| **H-02** | **El banner del SOC llama alerta sísmica a lo que no lo es.** El incidente se elige **solo por `severity === "critical"`**, y el banner lleva dos textos a fuego: `ALERTA SÍSMICA · PROTÉJASE` y `EDGE · RS4D · REGLAS LOCALES EJECUTADAS · ● AUTO`. **No mira el `trigger`.** Ante un quórum de pánico la app móvil pinta `NO ES UNA ALERTA SÍSMICA` para el mismo incidente. Es el defecto ya corregido en móvil, reintroducido en el SOC. *(Verificado a mano.)* | `web/src/features/console/ConsolePage.tsx:129`; `AlertBanner.tsx:23,39-41`; `mobile/src/features/alarm/BuildingAlarmView.tsx:66` | A3 |
| **H-03** | **No existe modo demostración de sistema.** Nada bloquea push, SMS, WhatsApp, correo, comandos firmados ni apertura de incidentes; ninguna pantalla del SOC ni de la app lo declararía. El SOC **retiró** su modo demo a propósito, y `simulated` en notificaciones es un estado *derivado de la ausencia de credenciales*: desaparece justo en el entorno donde se haría la demo. | `web/src/styles/soc.css:787`; `api/src/takab_api/notify/providers.py:47` | G5 |
| **H-04** | **La landing pública vende cuatro canales que ningún gabinete tiene.** Afirma que el sistema "acciona sirena, estrobo, **gas, ascensores y puertas**" y que se instala con "**respaldo de energía**". El gabinete real reporta **dos** canales y `ups_status: "unknown"`. En la lista de materiales el controlador que haría gas/ascensores/puertas está marcado **"Opcional"**, y el documento de entrega dice que ese driver es *"un extra no acreditado con equipo"*. El perímetro de claims que defiende el test de la landing cubre **cifras y normas**, no **capacidades no acreditadas** — por eso pasó. | `takabailert.com` (rev `2df5aa1`); `landing/tests/contenido.test.mjs:58`; `cotizacion/…C5`; `takab-docs/ENTREGA-Y-ACEPTACION-TAKAB.md:214` | — |
| **H-05** | **Si el gabinete muere, la sirena calla.** La mitigación que el propio proyecto llama *"la más importante del sistema"* es **obra pendiente, no prueba pendiente**: no existen el relé de enclavamiento ni el monoestable. El latido de software está escrito y probado, pero arranca deshabilitado y nada lo enciende — el gabinete vivo lo declara honestamente como `keepalive.estado: "sin_ruta"`. Variante **decidida** en `D-10`, materiales cotizados, compra **sin fecha** por `D-16`. | `edge/takab_edge/config/settings.py:510`; `takab-docs/PENDIENTES-MAURICIO.md:440-442`; `D-10`, `D-16` | A7 |
| **H-06** | **Seguir el runbook de alta de estación rompe la ingesta.** El runbook manda escribir UUIDs en `TAKAB_EDGE_TENANT_ID/SITE_ID/GATEWAY_ID`; la ingesta espera **códigos y seriales** y rechaza el resto con `gateway mismatch` → DLQ. Peor: el aprovisionador ya había escrito el valor correcto y el runbook manda sobrescribirlo. El gabinete queda conectado por mTLS y **mudo en la nube**, sin que nada explique por qué. *(Verificado a mano en los tres archivos.)* | `takab-docs/RUNBOOK-ALTA-DE-ESTACION.md:122-124` vs `api/src/takab_api/ingest/handlers.py:9-13,126` vs `infra/scripts/provision_gateway.sh:163` | D4 |
| **H-07** | **Los umbrales por tipo de inmueble del blueprint no existen.** `building_type` es texto libre sin catálogo y **nadie lo consulta** para resolver umbrales; los alcances son tenant/sitio/sensor. El default del edge está documentado como *"Default = hospital"* (0.040–0.060 g), así que **toda la flota corre la banda de hospital**, incluidos los industriales (0.080–0.120 g) y corporativos (0.100–0.150 g) que declara el blueprint. Un industrial dado de alta hoy avisa dos veces por debajo de su banda. | `db/schema.sql:134`; `edge/takab_edge/config/settings.py:63-73`; `BLUEPRINT-TECNICO-TAKAB.md:239` | G8 |
| **H-08** | **Publicar un umbral firmado a un gabinete físico nunca se ha hecho.** El mecanismo es serio (firma, anti-replay, versión monótona), pero el seed de producción deja el conjunto de reglas **deliberadamente sin la clave del edge** para que el worker no empuje nada, y `G-05` sigue abierto. Además **no hay rollback de umbrales**, que el blueprint exige por nombre. | `db/seeds/prod_fleet.sql:58-71`; `api/src/takab_api/commands/sync.py:60`; `BLUEPRINT-TECNICO-TAKAB.md:245` | G8 |
| **H-09** | **La notificación a personas no entrega por tres de cinco canales.** SMS, WhatsApp y push caen a simulado por falta de credenciales. El sistema es **honesto** al respecto (deriva `simulated` del proveedor con default pesimista y deja `sent_at` en NULL), y el documento de entrega coincide fila por fila — pero comercialmente significa que **hoy solo avisan de verdad el webhook y el correo a direcciones verificadas**. | `api/src/takab_api/notify/push.py:255`; `notify/twilio.py:549`; `notify/whatsapp.py:862` | A3, G9 |
| **H-10** | **Los falsos positivos son incontables, incluso a mano.** `incidents` no tiene clasificación, ni descarte, ni motivo de cierre: cerrar un incidente no admite razón y `in_review` no desemboca en ningún veredicto registrable. No hay endpoint de agregados. El sistema **se deslinda** de una tasa que no mide. | `db/schema.sql:279`; `api/src/takab_api/routers/incidents.py:43` | G14 |
| **H-11** | **El catálogo sísmico lleva congelado desde julio, y la magnitud nunca se escribe.** 13 filas transcritas a mano (sismos de 1985-09-19 a 2022-09-19), un solo commit, sin política de escritura en la base. Y el único INSERT a `seismic_events` pone `magnitude` en `NULL` literal, así que la rama del catálogo en la consola es **inalcanzable en producción**: el SOC siempre ve "S/CATÁLOGO". El enriquecimiento post-hoc que documenta el esquema **no existe como código**. *(Verificado a mano.)* | `db/seeds/reference_earthquakes.sql:24`; `api/src/takab_api/incident/engine.py:126`; `web/src/features/triage/model.ts:358` | B1, B2 |
| **H-12** | **La sección más pericial del dictamen sale vacía siempre en la nube real.** Onda cruda y espectro son best-effort desde una fila que **nadie escribe**: el worker de backfill no está en el compose de la nube. El PDF **explica la ausencia** con un texto concreto, así que no miente — pero la figura que un perito busca no llegará nunca hasta que se redespliegue. | `api/src/takab_api/dictamen/builder.py:313`; `deploy/cloud/docker-compose.yml`; `PENDIENTES-MAURICIO §2.11` | E2 |
| **H-13** | **No hay cifra de tiempo de recuperación de producción, y nadie ha comprobado que el respaldo llegue a S3.** El único tiempo medido (~2,3 s) es de un volcado de ~570 KiB en local, y el propio runbook prohíbe extrapolarlo. El objetivo de una hora es una declaración. El punto de recuperación de 900 s se **deriva de la configuración de la alarma**, que mide el código de salida del comando de archivado, no la presencia del objeto en el bucket. El registro del runbook está **enteramente vacío**. | `takab-docs/runbooks/RUNBOOK-backup-restore-db.md:101-110,527-537`; `T-2.72.a`, `T-2.74` | G10 |
| **H-14** | **LEGAL · El uso comercial de los datos del SSN no está resuelto ni documentado.** Sin texto de atribución acordado, sin convenio, y sin entrada en el inventario de terceros — y **ya se redistribuyen en el PDF de dictamen que alguien firma**. Choca con `D-20` (la consulta legal espera a que un cliente la pida): **gana la decisión**, se anota el conflicto (§5). | `takab-docs/REUNION-SSN-QUE-PEDIR.md:252-274`; `THIRD_PARTY_NOTICES.txt` | B3 |
| **H-15** | **LEGAL · Siete terceros tocan datos personales y ninguno está declarado.** AWS, Twilio, Meta, APNs, FCM, Expo y el webhook del propio cliente. El aviso de la plataforma **no nombra a uno solo**, y **no menciona la transferencia internacional**: los datos viven en Ohio. El párrafo más cercano —*"SUS DATOS NO CRUZAN A OTRA ORGANIZACIÓN"*— habla del aislamiento entre clientes y es fácil de leer como una negación de ello. Atenuante real: el aviso **se autodeclara provisional dentro del propio texto** y el motor re-pide consentimiento al cambiarlo. A nadie se le dice algo falso; se le dice nada. | `api/src/takab_api/privacy/texts/aviso_es_mx.json`; `takab-docs/RESIDENCIA-DE-DATOS-TAKAB.md:395-420` | G12 |
| **H-16** | **La IA no tiene tope de gasto, y el endpoint que la invocaría no tiene límite de frecuencia.** Solo hay coste por llamada (contabilizado y tirado) y techo de tokens por llamada: cero cuota, cero contador acumulado, cero corte. Un usuario autenticado puede reexportar el mismo incidente sin límite. Mitigado **solo** por la perilla apagada — lo que significa que el tope tiene que aterrizar **antes** de encenderla, no después. | `api/src/takab_api/narrative/base.py:90`; `narrative/openrouter.py:209`; `routers/reports.py` | F6 |

### MEDIA

| # | Hallazgo | Dónde | Ítem |
|---|---|---|---|
| **H-17** | **Un test que dice defender el deslinde impreso no comprueba nada.** El cuerpo entero de `test_ambos_llevan_el_deslinde` afirma que una constante empiece por una cadena y que el archivo sea un PDF. **Borrar la llamada que imprime el deslinde dejaría el test verde.** Lo mismo vale para los otros cinco deslindes del documento. El propio repo sabe hacerlo bien en la sección de compliance, que sí comprueba que las etiquetas cambian los bytes. *(Verificado a mano.)* | `api/tests/dictamen/test_pdf.py:190-195` | E6 |
| **H-18** | **El folio exporta a un tercero lo que la lista blanca dice que nunca sale.** El folio es `TKB-{código de sitio}-{fecha}-{8 hex del incidente}-{T\|E}` y viaja entero en el prompt; el docstring del redactor afirma que el identificador del incidente **nunca sale**. Y el test que lo defendería **borra el folio antes de afirmar**. No es fuga de dato personal —eso está limpio: ni notas de ocupantes, ni coordenadas, ni firmante—, pero sí un identificador estable y correlacionable entre dictámenes. *(Verificado a mano.)* | `api/src/takab_api/dictamen/builder.py:84-88`; `narrative/redact.py:8-10`; `api/tests/narrative/test_redact.py:53` | F3 |
| **H-19** | **El tiempo de acuse no se calcula, ni se almacena, ni se muestra.** Los dos sellos existen, así que el número es derivable restando a mano en la bitácora; nadie lo hace. Y **"quién recibió la alerta" no tiene endpoint**: la tabla donde vive el destinatario y la confirmación de entrega no se lee desde ningún router de consulta. Son las dos preguntas de una revisión post-incidente. | `api/src/takab_api/routers/incidents_ack.py:83-95`; `notification_jobs` | G6 |
| **H-20** | **El reporte post-simulacro no tiene tiempos ni forma de salir del navegador.** Hay acuse por sitio, honesto y bien probado (distingue *sin gabinete comandable* de *sin acuse*), pero **no existe la latencia de acuse por sitio** y no hay PDF ni CSV. El propio código llama a esto *"la evidencia de cumplimiento que se le entrega a Protección Civil"*, y no se puede entregar. | `web/src/features/console/DrillHistory.tsx:3-4`; `api/src/takab_api/routers/exports.py:39-50` | C7 |
| **H-21** | **La correlación con el catálogo es solo temporal.** Ventana de ±120 s, **sin distancia máxima ni magnitud mínima**; la geografía se calcula pero no decide, y en la ruta del receptor no hay epicentro propio que comparar. Hoy el riesgo está acotado por las 13 filas mexicanas; **con un feed vivo sube a ALTA**: un sismo de otro país dentro de la ventana se imprimiría en el dictamen firmado bajo el rótulo *"CONTRASTE CON CATÁLOGO"*. Y no existe el estado que diría "hay algo en el catálogo pero no es el nuestro". | `api/src/takab_api/forensics/__init__.py:52` | B4 |
| **H-22** | **No hay máquina de estados de procedencia del evento externo.** Ni los cinco estados que pide el encargo ni equivalente con otro nombre. Lo que hay son dos enums de presentación y un campo `source` de tres valores efectivos. Falta sobre todo el estado que convierte un "no sé" en algo legible: sin él, el operador lee una pantalla vacía como "no pasó nada". | `web/src/features/triage/model.ts:366`; `db/schema.sql:259` | B2 |
| **H-23** | **El defecto del fail-open del modo prueba sigue vivo, línea por línea.** Sigue siendo un log de nivel error por paquete, con un texto que describe el peor caso como si hubiera ocurrido, sin agrupación ni contador — y el `return` que lo desmiente está tres líneas más abajo. Medido en el gabinete real: 24 líneas, 0 incidentes abiertos. **La corrección no es bajar el nivel del log**: el fail-open es la dirección correcta y se conserva. | `edge/takab_edge/supervisor.py:592-600`, `:677` | G4 |
| **H-24** | **Los datos de demostración son indistinguibles de los reales en la consola.** La separación vive en el seed y en el despliegue, no en la pantalla: no hay columna que marque lo simulado ni marca visual en el mapa ni en la flota. En una demo local, un prospecto ve 21 sitios y 5 gabinetes con el mismo aspecto, de los cuales 20 y 4 no existen. El patrón visual **ya está resuelto** en el panel del gabinete, que sí pinta su cinta. | `db/seeds/sim_fleet.sql:1-21`; `web/src/features/fleet/` | D5 |
| **H-25** | **El guion de demo sirve para CI, no para una exposición.** Es reproducible desde cero y está bien aislado de producción con tres guardias reales, pero está construido para acreditar criterios: imprime marcas de verificación en terminal, trunca entre escenas y sale con código de error. Además **no ejercita simulacros**, y en el modo interactivo los datos **no se rotulan como simulados, por diseño**. | `demo/run.py:116,133`; `demo/soc_local.py:41-44` | G15 |
| **H-26** | **La huella del PDF se imprime a la mitad.** La cadena de custodia trunca el sha256 a 32 de 64 caracteres, mientras la portada instruye verificarlo con `sha256sum`. Con medio hash no se puede. | `api/src/takab_api/dictamen/pdf.py:427`, `:92-96` | E1, E5 |
| **H-27** | **El acto de mayor peso legal del sistema no entra en la bitácora de auditoría.** Firmar un dictamen escribe la fila del dictamen y —solo si el veredicto es habitable— una acción en el timeline, pero **no escribe en `audit_log`**. El hecho no se pierde (vive en una tabla append-only), pero el sitio donde un perito o un seguro busca *"quién firmó qué y cuándo"* no lo tiene. | `api/src/takab_api/routers/dictamens.py:75-124` | G7 |
| **H-28** | **Silenciar el gabinete principal no calla las sirenas de los secundarios.** El silencio local corta la sirena y el voceo del propio gabinete, pero solo el cierre de alerta propaga la orden a los nodos por radio. Ante una falsa alarma en un sitio con varios gabinetes, el operador calla el suyo y el edificio sigue sonando — que es el riesgo de credibilidad que motivó la decisión de la ruta de hardware. | `edge/takab_edge/gpio/__init__.py:264-281` vs `local_api/__init__.py:1387` | A6 |
| **H-29** | **El panel del gabinete pinta el desfase del reloj siempre en verde**, sin usar el ayudante de umbrales que todas las filas vecinas sí usan. Un desfase de cinco segundos se ve igual que uno de tres milisegundos. Y **no hay alarma de reloj** en la nube: se ve solo si alguien está mirando. Sin hora confiable ninguna evidencia sirve. | `edge/takab_edge/local_api/index.html:1317` vs `:1300` | G2 |
| **H-30** | **La pérdida de paquetes viaja a la nube y se descarta a propósito.** El SOC no puede ver la pérdida de paquetes de ningún gabinete: para diagnosticar un enlace degradado hay que ir al sitio o abrir el panel por red local. Está declarado en el código, no es descuido — pero es un hueco de operación remota. | `api/src/takab_api/ingest/handlers.py:459-460` | G3 |
| **H-31** | **La ficha de estación está partida en dos pantallas y le faltan cinco campos.** Modelo, firmware, serial y estado del respaldo eléctrico no están en el contrato del mapa: para verlos hay que abandonar la consola e ir a Flota, que en una demo es un salto de pantalla en el peor momento. Y **"tipo de enlace" no existe en ninguna capa** — ni columna, ni contrato, ni telemetría. | `shared/sdk-ts/src/gen/types.gen.ts:1346-1366` | D2 |
| **H-32** | **No hay plantillas de simulacro guardadas ni editables.** Ni tabla, ni campo, ni endpoint, ni interfaz. Para el macrosimulacro hay que teclear sitios, duración y nota a mano cada vez; lo más cercano reutiliza **una agenda concreta** y la consume. | `api/src/takab_api/schemas/drills.py:13-29` | C3 |
| **H-33** | **No se puede elegir el sonido del simulacro, y qué sonó solo consta en el journal del propio gabinete.** El perfil que la nube empuja cubre dos ranuras y **el voceo de simulacro no está entre ellas**. El sha256 se registra al arrancar, no al sonar, y el botón del panel deja rastro en un anillo **en memoria**. Si alguien pregunta qué sonó el 19 de septiembre en la torre B, la única respuesta está en ese journal. | `edge/takab_edge/audio/__init__.py:294`; `edge/takab_edge/config/settings.py:490` | C4 |
| **H-34** | **Dos documentos comerciales se contradicen sobre los relés, y el desactualizado es el que ve el cliente.** El de entrega dice *"están en MOCK"*; el censo de pendientes dice que eso **ya no es cierto**. La formulación correcta: **el backend de pines es real; lo que no hay es una sirena al final del cable.** | `ENTREGA-Y-ACEPTACION-TAKAB.md:244` vs `PENDIENTES-MAURICIO.md:447` | A5 |
| **H-35** | **No hay censo de dato viejo en la app móvil.** La consola sí lo tiene, derivado y comparado por igualdad. En móvil seis archivos consultan al servidor sin el envoltorio de frescura, y la lista del pase de vida solo declara el dato viejo **si el refetch está fallando**: un pase de lista de hace diez minutos con red sana se pinta como fresco. Es justo la pantalla que se enseña en una demo. | `mobile/src/app/(brigadista)/lista.tsx:205` | G1 |
| **H-36** | **Ningún gatillo de la decisión que aplaza la consulta legal se dispara al encender la IA.** `D-20` se escribió cuando el proveedor estaba apagado y no se había planteado como encargado de datos: el caso no estaba sobre la mesa. Hoy **nada en el repositorio revive la consulta** si alguien enciende la perilla. Es un hueco del mecanismo de revocación, no un desacuerdo con la decisión. | `takab-docs/DECISIONES-MAURICIO.md:966-975` | F5 |
| **H-37** | **La cifra de latencia más citada del producto solo existe como prosa.** Está replicada a mano en ocho documentos y **no hay ni un artefacto reproducible**: ni journal, ni acta, ni captura del estado del gabinete. Un cliente que pida la evidencia recibe un archivo de texto. Y el test que la guarda **reporta el mejor de cinco intentos**, no un percentil, tras fallar aproximadamente una de cada ocho corridas. | `edge/tests/test_e2e.py:104` | A1 |
| **H-38** | **No hay percentil medido del tramo gabinete→consola.** Lo que se vende como *"medido 214 ms"* es **una sola observación**, no un percentil. Y una cita de percentil del tablero apunta a una línea que no lo contiene. | `takab-docs/ENTREGA-Y-ACEPTACION-TAKAB.md:148` | A2 |

### BAJA

| # | Hallazgo | Dónde | Ítem |
|---|---|---|---|
| **H-39** | **La cabecera de la bitácora de decisiones declara 23 y hay 26.** Última actualización declarada: 2026-08-22; la última decisión es del 2026-08-30. `TASKS.md` y el censo de pendientes sí cuadran — **porque tienen test**. Esta cabecera no lo tiene: los 28 tests de consistencia documental nunca cuentan sus decisiones. Es exactamente la doctrina que el propio archivo predica: *un censo que enumera a mano acaba divergiendo*. | `takab-docs/DECISIONES-MAURICIO.md:15` | — |
| **H-40** | **El documento de traspaso abre con una deriva de despliegue de "tres commits"** sobre un commit que hoy está **103 por detrás**; la deriva real es de 13 (nube) y 25 (gabinete). Es el archivo que se manda leer al empezar una sesión. | `takab-docs/TRASPASO-SESION.md §0` | — |
| **H-41** | **La cifra de marcos incompletos del censo de estados está desfasada en uno**: la matriz y el propio docstring dicen 11, hoy son 10 — en la dirección buena (menos deuda de la declarada). | `web/src/serverDataCensus.test.ts:400`; `MATRIZ-REQUISITO-TEST.md:126` | G1 |
| **H-42** | **El PDF salta de la sección 11 a la 13** cuando no hay prosa. Por el camino normal nunca ocurre; un render directo sí. Un perito lee una sección faltante. | `api/src/takab_api/dictamen/pdf.py:481-483` | E1 |
| **H-43** | **El retiro de un sensor no exige la fricción que sí exigen sitio y gabinete** (teclear el código y el código de retiro del cliente), ni control de versión de fila. Y **la consola no permite editar ni retirar sensores**: hay que ir a la API a mano. Además, la regla *"un sitio no se borra"* la sostienen la ausencia de código y una clave foránea restrictiva, **no un privilegio revocado**. | `api/src/takab_api/routers/sensors.py:152-174`; `db/schema.sql:2601-2605` | D1 |
| **H-44** | **En el móvil el aviso de simulacro vive solo en la pantalla de inicio.** Si el brigadista está en otra vista, no lo ve. No es engañoso —no muestra nada falso—, pero el simulacro se le puede pasar. | `mobile/src/features/home/HomeView.tsx:56-59` | C6 |
| **H-45** | **El panel del gabinete identifica la estación solo por su identificador y el nombre del sitio.** El serial, el nombre del dispositivo en la nube y el código de estación del sensor existen en la configuración pero nunca viajan al panel: quien está de pie frente al gabinete no puede correlacionarlo con la consola sin abrir el archivo de entorno. | `edge/takab_edge/local_api/__init__.py:1152-1202` | D3 |
| **H-46** | **El tercer contract-test de la IA es más débil que su nombre.** Compara tres campos del *modelo* y comprueba que ambos documentos se generan; **no compara los bytes ni el texto impreso** del veredicto. | `api/tests/narrative/test_contract.py:57` | F2 |
| **H-47** | **La procedencia de la prosa se escribe y no la defiende ningún test.** Un refactor la borraría en verde. | `api/src/takab_api/routers/reports.py:115-121` | F4 |
| **H-48** | **El runbook de la sesión de vida se contradice consigo mismo** sobre si el latido de keep-alive está escrito: su cabecera dice que no, su propia sección posterior dice que sí. | `takab-docs/runbooks/RUNBOOK-sesion-de-vida.md:22-24` vs `:288-292` | A7 |
| **H-49** | **El texto de ausencia del catálogo filtra la ruta interna del seed a la pantalla del operador.** | `web/src/features/triage/CatalogPanel.tsx:52` | B1 |
| **H-50** | **El ensayo de restauración está fuera de CI**, con la razón escrita y el remedio cifrado (fijar el cliente de base de datos al mismo major, ~30 s). Es una decisión razonada, pero deja la ceremonia sin vigilante automático. | `Makefile:118-132` | G10 |

---

## 3 · Lo que NO debe decirse en una demo hoy

Frases literales a evitar, con la razón y con lo que sí se sostiene.

| ❌ No decir | Por qué | ✅ Decir en su lugar |
|---|---|---|
| *"El sistema cierra la válvula de gas, retorna los ascensores y libera las puertas."* | Ningún gabinete tiene esos canales cableados; el controlador que los haría está cotizado como **opcional** y su driver es, por escrito, *"un extra no acreditado con equipo"*. | *"El sistema tiene cinco canales de actuación y un adaptador para el equipamiento del edificio. En la unidad de referencia están cableados sirena y estrobo; gas, ascensores y puertas se acreditan canal por canal en la puesta en marcha de cada inmueble."* |
| *"Si el gabinete se apaga, la sirena suena igual por hardware."* | Esa ruta eléctrica **no está construida**. La variante está decidida y los materiales cotizados; la compra no tiene fecha. | *"La ruta de hardware está diseñada y decidida, y es parte de la instalación. Hasta que se acredite en el inmueble, no dé por hecho que la sirena suena con la computadora muerta."* |
| *"Le llega un SMS / un WhatsApp / una notificación al teléfono."* | Los tres canales están en simulado por falta de altas administrativas. Hoy solo entregan el webhook firmado y el correo a direcciones verificadas. | *"La cascada de notificación está construida y probada; los canales de SMS, WhatsApp y notificación push se activan con el alta de cada proveedor. Hoy entregan el correo y el webhook."* |
| *"Le decimos la magnitud y el epicentro del sismo."* | La magnitud **nunca se escribe** en la base y el catálogo lleva congelado desde julio de 2026. El receptor entrega un booleano. | *"El sistema mide lo que pasó en su edificio y lo dice con sus unidades. La magnitud y el epicentro los publica la fuente oficial; contrastarlos automáticamente es trabajo en curso, y cuando exista irá con su fuente y su hora de consulta."* |
| *"En cuánto tiempo le tardan en acusar sus brigadistas: aquí está el número."* | El tiempo de acuse **no se calcula ni se almacena**. Se ve quién acusó y quién no, no cuándo. | *"El sistema registra quién acusó, quién no respondió y quién no tenía gabinete comandable. El cronómetro por persona es la ficha siguiente."* |
| *"Restauramos la base en menos de una hora, está medido."* | El único tiempo medido es de un volcado de juguete en local, y el runbook prohíbe extrapolarlo. La hora es un objetivo. | *"El respaldo está construido, verificado por un comprobador que deriva sus expectativas del propio esquema, y ensayado localmente. La restauración contra la infraestructura real, con su tiempo medido, es una ventana pendiente."* |
| *"Aquí puede ver la demo: mire, disparo los actuadores."* | En el modo demo del panel del gabinete **los botones mandan órdenes reales**, incluido el que sostiene sirena y pulsa gas, ascensores y puertas. | **No tocar ningún botón del panel con el modo demo puesto** hasta que la ficha `T-5.01` esté cerrada. Enseñar el panel en solo lectura. |
| *"Los datos de esta pantalla son de un edificio real."* (en `make soc-local`) | Los sitios y gabinetes simulados **son visualmente idénticos** a los reales en el mapa y en la flota. | *"Este es el entorno de demostración; los sitios se llaman `Sitio Sim NNN`."* Y no enseñar el mapa poblado hasta que exista la marca visual. |
| *"El sistema cumple con la norma X."* | El sistema **no declara ninguna norma como cumplida**, a propósito y con test. El marco citable lo define el cliente con su abogado. | *"El sistema muestra el marco normativo que usted declare, con el deslinde de que TAKAB no lo respalda. Nuestra regla de evidencia inmutable es requisito propio, está construida y está probada."* |
| *"Sus datos no salen de México / no los comparte con nadie."* | Viven en Ohio, y siete terceros los tocan o los tocarán. Ninguno está declarado en el aviso. | *"Hoy la infraestructura está en la región de Ohio, y hay un análisis escrito de por qué no migramos todavía. El aviso de privacidad de la plataforma es provisional y se cierra con la revisión jurídica."* |
| *"La IA nos ayuda a decidir."* | La IA está **apagada**, y por diseño **jamás decide**: el objeto que produce no tiene campo donde poner un veredicto. | *"La IA está construida y apagada. Cuando se encienda, redactará prosa; el veredicto y todos los números son deterministas, y hay una prueba que se pone roja si eso cambia."* |
| *"Este es el espectrograma del sismo."* | No existe espectrograma; hay un espectro de amplitud, y en la nube real **la sección sale vacía siempre** porque el worker que archiva la onda no está desplegado. | *"El dictamen técnico trae la envolvente por canal y las métricas medidas. La onda cruda y su contenido espectral se adjuntan cuando hay registro archivado del evento."* |
| *"Le programo el simulacro y suena solo a las 11:00."* | **No existe disparo por hora, y es correcto que no exista**: la regla de oro 8 exige un humano con sesión viva. La agenda es un anuncio; el disparo es un clic. | *"El simulacro se agenda, y a la hora el botón queda armado para que una persona autorizada lo dispare. Un sistema que abre gas y mueve ascensores no se dispara solo."* |

---

## 4 · Tabla de veredictos

Un renglón por ítem. **Test** vacío significa que no hay ninguno que defienda la afirmación.

### A · Cadena de vida

| # | Veredicto | Evidencia | Test | Razón |
|---|---|---|---|---|
| **A1** | 🟡 | `edge/takab_edge/gpio/__init__.py:922-929` | `test_gpio.py::test_reflex_latency_is_measured_and_under_budget`; `test_e2e.py::test_latencia_contacto_wr1_a_los_cinco_reles_bajo_presupuesto` | **6.65 ms el 2026-07-14** y **4.16 ms en frío el 2026-07-31**, con el receptor real cableado. Pero la medición solo existe como prosa en ocho documentos, y el guardián reporta el mejor de cinco intentos. |
| **A2** | 🟡 | `gpio/__init__.py:905` → `supervisor.py:611,676-687` → `iot-core/main.tf:160` → `ingest/consumer.py:104` → `ingest/handlers.py:288` → `ws/hub.py:211` → `ConsolePage.tsx:233` | `test_ingest_e2e.py::test_local_event_escalates_into_single_incident` | Cadena entera trazada y ejercida con radio y broker reales. **El p95 declarado (<2 s) nunca se midió**; los 214 ms son una observación única. |
| **A3** | 🔴 | `ConsolePage.tsx:129`; `AlertBanner.tsx:23,39-41`; `notify/push.py:255` | `AlertBanner.test.tsx`; `source.test.ts` — **ninguno compara textos entre superficies** | El SOC afirma alerta sísmica ejecutada por el sensor ante un botón de pánico, mientras el móvil dice lo contrario para el mismo incidente. Y el push no entrega. |
| **A4** | 🟢 | `AlertBanner.tsx:23`; `CrisisView.tsx:44`; `local_api/index.html:259` | `AlertBanner.test.tsx` (sin magnitud ni cuenta atrás); `CrisisView.test.tsx` (escaneo del árbol); `test_local_api.py::test_index_has_no_external_resources` | Las tres superficies dicen `ALERTA SÍSMICA · PROTÉJASE` sin número, cada una con un test que se pone rojo si aparece uno, y las tres verificadas en hardware real. |
| **A5** | 🟡 | `edge/systemd/takab-gpio.service:36`; `gpio/__init__.py:139-195` | `test_gpio_conformance.py`; `test_hardware_gates.py` (censa los gates para que el verde no acredite) | **Backend de pines real**, no simulado. Pero nada eléctrico al final del cable: el readback compara el pin consigo mismo. `G-04` abierto desde el hito de Fase 1. |
| **A6** | 🟢 | `gpio/__init__.py:264-281`, `:965-982`; `audio/__init__.py:469-470` | `test_gpio.py::test_silence_stops_an_already_sounding_siren`, `::test_silence_keeps_visual_strobe`; `test_audio.py::test_silencio_detiene_el_voceo_en_curso` | El silencio calla sirena **y voceo**, deja el estrobo, no toca gas ni puertas, y una alarma nueva vuelve a sonar. Verificado presencialmente. |
| **A7** | 🔴 | `config/settings.py:510`; `gpio/__init__.py:355-448` | `test_gpio_latido.py::test_el_latido_CESA_con_el_lock_del_reflejo_tomado` (verificado contra sí mismo) | El latido está escrito y bien probado, pero **no hay ruta de hardware a la que gobernar**: la mitigación no mitiga nada hoy. |

### B · Procedencia del evento externo

| # | Veredicto | Evidencia | Test | Razón |
|---|---|---|---|---|
| **B1** | 🔴 | `db/seeds/reference_earthquakes.sql:24-77` | `test_catalog.py` (sobre filas propias) — **ninguno afirma el contenido de la semilla** | **13 filas** (5 del SSN, 8 de USGS; 11 sismos distintos), de **1985-09-19 a 2022-09-19**. Un solo commit, del 2026-07-10. La base solo concede lectura: nada puede actualizarlo. |
| **B2** | 🔴 | `db/schema.sql:1798-1810`; `incident/engine.py:126` | — | No existen los cinco estados ni equivalente. `reference_earthquakes` no tiene hora de consulta, ni bandera preliminar/revisado, ni identificador del proveedor. Y la magnitud **nunca se escribe**. |
| **B3** | 🔴 | ninguna llamada a fuente sísmica externa en todo el árbol | — | No hay ingestor. El feed del SSN es RSS **solo por HTTP** (443 cerrado), sin esquema documentado; **el uso comercial está sin resolver** y no hay atribución acordada. Ficha `T-2.149` bloqueada. |
| **B4** | 🟡 | `forensics/__init__.py:52-55`; `queries/forensics.py:65-78` | `test_forensics.py::test_casa_con_el_catalogo_dentro_de_la_ventana`, `::test_un_sismo_lejano_en_el_tiempo_no_casa` | Ventana de ±120 s y nada más: sin distancia máxima ni magnitud mínima. La distancia se calcula para describir, nunca para rechazar. |
| **B5** | 🟢 | `edge/takab_edge/catalog.py:28-31`; `rules/__init__.py:1-15` | `test_e2e.py::test_sasmex_reflex_and_sequence_cloud_off`; `test_forensics.py::test_un_sismo_lejano_en_el_tiempo_no_casa` | La cadena de vida no consulta ninguna fuente externa, ni puede; el contraste degrada a "SIN COINCIDENCIA" sin error. **VERDE por ausencia**, no por guarda — reauditar cuando entre el ingestor. |
| **B6** | 🟡 | `api/src/takab_api/dictamen/rules.py:39-56` (siete campos, ninguno de catálogo) | — | El desacoplamiento es estructural: el tipo de entrada del veredicto **ni siquiera admite** el dato. Pero nada fallaría en CI si alguien añadiera el campo mañana. |

### C · Simulacros

| # | Veredicto | Evidencia | Test | Razón |
|---|---|---|---|---|
| **C1** | 🟡 | `routers/drills.py:312,487,517,529,580`; `mobile_site.py:474`; `db/schema.sql:1398,1413`; `edge/takab_edge/drill/__init__.py:33` | `test_drills.py` (6), `test_drills_schedule.py` (17), `test_drill.py` (10), `DrillBanner.test.tsx` (16) | Agenda, disparo, paro, cancelación, acuse por sitio derivado por JOIN, ejecución desde agenda y comandabilidad evaluada al leer. Completo y bien probado; **nunca ejercido en un sitio real**. |
| **C2** | 🟡 | `drill/__init__.py:74,81,146-149,151-154`; `dispatch/__init__.py:175-203` | `test_drill.py::test_start_pinta_banner_y_vocea_sin_tocar_relays` (**mide relés antes y después**), `::test_sasmex_real_aborta_visiblemente`, `::test_pulso_de_prueba_cires_no_aborta`; `test_drills.py::test_un_drill_jamas_crea_incidentes` | El módulo **no tiene handle de escritura a relés**: la propiedad es estructural, no disciplinaria. Y el arranque falla cerrado si no puede comprobar la alerta. Falta el gate en hardware. |
| **C3** | 🔴 | `schemas/drills.py:13-29` (cinco campos, ninguno de plantilla) | — | No existen plantillas: ni tabla, ni endpoint, ni interfaz. |
| **C4** | 🔴 | `audio/__init__.py:294`; `config/settings.py:490` | `test_local_api_panel.py::test_sin_audio_no_se_ofrece_el_voceo_de_simulacro` (defiende "sin botones muertos", no la selección) | No hay selector; el perfil de la nube cubre dos ranuras y el voceo de simulacro no está entre ellas. Qué sonó consta solo en el journal local, sin sha256. |
| **C5** | 🟢 | `routers/drills.py:112,118,223-297`; `DrillBanner.tsx:206` | `test_drills_schedule.py::test_cancel_marca_la_agenda_y_no_emite_nada`; `DrillBanner.test.tsx` (armado a T−15, un clic a T−0) | **No existe disparo por hora en ninguna capa**, y eso es correcto: la agenda es un anuncio, la emisión va por la misma superficie firmada que los comandos, con sesión viva. Respeta la regla de oro 8. |
| **C6** | 🟡 | `DrillBanner.tsx:164`; `local_api/index.html:967,963-965`; `HomeView.tsx:58` | `DrillBanner.test.tsx::con incidente VIVO el banner se degrada a badge`; `test_local_api_panel.py::test_simulacro_se_anuncia_y_lo_real_lo_aborta`; `HomeView.test.tsx` | Las tres superficies rotulan y **codifican la precedencia con texto que cambia**, no solo un color. En móvil el aviso vive solo en la pantalla de inicio. |
| **C7** | 🟡 | `web/src/features/console/drill.ts:81`; `DrillHistory.tsx:34-42` | `drill.test.ts`; `test_drills_schedule.py::test_el_acuse_distingue_sin_gabinete_de_sin_acuse` | Hay reporte de acuse honesto por sitio. **Faltan los tiempos y cualquier forma de exportarlo.** |

### D · Estaciones e inventario

| # | Veredicto | Evidencia | Test | Razón |
|---|---|---|---|---|
| **D1** | 🟡 | `routers/sites.py:172`; `routers/sensors.py:152`→`queries/sensors.py:55`; `routers/fleet.py:494,550` | `test_fleet_admin.py::test_sensor_retire_keeps_the_row`, `::test_gateway_retire_and_restore_never_claims_online` | **Cero borrado duro** en las tres entidades: todo es retiro lógico. Faltan restore de sitio, lecturas individuales de sensor y gabinete, y edición/retiro de sensores en la consola. |
| **D2** | 🟡 | `MapPanel.tsx:96-168`; `DetailPanel.tsx:182-528`; `types.gen.ts:1346-1366` | `MapPanel.test.tsx::sin dato es GRIS, jamás verde`; `UpsGauge.test.tsx::estado desconocido ⇒ S/D (no finge 0%)` | El mapa y la ficha existen y **son honestos con los datos ausentes** — el medidor de respaldo no inventa un porcentaje. Falta identidad de hardware en la ficha, y el tipo de enlace no existe en ninguna capa. |
| **D3** | 🟢 | `local_api/__init__.py:1152-1202`, `:876-899`, `:790-806` | `test_local_api_panel.py::test_la_calibracion_dice_de_donde_viene`, `::test_sin_ubicacion_provisionada_no_hay_centro_inventado`, `::test_una_estacion_vecina_no_finge_medir` | Identidad, calibración con procedencia, sensor, umbrales **vigentes en el motor**, ubicación y vecinas. Probado por escena y medido contra el gabinete real. |
| **D4** | 🔴 | `RUNBOOK-ALTA-DE-ESTACION.md:122-124` vs `ingest/handlers.py:9-13,126` | — | **Siete divergencias** runbook↔código. La primera manda toda la ingesta a la cola de descarte; el runbook también documenta como inexistentes dos superficies que llevan meses en producción, omite la instalación del software y omite el equipamiento y el conjunto de reglas. |
| **D5** | 🔴 | `db/seeds/sim_fleet.sql:1-21`; ninguna marca en `web/src` | `test_fleet_sim.py::test_reparto_estacion_gateway_convencion_fija` (defiende la convención del seed, no la pantalla) | La separación vive en el seed y en el despliegue, no en la pantalla — que es justo donde se hace la demo. |

### E · Reportes, gráficas y evidencia

| # | Veredicto | Evidencia | Test | Razón |
|---|---|---|---|---|
| **E1** | 🟡 | `dictamen/pdf.py:57-77` (14 secciones), `:536-582` (ejecutivo) | `test_pdf.py::test_el_pdf_de_un_incidente_sin_mediciones_se_genera_igual`, `::test_un_incidente_sin_geometria_no_revienta_el_croquis`; `test_cctv_section.py::test_sin_camara_la_seccion_EXISTE_y_lo_declara` | Las 14 secciones existen y **todas degradan con un literal de ausencia**, nunca con un hueco. Fallan el hash truncado y el salto de numeración. |
| **E2** | 🔴 | `dictamen/builder.py:306-338`; `pdf.py:214-216` | `test_mseed.py::test_decodifica_exactamente_lo_que_escribio_el_edge` — **ningún test del render de la ausencia** | El texto de ausencia es concreto y honesto. Pero el worker que archiva la onda **no está desplegado**, así que la sección sale vacía siempre en la nube real. |
| **E3** | 🔴 | `dictamen/builder.py:341-362` (un solo `rfft`) | — | **No existe espectrograma.** Cero coincidencias de transformada por ventanas en todo el árbol. Aporta al pericial; a un cliente no técnico, no. |
| **E4** | 🟡 | `dictamen/sketch.py`; `pdf.py:102-165` | `test_matriz_trazabilidad.py` afirmación del croquis; `MapPanel.test.tsx::NO pinta bandas de intensidad` | El croquis es honesto y hay una guarda que **impide prometer una escala que no existe**. De las cuatro fichas de intensidad areal, solo la de intensidad instrumental mueve la aguja comercial. |
| **E5** | 🟢 | `dictamen/layout.py:103-108`; `routers/reports.py:97-111,115-130` | `test_pdf.py::test_el_mismo_modelo_produce_los_mismos_bytes`, `::test_la_huella_de_contenido_es_estable_y_cambia_con_el_contenido`; `test_reports.py::test_report_generates_pdf_evidence_and_audits`; `test_append_only.py::test_delete_blocked[evidence_objects]` | El PDF se hashea al generarse, se registra en tabla que no admite borrado y se audita dos veces; el determinismo del sello está defendido y el circuito se ejerció con hash idéntico verificado. |
| **E6** | 🟡 | `dictamen/model.py:51-55` y otros cinco deslindes; `compliance.py:74-87` | `test_compliance_section.py::test_el_deslinde_dice_las_tres_cosas_que_tiene_que_decir` (ancla carácter a carácter) — pero `test_pdf.py::test_ambos_llevan_el_deslinde` **no comprueba nada** | Once deslindes literales y completos en el papel. El que protege al proyecto en una reunión **no está defendido por ningún test que mire el documento**. |

### F · IA

| # | Veredicto | Evidencia | Test | Razón |
|---|---|---|---|---|
| **F1** | 🟢 | `settings.py:377-384`; `takab_api/narrative/__init__.py:51-52`; `narrative/openrouter.py:188,194` | `test_openrouter.py::test_apagado_no_abre_ningun_socket` (**sabotea el cliente HTTP entero**), `::test_sin_slug_de_modelo_no_se_enciende_aunque_el_flag_este_puesto` | Apagado, sin modelo, y el módulo **ni siquiera se importa** con la perilla en falso. Tres condiciones necesarias, no una. Ninguna variable de despliegue lo menciona. |
| **F2** | 🟢 | `api/tests/narrative/test_contract.py:24,34,57` | los tres, sin `skipif`, en el job que bloquea el merge | `test_narrative_no_tiene_donde_poner_un_veredicto` (nombres de campo), `test_la_capa_narrativa_no_puede_invocar_al_motor_de_reglas` (barrido del árbol de sintaxis), `test_el_veredicto_del_pdf_no_depende_de_la_prosa`. El tercero es más débil que su nombre. |
| **F3** | 🟡 | `narrative/base.py:28-61` (29 campos); `redact.py:33-42` (lista blanca doble) | `test_redact.py::test_el_nombre_del_inmueble_no_sale_de_la_nube`, `::test_las_coordenadas_no_salen_de_la_nube`, `::test_quien_firmo_no_sale` | **Ni un dato personal**: ni notas de ocupantes, ni coordenadas, ni firmante, ni identificador de dispositivo. Pero el folio exporta el código del sitio y ocho hex del incidente contra su propio docstring. |
| **F4** | 🔴 | `takab_api/narrative/__init__.py:75-81` (elige **un** proveedor) | — | No hay doble corrida, ni marca de sombra, ni identificador para emparejar las dos, ni persistencia de la razón del desacuerdo — **que sí se calcula y se tira**. |
| **F5** | 🔴 | `privacy/texts/aviso_es_mx.json` (no nombra un solo tercero) | — | **Conflicto con `D-20`: gana la decisión.** Se anota en §5. Lo que sí es un hueco propio: ningún gatillo de esa decisión se dispara al encender la perilla. |
| **F6** | 🔴 | `narrative/base.py:90`; `narrative/openrouter.py:209`; `routers/reports.py` | — | Coste por llamada contabilizado y tirado; techo de tokens por llamada. **Cero cuota, cero contador acumulado, cero corte, y el endpoint sin límite de frecuencia.** |

### G · Lo básico de un sistema de alertamiento

| # | Veredicto | Evidencia | Test | Razón |
|---|---|---|---|---|
| **G1** | 🟡 | `web/src/serverDataCensus.test.ts:487-494`; `mobile/src/app/(brigadista)/lista.tsx:205` | `serverDataCensus.test.ts::el recuento del censo es el que dice la ficha`, `::ninguno se calla una`; `test_local_api_panel.py::test_feature_vieja_no_se_pinta_como_medicion_viva`; `StateFrame.test.tsx` | La consola está **derivada y comparada por igualdad**: 21 componentes con dato de servidor, 12 con la prueba de los cuatro estados. Panel y móvil van por muestreo, y **no hay censo móvil**. |
| **G2** | 🟡 | `health/__init__.py:192-200`; `DetailPanel.tsx:292-296`; `schemas/fleet.py:162-163` | `test_fleet.py` (razón de degradación por desfase); `DetailPanel.test.tsx` | El desfase se mide de verdad con el demonio de reloj, viaja, se persiste y degrada el estado del sitio. **Ninguna de las 13 alarmas de la nube es de reloj**, y el panel lo pinta siempre en verde. |
| **G3** | 🟡 | `health/__init__.py:392-410`; `local_api/index.html:1303-1310`; `iot-core/main.tf:236-249` | `test_health.py`; `MultiChannelStrip.test.tsx::marca el clipping en su canal` | Lag, pérdida, saturación y última señal se miden y se pintan con umbrales en el gabinete; hay alarma de sensor mudo (nacida de un fallo real). **La pérdida de paquetes no llega a la nube.** |
| **G4** | 🔴 | `supervisor.py:592-600`, `:677` | `test_gpio_link.py::test_el_modo_prueba_ilegible_no_reporta_el_shake_caido` (defiende el fail-open, **no el ruido**) | El defecto sigue íntegro: nivel error por paquete, texto que afirma un daño que no ocurrió, sin agrupación. Medido en el gabinete real: 24 líneas, 0 incidentes. |
| **G5** | 🔴 | `local_api/index.html:1831,1837,1880,220`; `soc.css:787`; `notify/providers.py:47` | `test_local_api_panel.py::test_el_modo_demo_se_declara_siempre` (verifica **la cinta**, no que los botones estén inertes) | No existe modo demostración de sistema; y lo único que se llama demo es un reproductor de escenas **cuyos botones mandan órdenes reales**. |
| **G6** | 🟡 | `routers/incidents_ack.py:83-103`; `routers/mobile_incident.py:199-233` | `test_gov_ack.py` (7); `test_mobile_core.py::test_roster_cuenta_y_gatea` | Quién acusó y quién no respondió, sí, y distinguiendo *sin gabinete* de *sin acuse*. **El "en cuánto tiempo" no existe** para el acuse, y no hay endpoint que liste destinatarios. |
| **G7** | 🟢 | `audit.py:33-40,239`; `db/schema.sql:553-586,573-577` | `test_append_only.py::test_delete_blocked[audit_log]`; `test_append_only_dos_capas.py::test_capa_2_el_trigger_para_hasta_al_rol_mas_privilegiado`; `test_audit_single_writer.py::test_only_audit_module_inserts_audit_log`; `test_compliance_retention.py` | **72 verbos**, escritor único vetado por contract-test, dos capas independientes de inmutabilidad y exención de poda vigilada por tabla. Falta el verbo de firma del dictamen. |
| **G8** | 🔴 | `db/schema.sql:134`; `edge/takab_edge/config/settings.py:63-73`; `routers/rule_sets.py` | `test_rule_sets.py::test_stale_base_version_is_409_not_a_lost_update`, `::test_authz_edit_thresholds_only` — **sin test de rollback ni de tipología** | Versionado y conflicto por versión base son sólidos. **No hay tipo de inmueble** (toda la flota corre la banda de hospital), **no hay rollback**, y el camino consola→gabinete nunca se ejerció. |
| **G9** | 🟡 | `notify/providers.py:40-72,409-415`; `notify/twilio.py:549`; `notify/whatsapp.py:862`; `notify/push.py:255` | `test_notify_channels.py::test_los_canales_son_los_del_registro_no_una_lista_escrita_a_mano`; `test_orchestrator.py::test_canal_simulado_no_marca_sent` (+8 más) | Entregan **webhook y correo a verificados**. SMS, WhatsApp y push esperan altas. La honestidad es derivada, con default pesimista, y coincide fila por fila con el documento de entrega. |
| **G10** | 🟡 | `ops/restore_check.py`; `ops/restore_drill.py`; `RUNBOOK-backup-restore-db.md:71-110` | `test_restore_check.py` (**59 mutaciones destructivas**); `test_restore_drill.py` (29); cinco pruebas de Terraform | Mecanismo completo, honesto sobre lo que no midió, con 88 tests. **El tiempo de recuperación de producción no existe como número** y el registro del runbook está vacío. |
| **G11** | 🟡 | `api/src/takab_api/compliance.py:50-87`; `routers/compliance.py:78,96` | `TriagePage.test.tsx::no cita ninguna norma`; `test_compliance_surfaces.py::test_sin_etiquetas_el_movil_no_recibe_NADA_normativo` | **Cero normas escritas a fuego** en web, móvil, API o landing: el catálogo de afirmaciones no nombra ninguna, y la procedencia solo puede ser *declarada por el cliente*. El marco citable **no existe**, por decisión (`D-20`). |
| **G12** | 🔴 | `privacy/texts/aviso_es_mx.json`; `RESIDENCIA-DE-DATOS-TAKAB.md:395-420` | `test_privacy_artifacts.py::test_sin_revisar_es_provisional_y_dice_por_que` (verifica el **mecanismo**, no el contenido) | Siete terceros, ninguno declarado; falta la transferencia internacional. El mecanismo de versionado y consentimiento **sí es definitivo**; el texto se autodeclara provisional. |
| **G13** | 🟢 | `cloud/__init__.py:197`; `local_api/index.html:942`; `web/src/features/console/link.ts:24,75` | `test_cloud.py::test_offline_two_hours_then_reconnect_zero_loss_zero_dup` (+8); `test_local_api_panel.py::test_sin_enlace_a_nube_dice_que_la_proteccion_local_sigue`; `link.test.ts::SIN GABINETE ≠ SIN ENLACE` | Cola durable, cero pérdida y cero duplicados tras dos horas sin enlace, y la pantalla lo declara **en ámbar, no en rojo**, porque es el sistema funcionando. Verificado con navegador real contra el gabinete. |
| **G14** | 🔴 | `db/schema.sql:279`; `routers/incidents.py:43` | — | No hay clasificación, ni descarte, ni motivo de cierre, ni métrica. La tasa no es calculable ni a posteriori. |
| **G15** | 🟡 | `Makefile:92,102`; `demo/run.py:116,133`; `db/seeds/sim_fleet.sql:4-6` | `demo/tests/test_reset_guard.py`; `test_spool.py` | Reproducible desde cero y **bien aislado de producción** con tres guardias reales. Pero es un acreditador de CI: no rotula los datos como simulados y no toca simulacros. |

---

## 5 · Conflictos con decisiones e invariantes

Donde un ítem del encargo choca con una decisión escrita o con un invariante, **gana la decisión
y gana el invariante**. Se escriben aquí sin resolverlos.

1. **Ítem C5 (disparo por hora) ↔ regla de oro 8.** El ítem pide valorar un temporizador; la
   regla exige que el comando de actuadores lo emita **un humano con sesión viva**, firmado y con
   acuse. **La lectura compatible, y la que ya está implementada, es el armado**: la agenda
   anuncia, y a la hora el botón queda precargado para un clic humano. Un cron ciego se rechaza.

2. **Ítem F5 (encargado de datos) ↔ `D-20`.** El ítem pide levantar el asunto legal de encender
   la IA; `D-20` decidió que **la consulta legal espera a que un cliente la pida**, con tres
   gatillos escritos. Gana `D-20`. Lo que esta auditoría sí aporta, y cabe **dentro** de esa
   lógica: **ninguno de los tres gatillos se dispara al encender el proveedor** — la decisión se
   escribió cuando el caso no estaba sobre la mesa. Es un hueco del mecanismo de revocación
   (ficha `T-5.14`), no una petición de reabrir la decisión.

3. **Ítem B3 (uso comercial del catálogo) ↔ `D-20`.** Mismo choque, misma resolución. Se anota
   que el material **ya se redistribuye** en un documento firmado, que es un hecho nuevo respecto
   al momento en que se tomó la decisión.

4. **Ítem E4 (mini-ShakeMap) ↔ `BLUEPRINT §14`.** El mapa areal es la **única** viñeta diferida
   que una tarea puede derogar, y su derogación es un acto formal con nombre propio. La lectura
   compatible para V1-DEMO es **no tocarlo** y quedarse con la intensidad instrumental, que
   ningún invariante prohíbe.

5. **Ítem B2/B4 (cifras externas) ↔ invariantes 1 y 6.** Pintar epicentro y magnitud **no**
   contradice el invariante de la cuenta atrás: lo que este prohíbe es una cifra **derivada por
   nosotros del contacto seco**. Una cifra de una fuente externa citada, con su hora de consulta
   y su estado, es exactamente lo que el invariante contempla como *"fuente nueva y citable"*.
   La lectura compatible es: **con procedencia o no se pinta**.

6. **Ítem A5 ↔ `D-16`.** El ítem pregunta por relés reales; la compra del material de la ruta de
   hardware está autorizada solo para dominio y telefonía, y el resto quedó **sin fecha**. No se
   propone comprar: se ficha el gate con su dueño humano.

---

## 6 · Lo que esta auditoría NO comprobó

Escrito para que el informe no se lea como más completo de lo que es.

- **No se ejecutó ningún simulacro, ni una alerta real, ni una prueba de actuadores.** Todo lo de
  la cadena de vida se leyó del código, de los tests y del estado vivo del gabinete.
- **No se consultó la base de producción.** El conteo de 13 filas del catálogo es del seed y del
  hecho de que su inserción ignora conflictos; no excluye filas metidas a mano por otra vía.
- **No se midió ninguna latencia nueva.** Todas las cifras de este informe son citas de
  mediciones ajenas, con su fecha.
- **No se verificó si los checks del CI están marcados como obligatorios** en la protección de
  rama: eso no es visible desde el repositorio.
- **No se auditó el bloque de CCTV** salvo donde toca al PDF y a la retención: queda fuera del
  alcance de V1-DEMO.
- **El número de estaciones pintadas en el despliegue real: no encontrada.** La latencia real del
  sincronizado de configuración contra hardware: **no encontrada**. La latencia de publicación
  del feed del SSN: **no encontrada**.
