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
> **Última actualización:** 2026-08-15 · **9 decisiones** · 6 tomadas por Mauricio en la sesión del
> 2026-08-15, 3 delegadas el 2026-08-12.

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
