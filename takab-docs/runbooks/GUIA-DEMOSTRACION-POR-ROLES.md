# Guía de demostración · **qué abrir, quién eres en cada pantalla y qué haces**

> **Ficha:** [`T-7.28`](../TASKS.md) · **Dueño:** Mauricio
> **Compañera de:** [`RUNBOOK-demo-cliente.md`](RUNBOOK-demo-cliente.md) — **no lo sustituye.**
>
> Aquel runbook está organizado **por acto**: qué pasa, en qué orden y cómo se acredita. Éste
> está organizado **por rol y por pantalla**: quién eres en cada momento, qué tocas, qué NO
> puedes tocar y qué dices. Son el mismo ensayo mirado por dos ejes, y hacen falta los dos —
> el día de la demostración no te preguntas «¿qué acto toca?», te preguntas **«¿en qué pantalla
> estoy y qué hago aquí?»**.
>
> Lo que aquí no se repite y hay que leer allí: el aviso de que **esto no es un simulacro**
> (la sirena suena de verdad y la cascada notifica de verdad), el **Plan B** para cuando algo
> se cae en medio, y la lista **«lo que NO debe decirse»**.

---

## 0 · Lo primero: **esto no se improvisa el mismo día**

Hay tres cosas que **tardan** y que, si las descubres con el cliente delante, ya no hay
demostración. Ninguna es difícil; todas son irreversibles en el momento equivocado.

| Cuándo | Qué | Por qué no puede esperar |
|---|---|---|
| **Días antes** | crear los usuarios y **enrolar el MFA de cada uno** | el pool exige TOTP en el primer login: hay que abrir el authenticator, escanear el QR y guardarlo. Con el cliente delante es un minuto muerto por cada rol. |
| **Días antes** | instalar el APK en el Pixel y **entrar una vez con cada rol móvil** | la primera entrada del `occupant` puede quedarse en onboarding si le falta la asignación de zona (ver §2). |
| **El mismo día, antes de que entre nadie** | `--preflight`, **abrir la consola** y **mirar la edad del catálogo del panel** (⚠️ §1) | el preflight caza **una decena** de estados que rompen la demostración **sin dar error a la vista** — enumerados en [`RUNBOOK-demo-cliente.md § Precondiciones`](RUNBOOK-demo-cliente.md), que es donde está la tabla buena. *(Aquí decía «cuatro»: contado sobre `preflight()` de `deploy/demo/guion.sh` son diez comprobaciones — y tres de las no contadas, modo demostración, destinatarios ajenos y cero tokens de push, son justo las que fallan calladas.)* Y la consola hay que abrirla antes por lo del mapa (ver el Plan B, caso B4). |

```bash
# El mismo día, lo primero de todo:
AWS_PROFILE=takab-dev bash deploy/demo/guion.sh --preflight
```

**La puerta es `0 ✗`, no un número de ✓.** Cuántos ✓ salen depende de cuántas comprobaciones
tenga el guion ese día —el 2026-09-12 fueron 13— y fijarse en ese número envejece; lo que no
envejece es que **un solo ✗ hace que el guion falle en silencio**.

### 0·bis · La sesión el día de la demostración (`D-38`)

**Hasta el 2026-09-22 la sesión real duraba unos 60 minutos en la consola y en el teléfono**, y
el ensayo 1 duró 59. Con `D-38` (`T-8.02`…`T-8.05`) dura lo que dice el rol, contado **desde el
login**: 24 h los roles de consola, 30 días brigadista e inspector, 90 días el ocupante. Lo que
eso cambia en la preparación:

- **Un perfil de navegador por rol de consola** (o ventanas de incógnito separadas), porque la
  cookie de la Hosted UI de Cognito es **compartida**: cambiar de rol en el mismo perfil obliga a
  cerrar sesión y volver a teclear contraseña y código. Entra en cada uno **la misma mañana**. Un
  login del día anterior puede cumplir sus 24 h en mitad del acto 4; la consola avisa una hora
  antes con «SU SESIÓN TERMINA A LAS hh:mm · RENOVAR AHORA». Si sale ese aviso, renueva **antes**
  de empezar, no durante.
- **Cerrar la pestaña ya no cierra la sesión**: la consola la guarda en el navegador y la retoma.
  Recargar tampoco la cierra.
- **En el Pixel**, entra con brigadista e inspector el día anterior o antes: su sesión dura un
  mes y no vuelve a pedir el código. `security_guard` y `building_admin` duran 24 h: si se
  enseñan, entra con ellos la misma mañana.
- **Si la sesión termina por tope**, la pantalla lo dice («SU SESIÓN DE 24 H TERMINÓ»), no un
  error genérico. Hay que volver a entrar con contraseña y código. No hay prórroga, ni siquiera
  con un incidente abierto: es la decisión de `D-38`.

