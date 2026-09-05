> **Sesión de AUDITORÍA. No se arregla nada en esta sesión.** Cada hallazgo se convierte en
> una ficha de `TASKS.md`, no en un commit de código. Si encuentras algo roto y "es de una
> línea", **no lo toques**: anótalo. Una sesión que audita y arregla a la vez no puede
> declarar qué encontró y qué causó.
>
> **Único entregable de código permitido:** los dos documentos de salida (§7) y la
> actualización de la cabecera de `TASKS.md` si el plan añade fichas.

---

## 1 · Contexto y objetivo

TAKAB Ailert va a salir a **exposiciones y reuniones con clientes**. El objetivo de esta
auditoría no es "terminar el producto": es **saber con evidencia qué se puede afirmar
delante de un cliente y qué no**, y planificar lo que falte para poder afirmarlo.

Lee antes de empezar, en este orden:

1. `CLAUDE.md` — contexto maestro, reglas de oro, método.
2. `takab-docs/TASKS.md` — cabecera, §"RUTA CRÍTICA" y §"INVARIANTES" (al final).
3. `takab-docs/PENDIENTES-MAURICIO.md` — lo bloqueado en una persona.
4. `takab-docs/DECISIONES-MAURICIO.md` — `D-01`…`D-21`, para no reabrir lo decidido.
5. `takab-docs/BLUEPRINT-TECNICO-TAKAB.md` §4 y §13.

**Definición de V1-DEMO (el alcance de esta auditoría):** el sistema que se puede enseñar y
vender sin que ninguna pantalla afirme algo que no se ha acreditado.

---

## 2 · Invariantes que la auditoría debe DEFENDER, no discutir

Estos vienen de `TASKS.md §INVARIANTES`. Una parte de este prompt los roza de cerca; si algún
ítem del checklist pareciera pedirlos, **el ítem se reinterpreta, no el invariante**.

1. **Nada de T-MINUS ni magnitud derivada del WR-1.** El WR-1 entrega un booleano. Cualquier
   cifra en la pantalla de alerta que no venga de una fuente externa citada es inventada.
2. **La IA jamás veta ni dispara una alerta.** Asesora, redacta, prioriza. `Narrative` no
   tiene campo de veredicto y un contract-test lo defiende. Si el plan propone tocar eso, se
   rechaza sin discusión.
3. **Nada de streaming continuo de onda cruda.** miniSEED a S3 solo en eventos confirmados.
4. **No se toca el Shake OS.**
5. **UDP datacast solo preview/debug.**

**Y un invariante nuevo que esta auditoría debe verificar como si ya existiera:**

6. **Procedencia obligatoria en toda cifra sísmica externa.** Epicentro, magnitud,
   profundidad y hora de origen que no midió nuestro instrumento se pintan **con su fuente,
   su hora de consulta y su estado de confirmación**, o no se pintan. "M 6.8" a secas en una
   pantalla es indistinguible de una cifra inventada.

---

## 3 · Checklist V1-DEMO

**Cómo se marca cada ítem.** No basta con encontrar el archivo. Cada ítem se cierra con
**evidencia citable**: `ruta/archivo.py:línea` del código que lo implementa **y** el test que
lo defiende. Sin test que lo defienda, el ítem es AMARILLO aunque el código exista.

Veredictos permitidos, y solo estos tres:

- **VERDE** — implementado, con test, y ejercido al menos una vez fuera de los tests
  (desplegado, o corrido a mano con evidencia).
- **AMARILLO** — el código existe pero le falta test, despliegue, o un gate externo.
- **ROJO** — no existe, o existe algo que no hace lo que su nombre dice.

---

### A · Cadena de vida — la señal del WR-1 de punta a punta

> **Esta es la única sección donde un AMARILLO es un problema comercial, no técnico.** Es lo
> que el cliente compra.

- [ ] **A1** · Cierre de contacto del WR-1 → reflejo a sirena in-process, con latencia medida
      y registrada. Localiza la medición y **di la cifra y la fecha**, no que "está medido".
- [ ] **A2** · El evento sube a la nube y aparece en el SOC. Traza la ruta completa:
      `gpio` → publicación → SQS/IoT → motor de incidentes → WebSocket → pantalla.
      **Anota el p95 declarado y dónde está medido.**
