# Pendientes de Mauricio — lo que el software no puede cerrar

> **Qué es esto.** El censo de todo lo que está bloqueado en una persona, no en código. Sale de
> `TASKS.md` y **no lo sustituye**: cada punto de aquí enlaza a su ficha, que es donde vive el
> detalle. Esto es la lista de trabajo; aquellas son la especificación.
>
> **Última actualización:** 2026-08-12 (lotes `T-2.110…T-2.130`) · **26 pendientes** · Estado del
> backlog al escribirlo: 273 tareas · 201 `[x]` · 9 `[~]` · 63 `[ ]`, de las cuales la mayoría
> son `SOFTWARE` y las demás están aquí.
>
> **Bajaste de 29 a 26 sin hacer nada**, porque el 2026-08-12 se cerraron por delegación las tres
> decisiones que no exigían ni herramientas ni terceros (§1.2, §1.8, §1.9). Las que quedan **no
> se delegaron a propósito**: cuestan dinero, tiempo de un tercero, o afectan a un edificio con
> gente dentro.
>
> **Cambios de estas pasadas:** §1.6 (protección de rama) **cerrada — ya estaba hecha**; **§2.1
> cerrada: la nube desplegada y la base en `0038`**; §3.4 gana el aviso de re-correr
> `GATE-HW 02`; y **§1.2, §1.8 y §1.9 quedan DECIDIDAS por delegación explícita**, cada una con
> su razón escrita para poder revocarla. Entre las tres desbloquearon cinco fichas de software,
> todas ya cerradas el mismo día (`T-2.79.d`, `T-2.82.a`, `T-2.123`, `T-2.130`, `T-2.128`).
>
> **Y lo que ahora es lo siguiente, porque el despliegue de la nube lo dejó a un paso:** el
> gabinete todavía corre el código viejo. Hasta que se despliegue el edge, `T-2.116` no existe
> para el Pi —el acuse llega sin el estado del relé— y **`GATE-HW 02` acreditaría la conducta
> vieja**. Ver §3.4.

---

## Por qué esta lista importa más que la de software

De los seis elementos de la ruta crítica hacia el primer cliente, **el software controla uno y
medio**. Los otros cuatro y medio están en esta lista. Se puede terminar todo el código y seguir
sin poder vender.

Y hay dos que **tienen plazo externo** —dependen de que un tercero conteste—, así que **cuanto
antes se arranquen, antes dejan de ser el cuello de botella**: el alta de WhatsApp Business
(§4.2) y el marco normativo citable (§4.1).

---

## 1 · DECISIONES — no necesitan herramientas, solo criterio

Son las más baratas y las que **desbloquean software inmediatamente**. Ninguna requiere AWS, ni
el gabinete, ni un tercero.

> **Estado de esta sección (2026-08-12).** Cuatro puntos ya no piden nada:
>
> | | Punto | Estado |
> |---|---|---|
> | ✅ | §1.2 · ¿gana `empty` o `stale`? | **DECIDIDA** — gana `stale` |
> | ✅ | §1.6 · protección de rama | **HECHA** por Mauricio |
> | ✅ | §1.8 · `lock_timeout` del request | **DECIDIDA** — ~10 s, con cifras medidas |
> | ✅ | §1.9 · ¿arranca la consola sin base? | **DECIDIDA** — en degradado, declarando |
> | ⏳ | **§1.1 · ventana de mantenimiento vs hardware** | **abierta — cuesta un ciclo real de gas y puertas en un edificio con gente** |
> | ⏳ | **§1.7 · ¿un pánico despierta al edificio?** | **abierta — no es una decisión técnica** |
> | ⏳ | §1.3 · el teléfono del consentimiento | abierta (también legal) |
> | ⏳ | §1.4 · ¿quién actualiza el catálogo SSN? | abierta |
> | ⏳ | §1.5 · mini-ShakeMap y CCTV | abierta, no bloquea nada hoy |
>
> **Las tres decididas el 2026-08-12 lo fueron por delegación explícita** («decide por mí»), y
> cada una lleva su razón escrita **para que se pueda revocar con conocimiento**. Las dos que
> siguen en negrita **no se delegaron a propósito**: §1.1 cuesta un ciclo eléctrico real de gas y
> puertas en un edificio ocupado, y §1.7 es decidir si dos personas pueden despertar a un
> edificio entero de madrugada. Ninguna de las dos la puede tomar quien no responde por ella.