---

## 1 · El montaje · **cuatro superficies, y no todas son una pantalla**

| # | Superficie | Qué es | Quién la opera | Se ve desde |
|---|---|---|---|---|
| **A** | **Consola web (SOC)** | `https://16-58-11-196.sslip.io` | tú, cambiando de rol | proyector o pantalla grande |
| **B** | **App móvil** | APK en el Pixel 8 Pro | tú, y el cliente si quiere | el teléfono en la mano, o duplicado a pantalla |
| **C** | **Panel del gabinete** | `http://raspberry-cerebro.local:8080` | nadie lo «opera»: se mira | segunda pestaña del navegador |
| **D** | **El gabinete físico** | el WR-1, la sirena, el estrobo, el Raspberry Shake | tú, con la mano | la caja, abierta |

> **La superficie C es la que gana la demostración y casi siempre se olvida.** La consola cuenta
> lo que la nube sabe; el panel del gabinete cuenta **lo que el edificio hace sin depender de
> nadie**. Es donde se ve el acta del reflejo, la continuidad de SeedLink y —si se cae
> internet— es la única que sigue contando la historia. Tenla abierta desde el minuto cero.

> ⚠️ **Pero hay una pestaña del panel que hoy NO conviene abrir a ciegas: «Sismicidad SSN».**
> Medido el 2026-09-22 contra `http://raspberry-cerebro.local:8080/api/catalog`: la
> instantánea del catálogo es del **2026-07-31 09:16**, tiene **53 días** y su propio umbral
> de frescura son **2 días** — va **26× por encima**. El panel no lo disimula, que es lo
> bueno: rotula en ámbar «**CATÁLOGO VIEJO · INSTANTÁNEA DE HACE 53d · UMBRAL 2d**», el
> contador pasa a «15 **EN LA CAPTURA**» y el más cercano a «MÁS CERCANO **EN LA CAPTURA DE
> HACE 53d**». Lo malo sería que saliera sin que nadie lo hubiera anunciado.
>
> **Dónde aparece:** en la vista normal está **detrás de la pestaña**, no a la vista —el panel
> arranca en «Bitácora local»—, pero salta al frente en cuanto alguien pulsa **MURO** (la
> tira de chips de la cabecera), porque ese modo saca la tarjeta «Sismicidad regional · SSN»
> con el mismo rótulo ámbar. Si vas a proyectar en MURO, esto se ve desde el minuto cero.
>
> **Dos salidas, y hay que elegir una antes, no delante del cliente:**
> 1. **Refrescarla.** El camino existe y está vivo desde `T-2.24`: `POST /gateways/{id}/catalog`
>    publica la instantánea **firmada** nube→gabinete y el Pi la cambia en caliente. No hay
>    `make` que lo haga: pide un JWT de consola del pool web (SRP + TOTP una vez) y una captura
>    nueva, así que es tarea de **días antes**, no de la mañana.
> 2. **Contarla.** Si se proyecta vieja, la frase es: *«esa lista es una instantánea fechada, y
>    el panel les está diciendo su edad en vez de fingir que es de ahora. Eso es exactamente lo
>    que queremos que haga con cualquier dato viejo.»*
>
> ⚠️ **Y no se convierte en un argumento.** La fuente que ahí sale rotulada es el **Servicio
> Sismológico Nacional**, y el `§ C` del `goal-presentacion.sh` la tiene en la lista de lo que
> no se promete: **no se consulta para correlacionar**, y la atribución de sus cifras sigue sin
> cerrar (`D-06` / `T-2.149`). Es contexto regional en una pantalla local, nada más.

### El mínimo viable, y qué pierdes con él

| Montaje | Qué puedes enseñar | Qué NO |
|---|---|---|
| **1 portátil + 1 teléfono + tú** (lo normal) | todo el recorrido de los cuatro actos | el **quórum de 2 ocupantes** (`panic_vote`): con un solo teléfono sólo se emite el **1.er voto** |
| **+ 1 segundo teléfono** | además, el quórum de 2 y el pánico completo | — |
| **+ 1 segunda persona** | puedes dejar a alguien en la consola mientras tú estás en el gabinete | — (pero se pierde el control del ritmo) |

---

## 2 · Los usuarios · **DOS pools de Cognito, y cruzarlos es 401 en las dos direcciones**

⚠️ **Ésta es la trampa que puede dejarte sin demostración, y no da un error que se entienda.**
Los usuarios de consola y los de la app **no son los mismos ni viven en el mismo sitio**:

| Usuario | Pool | MFA | Entra en | Si lo creas en el pool equivocado |
|---|---|---|---|---|
| `takab_superadmin`, `tenant_admin`, `soc_operator`, `inspector`, `gov_operator`, `building_admin` | **principal** (`surface=web`) | **ON** — TOTP obligatorio | consola web | no entra **nunca** en la app |
| `brigadista` | **principal** | **ON** — TOTP obligatorio | app móvil | — |
| `occupant` | **de ocupantes** | opcional | app móvil | no entra **nunca** |

Se siembran con dos comandos distintos, y no es opcional que sean dos.

> ⚠️ **Antes de los dos: la sesión de AWS.** Los dos scripts leen la identidad de los pools
> del **estado de terraform** (`seed_console_users.sh:35`, `seed_mobile_users.sh:93-94`), así
> que sin sesión fresca no arrancan — y el error que dan **no menciona ni Cognito ni usuarios**.
> Medido el 2026-09-22 en la máquina de trabajo: `terraform … output -raw user_pool_id` →
> `InvalidGrantException`, **con `aws sts get-caller-identity` funcionando perfectamente**. Eso
> es caché de SSO rancia, y el reflejo natural —`aws sso login` a secas— **no la arregla**:
>
> ```bash
> aws sso logout && aws sso login --profile takab-dev   # el logout NO es adorno
> ```

```bash
# Consola (6 roles web). Imprime las credenciales UNA sola vez y las guarda en Secrets Manager.
make cloud-users

# App móvil (occupant + brigadista). Pool distinto, y ADEMÁS siembra la zona
# y el código de enrolamiento del ocupante.
make cloud-mobile-users
```

> **⚠️ Y una más, del ocupante.** El `occupant` **no lleva su alcance en el token** (decisión
> `R2`, ratificada en `T-2.00`): se resuelve contra `user_zone_assignments`. Un ocupante creado
> en Cognito y **sin fila de asignación** recibe **404** y la app **se queda en la pantalla de
> onboarding**, sin decir por qué. Esa fila la crea él mismo al consumir un **código de
> enrolamiento**, y eso es lo que siembra el paso 2 de `make cloud-mobile-users`.
>
> **Entra una vez con cada rol antes del día.** Si el ocupante se queda en onboarting delante
> del cliente, la única salida es sembrar el código — y eso pasa por un túnel a la base.

---

## 3 · Tabla maestra · **acto × superficie × rol × qué haces**

La lectura rápida el día de la demostración. Cada fila es «dónde estoy, quién soy, qué toco».

| Acto | Superficie | Tú eres | Qué haces | Qué tiene que verse |
|---|---|---|---|---|
| **0** | terminal | — | `guion.sh --preflight` | **0 ✗** (los ✓ que sean) |
| **1** | **A** consola | `soc_operator` | nada: enseñar | mapa con estaciones vivas, cola vacía, **el pulso de vida latiendo** |
| **1** | **C** panel | — | nada: enseñar | nivel `normal`, relés en reposo, nube en línea, SeedLink sin huecos |
| **2** | **D** gabinete | tú, con la mano | **un golpe seco** junto al Raspberry Shake | — |
| **2** | **C** panel | — | mirar | el nivel **sube** a `watch` / `restricted` |
| **2** | **A** consola | `soc_operator` | mirar y **no tocar** | escena de aviso, **«SOLO AVISO, SIN ACTUACIÓN»** · incidente `local_threshold` |
| **3** | **D** gabinete | tú | **pulsar el WR-1** | la **sirena suena** (reflejo local) |
| **3** | **B** teléfono | `occupant` | **nada: el teléfono está bloqueado en la mesa** | se enciende solo y abre la pantalla de crisis |
| **3** | **A** consola | `soc_operator` | **acusar** el incidente | incidente con origen `sasmex` |
| **3** | **C** panel | — | mirar | **el acta del reflejo**, con su latencia y su presupuesto |
| **4** | **B** teléfono | `brigadista` | foto forense → **reporte de daños** | la marca horneada en la foto; las fotos suben con su SHA-256 |
| **4** | **A** consola | **`inspector`** | abrir EVALUACIÓN y **firmar el dictamen** | el dictamen sucede al preliminar; la fase pasa a `reentry_approved` |
| **4** | **B** teléfono | `occupant` | mirar | le llega **«reingreso permitido»** (el ocupante NO recibe el PDF) |
| **4** | **A** consola | `inspector` | **generar** el PDF del dictamen | (`generate_report` sólo lo tienen `inspector` y `takab_superadmin` — el `soc_operator` **no**) |
| **4** | terminal | — | `guion.sh --reporte` | el PDF existe, lleva imágenes dentro y **su SHA-256 coincide** con el registrado |
| **cierre** | **C** panel | — | botón **CERRAR ALERTA** del panel (2 clics + **PIN**) | se suelta el enclavado |
| **cierre** | **A** consola | `soc_operator` | clasificar el incidente como **`reproduccion`** | el incidente cierra y **no** cuenta como sismo real |

