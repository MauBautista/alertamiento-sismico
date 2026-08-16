# Pendientes de Mauricio — lo que el software no puede cerrar

> **Qué es esto.** El censo de todo lo que está bloqueado en una persona, no en código. Sale de
> `TASKS.md` y **no lo sustituye**: cada punto de aquí enlaza a su ficha, que es donde vive el
> detalle. Esto es la lista de trabajo; aquellas son la especificación.
>
> **Lo decidido no vive aquí: vive en [`DECISIONES-MAURICIO.md`](DECISIONES-MAURICIO.md).** Esta
> lista solo contiene lo que **falta**. Cuando algo se decide, se borra de aquí y se escribe allí
> **con su razón**, porque una decisión sin razón no se puede revocar con conocimiento — solo
> olvidar.
>
> **Última actualización:** 2026-08-16 · **21 puntos** (§2: 9 · §3: 4 · §4: 5 · §5: 3)
>
> **Lo que cambió el 2026-08-15: la sección §1 desapareció entera.** Las seis decisiones que solo
> pedían criterio —§1.1, §1.3, §1.4, §1.5, §1.6 y §1.7— quedaron cerradas por Mauricio en una
> sesión, y se sumaron a las tres delegadas del 2026-08-12. **Ya no queda ni una decisión de
> escritorio pendiente.** Las nueve, con su razón, están en
> [`DECISIONES-MAURICIO.md`](DECISIONES-MAURICIO.md) como `D-01`…`D-09`.
>
> **Consecuencia, y es el titular de esta pasada:** **todo lo que queda en esta lista cuesta
> dinero, tiempo de un tercero, o tocar un edificio.** Nada de lo que sigue se puede resolver
> pensando.

---

## Por qué esta lista importa más que la de software

De los seis elementos de la ruta crítica hacia el primer cliente, **el software controla uno y
medio**. Los otros cuatro y medio están en esta lista. Se puede terminar todo el código y seguir
sin poder vender.

Y hay dos que **tienen plazo externo** —dependen de que un tercero conteste—, así que **cuanto
antes se arranquen, antes dejan de ser el cuello de botella**: el alta de WhatsApp Business
(§4.2) y el marco normativo citable (§4.1).

---

## 1 · DECISIONES — ✅ **sección cerrada** (2026-08-15)

**No queda ninguna.** Las nueve decisiones que solo pedían criterio están tomadas, cada una con su
razón escrita y su condición de revocación, en
[**`DECISIONES-MAURICIO.md`**](DECISIONES-MAURICIO.md):

| ID | Decisión | Fecha |
|---|---|---|
| `D-01` | Entre `empty` y `stale`, **gana `stale`** | 2026-08-12 |
| `D-02` | `lock_timeout` del request: **se pone, ~10 s** | 2026-08-12 |
| `D-03` | La consola **arranca con la base caída**, en degradado y declarándolo | 2026-08-12 |
| `D-04` | Dueño de los pines GPIO: **ventana avisada (A)**, nunca hardware | 2026-08-15 |
| `D-05` | Push de pánico: **solo a tácticos**, y sin acuse **escala al SOC** | 2026-08-15 |
| `D-06` | Catálogo SSN: **se automatiza** la ingesta | 2026-08-15 |
| `D-07` | Teléfono del consentimiento: **cripto-borrado** | 2026-08-15 |
| `D-08` | Bloque IV (mini-ShakeMap y CCTV): **se planifica ya** | 2026-08-15 |
| `D-09` | `enforce_admins`: **queda en `false`**, con gatillo escrito | 2026-08-15 |

> **Cuatro de ellas generan trabajo de software que hay que fichar en `TASKS.md`** —`D-05` (cablear
> `notify/` al voto de pánico, acuse del táctico, escalado al SOC), `D-06` (job de ingesta + fecha
> declarada + alarma por ausencia), `D-07` (cripto-borrado del `subject_ref`) y `D-08` (diseño de
> `T-3.09`/`T-3.10`)—. **Ese trabajo NO es tuyo: es de la máquina.** No vuelve a esta lista.
>
> **`D-04` sí te deja una acción física**, y es la única que salió de aquella sección: hacer el
> traspaso del dueño de los pines en el gabinete de desarrollo. Está en **§3.5**.

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

