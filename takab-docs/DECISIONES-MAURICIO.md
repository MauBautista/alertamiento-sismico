# Decisiones de Mauricio — bitácora

> **Qué es esto.** Cada decisión que salió de `PENDIENTES-MAURICIO.md` **con su razón escrita**.
> Aquella lista es el censo de lo que **falta**; ésta es el registro de lo que **se decidió**, y
> existe por un motivo concreto: **una decisión sin su razón no se puede revocar con
> conocimiento** — solo se puede olvidar o darle marcha atrás a ciegas.
>
> **Regla de esta bitácora:** una decisión no se borra nunca. Si se revoca, se le añade abajo el
> bloque `REVOCADA` con la fecha y el porqué, dejando el texto original intacto. Lo que se
> aprendió al equivocarse vale más que el acierto.
>
> **Identificadores estables (`D-nn`).** Cítalos desde el código y desde `TASKS.md` en vez de citar
> el `§` de la lista de pendientes: aquellos números se reciclan cuando la lista encoge, éstos no.
>
> **Última actualización:** 2026-08-17 · **21 decisiones** · 18 tomadas por Mauricio (6 el
> 2026-08-15, 2 el 2026-08-16, **10 el 2026-08-17**), 3 delegadas el 2026-08-12.
>
> **Lo que cambió el 2026-08-17, y merece el titular:** `PENDIENTES-MAURICIO §1` llevaba dos días
> cerrada, pero **quedaban diez decisiones enterradas dentro de puntos de acción** —el runbook de
> SES tenía seis en una tabla en blanco (`D-1`…`D-6` de su §2.2), el manual de operación citaba un
> teléfono que no existía, y `D-08` había dejado el CCTV a medias—. Una decisión escondida dentro
> de una tarea **no se ve como decisión**: se ve como trabajo bloqueado sin culpable. De ahí
> `D-12`…`D-21`.
>
> **La lección de método, que vale más que las diez decisiones:** `§1` se pudo declarar cerrada
> porque **enumeraba a mano** lo que contaba como decisión. Todo lo que vivía dentro de la tabla de
> un runbook, de una fila en blanco de un manual o de una nota al pie de otra decisión **no estaba
> en el censo** — y por tanto no existía. Es la misma doctrina que ya dejó escrita
> `TRASPASO-SESION`: **un censo que enumera a mano acaba divergiendo.**

---

## Índice