### 1.1 · ¿Ventana de mantenimiento, o hardware? — [`T-2.70.a`](TASKS.md), criterio 4
**La decisión:** pasar el dueño de los pines a su propio proceso cuesta **un ciclo eléctrico** de
`GAS_VALVE` y `DOOR_RETAINER`. En el edificio: el gas se cierra y las puertas se sueltan, una vez.

Está medido y **no tiene salida en software**: `LGPIOPin.close()` re-reclama la línea como
entrada, así que la bobina cae. Las opciones:

- **(A) Ventana de mantenimiento avisada, una sola vez.** Cuesta un ciclo, hoy, con el edificio
  sobre aviso. **Después de eso, reiniciar `takab-edge` cuesta CERO** — medido.
- **(B) Hardware**: enclavamiento del relé, o un pull-up que sostenga la bobina con la línea
  liberada. **Cambia SPOF-07**: un Pi colgado dejaría de fail-safear gas y puertas.

**Recomendación:** (A). El coste es idéntico al de cualquier despliegue de hoy, y **es el
último**. (B) compra que el traspaso sea gratis a cambio de debilitar el fail-safe, que es peor
negocio.

**Desbloquea:** el traspaso real en el gabinete, y con él `T-2.70` (canary + rollback).

### 1.2 · ~~¿Qué gana, `empty` o `stale`?~~ — ✅ **DECIDIDA: gana `stale`** (2026-08-12)

> **Decidida por delegación explícita de Mauricio** («decide por mí»), no por omisión. Queda aquí
> para que se pueda **revocar con conocimiento**, que es lo contrario de que se pierda.
>
> **La razón:** `empty` afirma un hecho **sobre el mundo** («no hay»). `stale` afirma un hecho
> **sobre nuestro conocimiento** («no lo sé desde las hh:mm»). Cuando los dos son ciertos a la
> vez, **solo el segundo se puede verificar**. Afirmar una ausencia que no puedes comprobar, en la
> consola de un SOC, es el modo de fallo que produce «no hay heridos» cuando lo que pasa es que
> el enlace está caído.
>
> Que sea **menos accionable es la virtud, no el defecto**: manda al operador a revisar el enlace
> en vez de a concluir. Es la regla de oro 7 —«un dato congelado presentado como vivo es peor que
> sin datos»— llevada al caso en que ambas cosas ocurren a la vez.
>
> **Desbloquea** `T-2.79.d` y `T-2.82.a` (`T-2.84.c` ya se había cerrado por otra vía).

> **La pregunta tal como estaba planteada**, para que la decisión se pueda revisar contra ella:
> cuando **no hay dato** *y* **lo poco que hay está viejo**, ¿la pantalla dice «no hay»
> —arriesgando afirmar una ausencia que quizá solo es desconexión— o dice «no lo sé desde las
> hh:mm», que es más honesto y menos accionable? No es un banner: **gobierna toda la consola**.
> La deriva de que cada componente lo resolviera por su cuenta ya había producido una franja muda
> y que **ningún panel de la pantalla donde se firma un dictamen** pudiera declarar su dato viejo.

### 1.3 · El teléfono del consentimiento — [`T-2.80.a`](TASKS.md) *(también `LEGAL`)*
**La decisión:** un sujeto identificado por teléfono tiene su número **en claro** en el registro
de consentimientos, que es **append-only**. Anonimizarlo exige abrir un hueco en ese registro.

¿Qué prevalece: **el derecho del titular** sobre su número, o **la prueba de la base legal** del
envío que ese consentimiento autoriza? Conviene consultarlo con quien lleve la parte legal (§4.1).

### 1.4 · ¿Quién actualiza el catálogo SSN? — [`T-2.66.b`](TASKS.md)
Hay push firmado nube→gabinete y funciona, pero **nadie ingesta el catálogo**. Decidir si se
automatiza contra el SSN, si se sube a mano con cadencia, o si se declara que no se actualiza.