### 2.1 · Los `terraform apply` que faltan — **cinco, y los cinco invisibles hasta que fallan**

> **Lo que ya NO está aquí porque se hizo:** las migraciones. Desplegado y verificado en la nube el
> 2026-08-11, no inferido del código de salida — siete contenedores en `48d530f`, `/api/health`
> respondiendo `{"status":"ok","build":"48d530f"}` y `alembic_version` en
> `0038_privacy_erasure_on_behalf`, la cabeza del repo.

Lo que sigue pendiente son **applies de IAM y de alarmas**. Ninguno da error al faltar: **dan una
conducta silenciosamente peor**, que es la familia de trampa más cara de este proyecto.

1. Los **tres statements IAM de las ventanas de mantenimiento** ([`T-2.71`](TASKS.md)) — el
   despliegue de imágenes **no los toca**.
2. **`sqs:ChangeMessageVisibility`** en el rol de los workers ([`T-2.132`](TASKS.md)). Ya está
   escrito en el Terraform; **sin el `apply` el arreglo es decorativo**. El worker no se cae —la
   llamada es best-effort— pero el mensaje se hace visible a mitad del reintento y otro worker
   **gasta justo la recepción que se estaba ahorrando**, que es el defecto entero de esa ficha.
3. **Dos alarmas de la Fase 2.6** ([`T-2.72.b/c`](TASKS.md)). El `apply` las crea y publica la
   versión nueva del documento SSM. **Trampa ya fichada:** cambiar el documento **no relanza la
   asociación** —el cambio aterriza hasta 24 h después—; hay que forzarla con
   `aws ssm start-associations-once`. **Si se dan por buenas las alarmas sin relanzarla**, las tres
   quedan sin publicador y `backup-base-ausente` manda un correo **que parece un fallo de respaldo
   y es un fallo de despliegue**.
   > **Y esto conviene saberlo antes de que llegue el correo:** `backup-base-ausente`
   > **NACE EN ALARM a propósito** — el día del `apply` todavía no hay backup base. **El correo de
   > OK, cuando §2.8 tome el primero, ES el acuse** de que la cadena consiguió ancla. Si ese OK
   > **no** llega, ahí sí hay un problema.
4. **Tres secretos y abrir el 443 para los webhooks de entrega** ([`T-2.77.b`](TASKS.md)). El
   endpoint público ya existe y **sin ellos responde 503 y lo grita** —no hay degradación
   silenciosa—, pero hasta entonces los tres canales siguen diciendo «el proveedor lo aceptó» y
   **nunca «llegó a una persona»**. Hacen falta:
   - `TAKAB_API_NOTIFY_SMS_STATUS_CALLBACK_URL`, `TAKAB_API_NOTIFY_WHATSAPP_APP_SECRET` y
     `TAKAB_API_NOTIFY_WHATSAPP_VERIFY_TOKEN` en el despliegue (los dos últimos, desde Secrets
     Manager).
   - **Abrir el 443 a los rangos de Twilio y Meta** en el security group: hoy está restringido por
     IP, así que **los callbacks no llegarían**.
5. **El suscriptor HTTPS de la cadena on-call** ([`T-2.78.a`](TASKS.md)), y **su ORDEN es estricto
   porque la suscripción SE CONFIRMA DURANTE EL `apply`**:
   1. Desplegar la API **con `TAKAB_API_OPS_ALERT_TOPIC_ARN`**.
   2. `curl -X POST …/api/ops/alerts/sns -d '{}'` → debe dar **404**. **Si da 503, falta el ARN:
      PARA AHÍ** — seguir hace que el `apply` muera a medias.
   3. Solo entonces `ops_alert_https_subscriber_enabled = true` + `apply`.
   4. Acuñar tu credencial de guardia: `python -m takab_api.ops.oncall issue`.
   > **Guárdala en el gestor de contraseñas y pon la página de acuse como marcador en el
   > teléfono.** La base solo guarda su **hash**, así que si la pierdes no se recupera: se acuña
   > otra y se revoca la vieja. **Y no viaja en el correo a propósito** — los escáneres de los
   > buzones pulsan los enlaces, así que un acuse por enlace lo daría una máquina antes de que tú
   > leyeras nada.