> **Cronometrado y en orden, de un tirón:**
> ```bash
> AWS_PROFILE=takab-dev bash deploy/demo/guion.sh --full
> ```
> Va acto por acto, espera a que hagas lo físico, mide cada uno y al final saca la tabla del
> § Registro lista para pegar. **No acciona nada**: lo físico lo haces tú.

---

## 4 · El recorrido, rol por rol · **qué tocas y qué dices**

### Acto 1 · Eres `soc_operator` — «así se ve un día en que no pasa nada»

**Abres:** consola → MONITOREO. Y la segunda pestaña con el panel del gabinete.

**Qué haces:** nada. Éste es el acto de no tocar.

**Lo que hay que señalar, porque no se ve solo:**
- **El pulso de vida late únicamente si el dato es en vivo.** Si el gabinete estuviera mudo, la
  franja lo diría **en vez de pintar un dato viejo como si fuera de ahora**. Eso es la regla de
  oro 7 y es más vendible que cualquier gráfica.
- **La cifra de continuidad del panel** (paquetes SeedLink, huecos). Es lo que contesta «¿y cómo
  sé que está vivo y no congelado?».

> *«Así se ve el 99,9 % del tiempo, y esto es lo que queremos que vean casi siempre.»*

### Acto 2 · Sigues siendo `soc_operator` — **el acto que más vende, y es el de no hacer nada**

**Qué haces:** vas al gabinete y **das un golpe seco** junto al sensor. Vuelves a la consola.

**Lo que tiene que pasar — y lo que tiene que NO pasar:** el nivel sube, la nube abre un
incidente `local_threshold`… **y ningún relé se mueve**. La sirena no suena.

> **Esto no es una limitación: es la política, y hay que contarla como tal.** Una sola estación
> **no acciona** (`T-2.32`, ratificada el 2026-08-03). Para que suene hace falta SASMEX o el
> acuerdo de **≥3 inmuebles**. Un sistema que grita porque alguien dio un portazo es un sistema
> que la gente aprende a ignorar — y entonces no sirve el día que importa.

> *«El edificio se movió, el sistema lo vio, lo registró… y no hizo sonar nada. Eso es
> deliberado. Una estación sola avisa; para actuar hacen falta tres edificios de acuerdo o la
> alerta oficial.»*

### Acto 3 · **El teléfono está bloqueado sobre la mesa. No lo toques.**

**Qué haces:** pulsas el WR-1. Nada más.

**El orden importa y hay que anunciarlo antes**, porque se ve en un segundo y si no lo
anticipas el cliente no sabe dónde mirar:

1. **La sirena suena** — reflejo local, **sin pasar por la nube ni por internet**.
2. **La consola abre el incidente** con origen `sasmex`.
3. **El teléfono se enciende solo**, con la pantalla bloqueada, y abre la pantalla de crisis.

**Como `soc_operator`, acusas el incidente** en MONITOREO.

**Después, en el panel (superficie C): el acta del reflejo.** Es el número que ningún
competidor enseña: cuánto tardó el sistema desde que entró la señal hasta que cerró el relé,
contra su presupuesto.

> *«Fíjense en el orden: primero sonó, y después se enteró la nube. Si en este momento cortamos
> internet, lo que acaban de oír pasa exactamente igual.»*

> ⚠️ **De los cuatro actos, éste es el único que no se puede repetir en frío.** Si sale mal hay
> que resetear el gabinete y volver a empezar el acto, con el cliente delante. De ahí el
> preflight.

### Entre el 3 y el 4 · **la sacudida se concluye sola**

No hay paso manual (`T-7.30`). El cierre llega cuando el suelo lleva **90 s** en calma, y
**nunca con la alerta enclavada**: si dejas el WR-1 pulsado, el teléfono sigue —correctamente—
en crisis. Si vas con prisa, esto parece un fallo. No lo es: dilo antes.

### Acto 4a · Cambias a `brigadista` en el teléfono

**Qué haces:** cámara forense → foto de un «daño» → reporte de daños con categoría.

**Qué señalar:** la foto lleva **horneada** la marca con hora, ubicación e identificador del
operador, y sube con su **SHA-256** a la cadena de custodia. Es evidencia, no una foto.