- [ ] **A3** · El evento llega a la app móvil (push + pantalla de alerta) y al panel LAN del
      gabinete. Verifica que los tres textos **dicen lo mismo** — si el SOC dice una cosa y
      el móvil otra, eso es un hallazgo de severidad alta.
- [ ] **A4** · El banner de alerta **no** muestra countdown ni magnitud (invariante 1).
      Verifica el texto literal en las tres superficies.
- [ ] **A5** · **Los relés: ¿MOCK o reales?** Di explícitamente en qué modo corre hoy el
      gabinete real y qué prueba existe de que un relé físico cerró.
- [ ] **A6** · Silencio y botón de prueba: qué hacen, qué NO paran, y si el silencio detiene
      también el voceo.
- [ ] **A7** · `G-02` — ¿suena la sirena con el Pi apagado? Reporta el estado real de esta
      mitigación y su decisión asociada.

---

### B · Procedencia del evento externo — "estimando epicentro" → confirmado

> **El bloque nuevo más grande de esta ronda.** Hoy existe `reference_earthquakes` +
> `GET /catalog/earthquakes`, pero es **semilla estática**: nadie la actualiza. Ver `T-2.149`
> (bloqueada) y `T-2.66.b` (decisión abierta).

- [ ] **B1** · Confirma que el catálogo actual es estático y **di cuántas filas tiene la
      semilla y de cuándo son**.
- [ ] **B2** · ¿Existe alguna máquina de estados de procedencia del evento externo? Se
      necesitan al menos estos, y el plan debe nombrarlos igual en las tres superficies:
      - `SIN_DATO_EXTERNO` — solo tenemos el booleano del WR-1.
      - `CONSULTANDO` — texto en pantalla: *"Consultando epicentro con SSN / USGS…"*
        (nunca *"el sistema está estimando"*: nosotros no estimamos, preguntamos).
      - `PRELIMINAR` — cifras con **fuente, hora de consulta y etiqueta PRELIMINAR**.
      - `CONFIRMADO` — cifras revisadas por la fuente, con su hora de revisión.
      - `SIN_CORRELACIÓN` — pasó la ventana y ninguna fuente reporta nada compatible.
        **Este estado es obligatorio:** su ausencia convierte un "no sé" en una pantalla
        vacía que el operador leerá como "no pasó nada".
- [ ] **B3** · El ingestor: evalúa **fuentes oficiales con API, no scraping de HTML**. Al
      menos USGS FDSN event + el catálogo del SSN. Documenta para cada una: si tiene API
      pública, licencia/términos de uso, latencia típica de publicación y si permite uso
      comercial. **Si una fuente no permite uso comercial, eso es un hallazgo legal, no
      técnico.**
- [ ] **B4** · Correlación: ¿con qué criterio se decide que un evento del catálogo es *el
      mismo* que disparó nuestro WR-1? Ventana temporal, distancia, magnitud mínima. Sin
      criterio explícito, el sistema puede colgarle a nuestra alerta un sismo de otro país.
- [ ] **B5** · Fail-open: si la fuente externa está caída, la alerta local **no se degrada**.
      La cadena de vida no puede depender de internet (regla de oro).
- [ ] **B6** · La cifra externa **nunca** entra al motor de reglas ni al veredicto del
      dictamen. Verifica que no hay ese acoplamiento y que un test lo defiende.

---

### C · Simulacros

> Existe `api/src/takab_api/routers/drills.py` y `edge/takab_edge/drill/`. **Audita lo que
> hay antes de proponer nada nuevo.**

- [ ] **C1** · Lo que ya funciona: agenda (`scheduled_at`), disparo, paro, cancelación, acuse
      por sitio, `from_scheduled`, banner "SIMULACRO — NO ES REAL", `commandable`.
      **Enumera qué hace hoy, con rutas.**
- [ ] **C2** · "Lo real gana": verifica que un SASMEX real aborta el drill y que el drill
      **jamás** toca relés. Nombra el test.
- [ ] **C3** · ¿Existen **plantillas de simulacro guardadas y editables** (ej. el macrosimulacro
      de septiembre, evacuación por piso, prueba trimestral)? Si no, es ficha nueva.
- [ ] **C4** · ¿Se puede **elegir el sonido** del simulacro? Hoy `edge/takab_edge/audio/`
      tiene assets fijos de sismo y simulacro con sha256 registrado. Un selector de audio
      debe conservar esa propiedad: **qué sonó exactamente queda auditable**.