> **La trampa del SSO se cobró el despliegue anterior, y conviene saber cómo se reconoce.** Falló
> con `InvalidGrantException` **mientras el `docker login` a ECR funcionaba**. Ésa es la firma: no
> es que falten credenciales, es la caché del SSO caducada, y `aws sts` puede seguir contestando
> mientras terraform ya no. `aws sso login` a secas **no lo arregla** — hace falta `aws sso logout`
> primero.

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

> **✅ Hoja de ruta escrita:** [`runbooks/RUNBOOK-sesion-de-vida.md`](runbooks/RUNBOOK-sesion-de-vida.md).
>
> ### ⚠️ Y trae un veredicto que conviene leer ANTES de agendar: **no es una sesión, son tres cosas**
>
> | Gate | Estado real (medido 2026-08-16) | Falta |
> |---|---|---|
> | **`G-01`** restart en frío | **se puede hacer HOY** | nada — 20 min |
> | **`G-04`** WR-1 → sirena <100 ms | **a medias** | una sirena real; y CIRES |
> | **`G-02`** sirena con el Pi apagado | **NO se puede probar** | **el hardware no existe** |
>
> **`G-02` no es una prueba pendiente: es una obra pendiente.** El relé `K_wd`, el monoestable, el
> relé de potencia y el riel con UPS **no están construidos**, y el **latido de keep-alive no está
> escrito** — no hay pin de latido en `GpioPins`. Y es, según la propia ficha, «la mitigación más
> importante del sistema».
>
> **Lo que la ficha dice y ya NO es cierto:** «los relés siguen en MOCK». El gabinete corre
> `LGPIOFactory (lgpio)` real con `DEV_MODE=false`, y la mitad eléctrica de `G-04` **ya pasa** con
> dos órdenes de magnitud de margen (6.65 ms / 4.16 ms contra un presupuesto de 100 ms). Lo que le
> falta a ese gate no es velocidad: es **que haya una sirena al final del cable**.
>
> **Variante de la ruta de hardware: DECIDIDA** — (B), fallback con watchdog
> ([`D-10`](DECISIONES-MAURICIO.md)). **La lista de materiales ya se puede comprar.**

### 3.2 · [`T-2.93`](TASKS.md) · Sesión instrumental — `G-03`, `G-05`, `G-07`, `G-10`
Incluye el gate #3 del Shake: hoy sus 5 tests se saltan cuando el sensor no está alcanzable, y la
suite **lo declara en voz alta** en vez de callarlo.

### 3.3 · [`T-2.94`](TASKS.md) · Sesión de sitio — `G-06`, `G-08`
> **Única dependencia declarada del Bloque III sobre el II:** necesita `T-2.78`, porque un
> simulacro con **cascada de notificación real** no se acredita con canales simulados.

### 3.4 · [`T-2.95`](TASKS.md) · `GATE-HW` móvil + voceo
Entorno preparado y verde; **falta un dispositivo físico**.