| ID | Decisión | Fecha | Quién |
|---|---|---|---|
| [D-01](#d-01) | Entre `empty` y `stale`, **gana `stale`** | 2026-08-12 | delegada |
| [D-02](#d-02) | `lock_timeout` en la conexión del request: **se pone, ~10 s** | 2026-08-12 | delegada |
| [D-03](#d-03) | La consola **arranca con la base caída**, en degradado y declarándolo | 2026-08-12 | delegada |
| [D-04](#d-04) | Dueño de los pines GPIO: **ventana avisada (A)**, nunca hardware | 2026-08-15 | Mauricio |
| [D-05](#d-05) | Push de pánico: **solo a tácticos (B)**, y sin acuse **escala al SOC** | 2026-08-15 | Mauricio |
| [D-06](#d-06) | Catálogo SSN: **se automatiza** la ingesta | 2026-08-15 | Mauricio |
| [D-07](#d-07) | Teléfono del consentimiento: **cripto-borrado** | 2026-08-15 | Mauricio |
| [D-08](#d-08) | Bloque IV (mini-ShakeMap y CCTV): **se planifica ya** | 2026-08-15 | Mauricio |
| [D-09](#d-09) | `enforce_admins`: **queda en `false`, con gatillo escrito** | 2026-08-15 | Mauricio |
| [D-10](#d-10) | Ruta de hardware de la sirena: **variante B**, fallback con watchdog | 2026-08-16 | Mauricio |
| [D-11](#d-11) | El quórum de pánico **abre incidente** `trigger='manual'` | 2026-08-16 | Mauricio |
| [D-12](#d-12) | Dominio raíz **`takabailert.com`**, DNS en Route 53 *(enmendada 21-ago)* | 2026-08-17 | Mauricio |
| [D-13](#d-13) | Teléfono de soporte: **número Twilio mexicano**, no un móvil personal | 2026-08-17 | Mauricio |
| [D-14](#d-14) | CCTV: **híbrido** — aforo en sitio + clips de evento confirmado | 2026-08-17 | Mauricio |
| [D-15](#d-15) | Sirena por jack: **encendida** en el gabinete de desarrollo | 2026-08-17 | Mauricio |
| [D-16](#d-16) | Compras: **sí** dominio y Twilio · **no todavía** BOM de `G-02` ni Apple | 2026-08-17 | Mauricio |
| [D-17](#d-17) | La ventana AWS se parte en **dos**: applies (A) y restore (B) | 2026-08-17 | Mauricio |
| [D-18](#d-18) | `console_scope_enforced`: **se enciende ya**, con los tests en el mismo commit | 2026-08-17 | Mauricio |
| [D-19](#d-19) | Tono de alerta de la app: **propio**, no el oficial de CIRES | 2026-08-17 | Mauricio |
| [D-20](#d-20) | Consulta legal: **espera a que un cliente la pida** | 2026-08-17 | Mauricio |
| [D-21](#d-21) | Sesión de vida: **se parte** — `G-01` esta semana, solo | 2026-08-17 | Mauricio |

---

<a id="d-04"></a>
## D-04 · Dueño de los pines GPIO — **ventana de mantenimiento avisada (A)**

**Fecha:** 2026-08-15 · **Decide:** Mauricio · **Venía de:** `PENDIENTES-MAURICIO §1.1` ·
**Ficha:** `T-2.70.a`, criterio 4 · **Desbloquea:** `T-2.70` (canary + rollback)

**La decisión.** Pasar el dueño de los pines a su propio proceso cuesta **un ciclo eléctrico** de
`GAS_VALVE` y `DOOR_RETAINER` — el gas se cierra y las puertas se sueltan, una vez. Se acepta ese
coste como **ventana avisada**, y se **descarta la salida por hardware**.

**La política, en dos partes y con la segunda como la que de verdad importa:**

1. **En el gabinete de desarrollo, el traspaso se hace ya y es gratis.** Medido contra su propia
   API: `relays_status.installed = ["siren","strobe"]` — **no tiene `GAS_VALVE` ni
   `DOOR_RETAINER` instalados**, así que no hay bobina que caer. El despliegue del 2026-08-12 no
   cicló nada: los dos relés siguieron desenergizados antes y después.
2. **En toda instalación real, el traspaso se hace en la PUESTA EN MARCHA** — antes de que el
   edificio dependa del sistema. Hecho en ese momento el ciclo **no le cuesta nada a nadie**,
   porque todavía no hay nada que proteger. Nunca en un gabinete ya en servicio salvo ventana
   avisada y aceptada por el cliente.

**Por qué no (B) —el hardware—.** El enclavamiento del relé o el pull-up que sostiene la bobina con
la línea liberada **cambia SPOF-07**: un Pi colgado dejaría de fail-safear gas y puertas. Compraba
evitar un ciclo que, hecho en el momento correcto, **es gratis**. Pagar con el fail-safe algo que
se puede obtener con calendario es mal negocio, y el fail-safe es lo que protege al edificio el día
que el Pi se cuelgue de verdad.

**Lo que hay que recordar al ejecutarlo:** el orden no es intercambiable, y por eso **no se hace a
mano** — lo hace `deploy/edge/deploy.sh`, que lo lee del gabinete, lo ordena y **verifica el
cerrojo** en su paso 7. Basta con declarar `TAKAB_EDGE_GPIO_OWNER=gpio` en `/etc/takab/edge.env` y
desplegar. Detalle y motivos, en `PENDIENTES-MAURICIO §3.5`.

> **✅ EJECUTADA en el gabinete de desarrollo el 2026-08-16.** `takab-gpio` sostiene los pines
> (paso 7 del despliegue: pid + unidad), `takab-edge` dejó de tocarlos, y el coste eléctrico fue
> **cero** — tal como predecía la medición. `T-2.70` queda desbloqueada.
>
> **La parte 2 de la política sigue viva y es la que importa:** en instalaciones reales, el
> traspaso va en la **puesta en marcha**. Esta decisión no se agota al ejecutarla en dev.

**Cómo se revocaría:** solo tiene sentido revocarla si aparece un cliente cuyo gabinete **no puede
tener ventana de puesta en marcha** (retrofit sobre un edificio en operación continua que prohíbe
un ciclo de gas). Ahí (B) volvería a la mesa **para ese sitio**, y con SPOF-07 re-evaluado por
escrito, no como excepción tácita.

---

<a id="d-05"></a>
## D-05 · Push de pánico — **solo a tácticos (B)**, con escalado al SOC

**Fecha:** 2026-08-15 · **Decide:** Mauricio · **Venía de:** `PENDIENTES-MAURICIO §1.7` ·
**Ficha:** `T-2.106`

**La decisión.** Cuando el quórum de pánico confirma, se manda push **solo a los roles tácticos**
(brigada, seguridad). **Y si ninguno acusa recibo en ~2 min, se levanta un aviso en la consola
SOC** — no se escala automáticamente al edificio.

**Lo que era cierto pase lo que pase, y conviene no perderlo de vista:** la sirena **ya suena** (el
quórum ya emite el comando) y la app **ya explica** la alarma. Lo único que esta decisión añadía
era **si además vibra el teléfono de alguien que está dormido**.

**La razón de (B) sobre (A).** La sirena ya cubre a todo el mundo; el push añade valor solo para
**quien tiene que hacer algo**. Y es la única de las tres opciones que **no cambia** si mañana
resulta que hay pánicos falsos: con (A) —push a todos— habría que dar marcha atrás delante de todo
el edificio. **Dos personas no deben poder despertar a 400**, porque un pánico falso a las 3 a.m.
quema credibilidad, y la credibilidad es exactamente lo que hace que la gente obedezca **la
siguiente** alerta, que puede ser la de verdad.

**La razón del escalado al SOC en vez de escalar a todos.** El agujero conocido de (B) es que la
brigada no conteste. Escalar automáticamente al edificio reintroduce (A) por la puerta de atrás,
solo que dos minutos después. Avisar al SOC pone a **un humano con contexto** a decidir si esto
merece despertar al edificio: **una máquina no debería tomar esa decisión por un timeout.**

**Lo que esto implica para el software** (deuda declarada aquí, no cerrada):
- La ruta del voto de pánico **no toca `notify/` hoy**. Hay que cablearla.
- Hace falta **acuse de recibo del táctico** — hoy no existe como concepto en ese flujo.
- El temporizador de ~2 min y el aviso al SOC son parte de la misma ficha; el aviso debe ir
  también a la cadena on-call de `PENDIENTES-MAURICIO §2.9` **cuando exista**, no antes.

---

<a id="d-06"></a>
## D-06 · Catálogo SSN — **se automatiza la ingesta**

**Fecha:** 2026-08-15 · **Decide:** Mauricio · **Venía de:** `PENDIENTES-MAURICIO §1.4` ·
**Ficha:** `T-2.66.b`

**La decisión.** La ingesta del catálogo sísmico se **automatiza contra el SSN** con un job
periódico. No se sube a mano ni se declara congelado.

**El contexto que la hacía necesaria.** El push firmado nube→gabinete existe y está verificado
E2E (`T-2.24`: se empuja desde la nube y el Pi cambia en caliente). Lo que faltaba era el otro
extremo: **nadie ingesta el catálogo**, así que el canal firmado no tenía qué transportar.

**El riesgo que se acepta al elegirla, y su mitigación obligatoria.** La fuente es de un tercero
**sin contrato**: si el SSN cambia de formato o cae, el catálogo se congela **en silencio**, que es
el modo de fallo que más caro sale en este sistema. Por eso la automatización **no está completa
sin**:

- **Declarar la fecha del último catálogo ingerido con éxito**, visible en la UI. Esto es
  [D-01](#d-01) aplicada al caso: un catálogo viejo se declara viejo, no se presenta como vivo
  (regla de oro 7).
- **Alarma por ausencia**, no por error: si no entra catálogo nuevo en el plazo esperado, avisa.
  Un scraper que falla en silencio produce exactamente la conducta que esta decisión quería evitar.
  Es la misma lección de la alarma del gabinete mudo: **se vigila la ausencia del latido.**

---

<a id="d-07"></a>
## D-07 · El teléfono del consentimiento — **cripto-borrado**

**Fecha:** 2026-08-15 · **Decide:** Mauricio · **Venía de:** `PENDIENTES-MAURICIO §1.3` ·
**Ficha:** `T-2.80.a` · **Postura por defecto, sujeta a la revisión legal de `T-2.96` (`§4.1`)**

**El hueco, medido.** ARCO alcanza al titular identificado por `sub` de Cognito. Un sujeto
identificado por **teléfono** tiene su número **en claro** en `privacy_consents.subject_ref`, y esa
tabla es **append-only** por el motor de `T-2.79`. Anonimizarlo exigía **abrir un hueco en el
guard**, y eso obligaba a elegir entre el derecho del titular sobre su número y la prueba de la
base legal del envío que ese consentimiento autoriza.

**La decisión: no se elige entre los dos bienes.** El número se guarda **cifrado con clave por
sujeto**; ejercer ARCO **destruye la clave**. Con eso:

- La tabla append-only queda **byte a byte intacta** — el guard no se abre.
- El digest **sigue probando la integridad** del registro.
- Se conserva la prueba de **que hubo consentimiento y cuándo**.
- Se destruye, de forma real e irreversible, la capacidad de leer **a quién**.

**Por qué no las otras dos.** «Prevalece el titular» resolvía el derecho **abriendo una rendija en
una tabla append-only** — pequeña y auditada, pero rendija, y el valor de esa tabla es justamente
que no las tiene. «Prevalece la prueba» dejaba un derecho **sin atender** que habría que defender
ante el titular y ante el INAI, apoyándose en una obligación de conservación que **nadie ha
confirmado todavía que exista** — y confirmarla es precisamente lo que falta (`§4.1`).

**Lo que esta decisión NO resuelve, y hay que llevarle al abogado:** si un número **cifrado** sigue
siendo dato personal mientras la clave exista (lo normal es que sí), y si la destrucción de clave
se acepta como cancelación a efectos de la LFPDPPP. **Esta postura se lleva a la consulta de
`§4.1`, no la sustituye.**

---

<a id="d-08"></a>
## D-08 · Bloque IV — **se planifica ya** (mini-ShakeMap y CCTV)

**Fecha:** 2026-08-15 · **Decide:** Mauricio · **Venía de:** `PENDIENTES-MAURICIO §1.5` ·
**Fichas:** `T-3.09` (mini-ShakeMap), `T-3.10` (arquitectura CCTV)

**La decisión.** Las dos entran en diseño ahora, en vez de esperar a que las pida un cliente.
Asumido el coste: **desvía esfuerzo de la ruta crítica hacia el primer cliente**, que es lo que
había que sopesar.

> ### ⚠️ La trampa de ejecución de esta decisión — léela antes de tocar el blueprint
>
> `T-3.09` **exige derogar por su nombre** la viñeta `[DIFERIDO · mini-ShakeMap]` de
> `BLUEPRINT §14`, y hay que actualizar también la viñeta correspondiente de `CLAUDE.md §8`.
>
> **La viñeta de al lado NO se toca.** Es `[INVARIANTE · streaming crudo continuo]`, que es la
> **regla de oro 9**. Las dos iban pegadas en una sola línea precisamente porque así se derogaban
> juntas por accidente. **Derogar solo la del mini-ShakeMap, y por su nombre.**

**Lo que la decisión no dice, y conviene fijar al abrir las fichas:** «planificar» es diseño y
fichas con criterios de aceptación, **no** implementación. El orden del proyecto (edge → cloud →
frontend) y la prioridad del primer cliente no se alteran por esto.

> ### ✅ EJECUTADA (2026-08-16) — y con un matiz que evitó una derogación prematura
>
> El diseño está escrito: [`design/BLOQUE-IV-ARQUITECTURA.md`](design/BLOQUE-IV-ARQUITECTURA.md),
> y las dos fichas ganaron los criterios que salen de él.
>
> **La viñeta NO se derogó, y es lo correcto.** `[DIFERIDO · mini-ShakeMap]` prohíbe
> **implementar**; esta decisión autorizó **planificar**. Derogarla al diseñar habría sido
> prematuro —y habría puesto en rojo la guarda de `§14` sin necesidad—. Se deroga al ejecutar
> `T-3.09`, que es lo que `CLAUDE.md §8` dice desde el principio.
>
> **Dos hallazgos del diseño que cambian el alcance de las fichas:**
> - **El mini-ShakeMap NO será un microservicio.** La viñeta diferida hablaba de uno, pero lo que
>   se calcula **no es continuo**: se calcula por evento en el worker que ya existe. Un servicio
>   más es un despliegue, una alarma y un rol IAM más, a cambio de nada.
> - **Depende de `T-2.149`** (el catálogo del SSN, hoy bloqueado): sin magnitud y epicentro no hay
>   capa estimada. El mapa existirá **degradado y declarándolo**, nunca inventando un epicentro.
>
> **Y una recomendación para el CCTV que conviene decidir pronto:** procesar el aforo **en el
> sitio** y subir solo el número elimina casi toda la superficie de PII de vídeo. Si el vídeo no
> sale del inmueble salvo por una acción explícita y auditada, media sección de privacidad
> desaparece.

---

<a id="d-09"></a>
## D-09 · `enforce_admins` — **queda en `false`, con gatillo escrito**

**Fecha:** 2026-08-15 · **Decide:** Mauricio · **Venía de:** `PENDIENTES-MAURICIO §1.6`

**El estado real.** La protección de rama sobre `main` está viva y bien: los **siete** checks
exigidos, con los nombres **coincidiendo literalmente** con los `name:` de `ci.yml` — importa,
porque un nombre que no case no bloquea, deja los PR *pendientes para siempre*, que se siente como
un fallo distinto y se diagnostica peor.

**La decisión.** `enforce_admins` se queda en **`false`** mientras Mauricio sea el único admin.

**El gatillo, que es la mitad que importa:** se pone en **`true` el día que entre una segunda
persona con acceso de push al repositorio.** Ese día deja de ser una válvula de escape personal y
pasa a ser un agujero heredado.

**Por qué así y no `true` ya.** Trabajando solo, un check en rojo por causa ajena —runner de GitHub
caído, un flaky— dejaría el repositorio bloqueado **sin un segundo admin que lo desatasque**. Lo
que hacía falta no era cerrar el agujero hoy: era **que fuera una elección y no un olvido**. Ahora
lo es.

---

<a id="d-10"></a>
## D-10 · Ruta de hardware de la sirena — **variante B, fallback con watchdog**

**Fecha:** 2026-08-16 · **Decide:** Mauricio · **Venía de:**
`RUNBOOK-SPOF-02-ruta-hardware-sirena.md §7`, primera decisión abierta · **Gobierna:** `G-02`, y con
él la lista de materiales de [`RUNBOOK-sesion-de-vida.md`](runbooks/RUNBOOK-sesion-de-vida.md) §C.1

**El problema.** La sirena tiene dos fuentes en lógica OR: el relé que gobierna el Pi, y una **ruta
de hardware sin CPU, firmware ni lógica programable** —contacto del WR-1 → relé de potencia →
sirena, con alimentación propia respaldada por UPS— que sobrevive a cualquier fallo del Pi. Lo que
había que decidir es **cuándo está activa esa segunda ruta**.

**La decisión: variante B.** La ruta de hardware queda **inhibida mientras el Pi está sano** y se
habilita sola si el Pi muere o se cuelga. Un relé `K_wd` (DPDT, energizado = Pi vivo) la inhibe;
cuando el latido cesa, `K_wd` de-energiza, su contacto NC cierra, y la ruta engancha.

**La razón, y es una sola:** preserva **el silencio del operador**. Ante una falsa alarma, con (B)
el Pi está vivo y gobierna, así que se puede callar. Con (A) la sirena de hardware **no es
silenciable** y sigue sonando hasta que el WR-1 libere el contacto — en un edificio con gente, una
sirena que nadie puede callar durante una falsa alarma quema la credibilidad que hace que la gente
obedezca la **siguiente** alerta. Es el mismo criterio que ya gobernó [`D-05`](#d-05).

**Lo que esta decisión COMPRA, y hay que pagarlo:**

- **Hardware:** un relé `K_wd` DPDT y un **monoestable retriggerable** (`t_wd` ≈ 2–3 s), además del
  relé de potencia que (A) también necesitaría.
- **Software, y es la parte delicada:** el **latido de keep-alive**, que no puede ser un
  `while True: toggle`.

> ### ⚠️ El requisito que hace peligrosa la implementación ingenua
> **El latido debe probar la liveness del CAMINO DE REFLEJO, no del proceso.** Un cuelgue parcial
> —el hilo del reflejo bloqueado con el lock tomado, los demás hilos vivos— dejaría el reflejo
> muerto mientras un latido ingenuo sigue latiendo: `K_wd` energizado, ruta de hardware
> **inhibida**, y **sirena muda ante una alerta real**. Que es exactamente el fallo que `G-02`
> existe para impedir — reintroducido por su propia mitigación.
>
> Cada pulso debe condicionarse a **adquirir y liberar el lock del reflejo y observar progreso**:
> un contador monótono que solo avanza si el camino SASMEX→relé pudo ejecutarse. **Un reflejo en
> deadlock no debe poder emitir el latido.** Pin sugerido **BCM 26**, a declarar en `GpioPins`.

**Cómo se revocaría:** si la medición de la semántica del WR-1 contra CIRES (`G-04`) revelara que
el contacto es un **pulso corto no enganchado**, el inconveniente de (A) —la no-silenciabilidad—
casi desaparece, porque la sirena de hardware se callaría sola en segundos. Entonces (A) volvería a
la mesa por simplicidad. **Mientras esa medición no exista, (B) es la elección segura**, y es la
que permite comprar hoy.

---

<a id="d-11"></a>
## D-11 · El quórum de pánico **abre incidente** `trigger='manual'`

**Fecha:** 2026-08-16 · **Decide:** Mauricio · **Sale de:** implementar [`D-05`](#d-05) ·
**Ficha:** `T-2.147`

**El obstáculo, medido.** `D-05` manda push a los tácticos cuando el quórum confirma. Pero toda la
maquinaria de notificación —reintento con backoff, evidencia en `incident_actions`, cuarentena de
canal caído, guarda de duplicados— **cuelga de un incidente**: `notification_jobs.incident_id` es
`NOT NULL` con FK. Y el quórum de pánico **no abre ninguno**: emite el comando firmado, audita, y
ahí acaba.

**La decisión.** Al alcanzar quórum, el pánico **abre un incidente con `trigger = 'manual'`** —
valor que el `CHECK` del esquema **ya contempla** y que hasta hoy nadie producía. Con eso, `D-05`
se cablea **sin tocar el esquema** y sin reinventar el subsistema de notificación en pequeño y
peor.

**Por qué es lo correcto y no un rodeo:** un pánico **es** operativamente un incidente — algo pasó
en el edificio, alguien tiene que responder, y tiene que quedar registro. Que no fuera sísmico
nunca fue razón para no registrarlo; era razón para **no titularlo como sismo**.

> ### ⚠️ El riesgo que hereda, y ya mordió una vez
> `T-2.104`: la app tituló **«ALERTA SÍSMICA SASMEX»** una alerta que no era de SASMEX, porque el
> titular estaba escrito a fuego para las cuatro fuentes mientras abajo decía «FUENTE · REGLAS
> LOCALES». Un incidente `manual` **no puede presentarse como sísmico**, y eso se cierra **por el
> campo `trigger`**, no negándose a registrarlo.
>
> Y con [`D-05`](#d-05) y la regla de quién puede ordenar evacuar: un incidente `manual` **no
> ordena evacuar a nadie**. Solo SASMEX o ≥3 inmuebles simultáneos lo hacen.

**Por qué no las otras dos.** Relajar `incident_id` a NULL rompe la garantía de que **toda
notificación pertenece a un incidente**, que es lo que hace auditable la cadena de evidencia — y
deja el escalado al SOC sin ancla donde vivir. Un camino aparte sin la cola sería rápido de
escribir y se quedaría **sin reintento, sin evidencia, sin guarda de duplicados y sin cuarentena**,
justo en el camino de una emergencia.

---

<a id="d-12"></a>
## D-12 · Dominio raíz — **`takabailert.mx`**, con DNS en Route 53

**Fecha:** 2026-08-17 · **Decide:** Mauricio · **Venía de:** la tabla `D-1`…`D-6` de
[`runbooks/RUNBOOK-ses-produccion-y-cadena-oncall.md §2.2`](runbooks/RUNBOOK-ses-produccion-y-cadena-oncall.md),
en blanco desde que se escribió · **Desbloquea:** `PENDIENTES §2.9` (`T-2.78`, SES) y
`PENDIENTES §4.2` (`T-2.77.a`, WhatsApp) — **los dos únicos puntos de plazo externo del proyecto**

**Por qué esta decisión valía por dos.** El dominio no aparecía en la lista de decisiones porque
estaba enterrado en la tabla de un runbook. Y mientras tanto bloqueaba **las dos cosas que no se
pueden acelerar después**, porque las contesta un tercero: AWS (salida del sandbox de SES) y Meta
(verificación de negocio). Nada de lo que hay debajo se podía empezar sin él.

**Los seis valores, que son la tabla del runbook rellenada:**

| # | Decisión | Valor |
|---|---|---|
| D-1 | Dominio raíz | **`takabailert.mx`** |
| D-2 | DNS | **Route 53** (zona alojada en la cuenta `634882473845`) |
| D-3 | Remitente de notificaciones | **`alertas@takabailert.mx`** |
| D-4 | Subdominio MAIL FROM | **`mail.takabailert.mx`** — no envía ni recibe correo |
| D-5 | Buzón de informes DMARC (`rua=`) | **`dmarc@takabailert.mx`** |
| D-6 | `ops_alert_email` | **`ops@takabailert.mx`** — migra del gmail personal |

**Las razones, una por elección que tenía alternativa real:**

- **`.mx` sobre `.com`.** El dominio lo va a mirar un tercero antes que un cliente: Meta lo pide
  para verificar el negocio y AWS lo pide como `Website URL`. Un `.mx` responde a la pregunta
  «¿esto es una empresa mexicana?» sin que nadie tenga que preguntarla. Cuesta ~4× más al año, y
  esa diferencia es irrelevante frente a una solicitud devuelta.
- **Route 53 sobre el DNS del registrador.** SES y ACM pueden publicar **ellos mismos** sus
  registros de verificación. Eso importa más de lo que parece: el propio runbook documenta que el
  modo de fallo típico de DKIM es un CNAME copiado a mano con un `_` de más
  (`_abc123._domainkey…` en vez de `abc123._domainkey…`), y un DKIM mal copiado **no da error: da
  correo que no se entrega**. Además deja el DNS bajo Terraform en vez de en un panel ajeno.
- **`alertas@` sobre `no-reply@`.** Un correo de alerta sísmica que dice «no contestes» le está
  dando una instrucción equivocada a la persona exacta que quizá deba contestar. El coste de
  atender respuestas es real, pero es el coste correcto.
- **On-call al dominio en vez de seguir en gmail.** Hoy hay un solo guardia y el gmail funcionaría.
  El día que entre el segundo, migrar significa tocar el ARN de SNS, el Terraform y la
  documentación — y ese día es, por definición, un día ocupado. Es la misma lógica del gatillo de
  [`D-09`](#d-09), solo que resuelta antes en vez de dejada escrita.

**Lo que esta decisión NO resuelve:** el dominio hay que **registrarlo**, y eso es una acción con
tarjeta de por medio. Hasta que exista, `§2.9` y `§4.2` siguen parados — pero ya **no por falta de
criterio**, que era el estado anterior y el peor de los dos.

> ### ⚠️ EJECUCIÓN PARCIAL (2026-08-21) — y con la trampa que este proyecto ya conoce
>
> Se creó la **zona alojada** en Route 53. **El dominio NO está registrado**: NIC México sigue
> contestando `Disponible/Available` al 2026-08-21.
>
> **Y ésa es exactamente la trampa:** `route53 create-hosted-zone` **no comprueba que el dominio sea
> tuyo**. Acepta cualquier nombre, devuelve cuatro *name servers* con aire de éxito y cobra su
> cuota — **delegando nada**. El comando sale `PENDING` → `INSYNC` y parece progreso; lo único que
> existe es un contenedor de DNS vacío esperando a un dominio que no se ha comprado. **Es un
> fallback que se presenta como `ok`**, que es la doctrina que `TRASPASO-SESION` ya dejó escrita.
>
> **Zona buena:** `Z010061324UQDJRQEXIVW`. Sus NS son los que van a NIC México:
> `ns-599.awsdns-10.net` · `ns-1485.awsdns-57.org` · `ns-68.awsdns-08.com` ·
> `ns-1597.awsdns-07.co.uk`.
>
> ### Y una segunda trampa, más barata pero más fácil de repetir: **salieron TRES zonas**
>
> `create-hosted-zone` **no es idempotente**: cada ejecución crea una zona nueva, con **NS
> distintos**, sin avisar de que ya había una. Salieron tres —una del 2026-08-17 y dos del
> 2026-08-21 separadas por cinco minutos— porque `--caller-reference` lleva un *timestamp*, así que
> nunca colisiona. Las tres vacías (`NS`+`SOA`), a $0.50/mes cada una.
>
> **El daño real no es el $1.00/mes de sobra: es que solo un juego de NS puede delegarse.** Pegar
> en NIC México los de una zona y publicar los registros de DKIM en otra da **correo que no se
> entrega sin un solo error a la vista** — que es el mismo modo de fallo por el que `D-12` eligió
> Route 53 (para que SES publicara sus registros él mismo en vez de copiarlos a mano).
>
> **Antes de dar el dominio por hecho, comprobar las dos cosas por separado:**
> ```bash
> whois "=takabailert.mx" | head -3      # -> tiene que DEJAR de decir "Disponible"
> aws --profile takab-dev route53 list-hosted-zones-by-name \
>   --dns-name takabailert.mx --query "HostedZones[].Id" --output text   # -> UNA sola
> ```

> ### ✏️ ENMENDADA el 2026-08-21 — el dominio comprado fue **`takabailert.com`**
>
> El texto de arriba queda intacto (regla de la bitácora). Lo que cambia es **`D-1`**: Mauricio ya
> tenía contratado **`takabailert.com`** en **Namecheap**, así que no se registra el `.mx` y su zona
> de Route 53 se borró.
>
> **La tabla vigente:**
>
> | # | Decisión | Valor vigente |
> |---|---|---|
> | D-1 | Dominio raíz | **`takabailert.com`** (Namecheap) |
> | D-2 | DNS | **Route 53** — zona **`Z01047862QJFIRSOR5IC5`** *(confirmada, ver abajo)* |
> | D-3 | Remitente | **`alertas@takabailert.com`** |
> | D-4 | Subdominio MAIL FROM | **`bounce.takabailert.com`** ← **cambiado, ver la colisión** |
> | D-5 | Buzón DMARC | **`dmarc@takabailert.com`** |
> | D-6 | On-call | **`ops@takabailert.com`** |
>
> **Lo que se pierde al pasar de `.mx` a `.com`, dicho sin adornos:** la razón principal del `.mx`
> era **señal** ante Meta y ante el cliente institucional. Meta acepta `.com` sin problema —la
> verificación de negocio se hace con **documentos legales**, no con el TLD—, así que **se pierde
> señal de marca, no capacidad**. Ninguna capacidad técnica depende del TLD.
>
> ### ⚠️ La colisión que obligó a cambiar `D-4`, y no daba error
>
> `D-4` decía `mail.<dominio>`. **Namecheap Private Email usa `mail.<dominio>` como CNAME** de su
> webmail, y **SES exige en el subdominio MAIL FROM un `MX` y un `TXT` propios**. Un CNAME **no
> puede convivir con otros registros en el mismo nombre**: es ilegal en DNS. Se resuelve moviendo
> el MAIL FROM a **`bounce.takabailert.com`**, que además cumple mejor el requisito de SES de que
> ese subdominio **no se use para enviar ni recibir correo**.
>
> ### ⚠️ Y el hallazgo que cambió el plan de correo — `D-2` se confirmó, pero cuesta
>
> El dominio venía con el **reenvío gratuito de Namecheap** activo (`MX → eforward1-5`). Y ese
> servicio **solo funciona con los nameservers de Namecheap**: al delegar en Route 53 **deja de
> recibir**, sin error y sin aviso.
>
> **Se confirma Route 53** —SES y ACM publican sus propios registros, y el DNS queda bajo Terraform
> para cuando la consola deje `sslip.io` por `console.takabailert.com` con certificado real— y se
> **compra un buzón** (Namecheap Private Email, ~$15/año), que sí funciona con DNS de terceros.
> Enmienda de [`D-16`](#d-16).
>
> **Por qué buzón de pago y no el plan gratuito de Zoho:** el gratuito de Zoho es **solo
> webmail/app, sin IMAP/POP**. `ops@` es la **cadena on-call**: tiene que sonar en un teléfono a
> las 3 a.m., y eso pide IMAP y push nativo. Para `dmarc@` habría bastado; para `ops@` era el
> eslabón débil.
>
> **La distinción que evitó comprar de más:** **enviar no necesita buzón** —SES manda desde
> `alertas@` con solo registros DNS—. Solo **recibir** lo necesita, y solo dos direcciones reciben.

> ### ⚠️ Y la corrección que más vale de esta sesión: **`T-2.78.b` ya estaba escrito en Terraform**
>
> El alta de SES se hizo primero **por CLI** —identidad de dominio, DKIM, MAIL FROM y DMARC—, y
> funcionó: verificó en minutos. **Y estaba mal hecho**, porque
> `infra/terraform/modules/identity/main.tf` ya tenía todo eso codificado y gateado por
> `var.ses_domain`. Se revirtió entero y se dejó que lo cree Terraform.
>
> **No era un empate de estilo. El repo era mejor en dos puntos concretos:**
>
> | | CLI (revertido) | Terraform (vigente) |
> |---|---|---|
> | `behavior_on_mx_failure` | `USE_DEFAULT_VALUE` | **`REJECT_MESSAGE`** |
> | Rebotes y quejas | **nada** | configuration set + lista de supresión + topic SNS + destino de eventos |
>
> **El primero invierte la doctrina del proyecto.** Con `USE_DEFAULT_VALUE`, si el MX del MAIL FROM
> deja de resolver, **SES sigue enviando** con el Return-Path de `amazonses.com`: se pierde la
> alineación SPF, el correo se va a spam **y nada falla** — el inspector no recibe su solicitud de
> dictamen y el sistema cree que sí. El comentario del propio Terraform lo dice mejor: *«el canal
> que no entrega no finge»*. El razonamiento del CLI («no cortes el correo de un sistema de
> alertas») suena prudente y produce **exactamente el fallo silencioso** que este proyecto lleva un
> año cazando.
>
> **El segundo habría hecho mentir a la solicitud de AWS.** La salida del sandbox exige declarar
> que existe un proceso para rebotes y quejas. La identidad creada por CLI **no tenía configuration
> set**, así que no había ni supresión ni topic: el proceso solo se podía declarar mintiendo. El
> Terraform crea el topic, su política de recurso y la suscripción **precisamente para que esa
> casilla se pueda marcar siendo verdad**.
>
> **La lección, y es de método:** antes de resolver algo por CLI en un repo con IaC, **mirar si el
> repo ya lo resuelve**. Aquí no solo lo resolvía: lo resolvía con dos decisiones razonadas por
> escrito que el atajo pisó sin verlas. Es la misma familia que *«un censo que enumera a mano acaba
> divergiendo»* — el atajo no sabía lo que el repo ya sabía.
>
> **Lo que sí quedó bien del CLI y se conserva:** la zona (`Z01047862QJFIRSOR5IC5`, que el módulo
> espera recibir por ID y no gestiona), los `MX`/`TXT` de Private Email en la raíz, y el TTL de
> caché negativa del `SOA` bajado de 86400 a 300.

**Cómo se revocaría:** si NIC México pusiera un requisito que Mauricio no puede cumplir, o si el
registro se demorara más que el plazo de Meta, se registra un `.com` gemelo como puente y el `.mx`
se conserva para la cara pública. La estructura de subdominios (`mail.`, `alertas@`, `ops@`) no
cambia: es independiente del TLD.

---

<a id="d-13"></a>
## D-13 · El teléfono de soporte — **un número Twilio mexicano**

**Fecha:** 2026-08-17 · **Decide:** Mauricio · **Venía de:** `MANUAL-OPERACION-TAKAB.md §1`, fila
«Soporte TAKAB — teléfono», **en blanco** · **Ficha:** `T-2.76.a` (`PENDIENTES §4.3`)

**El hueco, y por qué era grave sin parecerlo.** El manual de operación —el documento que se le
entrega al guardia de un edificio— dice **«avisa a soporte»** unas 25 veces, y en las filas rojas
dice literalmente **«llama a soporte AHORA»**. Ese teléfono **no existía en ninguna parte del
repositorio**. Un manual que manda llamar a un número en blanco no es un manual incompleto: es un
procedimiento de emergencia que falla en el momento en que se usa.

**La decisión.** El teléfono de soporte es un **número mexicano de Twilio**, el mismo trámite que
`§4.3` ya exigía para el canal SMS. Un alta, dos necesidades cubiertas.

**La razón, y es de las que solo se ven a un año vista.** Un número de Twilio se **redirige**: el
día que la guardia la lleve otra persona, o haya rotación, o Mauricio cambie de móvil, el número
impreso **sigue siendo el correcto**. Un móvil personal impreso en un manual ya distribuido obliga
a reeditar y redistribuir el documento **en cada sitio instalado** — y en la práctica eso significa
que el manual del edificio 3 sigue teniendo el número viejo para siempre.

**Y hay una segunda razón, menos obvia:** un número de empresa separa el rol de la persona. El día
que un cliente institucional pregunte «¿a quién llamo a las 3 a.m.?», la respuesta no debería ser
el móvil de alguien.

**Lo que implica para el software y los documentos** (deuda declarada, no cerrada):
- Rellenar `MANUAL-OPERACION-TAKAB.md §1` con el número **en cuanto exista** — hoy sigue en blanco
  a propósito, porque poner un número falso es peor que no poner ninguno.
- Lo mismo en `ENTREGA-Y-ACEPTACION-TAKAB.md`.
- El número debe apuntar a la **cadena on-call** de `§2.9`, no a un buzón de voz sin dueño.

---

<a id="d-14"></a>
## D-14 · CCTV — **híbrido**: aforo en el sitio, clips solo de evento confirmado

**Fecha:** 2026-08-17 · **Decide:** Mauricio · **Venía de:** la recomendación abierta al final de
[`D-08`](#d-08) («conviene decidir pronto») · **Ficha:** `T-3.10` (arquitectura CCTV) ·
**Diseño:** [`design/BLOQUE-IV-ARQUITECTURA.md`](design/BLOQUE-IV-ARQUITECTURA.md)

**La decisión.** El **aforo se calcula en el inmueble** y a la nube sube **solo el número**. Además,
ante un **evento confirmado**, suben **clips cortos** de ese evento — no vídeo continuo.

**La razón de la mitad local.** Procesar en sitio elimina casi toda la superficie de PII de vídeo:
si las imágenes no salen del edificio en operación normal, la mayor parte de la conversación de
privacidad con un cliente institucional **deja de existir** en vez de tener que ganarse.

**La razón de admitir los clips, que es la que hace esto híbrido y no puro.** Un número de aforo
dice «hay 40 personas» y **no dice si están saliendo o atrapadas**. En un post-sismo, la diferencia
entre esas dos cosas es la decisión operativa entera. Un clip corto de un evento **ya confirmado**
es evidencia, y la evidencia post-sismo es producto, no adorno.

> ### ⚠️ La condición que hace aceptable la mitad que sube, y no es opcional
> Los clips son **por evento confirmado**, nunca continuos ni «por si acaso». Eso es la **regla de
> oro 9** aplicada al vídeo: el mismo criterio que prohíbe subir forma de onda cruda en continuo y
> la sube **solo en eventos confirmados**. Si el CCTV subiera en continuo estaría violando en
> vídeo la regla que el sismómetro respeta en señal.
>
> Y hereda las obligaciones de `T-3.10`: retención acotada y declarada, consentimiento, y que la
> salida de vídeo quede **auditada** igual que un comando de actuador.

**Por qué no las otras dos.** «Todo a la nube» compraba modelos más pesados pagando con una
conversación legal entera **por cada cliente**, ancho de banda continuo y PII de un edificio ajeno
almacenada fuera de él. «Solo el número» era más limpio de defender, pero deja al SOC ciego justo
en el escenario para el que existe el módulo.

**Cómo se revocaría:** si la revisión legal de [`§4.1`](PENDIENTES-MAURICIO.md) concluye que el
clip de evento exige un consentimiento que un edificio con público no puede recabar, se cae a
**solo aforo** — y el diseño debe permitir esa caída **por configuración de sitio**, no por
reescritura. Fichar así en `T-3.10`.

---

<a id="d-15"></a>
## D-15 · Sirena por jack — **encendida** en el gabinete de desarrollo

**Fecha:** 2026-08-17 · **Decide:** Mauricio · **Venía de:** `PENDIENTES §3.4`, la viñeta
«algo que puedes encender HOY» · **Ficha:** `T-1.68`

**La decisión.** `TAKAB_EDGE_AUDIO_SIREN_ENABLED=true` en `gw-dev-0001`. El gabinete emite sirena
audible por el jack de 3.5 mm con el WAV ya empaquetado
(`edge/takab_edge/audio/assets/siren.wav`).

**La razón.** El escenario manual del `GATE-HW` (`§3.4`) necesita una alerta **con sirena audible**,
y hasta hoy la única forma de tenerla era comprar hardware que aún no existe
([`D-16`](#d-16) lo aplazó). Esto da sonido real **hoy, gratis y sin comprar nada**.

**Lo que lo hizo barato, y es consecuencia de otra decisión:** encenderlo exige reiniciar
`takab-edge`, y desde [`D-04`](#d-04) —ejecutada el 2026-08-16— **ese reinicio ya no mueve un solo
relé**. Antes habría costado un ciclo de gas y puertas; hoy cuesta cero. Es un ejemplo limpio de
decisión que abarata a la siguiente.

> **Lo que NO es, y conviene no confundirlo nunca:** `TAKAB_EDGE_AUDIO_SIREN_ENABLED` (sirena) es
> **independiente** de `TAKAB_EDGE_AUDIO_ENABLED` (voceo hablado). El segundo **exige las dos
> grabaciones** y **rompe el arranque si faltan**. Sigue apagado.
>
> **Y esto no sustituye a `G-02`.** La sirena por jack depende del Pi: si el Pi muere, calla. La
> ruta de hardware de [`D-10`](#d-10) existe precisamente para el caso en que el Pi no está.

> ### ✅ VERIFICADA — y resultó que **ya estaba encendida** (2026-08-17)
>
> Al ir a ejecutarla, el gabinete `gw-dev-0001` **ya la tenía activa**. No inferido del fichero de
> configuración, sino **del proceso vivo**:
>
> | | |
> |---|---|
> | `TAKAB_EDGE_AUDIO_SIREN_ENABLED` | `true` en `/etc/takab/edge.env` |
> | Asset cargado | `/opt/takab/edge/takab_edge/audio/assets/siren.wav` · `sha256=5a6b73d1…5932b` |
> | Desde | **2026-08-16 19:49:30 CST**, `NRestarts=0` |
> | Voceo hablado | **`DESHABILITADO`** (`audio_enabled=false`) — correcto, sigue tras el gate A-6 |
>
> Se encendió sola en el despliegue del traspaso de pines ([`D-04`](#d-04)) del 2026-08-16.
>
> ### ⚠️ Y el hallazgo que vale más que la decisión
> `PENDIENTES §3.4` ofrecía esto como **«algo que puedes encender HOY»** sobre algo que llevaba
> **un día entero funcionando**. Nadie mintió: el documento se escribió antes del despliegue y
> **nada lo volvió a mirar**. Es la misma familia de defecto que este proyecto ya tiene fichada —
> un documento que describe un estado del mundo y **no se verifica contra el mundo** — y aquí salió
> barato porque el error era a favor. **La comprobación buena no es leer `edge.env`: es leer el
> journal del proceso**, que declara el `sha256` del WAV que puede sonar por el altavoz de un
> inmueble.

**Lo que queda por hacer, y es una sola línea:** oírla. `POST /api/siren-test` en el panel del
gabinete hace sonar el tono **de verdad** — no se dispara sin avisar a quien esté en el sitio.

---

<a id="d-16"></a>
## D-16 · Compras — **sí** dominio y Twilio · **no todavía** el hardware de `G-02` ni Apple

**Fecha:** 2026-08-17 · **Decide:** Mauricio · **Venía de:** `PENDIENTES §3.1`, `§4.3`, `§4.4`,
`§4.5`

**Lo autorizado en esta pasada:**

| Compra | Coste | Qué desbloquea |
|---|---|---|
| Dominio `takabailert.mx` + zona Route 53 | ~$55 USD/año | `§2.9` (SES) **y** `§4.2` (WhatsApp) |
| Twilio: cuenta + número mexicano | ~$3 USD/mes | `§4.3` (SMS) **y** el teléfono de [`D-13`](#d-13) |

**Lo aplazado, y con ello lo que queda parado — que es la mitad que hay que no olvidar:**

| Aplazado | Consecuencia declarada |
|---|---|
| **BOM del `G-02`** (`K_wd` DPDT, monoestable, relé de potencia, riel, UPS) | **`G-02` sigue siendo obra, no prueba.** Es, según su propia ficha, «la mitigación más importante del sistema». Mientras no se compre, **si el Pi muere la sirena calla** y no hay segunda ruta. [`D-10`](#d-10) dejó la lista lista para comprar; comprarla es lo que falta |
| **Apple Developer** ($99/año) | `§4.4` (`GATE-STORE`) y `§4.5` (entitlement de Critical Alerts) **no se pueden ni empezar**. El entitlement lo concede Apple **caso por caso y es plazo externo**: el reloj no arranca hasta que hay cuenta |

**El criterio que ordena las dos columnas.** Se compró **lo que desbloquea plazo externo hoy** —
dominio y Twilio abren AWS, Meta y el canal SMS a la vez. Se aplazó lo que, aun siendo importante,
**no tiene un tercero esperando** (el hardware del `G-02`) o cuyo plazo externo se acepta arrancar
más tarde (Apple).

> ### ⚠️ La asimetría que hay que vigilar, porque es la que muerde
> El `G-02` es aplazamiento de **riesgo**, no de trámite: cada día sin esa ruta es un día en que un
> Pi colgado deja el edificio sin sirena. Apple es aplazamiento de **calendario**: cada día sin
> cuenta es un día que se suma al final, cuando toque publicar. **No son la misma clase de deuda**,
> y conviene no meterlas en el mismo cajón mental solo porque las dos digan «no todavía».

> ### ✏️ ENMENDADA el 2026-08-21 — se añade un buzón de pago
>
> **`ops@takabailert.com` y `dmarc@takabailert.com` necesitan recibir**, y delegar el DNS en
> Route 53 **mata el reenvío gratuito de Namecheap** (solo funciona con sus nameservers). Se
> autoriza **Namecheap Private Email, ~$15/año**, que sí funciona con DNS de terceros y da IMAP.
>
> **No es un gasto que se pueda saltar:** `ops@` es la cadena on-call de `§2.9`. Un buzón que no
> hace push a un teléfono es una guardia que no despierta a nadie.
>
> **Lo que NO cambia:** el dominio ya estaba comprado (`takabailert.com`), así que del presupuesto
> de `D-12` solo queda vivo el coste de la zona de Route 53 (~$0.50/mes). El BOM del `G-02` y la
> cuenta de Apple **siguen aplazados** — y el `G-02` sigue siendo deuda de **riesgo**, no de
> trámite.

**Cómo se revocaría:** el `G-02` vuelve a la mesa **en cuanto haya fecha para la sesión de vida**
(`§3.1`), porque la obra tiene que estar hecha antes. Apple, en cuanto la app tenga fecha de
publicación — y con margen, porque el entitlement no se concede al instante.

---

<a id="d-17"></a>
## D-17 · La ventana AWS se parte en **dos**

**Fecha:** 2026-08-17 · **Decide:** Mauricio · **Venía de:** `PENDIENTES §2`

**La decisión.**

- **Ventana A** (~1 h, sin build): los cinco `terraform apply` de `§2.1`, más `§2.2` (confirmar que
  la alarma del fantasma sale de `INSUFFICIENT_DATA`), `§2.3` (Cognito), `§2.4` (CI OIDC), `§2.5`
  ([`D-18`](#d-18)), `§2.6` (occupant real) y `§2.7` (e2e).
- **Ventana B** (~3 h, con build): `§2.8` / `T-2.74` — el restore real con RTO medido (`G-09`).

**La razón, y está medida, no supuesta.** La ventana B empieza por `make cloud-images`, que **tarda
~40 min**, y la trampa ya cobrada es que **el token SSO expira a mitad**: terraform muere con
`InvalidGrantException` **mientras `docker login` a ECR sigue funcionando**, que es la firma que
hace perder media hora diagnosticando credenciales que sí están. Meter ese build dentro de una
sesión que ya lleva una hora de applies **garantiza** que el token no llegue vivo al final.

Partirlo permite además **renovar el SSO justo antes** de la B (`aws sso logout` **y luego**
`login` — a secas no basta), que es la única mitigación que funciona.

**Lo que la decisión NO cambia:** el **orden interno** de cada ventana sigue siendo obligatorio. En
particular el de `§2.1.5` (suscriptor HTTPS de la cadena on-call), donde **la suscripción se
confirma durante el `apply`**: si el `curl` de prueba da 503 en vez de 404, **hay que parar ahí** —
seguir mata el `apply` a medias.

---

<a id="d-18"></a>
## D-18 · `console_scope_enforced` — **se enciende ya**, con los tests en el mismo commit

**Fecha:** 2026-08-17 · **Decide:** Mauricio · **Venía de:** `PENDIENTES §2.5` ·
**Ficha:** `T-2.89` · **Va dentro de:** la ventana A de [`D-17`](#d-17)

**La decisión.** Se enciende en la ventana A, siguiendo la secuencia obligada —**recorrer** los
`scope_gap` del `audit_log`, **asignar** alcance, **encender** al final— y **los dos tests HTTP que
hoy fijan la conducta *no* impuesta se invierten en el MISMO commit**.

**La razón de no esperar.** Es **la única brecha multi-tenant viva en producción**, y la regla de
oro 5 no admite grados. Hoy el coste de cerrarla es bajo: un solo tenant de desarrollo, sin datos
de nadie dentro y sin nadie mirando. El día que entre el primer cliente, ese mismo cambio se hace
**con datos reales dentro, bajo presión y con el cliente delante** — y la secuencia, invertida,
deja a cada `soc_operator` con **cero estaciones**, que es un incidente visible.

**La razón de meter los tests en el mismo commit, que es la mitad operativa.** Se sabe de antemano
que encenderlo **pone la suite en rojo** — dos tests aseveran hoy la conducta permisiva. Si esa
inversión se deja «para después», el rojo aparece **en mitad de la ventana**, donde se parece a un
fallo del despliegue y no a lo que es. Un rojo esperado que llega por sorpresa se diagnostica como
un rojo inesperado, y ahí es donde se pierde la ventana.

---

<a id="d-19"></a>
## D-19 · El tono de alerta de la app — **propio**, no el oficial de CIRES

**Fecha:** 2026-08-17 · **Decide:** Mauricio · **Venía de:** `PENDIENTES §4.4` (`GATE-STORE`,
«APNs/FCM reales + tono SASMEX») · **Ficha:** `T-2.97`

**La decisión.** La app suena con un **tono propio de TAKAB**, agudo y reconocible. No se usa el
tono oficial del SASMEX ni se pide licencia a CIRES.

**Las tres razones, en orden de peso:**

1. **Es el deslinde, hecho sonido.** El sistema ya declara por escrito que **no** es SASMEX y que
   no lo respalda —es lo que `§4.1` va a llevar al abogado—. Reproducir el tono oficial diría lo
   contrario **por el altavoz**, que es el canal que la gente cree antes que el texto. Y ya hay
   precedente medido: `T-2.104`, cuando la app tituló «ALERTA SÍSMICA SASMEX» algo que no lo era.
2. **Elimina un plazo externo entero.** Pedir el tono es depender de que un tercero conteste, y
   `GATE-STORE` quedaría esperando a alguien que puede no contestar nunca.
3. **No se puede perder después.** Un permiso concedido puede revocarse; un tono propio, no. Lo
   contrario obligaría a publicar una versión de emergencia para cambiar un sonido.

**Lo que se paga, y hay que decirlo:** el tono oficial es el que la población **ya reconoce y
obedece**, y esa ventaja en una evacuación es real. Se compensa con diseño —que el tono propio sea
inconfundible y no se parezca a una notificación cualquiera— y con el texto en pantalla, que sí
nombra el origen.

**Cómo se revocaría:** si CIRES ofreciera licencia explícita **por escrito** y el abogado de `§4.1`
confirmara que usarla no debilita el deslinde, se puede añadir como tono **alternativo por sitio**.
Nunca como sustituto silencioso: cambiar el sonido de una alarma que la gente ya aprendió es un
cambio de producto, no de configuración.

---

<a id="d-20"></a>
## D-20 · La consulta legal — **espera a que un cliente la pida**

**Fecha:** 2026-08-17 · **Decide:** Mauricio · **Venía de:** `PENDIENTES §4.1` (`T-2.96`,
`GATE-LEGAL`) · **Documento ya escrito:** [`CONSULTA-LEGAL-TAKAB.md`](CONSULTA-LEGAL-TAKAB.md)

**La decisión.** No se contrata abogado hoy. El documento de consulta queda **escrito y listo para
enviar**, y se activa el día que un cliente institucional pregunte por el marco normativo.

**La razón.** El gasto es real y **no desbloquea una sola línea de código**: `GATE-LEGAL` no es
dependencia de ninguna ficha de software. Con `D-16` acabando de comprometer dominio y Twilio, el
dinero disponible se pone donde hay un tercero **ya esperando** (AWS, Meta) y no donde el tercero
solo aparece cuando lo llamas.

**El riesgo que se acepta, y está medido en la propia lista de pendientes:** esto es **plazo
externo**. El día que llegue la pregunta, el reloj empieza **ese día** — y una opinión escrita en
responsabilidad de producto no se entrega en 48 horas. Es decir: el ahorro de hoy se paga en
**calendario del cliente**, en el peor momento posible de una venta.

> **Lo que hace que este aplazamiento sea barato y no temerario, y conviene tenerlo presente:** el
> sistema **hoy no afirma un marco propio**. Declara el que **el cliente** afirma, con su deslinde
> explícito de que TAKAB no lo respalda. Eso es honesto y es defendible mientras nadie pida más. La
> deuda aparece cuando alguien pida más — no antes.
>
> **Y hay una pieza que queda colgando:** [`D-07`](#d-07) (cripto-borrado del teléfono del
> consentimiento) es **postura por defecto sujeta a esta revisión legal**. Aplazarla deja `D-07`
> sin confirmar: en concreto, si un número cifrado sigue siendo dato personal mientras exista la
> clave, y si destruir la clave cuenta como cancelación ante la LFPDPPP. Se implementa igual —es la
> mejor postura disponible—, pero **no está validada**.

**Cómo se revoca — el gatillo, escrito para que no dependa de acordarse:**

1. **Un cliente institucional pregunta por el marco normativo o por la política de privacidad.** Es
   el disparo principal. Ese día se manda `CONSULTA-LEGAL-TAKAB.md` **completo** (las 5 preguntas
   del §4 **más** el §4.4 de `D-07`), no la mitad.
2. **O antes, si aparece un ejercicio ARCO real** sobre un `subject_ref` identificado por teléfono
   — ahí `D-07` deja de ser hipótesis.
3. **O antes, si el sistema empieza a afirmar un marco propio** en vez de citar el del cliente. Ese
   cambio **no debe hacerse sin la consulta**: es exactamente lo que convierte una postura en una
   declaración.

---

<a id="d-21"></a>
## D-21 · La sesión de vida se **parte**: `G-01` esta semana, solo

**Fecha:** 2026-08-17 · **Decide:** Mauricio · **Venía de:** `PENDIENTES §3.1` (`T-2.92`) ·
**Runbook:** [`runbooks/RUNBOOK-sesion-de-vida.md`](runbooks/RUNBOOK-sesion-de-vida.md)

**La decisión.** `T-2.92` deja de tratarse como una sesión y pasa a ser **tres cosas con calendarios
distintos**. `G-01` (restart en frío) se acredita **esta semana**, en ~20 min, por su cuenta.

**La razón.** El propio veredicto medido del 2026-08-16 ya decía que no eran una sesión:

| Gate | Estado | Depende de |
|---|---|---|
| `G-01` | **se puede hacer hoy** | nada |
| `G-04` | a medias (la mitad eléctrica ya pasa con 2 órdenes de magnitud de margen) | una sirena real + medición contra CIRES |
| `G-02` | **no se puede probar** | hardware que [`D-16`](#d-16) aplazó |

Atarlos en un solo evento hacía que **el que está listo esperase al que ni siquiera está
construido**. Y con `D-16` dejando la BOM del `G-02` sin fecha, esa espera pasaba a ser indefinida:
un gate acreditable habría quedado abierto meses por vecindad de agenda, no por dificultad.

**Lo que NO cambia, y hay que decirlo para que el gate parcial no se lea como gate cerrado:**
acreditar `G-01` **no cierra `T-2.92`**. `G-02` sigue siendo **obra pendiente** —el relé `K_wd`, el
monoestable, el relé de potencia, el riel con UPS **y el latido de keep-alive, que ni siquiera está
escrito**— y `G-04` sigue sin sirena al final del cable. Hasta entonces, **todo lo que el software
mide sobre actuación se mide contra una carga que no existe**.

**Cómo se revocaría:** no hay nada que revocar — partir la sesión no cierra ninguna puerta. Lo que
sí hay que vigilar es lo contrario: que acreditar `G-01` **no se cuente como progreso de la sesión
de vida**. Es un gate de tres, y es el barato.

---

<a id="d-01"></a>
## D-01 · Entre `empty` y `stale` — **gana `stale`**

**Fecha:** 2026-08-12 · **Decide:** delegación explícita de Mauricio («decide por mí») ·
**Venía de:** `PENDIENTES-MAURICIO §1.2` · **Desbloqueó:** `T-2.79.d`, `T-2.82.a`

**La pregunta.** Cuando **no hay dato** *y* **lo poco que hay está viejo**, ¿la pantalla dice «no
hay» —arriesgando afirmar una ausencia que quizá solo es desconexión— o dice «no lo sé desde las
hh:mm»? No es un banner: **gobierna toda la consola.**

**La decisión: gana `stale`.**

**La razón.** `empty` afirma un hecho **sobre el mundo** («no hay»). `stale` afirma un hecho
**sobre nuestro conocimiento** («no lo sé desde las hh:mm»). Cuando los dos son ciertos a la vez,
**solo el segundo se puede verificar**. Afirmar una ausencia que no puedes comprobar, en la consola
de un SOC, es el modo de fallo que produce «no hay heridos» cuando lo que pasa es que el enlace
está caído.

Que sea **menos accionable es la virtud, no el defecto**: manda al operador a revisar el enlace en
vez de a concluir. Es la regla de oro 7 llevada al caso en que ambas cosas ocurren a la vez.

**Lo que la motivó:** la deriva de que cada componente lo resolviera por su cuenta ya había
producido una franja muda, y que **ningún panel de la pantalla donde se firma un dictamen**
pudiera declarar su dato viejo.

---

<a id="d-02"></a>
## D-02 · `lock_timeout` en la conexión del request — **se pone, ~10 s**

**Fecha:** 2026-08-12 · **Decide:** delegación explícita de Mauricio («decide por mí»), **con las
cifras de `T-2.121` sobre la mesa** · **Venía de:** `PENDIENTES-MAURICIO §1.8` ·
**Implementada en:** `T-2.130` · **Planteamiento original:** `T-2.73.c`

**El criterio duro, que manda sobre el número exacto:** `lock_timeout` **< timeout del pool
(30 s)**. Por debajo, un bloqueo degrada *una petición*; por encima —o sin tope, como hasta
entonces— degrada *el proceso entero*, porque diez esperas agotan el pool y entonces **falla
también lo que ni siquiera tocaba la tabla bloqueada**.

**Valor: ~10 s**, y no los 3 s de las conexiones de segundo plano. La diferencia tiene razón: una
auditoría lateral es best-effort y se puede tirar; **una petición es una persona esperando**, y hay
esperas legítimas por lock de **fila** —serialización de acuses— que cortar a 3 s rompería.

**Lo que estaba medido, no supuesto** (`T-2.121`, con un `LOCK TABLE incidents IN ACCESS EXCLUSIVE
MODE` de un tercero):

| Hecho | Medido |
|---|---|
| El hub del WebSocket queda **encolado, no lento** | `pg_locks`: `granted=false` |
| El reparto no vuelve | **25.16 s** y seguía esperando (techo del test) |
| **El SOC entero se queda mudo** | el reparto es en serie: un segundo aviso que ni tocaba la base no llegó en 25 s |
| El operador **no se entera** | la consola seguía diciendo «CONECTADO» y «● LIVE» |
| **Y arrastra a toda la API** | 10 lectores encolados agotan el pool: cualquier petición, `TimeoutError` a los 30 s |

**Lo que esta decisión NO absorbe**, y conviene no darlo por hecho: `T-2.128` (el fan-out del
WebSocket es en serie) es **otra cosa**. Un tope global convierte el silencio del hub en una
excepción registrada, nada más: no hace que al operador **se le diga**, ni arregla que el reparto
en serie convierta un lock en un **apagón del SOC** en vez de un frame perdido.

---

<a id="d-03"></a>
## D-03 · La consola **arranca con la base caída**, en degradado y declarándolo

**Fecha:** 2026-08-12 · **Decide:** delegación explícita de Mauricio («decide por mí») ·
**Venía de:** `PENDIENTES-MAURICIO §1.9` · **Desbloqueó:** `T-2.123`, `T-2.128`

**El contexto.** `T-2.114` necesitaba que `/me` devolviera el inmueble del ocupante —el dato no
viaja en el claim de Cognito—, así que **`/me` dejó de ser claims puros y abre sesión de base**.
Efecto: con Postgres caído, la consola web ya no arrancaba. En móvil no hay regresión (conserva la
sesión y resuelve del caché, regla de oro 2).

**La decisión: la consola ARRANCA, DECLARANDO que no puede establecer el alcance del operador, y
sin pintar NI UN dato de tenant.**

Es la única combinación que respeta las tres reglas que aquí tiran en direcciones opuestas:

- **No arrancar es inaceptable** porque una caída de base **coincide a menudo con un incidente**:
  deja al SOC sin pantalla justo cuando hace falta.
- **Arrancar mostrando datos sin alcance resuelto es inaceptable** (regla de oro 5): adivinar el
  alcance de un `soc_operator` es exactamente la brecha multi-tenant.
- Arrancar el armazón y **declarar lo que no se sabe** (regla de oro 7) es verdadero, seguro y
  accionable: el operador ve que el sistema vive y que **no puede establecer su identidad**.

**El riesgo que hay que vigilar, y por eso lleva test propio:** que el degradado se convierta en
**puerta trasera**. Sin `/me` no hay alcance, así que no puede haber ninguna ruta que pinte datos.
Si alguna pantalla resulta accesible en degradado y consulta la API, es un fallo.

**Lo que la decisión NO cambia:** `/me` sigue abriendo sesión de base, y debe seguir haciéndolo —
volver a claims puros reabriría `T-2.114` y dejaría al ocupante móvil sin edificio. Lo que se
arregla es **cómo reacciona el cliente cuando `/me` no contesta**.