### 1.5 · Mini-ShakeMap y la arquitectura de CCTV — [`T-3.09`](TASKS.md), [`T-3.10`](TASKS.md)
Van con el Bloque IV; no bloquean nada hoy. `T-3.09` **exige derogar por su nombre** la viñeta
diferida del blueprint — y solo esa.

### 1.6 · ~~`main` NO tiene protección de rama~~ — ✅ **HECHO** (verificado 2026-08-10)

**Ya está puesta, y bien.** `gh api` confirma protección viva sobre `main` con los **siete**
checks exigidos, y **verifiqué que los nombres coinciden literalmente con los `name:` de
`ci.yml`** — importa, porque un nombre que no case no bloquea: deja los PR *pendientes para
siempre*, que se siente como un fallo distinto y se diagnostica peor.

Con esto, la matriz de trazabilidad deja de ser más optimista que la realidad: su modelo de
`CUBIERTO` («lo corre un job que bloquea el merge») por fin describe lo que pasa de verdad.

**Lo único que queda, y es decisión tuya, no trámite:** `enforce_admins` está en **`false`**. Tú
eres el único admin, así que **puedes mergear con el gate en rojo**. Hoy eso es una válvula de
escape útil trabajando solo; el día que entre alguien más al repositorio, es un agujero. No hace
falta cerrarlo ahora — hace falta que sea una elección y no un olvido.

### 1.9 · ~~¿Debe arrancar la consola con la base caída?~~ — ✅ **DECIDIDA: arranca en degradado** (2026-08-12)

**El contexto.** `T-2.114` necesitaba que `/me` devolviera el inmueble del ocupante —el dato no
viaja en el claim de Cognito—, así que **`/me` dejó de ser claims puros y abre sesión de base**.
Efecto: con Postgres caído, la consola web ya no arrancaba. En móvil no hay regresión (conserva
la sesión y resuelve del caché, regla de oro 2).

> **Decidida por delegación explícita de Mauricio** («decide por mí»). Revocable con esto escrito.
>
> **LA DECISIÓN: la consola ARRANCA, DECLARANDO que no puede establecer el alcance del operador,
> y sin pintar NI UN dato de tenant.**
>
> Es la única combinación que respeta las dos reglas que aquí tiran en direcciones opuestas:
> - **No arrancar es inaceptable** porque una caída de base **coincide a menudo con un incidente**:
>   deja al SOC sin pantalla justo cuando hace falta.
> - **Arrancar mostrando datos sin alcance resuelto es inaceptable** (regla de oro 5): adivinar el
>   alcance de un `soc_operator` es exactamente la brecha multi-tenant.
> - Arrancar el armazón y **declarar lo que no se sabe** (regla de oro 7) es verdadero, seguro y
>   accionable: el operador ve que el sistema vive y que **no puede establecer su identidad**.
>
> **El riesgo que hay que vigilar, y por eso lleva test propio:** que el degradado se convierta en
> **puerta trasera**. Sin `/me` no hay alcance, así que no puede haber ninguna ruta que pinte
> datos. Si alguna pantalla resulta accesible en degradado y consulta la API, es un fallo.
>
> **Lo que la decisión NO cambia:** `/me` sigue abriendo sesión de base, y debe seguir haciéndolo
> — volver a claims puros reabriría `T-2.114` y dejaría al ocupante móvil sin edificio. Lo que se
> arregla es **cómo reacciona el cliente cuando `/me` no contesta**.

### 1.7 · ¿Un pánico despierta a todo el edificio? — [`T-2.106`](TASKS.md)
El quórum de pánico emite el comando de sirena y **no notifica a nadie**: la ruta del voto no
toca `notify/`. Con `T-2.106` la app ya explica la alarma, pero se entera **en el siguiente
sondeo** — 30 s en reposo, que bajan a 5 s en cuanto entra en `building_alarm`.

Mandar push por una activación manual **no es decisión técnica**: es decidir si dos personas
pueden despertar a un edificio entero de madrugada. Las tres salidas son legítimas —push a todos,
push solo a tácticos, o nada y que lo diga la sirena— y ninguna se puede elegir desde el código.