> **✅ Hoja de ruta escrita:**
> [`runbooks/RUNBOOK-gate-hw-movil-y-voceo.md`](runbooks/RUNBOOK-gate-hw-movil-y-voceo.md).
>
> ### ⚠️ CORRECCIÓN — lo que esta sección decía hasta el 2026-08-16 era falso
>
> Decía: «re-correr el flujo **`GATE-HW 02`**, que se acreditó contra la conducta vieja». **La
> premisa no se sostiene.** `02-tactico-foto-danos.yaml` es **cámara forense → daños → Triage**: no
> pulsa el control táctico, no silencia nada y no lee la hoja de acuse. Re-correrlo no mostraría
> nada nuevo.
>
> Y no es solo el 02: **ninguno de los seis flujos de Maestro toca el control táctico.** O sea que
> la conducta de `T-2.107`→`T-2.116`→`T-2.120` **no tiene cobertura E2E en dispositivo real** —
> está probada en CI (`ackTracking.test.tsx` conduce la ruta real y asserta el texto), pero no en
> un teléfono. El runbook trae el escenario manual (Bloque B) que sí la acredita.
>
> **Y una trampa que ese escenario tiene dentro:** el **modo prueba del WR-1 NO sirve** para esto.
> No publica a la nube, así que la app nunca vería una alerta vigente. **Hace falta una alerta
> real** — con incidente, notificaciones y sirena audible. Va con aviso previo.
>
> **Lo que de verdad falta acreditar:** el flujo **`03` (dictamen → liberación)**, que es el único
> de los seis **nunca acreditado** y necesita la firma de un inspector en la consola web.
>
> ### 🎁 Y algo que puedes encender HOY, sin comprar ni grabar nada
> `TAKAB_EDGE_AUDIO_SIREN_ENABLED=true` da **sirena audible por el jack de 3.5 mm** con el WAV ya
> empaquetado. No confundir con `TAKAB_EDGE_AUDIO_ENABLED` (voceo hablado), que **exige las dos
> grabaciones y rompe el arranque si faltan**. Y ahora es barato: desde
> [`D-04`](DECISIONES-MAURICIO.md), reiniciar `takab-edge` no mueve un relé.

### 3.5 · ~~El traspaso del dueño de los pines~~ — ✅ **HECHO en dev** (2026-08-16)

**Ejecutado y medido en `gw-dev-0001`.** Los pines los sostiene **`takab-gpio`**, y `takab-edge`
dejó de tocarlos:

| | |
|---|---|
| `takab-gpio` | `enabled` + `active` desde **02:41:01**, `NRestarts=1` |
| `takab-edge` | `enabled` + `active` desde **02:44:51**, `NRestarts=0` |
| Dueño del cerrojo | **`takab-gpio`**, confirmado por el paso 7 del despliegue (pid + unidad) |
| Coste eléctrico | **CERO** — `installed = ["siren","strobe"]`; no hay gas ni retenedores que ciclar |

> **Ese `NRestarts=1` no es un defecto: es la conducta esperada, y conviene reconocerla.**
> `takab-gpio` arrancó con `takab-edge` todavía dueño, **chocó una vez contra el cerrojo**, y al
> reiniciarse `takab-edge` —ya leyendo `owner=gpio`— soltó los pines y el dueño nuevo los tomó.
> Se cura solo (`Restart=always`, `RestartSec=1`).
>
> **Y por eso este traspaso NO se hace a mano**, aunque esta vez saliera bien: en ese hueco parece
> un fallo, y el movimiento natural del operador —`systemctl stop takab-gpio` para «liberar» los
> pines— **sí es actuación física sobre gas y puertas**. `deploy/edge/deploy.sh` hace los tres
> pasos en orden y **verifica el cerrojo**; `systemctl is-active takab-edge` **no vale como
> comprobación**: sale `active` con los pines sin dueño.

**Desbloquea [`T-2.70`](TASKS.md)** (canary + rollback). Desde ahora, **reiniciar `takab-edge` no
mueve un solo pin** — que era el objetivo entero de `T-2.70.a`.

**Lo que queda vivo de aquí, y es la mitad que importa dentro de un año:** en una instalación
**real**, esto se hace en la **puesta en marcha**, antes de que el edificio dependa del sistema.
Nunca en un gabinete ya en servicio salvo ventana avisada y aceptada por el cliente. Es la política
[`D-04`](DECISIONES-MAURICIO.md), y sobrevive a esta ficha.

---

## 4 · LEGAL Y COMERCIAL — plazo externo, arrancar YA