- [ ] **C5** · Disparo por hora. **Ojo con la regla de oro 8** (el disparo lo hace un humano
      con sesión viva). Si se propone un temporizador automático, el plan debe explicar cómo
      convive con esa regla — probablemente como *"armado + confirmación de un humano en la
      ventana"*, no como cron ciego.
- [ ] **C6** · Animación distinta por superficie: SOC, panel LAN y móvil deben ser
      **inconfundibles** con una alerta real. Evalúa qué hay hoy y qué falta.
- [ ] **C7** · Reporte post-simulacro: quién acusó, en cuánto tiempo, qué sitios no
      respondieron. Es el entregable que el cliente enseña a Protección Civil.

---

### D · Estaciones e inventario

- [ ] **D1** · CRUD de sitios, sensores y gabinetes: confirma qué existe hoy
      (`routers/sites.py`, `routers/sensors.py`, `routers/fleet.py`) y qué operaciones
      faltan. Presta atención a **baja vs. retiro**: un borrado duro rompe la trazabilidad
      histórica de incidentes.
- [ ] **D2** · Mapa SOC con todas las estaciones y su ficha. ¿Qué campos muestra y cuáles
      faltan para una demo (modelo, firmware, última señal, enlace, batería)?
- [ ] **D3** · Vista de la estación local en el panel LAN del gabinete: qué muestra hoy.
- [ ] **D4** · Alta de estación de punta a punta: ¿está el runbook
      (`RUNBOOK-ALTA-DE-ESTACION.md`) alineado con lo que hace el código hoy? Un runbook que
      diverge del código es un hallazgo.
- [ ] **D5** · Datos de demostración: ¿se distinguen visualmente de los reales? Un gabinete
      simulado que se ve igual que uno real en una demo es un riesgo de credibilidad.

---

### E · Reportes, gráficas y evidencia

> `dictamen/pdf.py` ya produce dos documentos con croquis, trazas, onda cruda y espectro.
> **Audita, no reescribas.**

- [ ] **E1** · Qué contiene hoy el PDF técnico y el ejecutivo. Enuméralo.
- [ ] **E2** · Sismograma y espectro: confirma que existen y bajo qué condiciones aparecen
      (best-effort desde S3). **Di qué pasa cuando no hay miniSEED** — el PDF debe explicar
      la ausencia, no dejar un hueco.
- [ ] **E3** · **Espectrograma** (tiempo-frecuencia): ¿existe? Si no, ficha nueva.
      Justifica en el plan si aporta a un cliente no técnico o solo al pericial.
- [ ] **E4** · **ShakeMap / mapa de intensidad del inmueble**: hoy hay croquis vectorial sin
      cartografía base (decisión documentada). Fase 3.1 (`T-3.06`…`T-3.09`) está entera
      abierta: MMI instrumental, Sa, deriva de entrepiso, mini-ShakeMap. **Evalúa cuáles de
      esas cuatro son necesarias para V1-DEMO y cuáles no** — no todo lo abierto es urgente.
- [ ] **E5** · Firma, sha256 y cadena de custodia del PDF: verifica que están y que un test
      los defiende.
- [ ] **E6** · Deslinde impreso: qué dice hoy el documento sobre lo que el sistema **no**
      hace. Es lo que protege al proyecto en una reunión comercial.

---

### F · IA (OpenRouter)

> `narrative/openrouter.py` está **completo y apagado** (`openrouter_enabled=False`), con
> guardrail, redacción y fail-open al determinista. Fase 3.0 (`T-3.01`…`T-3.05`) es lo que
> falta.

- [ ] **F1** · Verifica el estado real: apagado, sin slug de modelo, sin abrir socket por
      defecto.
- [ ] **F2** · Los tres contract-tests que impiden que la IA toque el veredicto: nómbralos y
      confirma que pasan.
- [ ] **F3** · `narrative/redact.py`: **qué se le envía exactamente a OpenRouter**. Enumera
      los campos. Si va un solo dato personal (nombre, teléfono, ubicación de una persona),
      es hallazgo de severidad alta.
- [ ] **F4** · Shadow-mode (`T-3.01`, `T-3.02`): qué haría falta para encenderlo registrando
      procedencia y midiendo acuerdo/desacuerdo contra el determinista, **sin que ninguna
      salida llegue todavía al usuario**.