### 1.8 · ~~`lock_timeout` global en la conexión del request~~ — ✅ **DECIDIDA: se pone, ~10 s** (2026-08-12)

> **Decidida por delegación explícita de Mauricio** («decide por mí»), **con las cifras de
> `T-2.121` sobre la mesa** — que es lo que la convirtió de corazonada en decisión. Se implementa
> en `T-2.130`. Revocable con todo esto escrito.
>
> **El criterio duro, y es el que manda sobre el número exacto:** `lock_timeout` **< timeout del
> pool (30 s)**. Por debajo, un bloqueo degrada *una petición*; por encima —o sin tope, como
> hasta hoy— degrada *el proceso entero*, porque diez esperas agotan el pool y entonces **falla
> también lo que ni siquiera tocaba la tabla bloqueada**. Eso está medido, no supuesto.
>
> **Valor: ~10 s**, y no los 3 s de las conexiones de segundo plano. La diferencia tiene razón:
> una auditoría lateral es best-effort y se puede tirar; **una petición es una persona
> esperando**, y hay esperas legítimas por lock de **fila** —serialización de acuses— que cortar
> a 3 s rompería.
>
> **Lo que esta decisión NO absorbe**, y conviene no darlo por hecho: `T-2.128` (el fan-out del
> WebSocket es en serie) sigue abierta. Un tope global habría convertido el silencio del hub en
> una excepción registrada, nada más.
>
> **Queda una pregunta dentro de la ficha, no de esta lista:** si el tope aplica también a los
> **workers**. Un worker de ingesta que aborta por un lock puede perder un lote si no reintenta;
> lo resuelve `T-2.130` con su razón escrita.

### 1.8.bis · El planteamiento original — [`T-2.73.c`](TASKS.md)
`T-2.73.c` cerró el interbloqueo por el lado de la conexión **lateral**. La conexión **del
request** sigue sin tope: si `audit_log` está bloqueada *antes* de que el request empiece, se
cuelga en el primer `SELECT`.

Poner un `lock_timeout` global en `get_tenant_conn` cambia el comportamiento de **toda** la API
bajo contención —convierte esperas en errores 5xx— y eso es una decisión de producción, no un
refactor. Decidir si se pone, con qué valor, y si aplica también a los workers.

> ## ⚠️ Actualización 2026-08-11 — **esto ya no es una decisión a ciegas: está medido**
>
> `T-2.121` reprodujo el escenario con un `LOCK TABLE incidents IN ACCESS EXCLUSIVE MODE` de un
> tercero y midió qué pasaba **antes** de arreglarlo:
>
> | Hecho | Medido |
> |---|---|
> | El hub del WebSocket queda **encolado, no lento** | `pg_locks`: `granted=false` |
> | El reparto no vuelve | **25.16 s** y seguía esperando (techo del test) |
> | **El SOC entero se queda mudo** | el reparto es en serie: un segundo aviso que ni tocaba la base no llegó en 25 s |
> | El operador **no se entera** | la consola seguía diciendo «CONECTADO» y «● LIVE» |
> | **Y arrastra a toda la API** | 10 lectores encolados agotan el pool: cualquier petición, **`TimeoutError` a los 30 s** |
>
> Eso último es lo que convierte esto de «una molestia del WebSocket» en un problema de la API
> entera: **falla también lo que ni siquiera tocaba la tabla bloqueada.**
>
> **La recomendación, con su criterio duro:** ponlo, y con **`lock_timeout` MENOR que el timeout
> del pool (30 s)**. Por debajo de esa cifra un bloqueo degrada *una petición*; por encima —o sin
> tope, como hoy— degrada *el proceso*. Valor sugerido: **~10 s** para la conexión de la petición,
> **no** los 3 s de las conexiones de segundo plano — una auditoría lateral es best-effort y se
> puede tirar, una petición es **una persona esperando**, y hay esperas legítimas por lock de fila
> que no conviene cortar tan corto.
>
> **Y una corrección a lo que decía esta sección ayer:** escribí que la decisión global
> «absorbería `T-2.121` entera». **Es falso**, y lo demuestra la medición: un tope global habría
> convertido el silencio del hub en una excepción registrada, nada más. No absorbe que al
> operador **se le diga** (hoy se le cierra el canal y la consola pinta «● SIN LIVE»), ni el
> hallazgo de que el reparto es en serie — que es lo que convertía un lock en un **apagón del
> SOC** en vez de un frame perdido. Eso quedó fichado aparte ([`T-2.128`](TASKS.md)).
>
> **Lo que sigue sin tope y por eso te toca decidir:** la conexión de la **petición**. Medido: un
> request REST contra la tabla bloqueada **sigue esperando para siempre** (sin respuesta en 40 s
> de techo). Ya no es teoría.