### 4.1 · [`T-2.96`](TASKS.md) · `GATE-LEGAL` · marco normativo citable
> **La cita vieja «NOM-003-SCT» era una norma de TRANSPORTE y no aplicaba.** Hoy el sistema
> declara el marco que **el cliente** afirma, con su deslinde: TAKAB no lo respalda. Eso es
> honesto pero **no es un marco propio**, y un cliente institucional lo va a pedir.
>
> ### 📋 QUÉ TIENES QUE HACER — **el paso 1 ya está hecho**
>
> **✅ El documento para el abogado está escrito:**
> [`CONSULTA-LEGAL-TAKAB.md`](CONSULTA-LEGAL-TAKAB.md). Recoge, separado y sin mezclar, **lo que el
> sistema afirma hoy** (§2), **lo que niega afirmar** con el deslinde literal (§3) y **las cinco
> preguntas** (§4). Incluye lo que **NO** está acreditado —el gate de latencia física
> contacto→relé→sirena— porque un documento legal que mezcle lo medido con lo aspirado convierte
> una consulta en una declaración.
>
> **Lo que queda es tuyo y no depende de nadie más:**
> 1. **Llévaselo a un abogado con experiencia en protección civil o en responsabilidad de producto
>    en México.** Pídele las dos cosas del §4.1 y §4.2 del documento: qué marco es citable, y qué
>    frases habría que cambiar.
> 2. **En la misma consulta va el §4.4**, que es la postura [`D-07`](DECISIONES-MAURICIO.md)
>    —cripto-borrado del teléfono del consentimiento— con las dos preguntas que deja abiertas a
>    propósito. Es de la misma persona y ahorra una segunda vuelta.
>
> **Por qué corre prisa aunque no bloquee código:** es **plazo externo**. El día que un cliente
> institucional lo pida, el reloj empieza entonces — y ya llevas semanas de margen gastadas.

### 4.2 · [`T-2.77.a`](TASKS.md) · Alta del WhatsApp Business Account + aprobación de plantilla
> **Plazo externo: lo aprueba Meta.** El código está completo y probado (53 tests); la plantilla
> del repo está `PENDING` a propósito y el canal **cae solo** si Meta la pausa. Arrancarlo ya es
> lo que evita que sea el cuello de botella.
>
> ### 📋 QUÉ TIENES QUE HACER, paso a paso
>
> **✅ Runbook escrito:**
> [`runbooks/RUNBOOK-alta-whatsapp-business.md`](runbooks/RUNBOOK-alta-whatsapp-business.md).
> Trae el **cuerpo literal** que hay que mandarle a Meta, el **digest** de la plantilla, por qué
> `UTILITY` no es una preferencia de estilo, y el checklist de estado.
>
> **Empieza por el paso 2 —verificar el negocio—, no por el 1.** Es el lento, y es independiente
> de la plantilla. Y ojo: **ese trámite necesita dominio, igual que §2.9** — si compras dominio
> para Meta, cómpralo pensando también en SES. Es el mismo trámite sirviendo a dos cosas.
>
> **Y una cosa que conviene saber antes de empezar:** si Meta **pausa** la plantilla por calidad,
> **el canal cae solo y queda en cuarentena persistida** (`T-2.77.c`) — no hay que hacer nada, y
> no se martillea la plantilla pausada. Eso ya está resuelto.

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
   las únicas que no se pueden acelerar después. Encabezan la lista porque **ya no hay nada más
   barato por delante**: las decisiones de escritorio se acabaron el 2026-08-15.
2. **La sesión de vida (§3.1).** Es la que dice si el producto es real, y no espera a nada.
3. **`GATE-HW 02` (§3.4).** Necesita un teléfono en la mano y nada más; se acreditó contra la
   conducta vieja y hoy el gabinete ya corre la nueva.

> **Lo que estaba en el puesto 2 hasta el 2026-08-16 —el traspaso de los pines— ya está hecho**
> (§3.5), así que la lista subió un escalón. Es la segunda vez seguida que esta sección se acorta
> por arriba: cada vez que pasa, lo que queda es más caro.