- [ ] **F5** · **`GATE-LEGAL` nuevo:** OpenRouter es un **encargado de datos** bajo LFPDPPP.
      Encenderlo con datos de clientes reales exige aviso de privacidad actualizado y
      cláusula contractual. Levanta esto como ficha con dueño humano, no como tarea de
      código.
- [ ] **F6** · Costo: ¿hay tope de gasto, por tenant y por mes? Un tercero con costo por
      request y sin tope es la categoría de riesgo que OWASP llama *unrestricted resource
      consumption*, y ya está en el blueprint.

---

### G · Lo básico que un sistema de alertamiento debe tener y no está en la lista de arriba

> **Esta sección la audita Claude Code sin que nadie se la pida.** Son los ítems que no se
> echan de menos hasta que fallan delante de un cliente.

- [ ] **G1** · **Honestidad de dato viejo.** Toda pantalla que muestre un número debe poder
      declarar que ese número está rancio o que no lo tiene. Verifica cobertura en SOC, panel
      LAN y móvil. Un "● LIVE" sobre datos de hace diez minutos es el peor fallo posible en
      una demo.
- [ ] **G2** · **Reloj.** Offset NTP visible y alarmable. Sin hora confiable, ninguna
      evidencia sirve.
- [ ] **G3** · **Salud del enlace y del sensor**: packet loss, lag de SeedLink, clipping,
      última señal. Qué se ve y dónde.
- [ ] **G4** · **Modo mantenimiento / ventana de prueba**, para que probar no despierte a
      nadie. Ojo: `T-2.172` reporta que el fail-open del modo prueba grita 24 veces por
      ventana. Confirma si sigue vivo.
- [ ] **G5** · **Modo demostración**: un estado explícito en el que el sistema **no** dispara
      notificaciones reales, **no** cierra relés y lo anuncia en pantalla. ¿Existe? Si no, es
      probablemente la ficha más urgente de todo este documento: sin él, cada exposición es
      un riesgo de disparar algo real o de enseñar datos falsos sin etiquetar.
- [ ] **G6** · **Cadena de acuse**: quién recibió la alerta, quién acusó, en cuánto tiempo,
      quién no respondió. Es la métrica que el cliente va a pedir.
- [ ] **G7** · **Bitácora de auditoría inmutable**: qué se registra y qué no se puede borrar.
- [ ] **G8** · **Umbrales por tipo de inmueble** y quién puede cambiarlos, con versionado y
      rollback.
- [ ] **G9** · **Notificación real**: estado de Twilio, WhatsApp y SES. Di cuáles están
      construidos y cuáles esperan un alta administrativa.
- [ ] **G10** · **Respaldo y restauración**: estado de `T-2.72.a` y `T-2.74` (`G-09`).
      Un cliente institucional pregunta esto en la primera reunión.
- [ ] **G11** · **Marco normativo citable** (`T-2.96`). **Si un cliente pregunta "¿bajo qué
      norma opera esto?", ¿hay una respuesta escrita hoy?** Verifica también que ninguna
      etiqueta normativa esté hardcodeada: deben venir del endpoint de compliance.
- [ ] **G12** · **Aviso de privacidad y encargados** (LFPDPPP): lista de terceros que tocan
      datos (OpenRouter, Twilio, Meta, AWS) y si están declarados.
- [ ] **G13** · **Qué pasa cuando se cae internet**: verifica que existe y está probado el
      comportamiento degradado, y que la pantalla lo dice.
- [ ] **G14** · **Falsos positivos**: ¿hay forma de contarlos hoy? Es la métrica que decide
      si el cliente renueva.
- [ ] **G15** · **Guion de demo reproducible**: ¿se puede levantar una demo completa desde
      cero, con datos etiquetados como simulados, sin tocar producción?
      Revisa `demo/` y di si sirve para una exposición o solo para CI.

---

## 4 · Cómo tratar los conflictos

Si un ítem del checklist choca con una decisión de `DECISIONES-MAURICIO.md` o con un
invariante: **gana la decisión y el invariante**. Escribe el conflicto en el informe con la
referencia (`D-xx` o el número del invariante) y **no lo resuelvas por tu cuenta**.

Si un ítem parece pedir algo que el proyecto ya rechazó por escrito, dilo así de claro:
*"Este ítem propone X; X está prohibido por el invariante N; la lectura compatible es Y."*

---

## 5 · Prohibiciones de esta sesión