---

## 2 · VENTANA AWS — una sesión con credenciales, en este orden

> **Trampas ya pagadas, léelas antes de empezar:**
> - **SSO rancio:** `aws sso login` a secas **no basta**; hace falta `aws sso logout` primero, o
>   terraform muere con `InvalidGrantException` aunque `aws sts` funcione.
> - **`terraform apply` sin `-var serve_enabled=true` destruía la consola.** Hoy el
>   `auto.tfvars` lo trae, pero conviene mirarlo.
> - **Toda regla IoT nueva exige su línea en la política de flota**, o AWS desconecta al gabinete
>   en cada publish.
> - La IP doméstica rota a diario: si algo da **timeout** (no 403), es el firewall.

### 2.1 · ~~Aplicar las migraciones que estaban escritas y sin desplegar~~ — ✅ **HECHO** (2026-08-11)

**Desplegado y verificado en la nube**, no inferido del código de salida: los **siete**
contenedores corriendo en `48d530f`, `/api/health` respondiendo `{"status":"ok","build":"48d530f"}`
y `alembic_version` de la base **en `0038_privacy_erasure_on_behalf`**, que es la cabeza del repo.
O sea que entraron las 0027…0036 que faltaban **y** las dos nuevas (0037, 0038).

**Sigue pendiente de esta sección**, y son **dos** cosas, las dos de IAM y las dos invisibles
hasta que fallan:

1. El `terraform apply` de los tres statements IAM de las ventanas de mantenimiento
   ([`T-2.71`](TASKS.md)) — el despliegue de imágenes **no lo toca**.
2. **Nuevo (2026-08-13, `T-2.132`): `sqs:ChangeMessageVisibility`** en el rol de los workers. Ya
   está escrito en el Terraform; **sin el `apply` el arreglo es decorativo**. El worker no se cae
   —la llamada es best-effort— pero el mensaje se hace visible a mitad del reintento y otro worker
   **gasta justo la recepción que se estaba ahorrando**, que es el defecto entero de esa ficha.
   Es de la misma familia que la trampa ya pagada de las reglas IoT: **un permiso que falta no da
   error, da una conducta silenciosamente peor**.

> **La trampa del SSO se cobró este despliegue, y conviene saber cómo se reconoce.** Falló con
> `InvalidGrantException` **mientras el `docker login` a ECR funcionaba**. Ésa es la firma: no es
> que falten credenciales, es la caché del SSO caducada, y `aws sts` puede seguir contestando
> mientras terraform ya no. `aws sso login` a secas **no lo arregla** — hace falta
> `aws sso logout` primero.

### 2.2 · Confirmar que la alarma del gabinete fantasma **sale** de `INSUFFICIENT_DATA`
Está escrito en tres sitios y es contraintuitivo: `insufficient_data_actions` dispara **solo al
transitar**, así que una métrica que nunca arranca deja la alarma **nacida** en ese estado y
aparcada. **Si no llega el correo de `ok_actions` en ~15 min, la métrica nunca empezó.**

### 2.3 · [`T-2.87`](TASKS.md) · Apply de Cognito
### 2.4 · [`T-2.88`](TASKS.md) · Rol CI OIDC endurecido *(cierra también `T-1.44`)*
### 2.5 · [`T-2.89`](TASKS.md) · Encender `console_scope_enforced`
> **La única brecha multi-tenant viva en producción.** Tiene **secuencia obligada** —invertirla
> deja a cada `soc_operator` con cero estaciones—: primero recorrer los `scope_gap` del
> `audit_log`, luego asignar alcance, y **encenderlo al final**.
>
> **⚠️ Y pondrá la suite en rojo:** dos tests HTTP fijan hoy la conducta *no* impuesta. Hay que
> invertirlos **en el mismo cambio**, no después. Que no se descubra en mitad de la ventana.