> ⚠️ **Y aquí hay que decir una cosa, no callarla:** la redacción asistida **está encendida en
> esta nube** —aquí decía «si el despliegue tiene encendida la…», y ese condicional es una
> invitación a saltarse el párrafo—. Medido el 2026-09-22 en la instancia desplegada:
> `TAKAB_API_OPENROUTER_ENABLED=true` (`T-7.26`, desplegada el 2026-09-21), y el `goal` la
> exige encendida. Así que **la imagen del daño se envía fuera de México** a un proveedor de
> IA para que la describa en el informe. Va **sin el sello** —la franja con hora, ubicación e
> identificador se tapa antes de salir— y el nombre y el teléfono no viajan. **La propia app se
> lo dice al brigadista en la pantalla donde dispara.** Enseña ese aviso: que el sistema lo
> advierta solo vale más que cualquier explicación tuya.

### Acto 4b · Cambias a `inspector` en la consola — **el único que puede firmar**

**Abres:** consola → **EVALUACIÓN** (la ruta sigue siendo `/triage`).

**Qué haces:** revisas y **firmas el dictamen**. Te pedirá el segundo factor.

**Por qué este rol y no otro:** el `inspector` es el único con **Total** en EVALUACIÓN. Ni el
`soc_operator` ni el `tenant_admin` firman, y **el `takab_superadmin` tampoco** — no es un
descuido, es que firmar un dictamen estructural es un acto profesional con nombre y cédula
detrás, no un privilegio administrativo.

> *«Esto no lo firma el sistema ni lo firma el administrador. Lo firma un ingeniero estructural,
> con su segundo factor, y queda registrado quién y cuándo.»*

> ⚠️ **Lo que este acto acredita, y conviene saberlo:** el flujo móvil `03` —dictamen →
> liberación— es el **único de los seis que nunca se ha acreditado**, justamente porque le
> faltaba la firma de un inspector en la consola. Si lo haces en la demostración **lo estás
> acreditando**: apunta la hora y guárdalo.

### Acto 4c · Vuelves a `occupant` en el teléfono

Le llega **«reingreso permitido»**. **Y sólo eso**: el ocupante **no recibe el PDF**. Es
deliberado — el dictamen técnico va a quien lo tiene que leer.

### Cierre · **parte del guion, no del después**

1. **Soltar el enclavado desde el panel** (superficie **C**): botón **CERRAR ALERTA**,
   que sale solo cuando hay algo que soltar. Son **2 clics + PIN** — el primero arma («CLIC
   NUEVAMENTE PARA CONFIRMAR»), el segundo manda.
2. En la consola: clasificar el incidente como **`reproduccion`**.

> ⚠️ **Aquí decía `curl -X POST http://raspberry-cerebro.local:8080/api/reset`, a secas, y
> eso NO funciona.** Medido el 2026-09-22 contra el gabinete real: ese `curl` devuelve **401**
> con `{"error":"pin"}` mientras `GET /api/status` contesta 200 — o sea, el gabinete está
> perfectamente vivo y lo que falta es el PIN. No es un fallo: desde `T-1.43` toda acción del
> panel se autoriza antes de tocar GPIO, porque silenciar la sirena de un edificio no puede
> depender sólo de estar en la misma LAN. **Con el cliente delante, un 401 en el último paso
> se lee como «se colgó».**
>
> **Por qué el botón y no el `curl`:** el campo del PIN del panel es `type="password"`, así que
> los seis dígitos **no salen en el proyector**; en un `curl` van en la línea de comandos, a la
> vista y al historial del shell. Si aun así hace falta la terminal, el comando completo es:
>
> ```bash
> curl -X POST -H "X-Takab-Pin: <PIN de 6 dígitos del gabinete>" \
>      http://raspberry-cerebro.local:8080/api/reset
> ```
>
> **De dónde sale el PIN:** lo genera `provision_gateway.sh` y lo imprime **una sola vez**
> («PIN del panel local de …»); vive en el gabinete como `TAKAB_EDGE_LOCAL_API_PIN` dentro de
> `/etc/takab/edge.env`, que es **root-only** — leerlo sin `sudo` da un «permission denied» que
> se lee como «no está declarado». Tenlo a mano ANTES, no lo busques en caliente.
>
> ⚠️ **Y ojo con reintentar a ciegas: a los 5 PIN erróneos el panel se bloquea 60 s** (429).
> Un POST **sin** header no gasta intento —el servidor lo trata como el sondeo de la página—,
> pero uno con el PIN equivocado sí.
>
> **Qué pasa si el cierre no se hace:** el enclavado sigue vivo, así que (a) el teléfono del
> ocupante se queda —correctamente— en pantalla de crisis, que es justo lo que «Entre el 3 y
> el 4» avisa que parece un fallo; y (b) el siguiente `--preflight` sale en ✗ por
> `c_enclavado`, y el acto 3 de la próxima demostración no se distinguiría del acto 2.

> ⚠️ **`reproduccion`, no `prueba`.** Las dos cierran y ninguna entra en la tasa de falsos
> positivos, así que **equivocarse no se ve en ningún número**: se ve en lo que el historial
> dice que pasó. `prueba` es mantenimiento; `reproduccion` es exactamente esto, una
> demostración. El valor existe (`T-7.14` · `D-33`) porque una corrida de demostración **no
> cabía en las otras cuatro sin mentir**.