1. **No arreglar nada.** Ni un typo, ni un test rojo, ni un import sin usar.
2. **No reescribir lo que ya funciona.** Si el checklist menciona algo que ya existe, el
   trabajo es auditarlo, no rehacerlo.
3. **No inventar cifras.** Si no encuentras una medición, escribe "no encontrada", no una
   estimación.
4. **No marcar VERDE por la existencia de un archivo.** Un archivo llamado `spectrogram.py`
   no es un espectrograma; ábrelo.
5. **No proponer IA en la ruta determinista**, en ninguna forma, ni "solo para filtrar".

---

## 6 · Un aviso sobre el modo de fallo de esta auditoría

El fallo característico de este proyecto, documentado en su propia historia, es
**la superficie que miente en verde**: el conteo de `TASKS.md` que llevaba 36 tareas de
retraso, `T-2.143` desplegado y sin hacer nada, el SOC diciendo "● LIVE" mientras estaba
mudo, el checklist de gas y puertas en verde sin gas ni puertas.

**Esta auditoría existe para encontrar la próxima de esas, no para producir una lista bonita
de palomitas.** Un informe con 60 VERDES y ningún hallazgo es, casi con certeza, un informe
mal hecho. Si algo se ve demasiado bien, ejercítalo antes de creerle.

---

## 7 · Entregables

### 7.1 · `takab-docs/INFORME-V1-COMERCIAL.md`

- Tabla con **un renglón por ítem** del checklist (A1…G15): veredicto, evidencia
  (`ruta:línea`), test que lo defiende, y una línea de razón.
- Resumen ejecutivo de máximo 15 renglones: **qué se puede afirmar hoy delante de un cliente
  y qué no.** Esta parte se escribe pensando en que Mauricio la lea antes de una reunión.
- **Lista de hallazgos** numerados `H-01`, `H-02`… con severidad (ALTA / MEDIA / BAJA),
  donde ALTA = una pantalla que miente, un dato personal que se fuga, o una afirmación
  comercial no acreditable.
- Sección **"Lo que NO debe decirse en una demo hoy"**: afirmaciones concretas que el estado
  actual no respalda. Sé literal, con las frases exactas que hay que evitar.

### 7.2 · `takab-docs/PLAN-V1-COMERCIAL.md`

- Fichas nuevas en **el formato exacto de `TASKS.md`** (encabezado `### [ ] T-x.xx · …`,
  componente, depende de, objetivo, criterios de aceptación). Numéralas en un bloque nuevo
  que no colisione con lo existente y dilo explícitamente.
- Cada ficha con **etiqueta de tipo de bloqueo**: `SOFTWARE`, `DECISIÓN`, `GATE-HW`,
  `GATE-AWS`, `GATE-LEGAL`, `GATE-STORE`.
- **Ruta crítica hacia V1-DEMO**, con la misma honestidad que la ruta actual de `TASKS.md`:
  di cuántos de los ítems críticos dependen de código y cuántos de un humano con agenda.
- **Orden de ejecución propuesto en tres tandas**: lo que hay que tener para la **primera**
  exposición, lo que puede esperar a la segunda, y lo que puede esperar al primer contrato
  firmado. Esta separación es el valor principal del documento — sin ella el plan es una
  lista de deseos.
- **Estimación por ficha en sesiones de Claude Code**, no en horas.

### 7.3 · Actualización de `takab-docs/TASKS.md`

Solo si el plan añade fichas: **actualiza la cabecera de conteo en el mismo commit**, como
exige `test_la_cabecera_de_tasks_declara_el_conteo_real`.

---

## 8 · Criterios de aceptación de la sesión

- [ ] Los 60+ ítems del checklist tienen veredicto y evidencia citable. **Ninguno sin marcar.**
- [ ] Todo VERDE tiene ruta y test. Todo ROJO tiene ficha en el plan.
- [ ] Los hallazgos de severidad ALTA están en el resumen ejecutivo, no enterrados en la tabla.
- [ ] La sección "Lo que NO debe decirse en una demo hoy" existe y es específica.
- [ ] Ningún fichero de código modificado (`git status` limpio salvo los tres documentos).
- [ ] `make lint` y `make test` siguen verdes.
- [ ] Todo va por rama + PR con los siete checks. **Nada de push directo a `main`.**
- [ ] Commits con autoría única de Mauricio, Conventional Commits, sin footers de IA.