### 2.6 · [`T-2.91`](TASKS.md) · Sembrar un occupant real
Hoy **no existen** usuarios móviles de prueba. Los scripts están escritos y **nunca se han
corrido**. El occupant necesita código de enrolamiento.

### 2.7 · [`T-2.90`](TASKS.md) · e2e contra el entorno desplegado
### 2.8 · [`T-2.74`](TASKS.md) · `G-09` · restore real con RTO medido
> **DESBLOQUEADA el 2026-08-09**: `T-2.73.a` está cerrada en software y el checklist ejecutable
> vive en el **§9.3 del runbook de backup**, con los comandos completos. En orden:
>
> 1. `make cloud-images && make cloud-deploy` — **la imagen desplegada hoy no conoce el flag
>    nuevo**. Renueva el SSO justo antes: el build tarda ~40 min y el token expira a mitad.
> 2. `terraform apply` del env dev. **Mira el plan primero**: `aws_instance.db` **no** debe
>    aparecer ni como update ni como replace. Si aparece, para — significa que algo se movió al
>    `user_data` y eso **tira la base**.
> 3. `aws ssm start-associations-once` sobre la asociación nueva: no se relanza sola y puede
>    tardar 24 h.
> 4. **Lee la salida de esa pasada.** Dice `OK: la imagen … sabe tomar la huella anclada` o
>    `AVISO: … NO acepta …`. **Ése es el criterio 3 de `T-2.73.a`, respondido con un comando** —
>    en vez de descubrirlo a mitad de la ventana.
> 5. Dispara `/opt/takab/bin/takab-backup.sh` a mano y comprueba que en S3 están **los dos**
>    objetos del día (`.dump` **y** `.fingerprint.json`).
>
> Y recuerda: **un SKIP no es un PASS** — el checklist de restore salía verde perdiendo datos.

### 2.9 · [`T-2.78`](TASKS.md) · SES fuera de sandbox + cadena on-call
> **Bloqueado por algo que no es un trámite: no hay dominio.** Sin dominio no hay DKIM/SPF.
> El runbook está escrito con los comandos y los registros DNS; los tres registros de
> verificación (S-1…S-12, C-1…C-10, escalamiento) están **en blanco**.
>
> **Y de aquí sale un dato que hoy no existe y que ya se está usando:** el manual de operación
> dice «avisa a soporte» unas 25 veces, **y ese teléfono no está en ninguna parte**.

---

## 3 · SESIONES FÍSICAS — con el gabinete y el edificio

> `G-04` (relés reales, latencia <100 ms acreditada) sigue abierto **desde el hito de la Fase 1**.
> Hasta cerrarlo, todo lo que el software mide sobre actuación es contra relés en MOCK.

### 3.1 · [`T-2.92`](TASKS.md) · Sesión de vida — `G-01`, `G-02`, `G-04`
**La sesión que decide si el producto es real.** No espera a nada más.

### 3.2 · [`T-2.93`](TASKS.md) · Sesión instrumental — `G-03`, `G-05`, `G-07`, `G-10`
Incluye el gate #3 del Shake: hoy sus 5 tests se saltan cuando el sensor no está alcanzable, y la
suite **lo declara en voz alta** en vez de callarlo.

### 3.3 · [`T-2.94`](TASKS.md) · Sesión de sitio — `G-06`, `G-08`
> **Única dependencia declarada del Bloque III sobre el II:** necesita `T-2.78`, porque un
> simulacro con **cascada de notificación real** no se acredita con canales simulados.

### 3.4 · [`T-2.95`](TASKS.md) · `GATE-HW` móvil + voceo
Entorno preparado y verde; **falta un dispositivo físico**.