---

## 5 · Qué enseña cada rol · **el mapa para cuando te preguntan algo fuera de guion**

Si el cliente pregunta por algo que no está en los cuatro actos, esto dice **con qué rol se
enseña** y qué pierde si abres el equivocado.

| Si preguntan… | Entra como | Dónde | Cuidado |
|---|---|---|---|
| «¿quién ve qué?» | `takab_superadmin` | Multi-Tenant | pide MFA; **ningún proceso automático puede usarlo** |
| «¿y si tengo 40 edificios?» | `soc_operator` | MONITOREO | su alcance es **su tenant**, no la plataforma |
| «¿quién administra mi organización?» | `tenant_admin` | Dash Edificio · umbrales · Flota Edge | «lectura + ack» en MONITOREO es la celda de `RBAC-TAKAB.md §2`; **el código le da además `classify_incident` y `request_dictamen`** (ver §5·bis), así que va a ver esos botones. Lo que NO tiene son las acciones **de campo** —`manual_activate`, `siren_silence`, `roster_read`—: no opera la crisis desde dentro del edificio |
| «¿y Protección Civil?» | `gov_operator` | MONITOREO (lectura) | ve **sólo** los tenants marcados `gov_shared`, y **no puede silenciar ni probar actuadores ajenos** — decisión cerrada |
| «¿el responsable de mi edificio?» | `building_admin` | Dash Edificio | **Total** en su edificio, nada fuera |
| «¿queda rastro de todo?» | `takab_superadmin` | Auditoría | es **lectura**: el registro es append-only y no se poda |
| «¿y el técnico que da soporte?» | `takab_superadmin` (ver el ⚠️ de abajo) | Flota Edge | `takab_support` **LEE** la flota, no la escribe. Aquí decía «**Total** en flota» copiando la celda de `RBAC-TAKAB.md §2`, y **el código la desmiente**: `manage_fleet` (alta/edición/retiro de sitios, gabinetes y sensores) es de `takab_superadmin` y `tenant_admin` y de nadie más — `matrix.py` da a `takab_support` **una sola acción, `read_audit`** |
| «¿de qué magnitud fue?» | `inspector` | EVALUACIÓN → el dictamen | **no la calculamos.** Ver el punto **4** del §8: la magnitud, si aparece en el papel, es de **catálogo externo** con su fuente y su hora |

> ⚠️ **Y no hay credencial de `takab_support` que meter.** `seed_console_users.sh:32` siembra
> **seis** roles —`takab_superadmin`, `tenant_admin`, `soc_operator`, `inspector`,
> `gov_operator`, `building_admin`— y ése **no está**. Delante del proyector eso es un minuto
> muerto con el pool pidiendo TOTP. Dos salidas: enseñar la Flota Edge como
> `takab_superadmin` (que sí se siembra y sí tiene `manage_fleet`) y **contar** que soporte la
> ve pero no la mueve; o sembrarlo **días antes**, con su MFA enrolado, porque el script acepta
> roles por argumento:
>
> ```bash
> make cloud-users ROLES="takab_support"
> ```
>
> Razón de la decisión, por si la preguntan: mover la ubicación de una estación **reencuadra la
> ventana de asociación del quórum** (depende de la distancia entre sitios), así que es un acto
> de dueño del tenant, no de soporte (`T-1.32`). Está anclada por partida doble:
> `api/tests/auth/test_matrix.py::test_manage_fleet_excludes_takab_support` (la matriz) y
> `api/tests/api/test_fleet_admin.py::test_takab_support_cannot_manage_fleet` (el 403 real
> del endpoint).

---

## 5·bis · La tabla que manda · **derivada del código, no de la prosa**

Sale de `api/src/takab_api/auth/matrix.py`, que es la **fuente única** de la que
`routers/dictamens` deriva sus `SIGN_ROLES`. Si alguna vez discrepa de una tabla en prosa,
**gana `matrix.py`**.

> ⚠️ **Rectificación (2026-09-22).** Aquí decía que esta tabla «no está escrita a mano» y que
> «hay un test de paridad que pone CI en rojo si divergen». **Las dos cosas eran falsas**, y se
> midieron: un barrido del repositorio entero por el nombre de este fichero
> (`grep -rn GUIA-DEMOSTRACION --include=*.py --include=*.ts --include=*.sh --include=*.yml`)
> devuelve **cero** resultados — ningún test, ningún generador y ningún job de CI leen esta
> guía. El test que sí existe (`api/tests/auth/test_matrix.py`) ancla `matrix.py` contra
> `RBAC-TAKAB.md §2`, **no contra esta hoja**. Y la divergencia que la frase juraba imposible
> ya había ocurrido once líneas más arriba, en la fila de `takab_support`.
>
> Lo cierto es esto: **copiada de `matrix.py` y verificada acción por acción el 2026-09-22** —
> las trece filas coinciden hoy—. Si el código cambia, **esta hoja hay que re-derivarla a
> mano**: es el «censo que enumera a mano acaba divergiendo» de `TRASPASO-SESION.md`, y saberlo
> es lo que obliga a revisarla antes de cada demostración.