> ## ✅ El bloqueo se levantó: el gabinete YA corre el código nuevo (2026-08-12)
>
> **`gw-dev-0001` está `online` con `fw_version` = `fw_running` = `2d12c3a`** —las dos columnas
> existen precisamente para cazar «código escrito que nadie corre», y coinciden— y con
> `SCHEMA_VERSION 1.11.0`. La nube va en el mismo commit. **`T-2.116` y `T-2.120` dejan de ser
> teoría: el acuse ya trae el estado real del relé tras el arbitraje.**
>
> **Lo que te toca a ti, y ahora sí se puede:** re-correr el flujo **`GATE-HW 02`**, que se
> acreditó contra la conducta vieja. Lo que verás distinto: silenciar durante una alerta vigente
> ahora dice **«SU DEMANDA SE RETIRÓ · LA SIRENA SIGUE ACTIVA»** en vez de fingir éxito. Necesita
> un dispositivo físico, así que no lo puede correr el software.
>
> **Del despliegue quedó una medición que vale para §1.1:** este gabinete **no lleva `GAS_VALVE`
> ni `DOOR_RETAINER`** (`relays_status.installed = ["siren","strobe"]`), así que el reinicio de
> `takab-edge` **no cicló nada** — sirena y estrobo siguieron desenergizados antes y después. El
> coste de un ciclo que describe §1.1 es real **solo en un gabinete que los tenga instalados**;
> en el de desarrollo, desplegar es gratis.

### 3.5 · El traspaso del dueño de los pines
Depende de la decisión §1.1. Si es (A), va en esta misma visita. **Orden correcto y no
intercambiable:** `TAKAB_EDGE_GPIO_OWNER=gpio` en `edge.env` → `systemctl enable --now
takab-gpio` → `systemctl restart takab-edge`. Al revés falla contra el cerrojo.

---

## 4 · LEGAL Y COMERCIAL — plazo externo, arrancar YA

### 4.1 · [`T-2.96`](TASKS.md) · `GATE-LEGAL` · marco normativo citable
> **La cita vieja «NOM-003-SCT» era una norma de TRANSPORTE y no aplicaba.** Hoy el sistema
> declara el marco que **el cliente** afirma, con su deslinde: TAKAB no lo respalda. Eso es
> honesto pero **no es un marco propio**, y un cliente institucional lo va a pedir.

### 4.2 · [`T-2.77.a`](TASKS.md) · Alta del WhatsApp Business Account + aprobación de plantilla
> **Plazo externo: lo aprueba Meta.** El código está completo y probado (53 tests); la plantilla
> del repo está `PENDING` a propósito y el canal **cae solo** si Meta la pausa. Arrancarlo ya es
> lo que evita que sea el cuello de botella.

### 4.3 · [`T-2.76.a`](TASKS.md) · Cuenta Twilio + número mexicano
### 4.4 · [`T-2.97`](TASKS.md) · `GATE-STORE` · APNs/FCM reales + tono SASMEX
### 4.5 · [`T-2.98`](TASKS.md) · Entitlement Critical Alerts de Apple
> Apple lo concede caso por caso. **Plazo externo.**

---

## 5 · CIERRE DEL PROYECTO

### 5.1 · [`T-4.01`](TASKS.md) · Auditoría de cierre final
### 5.2 · [`T-4.03`](TASKS.md) · Traspaso operativo
### 5.3 · [`T-4.04`](TASKS.md) · Aceptación firmada
> El documento está escrito con los campos y las firmas **en blanco**:
> [`ENTREGA-Y-ACEPTACION-TAKAB.md`](ENTREGA-Y-ACEPTACION-TAKAB.md).

---

## Si solo se pueden hacer tres cosas

1. **Arrancar §4.1 y §4.2.** Son las de **plazo externo** —las contesta un tercero—, así que son
   las únicas que no se pueden acelerar después. Ahora encabezan la lista porque lo que estaba
   antes en este puesto (proteger `main`, §1.6) **ya está hecho**.
2. **Las decisiones de §1.1 y §1.2.** Cuestan pensar, no herramientas, y desbloquean cinco fichas
   de software entre las dos.
3. **La sesión de vida (§3.1).** Es la que dice si el producto es real, y no espera a nada.

Y en cuanto haya un hueco con el edificio: **la sesión de vida (§3.1)**, que es la que dice si el
producto es real y no espera a nada.