| Acción | Quién la tiene |
|---|---|
| **`sign_dictamen`** — firmar el dictamen | **`inspector`, y nadie más** |
| `generate_report` — generar el PDF | `inspector`, `takab_superadmin` |
| `request_dictamen` — pedir el dictamen técnico | `soc_operator`, `takab_superadmin`, `tenant_admin` |
| `ack_incident` — acusar | `gov_operator`, `soc_operator`, `takab_superadmin`, `tenant_admin` |
| `classify_incident` — clasificar (el cierre) | `building_admin`, `soc_operator`, `takab_superadmin`, `tenant_admin` |
| `damage_report_submit` · `evidence_upload` | `brigadista`, `inspector`, `security_guard` |
| `panic_vote` — el voto del ocupante | **`occupant`, y nadie más** |
| `manual_activate` — sirena manual individual | `brigadista`, `building_admin`, `inspector`, `security_guard` |
| `siren_silence` — silenciar | `brigadista`, `building_admin`, `security_guard` |
| `checkin_submit` — «estoy a salvo» | `brigadista`, `building_admin`, `inspector`, `occupant`, `security_guard` |
| `roster_read` — pase de lista | `brigadista`, `building_admin`, `security_guard` |
| `dictamen_read` — leer el PDF en el móvil | `brigadista`, `building_admin`, `inspector`, `security_guard` |
| `panel_read` — el táctico del gabinete | `brigadista`, `building_admin`, `inspector`, `security_guard` |

**Tres cosas que esta tabla dice y la prosa no dejaba claras:**

1. **El `takab_superadmin` NO firma dictámenes** — lo tiene en `False`, explícitamente. Puede
   generar el PDF y puede pedirlo, pero la firma es del inspector. No es una omisión: firmar un
   dictamen estructural es un acto profesional, no un privilegio administrativo.
2. **El ocupante no «activa la sirena»: VOTA.** Su acción es `panic_vote` y **no tiene**
   `manual_activate`. Por eso hacen falta dos ocupantes: uno solo no acciona nada.
3. **El `occupant` no tiene `dictamen_read`.** Recibe el aviso de «reingreso permitido», no el
   documento — y eso es deliberado.

---

## 6 · Los flujos móviles · **cuáles están acreditados y cuál no**

Dicho tal cual, porque prometer uno que no está acreditado es exactamente lo que este
repositorio lleva una fase entera cazando.

| Flujo | Estado | Qué hace falta para enseñarlo |
|---|---|---|
| Toma de crisis | ✅ acreditado | nada — sale solo en el acto 3 |
| Check-in de vida («a salvo / necesito ayuda») | ✅ acreditado | tocarlo en el teléfono tras el acto 3 |
| Táctico: foto → daños | ✅ acreditado | es el acto 4a |
| **Dictamen → liberación** | ❌ **nunca acreditado** | **la firma del inspector**: es el acto 4b. Enseñarlo **lo acredita** |
| Pánico quórum-de-2 | ⚠️ sólo el 1.er voto | el 2.º voto exige **un segundo teléfono** con otro usuario |
| Offline-first | ✅ acreditado | modo avión. ⚠️ **el modo avión de Android no apaga el WiFi**: apágalo aparte |

---

## 7 · Cuando algo se cae · **no improvises**

Los cuatro casos —sin internet, sin aviso al teléfono, sin IA, sin mapa— están escritos con lo
que **sigue** funcionando y con la frase con la que se cuenta cada uno, en
[`RUNBOOK-demo-cliente.md § Plan B`](RUNBOOK-demo-cliente.md).

**La regla que los gobierna a todos:** dilo tú antes de que lo pregunten. Una demostración en
la que se cae algo y quien la conduce lo nombra es la demostración de un sistema honesto; la
misma caída descubierta por el cliente es otra cosa.

---

## 8 · Antes de abrir la boca · **la lista de lo que no debe decirse**

Está en [`RUNBOOK-demo-cliente.md § Lo que NO debe decirse`](RUNBOOK-demo-cliente.md), es
**viva** y se lee antes de cada demostración. Las **cuatro** que más fácil se cuelan en este
recorrido:

1. **«Así se sacudió su colonia»**, señalando los anillos del mapa de sacudida. **Falso:** los
   anillos son **modelados**, no medidos. Los puntos son lo medido, y donde no hay sensores el
   mapa dice `SIN COBERTURA` en vez de rellenar.
2. **«Las fotos se quedan aquí.»** Falso desde que la redacción asistida está encendida.
3. **«Si el gabinete se apaga, la sirena suena igual por hardware.»** Esa ruta eléctrica está
   diseñada y decidida, **no construida** (`G-04` sigue abierto).
4. **«El sistema calculó una magnitud de X.»** ⚠️ **Entrada nueva, y lo es a propósito:** hasta
   `T-7.25` (2026-09-21) el dictamen no podía imprimir una magnitud, y esta guía no la nombraba
   ni una sola vez. Hoy la consulta al catálogo externo **está encendida y desplegada**
   (`TAKAB_API_CATALOG_USGS_ENABLED=true`), y cuando casa, el papel firmado imprime una línea
   de la forma `<fuente> <identificador> · M 4.2 (confirmado) · Δt … s · CONTRASTE … km`
   (`dictamen/builder.py`).
   **Eso no es una cifra nuestra.** TAKAB **no calcula magnitud**, y no es un pendiente: es
   invariante (blueprint §14). Tampoco reporta **intensidad macrosísmica (MMI)**, a propósito.
   ✅ Lo que se dice: *«lo que nosotros medimos es la intensidad EN ESTE EDIFICIO — PGA y PGV
   pico, con su instante y su umbral. La magnitud se la preguntamos después a la fuente
   oficial y la citamos con su procedencia: qué catálogo, qué identificador y a qué hora se
   consultó. No la calculamos, y el papel nunca la enseña sin esa procedencia.»*
   ⚠️ **Y en ESTA demostración no va a haber cifra**, porque no hay sismo: el golpe y el WR-1
   no aparecen en ningún catálogo del mundo. Lo que imprimirá el dictamen es el **estado de la
   consulta** —que preguntó y ningún sismo publicado satisface el criterio de identidad, o que
   la pregunta sigue en vuelo—, que son dos frases distintas a propósito. **Enséñalo como una
   virtud**, no lo escondas: el papel declara lo que sabe y lo que no, debajo de una firma que
   después no se retira.

---

## 9 · Lista de verificación · **para imprimir**

**Días antes**
- [ ] `aws sso logout && aws sso login --profile takab-dev` — **primero**: los dos `make` de
      abajo leen los pools del estado de terraform y con la caché rancia mueren con
      `InvalidGrantException` aunque `aws sts` funcione. **El `logout` no es adorno.**
- [ ] `make cloud-users` y `make cloud-mobile-users` — y **MFA enrolado en cada rol**
- [ ] si vas a enseñar el rol de soporte: `make cloud-users ROLES="takab_support"` (no entra en
      los seis por defecto) — y su MFA
- [ ] **catálogo del panel fresco** — las dos cifras viven **dentro de `.provenance`**, no en
      la raíz de la respuesta:
      `curl -s http://raspberry-cerebro.local:8080/api/catalog | jq '.provenance | .captured_age_s < .stale_after_s'`
      → tiene que decir `true`. El 2026-09-22 decía `false` (4 610 656 s contra 172 800 s).
      Refrescarlo es un publish firmado (`POST /gateways/{id}/catalog`) y **pide JWT de
      consola**: no se improvisa la mañana. Si no se refresca, lleva preparada la frase del
      ⚠️ de §1
- [ ] APK instalado en el Pixel y **una entrada con cada rol móvil** (el ocupante, hasta ver su edificio y no el onboarding)
- [ ] leer la lista «lo que NO debe decirse»

**El mismo día, antes de que entre nadie**
- [ ] `guion.sh --preflight` → **0 ✗** (el número de ✓ da igual; el que manda es el cero)
- [ ] consola **abierta** y con el mapa dibujado
- [ ] panel del gabinete abierto en la segunda pestaña
- [ ] Pixel **cargado, desbloqueado una vez y luego bloqueado** sobre la mesa
- [ ] avisar en el edificio de que **va a sonar una sirena de verdad**
- [ ] `guion.sh --full` listo en una terminal

**Al terminar**
- [ ] soltar el enclavado en el panel: botón **CERRAR ALERTA** (2 clics + **PIN**). Ten el PIN
      a mano ANTES — un `POST /api/reset` sin `X-Takab-Pin` da **401**, y 5 fallos bloquean 60 s
- [ ] clasificar el incidente como **`reproduccion`**
- [ ] pegar la tabla de tiempos en el § Registro del runbook
- [ ] si firmaste un dictamen: **apuntar la hora — acabas de acreditar el flujo `03`**
