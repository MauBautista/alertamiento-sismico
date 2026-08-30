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
> **Última actualización:** 2026-08-17 · **21 puntos** (§2: 9 · §3: 4 · §4: 5 · §5: 3)
>
> ## ⚠️ Lo que cambió el 2026-08-17, y corrige lo que esta cabecera decía
>
> El 2026-08-15 esta lista declaró que **«ya no queda ni una decisión de escritorio pendiente»**.
> **Era falso, y el modo en que era falso es lo interesante:** quedaban **diez**, pero ninguna
> estaba en la §1. Vivían **enterradas dentro de puntos de acción** —seis en una tabla en blanco
> del runbook de SES, una en una fila vacía del manual de operación, una en una nota al pie de
> `D-08`, y dos en el modo de agendar `§2` y `§3.1`—.
>
> **Una decisión escondida dentro de una tarea no se lee como decisión: se lee como trabajo
> bloqueado sin culpable.** Por eso el dominio —que bloqueaba **los dos únicos puntos de plazo
> externo del proyecto**— llevaba semanas parado sin que nadie lo señalara: parecía trámite.
>
> Las diez quedaron cerradas el 2026-08-17 como
> [`D-12`…`D-21`](DECISIONES-MAURICIO.md). **La §1 sigue vacía, y ahora es verdad** — pero la
> lección es de método: `§1` enumeraba a mano lo que contaba como decisión, y **un censo que
> enumera a mano acaba divergiendo**.
>
> **Lo que sigue siendo cierto, y ahora más:** todo lo que queda en esta lista cuesta **dinero,
> tiempo de un tercero, o tocar un edificio**. Lo que cambió es que ya se sabe **qué** se compra y
> **en qué orden** — ver [`D-16`](DECISIONES-MAURICIO.md#d-16) y
> [`D-17`](DECISIONES-MAURICIO.md#d-17).

---

## Por qué esta lista importa más que la de software

De los seis elementos de la ruta crítica hacia el primer cliente, **el software controla uno y
medio**. Los otros cuatro y medio están en esta lista. Se puede terminar todo el código y seguir
sin poder vender.

Y hay dos que **tienen plazo externo** —dependen de que un tercero conteste—, así que **cuanto
antes se arranquen, antes dejan de ser el cuello de botella**: el alta de WhatsApp Business
(§4.2) y el marco normativo citable (§4.1).

---

## 1 · DECISIONES — ✅ **sección cerrada** (re-verificada el 2026-08-17)

**No queda ninguna** — pero esta frase ya fue falsa una vez, así que ahora viene con la lista
completa. Las **veinticinco** decisiones tomadas, cada una con su razón escrita y su condición de
revocación, están en [**`DECISIONES-MAURICIO.md`**](DECISIONES-MAURICIO.md):

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
| `D-10` | Ruta de hardware de la sirena: **variante B**, fallback con watchdog | 2026-08-16 |
| `D-11` | El quórum de pánico **abre incidente** `trigger='manual'` | 2026-08-16 |
| **`D-12`** | **Dominio raíz `takabailert.com`**, DNS en Route 53 *(enmendada 21-ago)* | **2026-08-17** |
| **`D-13`** | Teléfono de soporte: **número Twilio mexicano** | **2026-08-17** |
| **`D-14`** | CCTV: **híbrido** — aforo en sitio + clips de evento confirmado | **2026-08-17** |
| **`D-15`** | Sirena por jack: **encendida** en el gabinete de desarrollo | **2026-08-17** |
| **`D-16`** | Compras: **sí** dominio y Twilio · **no todavía** BOM de `G-02` ni Apple | **2026-08-17** |
| **`D-17`** | La ventana AWS se parte en **dos**: applies (A) y restore (B) | **2026-08-17** |
| **`D-18`** | `console_scope_enforced`: **se enciende ya**, tests en el mismo commit | **2026-08-17** |
| **`D-19`** | Tono de la app: **propio**, no el oficial de CIRES | **2026-08-17** |
| **`D-20`** | Consulta legal: **espera a que un cliente la pida** | **2026-08-17** |
| **`D-21`** | Sesión de vida: **se parte** — `G-01` esta semana, solo | **2026-08-17** |
| **`D-22`** | La consola **se abre al público**; Cognito con MFA, única capa | **2026-08-22** |
| **`D-23`** | ARCO por teléfono: **lo acredita el cliente institucional** | **2026-08-22** |
| **`D-24`** | CCTV: el **conteo pasa a la nube**; el clip se ve y se descarga *(enmienda `D-14`)* | **2026-08-29** |
| **`D-25`** | Bloque IV **arranca ya en software**; encenderlo espera a `G-04` | **2026-08-29** |

> **Las que generan trabajo de software se fichan en `TASKS.md` y NO vuelven a esta lista** —`D-05`
> (cablear `notify/` al voto de pánico, acuse del táctico, escalado al SOC), `D-06` (job de ingesta
> + fecha declarada + alarma por ausencia), `D-07` (**hecho**: `T-2.150`, mergeado el 2026-08-17),
> `D-08` (diseño de `T-3.09`/`T-3.10`), `D-14` (aforo local + clips, con caída a *solo aforo* **por
> configuración de sitio**), `D-18` (invertir dos tests HTTP), `D-19` (grabar el tono propio) y `D-24`/`D-25`
> (el módulo CCTV entero: `T-3.10`…`T-3.12`).
> **Ese trabajo es de la máquina.**
>
> ### ⚠️ Las que sí te dejan una acción tuya — y son las únicas que importan de esta sección
>
> | Decisión | Tu acción | Dónde vive |
> |---|---|---|
> | `D-12` + `D-16` | **Delegar los NS** de `takabailert.com` en Namecheap + **comprar el buzón** (~$15/año) · *(dominio comprado y zona `Z01047862QJFIRSOR5IC5` creada)* | §2.9 y §4.2 |
> | `D-13` + `D-16` | **Abrir cuenta Twilio** y comprar el número mexicano | §4.3 |
> | `D-15` | **Encender la sirena por jack** (un comando) | §3.4 |
> | `D-21` | **Acreditar `G-01`** esta semana, 20 min | §3.1 |
> | `D-25` | **Acreditar `G-04`** y medir `B.2` — es lo que destraba **encender** el CCTV en el gabinete; hasta entonces el software se entrega apagado | §3.1 |
> | `D-24` | **Ventana AWS** para el Lambda de conteo (ECR + IAM) | §2 |
> | ~~`D-24`~~ | ~~**Un clic en GitHub**: añadir el check **`licenses`** a la protección de `main`~~ · ✅ **HECHO el 2026-08-30**, y con él se cazó el mismo defecto en **`analyzer`**: los dos jobs nuevos del bloque de CCTV estaban verdes y **ninguno bloqueaba**. La rama exige checks por nombre literal (`D-09`) y ahora son **nueve**. Queda **uno** sin exigir a propósito: `landing`, que se añade cuando aterrice la PR #93 | §2 |
>
> `D-04` dejaba una cuarta —el traspaso del dueño de los pines— y **ya está hecha** (§3.5).

---

## 2 · VENTANA AWS — **DOS** sesiones con credenciales, en este orden

> ### 📅 El reparto, decidido en [`D-17`](DECISIONES-MAURICIO.md#d-17) — ya no es una sola sesión
>
> | | Qué entra | Duración | Por qué va aparte |
> |---|---|---|---|
> | **Ventana A** | §2.1 (los 5 applies) · §2.2 · §2.3 · §2.4 · §2.5 · §2.6 · §2.7 | ~1 h | Sin build. Todo son applies y verificaciones |
> | **Ventana B** | §2.8 (`T-2.74`, restore con RTO medido) | ~3 h | Empieza con `make cloud-images`, que tarda **~40 min** |
>
> **La razón de partirlas está medida, no supuesta:** el token SSO **expira a mitad del build**, y
> la firma del fallo engaña — terraform muere con `InvalidGrantException` **mientras el `docker
> login` a ECR sigue funcionando**. Meter ese build al final de una sesión que ya lleva una hora
> **garantiza** que el token no llegue vivo. Partirlo permite `aws sso logout` + `login` justo
> antes de la B, que es la única mitigación que funciona.
>
> **§2.9 (SES) no está en ninguna de las dos:** hasta que el dominio de
> [`D-12`](DECISIONES-MAURICIO.md#d-12) exista, no hay nada que aplicar.

> **Trampas ya pagadas, léelas antes de empezar:**
> - **SSO rancio:** `aws sso login` a secas **no basta**; hace falta `aws sso logout` primero, o
>   terraform muere con `InvalidGrantException` aunque `aws sts` funcione.
> - **`terraform apply` sin `-var serve_enabled=true` destruía la consola.** Hoy el
>   `auto.tfvars` lo trae, pero conviene mirarlo.
> - **Toda regla IoT nueva exige su línea en la política de flota**, o AWS desconecta al gabinete
>   en cada publish.
> - La IP doméstica rota a diario: si algo da **timeout** (no 403), es el firewall.

### 2.1 · Los `terraform apply` que faltan — **quedan TRES** (2 y 3 se hicieron el 2026-08-21)

> **Lo que ya NO está aquí porque se hizo:** las migraciones, **redesplegadas el 2026-08-21**.
> Verificado en la nube, no inferido del código de salida: siete contenedores en `5399a57`,
> `/api/health` respondiendo `{"status":"ok","build":"5399a57"}` y `alembic_version` en
> **`0046_privacy_subject_sealing`**, la cabeza del repo.
>
> ### ⚠️ Y la razón por la que hubo que redesplegar merece quedar escrita
> El despliegue del 2026-08-11 dejó la nube en `0038`, que **era** la cabeza entonces. Diez días
> después el repo iba por `0046` y **nada lo dijo**: ni un test, ni una alarma, ni el health. Se
> descubrió por un síntoma lateral —una alarma de retención de PII que no podía apagarse porque
> `0043` no había creado su tabla— tras media hora persiguiendo el script equivocado. **Está
> fichado como [`T-2.153`](TASKS.md), y no lo cierra este redespliegue:** lo que hay que arreglar
> no es la deriva, es que la deriva sea **invisible**.

Lo que sigue pendiente son **applies de IAM y de alarmas**. Ninguno da error al faltar: **dan una
conducta silenciosamente peor**, que es la familia de trampa más cara de este proyecto.

1. Los **tres statements IAM de las ventanas de mantenimiento** ([`T-2.71`](TASKS.md)) — el
   despliegue de imágenes **no los toca**.
2. ~~**`sqs:ChangeMessageVisibility`** en el rol de los workers ([`T-2.132`](TASKS.md))~~ —
   ✅ **APLICADO el 2026-08-21**, verificado en el rol `takab-dev-db`. Entró de propina con el
   apply del dominio de SES.
3. ~~**Dos alarmas de la Fase 2.6** ([`T-2.72.b/c`](TASKS.md))~~ — ✅ **APLICADAS el
   2026-08-21.** Cuatro alarmas y tres documentos SSM creados; las tres asociaciones corrieron
   solas al crearse y se relanzó a mano la del PITR (documento actualizado). **Las cuatro en `OK`**
   tras el redespliegue.
   > ### ⚠️ CORRECCIÓN — lo que esta viñeta decía sobre `backup-base-ausente` era falso
   >
   > Decía que **«nace en ALARM a propósito, porque el día del `apply` todavía no hay backup
   > base»**, y que el correo de OK sería el acuse. **Nació en `OK`**, porque la premisa no se
   > sostenía: **ya había backup base** y su métrica ya fluía. Nunca hubo tal acuse que esperar.
   >
   > **Y quien sí dio guerra fue su hermana.** `backup-base-atrasado` entró en `ALARM` con una
   > edad de 7,006 días y salió sola veinte minutos después, al aterrizar el backup del día. **No
   > era la cadena rota: era el diente de sierra**, porque el umbral iguala exactamente la
   > cadencia. Se repetirá **cada 7 días**. Fichado como [`T-2.154`](TASKS.md).
   >
   > **La lección, que es la que sobrevive a las dos:** esta lista predijo por escrito el estado
   > de nacimiento de dos alarmas y **acertó en ninguna**. Un estado de alarma **se mide cuando
   > existe**; escribirlo por adelantado es adivinar, y luego se lee como si fuera un hecho.
   >
   > **Lo que sigue siendo verdad y no hay que perder:** cambiar un documento SSM **no relanza su
   > asociación** —el cambio puede tardar 24 h—; `aws ssm start-associations-once` la fuerza.
4. **Tres secretos y abrir el 443 para los webhooks de entrega** ([`T-2.77.b`](TASKS.md)). El
   endpoint público ya existe y **sin ellos responde 503 y lo grita** —no hay degradación
   silenciosa—, pero hasta entonces los tres canales siguen diciendo «el proveedor lo aceptó» y
   **nunca «llegó a una persona»**. Hacen falta:
   - `TAKAB_API_NOTIFY_SMS_STATUS_CALLBACK_URL`, `TAKAB_API_NOTIFY_WHATSAPP_APP_SECRET` y
     `TAKAB_API_NOTIFY_WHATSAPP_VERIFY_TOKEN` en el despliegue (los dos últimos, desde Secrets
     Manager).
   - **Abrir el 443 a los rangos de Twilio y Meta** en el security group: hoy está restringido por
     IP, así que **los callbacks no llegarían**.
5. **Nuevo (2026-08-17, `T-2.150`): dos secretos del sujeto-teléfono, y sin ellos el registro de
   consentimientos por WhatsApp SE CAE EN CERRADO.** `TAKAB_API_PRIVACY_SUBJECT_PEPPER` y
   `TAKAB_API_PRIVACY_SUBJECT_MASTER_KEY`, desde Secrets Manager. **No hay degradación
   silenciosa**: sin ellos la ruta devuelve **503 y lo dice**, porque la alternativa —guardar el
   teléfono en claro— lo dejaría en una tabla append-only **para siempre**.
   > **Y aquí el reloj corre en contra de verdad:** este mecanismo **no protege hacia atrás**. Cada
   > teléfono ya escrito en claro se queda así. **La fecha de este despliegue es la línea que
   > separa los números recuperables de los que no**, así que cuanto antes entre, menos hay.
   >
   > **Genera la pimienta y la clave con entropía real** (`openssl rand -base64 32` para cada una)
   > y **guárdalas donde no se pierdan**: rotar la pimienta invalidaría todos los índices, y
   > recalcularlos exigiría reescribir `privacy_consents`, que es append-only. Perder la clave
   > maestra destruye todos los teléfonos a la vez.

6. **El suscriptor HTTPS de la cadena on-call** ([`T-2.78.a`](TASKS.md)), y **su ORDEN es estricto
   porque la suscripción SE CONFIRMA DURANTE EL `apply`**:
   1. Desplegar la API **con `TAKAB_API_OPS_ALERT_TOPIC_ARN`**.
   2. `curl -X POST …/api/ops/alerts/sns -d '{}'` → debe dar **404**. **Si da 503, falta el ARN:
      PARA AHÍ** — seguir hace que el `apply` muera a medias.
   3. Solo entonces `ops_alert_https_subscriber_enabled = true` + `apply`.
   4. Acuñar tu credencial de guardia — **en `takab-cloud-notify-1`, NO en el de la API**:
>      ```bash
>      sudo docker exec -it takab-cloud-notify-1 \
>        python -m takab_api.ops.oncall issue --label "Mauricio (primaria)" --days 90
>      ```
>      El de la API conecta como `takab_app` y la tabla lo **niega por diseño**; hace falta un rol
>      con `BYPASSRLS`. Y va por `ssm start-session`, no por `send-command`: la salida de éste se
>      guarda 30 días en AWS, y esto es un secreto que se enseña una vez.
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
### 2.5 · [`T-2.89`](TASKS.md) · Encender `console_scope_enforced` — **va en la ventana A**
> **La única brecha multi-tenant viva en producción.** Tiene **secuencia obligada** —invertirla
> deja a cada `soc_operator` con cero estaciones—: primero recorrer los `scope_gap` del
> `audit_log`, luego asignar alcance, y **encenderlo al final**.
>
> **⚠️ Y pondrá la suite en rojo:** dos tests HTTP fijan hoy la conducta *no* impuesta. Hay que
> invertirlos **en el mismo cambio**, no después. Que no se descubra en mitad de la ventana.
>
> **✅ Momento decidido — [`D-18`](DECISIONES-MAURICIO.md#d-18): se enciende YA**, no se espera al
> primer cliente. Hoy hay un solo tenant de desarrollo, sin datos de nadie dentro: cerrar la brecha
> cuesta lo mínimo que va a costar nunca. El día que entre un cliente, este mismo cambio se hace
> con datos reales dentro y con él delante.

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
> **Ya no está bloqueado por criterio: está bloqueado por una tarjeta.** Y la diferencia importa,
> porque lo primero no lo desatascaba nadie leyendo el runbook.
>
> **✅ Decidido en [`D-12`](DECISIONES-MAURICIO.md#d-12)** — la tabla `D-1`…`D-6` del
> [runbook de SES](runbooks/RUNBOOK-ses-produccion-y-cadena-oncall.md) está **rellenada**:
>
> | | |
> |---|---|
> | Dominio raíz | **`takabailert.com`** — comprado en **Namecheap** |
> | DNS | **Route 53**, cuenta `634882473845` |
> | Remitente | **`alertas@takabailert.com`** |
> | MAIL FROM | **`bounce.takabailert.com`** — *`mail.` colisiona con el webmail del buzón* |
> | DMARC `rua=` | **`dmarc@takabailert.com`** |
> | On-call | **`ops@takabailert.com`** (migra del gmail personal) |
>
> ### ➡️ TU ACCIÓN — **estado al 2026-08-21: la zona SÍ, el dominio NO**
>
> | | Estado al 2026-08-21 |
> |---|---|
> | Dominio | ✅ **`takabailert.com` comprado** en Namecheap |
> | Zona alojada en Route 53 | ✅ **`Z01047862QJFIRSOR5IC5`** (las 3 zonas `.mx` duplicadas, borradas) |
> | **Buzón** (Namecheap Private Email, ~$15/año) | ❌ **PENDIENTE** — sin él, `ops@` y `dmarc@` no reciben |
> | **Delegar los NS** en Namecheap | ❌ pendiente — **y va DESPUÉS del buzón**, ver el orden |
>
> **⚠️ Crear la zona NO es tener el dominio, y el comando no lo dice.**
> `route53 create-hosted-zone` **acepta cualquier nombre sin comprobar que sea tuyo**: devuelve
> cuatro NS con aire de éxito y cobra su cuota **delegando nada**. Parece progreso y no lo es.
> Detalle en [`D-12`](DECISIONES-MAURICIO.md#d-12).
>
> **Y salieron TRES zonas** (una del 17-ago, dos del 21-ago), porque el comando **no es
> idempotente** y `--caller-reference` lleva timestamp. **Hay que borrar dos:** solo un juego de NS
> puede delegarse, y mezclarlos da correo que no se entrega **sin un solo error a la vista**.
>
> Hasta que el dominio exista, los CNAME de DKIM no se pueden publicar y **§4.2 (WhatsApp) sigue
> igual de parado** — es el mismo dominio sirviendo a dos trámites.
>
> Los tres registros de verificación del runbook (S-1…S-12, C-1…C-10, escalamiento) siguen **en
> blanco**: se rellenan durante la sesión, no antes.
>
> **El teléfono de soporte ya tiene dueño:** el manual dice **«avisa a soporte» 36 veces** (y menciona «soporte» 52 en total; medido el 2026-08-23, no estimado) y ese número
> no existía. Por [`D-13`](DECISIONES-MAURICIO.md#d-13) será el **número Twilio mexicano** de §4.3
> — un alta, dos necesidades. Se rellena `MANUAL-OPERACION-TAKAB.md §1` **cuando el número exista**,
> nunca antes: un número falso en un manual de emergencia es peor que una casilla vacía.

---

### 2.10 · [`T-2.167`](TASKS.md)/[`T-2.168`](TASKS.md) · Landing pública: un plan+apply corto y el primer deploy

> **Qué es:** la landing real de `landing/` reemplaza al sitio mínimo de `T-2.156`. El código y
> el terraform están listos y en verde; falta la mitad que solo tú puedes correr. **~20 min,
> cabe al principio de cualquier ventana** (sin build de imágenes, sin ECR).
>
> ### 📋 QUÉ TIENES QUE HACER — el orden importa (anti-ventana, runbook en `deploy/landing/README.md`)
> 1. `bash deploy/landing/deploy.sh --pre` — sube los assets con su metadata SIN tocar `index.html`.
> 2. `terraform -chdir=infra/terraform/envs/dev plan` — **gate duro: `0 to destroy`** y
>    `aws_s3_object.index` saliendo del estado como «no longer managed». Si dice
>    «will be destroyed», PARA: la portada se caería hasta el primer sync.
> 3. `terraform apply`.
> 4. `make landing-deploy` — guardas incluidas; termina con smoke (el `/no-existe` debe dar **404**).
>
> **Trampa ya pagada que aplica aquí:** jamás subas `index.html` a mano antes del apply — el
> etag del objeto histórico haría que un apply posterior lo REVIRTIERA al bootstrap.

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
> | **`G-01`** restart en frío | ✅ **ACREDITADO 2026-08-24** | — |
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
>
> ### 📅 Lo decidido el 2026-08-17, y parte esta ficha en dos
>
> **[`D-21`](DECISIONES-MAURICIO.md#d-21): `G-01` se acredita esta semana, SOLO.** Deja de esperar a
> los otros dos. Son ~20 min y no depende de comprar nada — atarlo a `G-02` lo dejaba rehén de una
> obra sin fecha.
>
> **[`D-16`](DECISIONES-MAURICIO.md#d-16): la BOM del `G-02` NO se compra todavía.** Y esto hay que
> leerlo por lo que es: **`G-02` es aplazamiento de RIESGO, no de trámite.** Cada día sin esa ruta
> es un día en que **un Pi colgado deja el edificio sin sirena** — y es, según la propia ficha, «la
> mitigación más importante del sistema». La lista está lista para comprar desde `D-10`; lo que
> falta es la compra.
>
> **Ojo con contar mal el progreso:** acreditar `G-01` **no cierra `T-2.92`**. Es uno de tres, y es
> el barato.
>
> ### 🔴 Y desde el 2026-08-23 `G-01` dejó de ser sólo el gate más barato: es el que gatea `T-2.70`
>
> `T-2.70` (actualización remota con canary y rollback) **está cerrada en software**: el gabinete
> despliega A/B —cada versión con su propio venv, `/opt/takab/edge` como symlink—, activa con
> remojo, vuelve atrás sola si falla, y la nube ordena todo eso con comando firmado y por
> cohortes. Lo que NO se puede cerrar desde el código es el primer despliegue A/B de un gabinete
> real: **convierte `/opt/takab/edge` de directorio a symlink, o sea que cambia la ruta desde la
> que arrancan las dos unidades del camino de vida.**
>
> Eso no se declara bueno con tests en verde. Se declara bueno con un **restart en frío del Pi
> con el layout nuevo**, que es literalmente `G-01`. El procedimiento está escrito y son ~10
> minutos más sobre los 20 que ya costaba: [`RUNBOOK-sesion-de-vida.md` §A.5](runbooks/RUNBOOK-sesion-de-vida.md).
>
> ✅ **HECHO el 2026-08-24.** El gabinete corre el layout A/B, arrancó en frío desde el symlink
> (`NRestarts` 0 y 0, `LGPIOFactory (lgpio)`, `flock=9`) y la prueba de actuadores movió los
> **5 canales** con `readback_ok` — sirena y estrobo vistos y oídos, y el gabinete de vuelta a
> reposo solo. **`T-2.70` queda CERRADA del todo.**

### 3.2 · [`T-2.93`](TASKS.md) · Sesión instrumental — `G-03`, `G-05`, `G-07`, `G-10`
Incluye el gate #3 del Shake: hoy sus 5 tests se saltan cuando el sensor no está alcanzable, y la
suite **lo declara en voz alta** en vez de callarlo.

### 3.3 · [`T-2.94`](TASKS.md) · Sesión de sitio — `G-06`, `G-08`
> **Única dependencia declarada del Bloque III sobre el II:** necesita `T-2.78`, porque un
> simulacro con **cascada de notificación real** no se acredita con canales simulados.

### 3.3.b · Poner en hora la cámara del CCTV — **5 minutos, y bloquea la evidencia**

La cámara del sitio (`192.168.3.132`, Imou/Dahua `IPC-S41FE`) llegó con el **huso de fábrica
del fabricante**, `GMT+08:00`, y nadie lo tocó. Su UTC es correcto; lo que está mal es lo que
**quema en los píxeles**. Medido el 2026-08-30:

| | |
|---|---|
| hora del sitio | `2026-08-30 11:57` |
| lo que decía la foto | **`2026-08-31 01:57`** |

Catorce horas y **un día distinto**, en una imagen que va al dictamen con su `sha256`. El
software ya lo avisa al arrancar (quinta comprobación de `takab-cctv`), pero **avisar no lo
arregla**: mientras la cámara siga así, toda captura que salga de ella lleva el sello corrido.

Y hay una segunda mitad que se olvida: `DateTimeType` está en **`Manual`**, o sea **sin NTP**.
Aunque hoy se ponga la hora a mano, sin servidor de tiempo vuelve a derivar sola.

**Las dos cosas se hacen en la misma pantalla** de la interfaz web de la cámara
(`http://192.168.3.132`, usuario `admin`) → *Configuración · Sistema · General · Fecha y hora*:

1. **Huso horario** → el del sitio (`GMT-06:00`, Ciudad de México).
2. **Sincronizar con NTP** → encendido. Cualquier `pool.ntp.org` sirve; mejor aún, el propio
   gabinete, que ya tiene hora buena y no depende de que la cámara salga a internet.
3. Comprobar que el **sello de la imagen** cambió — no basta con que la pantalla de
   configuración diga la hora buena: lo que importa es el rótulo quemado en el fotograma.

> **Por qué está aquí y no en `TASKS.md`:** el software ya hace todo lo que puede hacer
> —detectarlo y decirlo—. Poner en hora una cámara es tocar la cámara.

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
> ### ✅ La sirena por jack ya está encendida — **verificado el 2026-08-17**
> Esta sección ofrecía `TAKAB_EDGE_AUDIO_SIREN_ENABLED=true` como «algo que puedes encender HOY».
> **Ya lo estaba** desde el 2026-08-16 19:49:30 (se encendió sola en el despliegue del traspaso de
> pines), y no se comprobó leyendo `edge.env` sino **el journal del proceso vivo**, que declara el
> `sha256` del WAV que puede sonar por el altavoz de un inmueble. Detalle en
> [`D-15`](DECISIONES-MAURICIO.md#d-15).
>
> **Lo único que falta es oírla**, y eso no se dispara sin avisar a quien esté en el sitio:
> ```bash
> ssh takab-pi5 'curl -s -X POST http://127.0.0.1:8080/api/siren-test'
> ```
> **El voceo hablado sigue apagado y debe seguirlo:** `TAKAB_EDGE_AUDIO_ENABLED` es **otra cosa**,
> exige las dos grabaciones y **rompe el arranque si faltan**.

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

### 3.6 · Capturas reales para la landing v1.1 — **OPCIONAL, no bloquea el corte**

> La landing v1 salió sin fotografía ni capturas (decisión 2026-08-25). Cuando quieras subirle
> materialidad: (a) conecta el **Pixel real por USB** para capturar la app (regla: nunca
> emuladores), (b) capturas de la consola con `make soc-local` sembrado, (c) si algún día hay
> sesión de fotos del gabinete instalado, entran por `astro:assets` (AVIF/WebP automático).
> Nada de esto usa los mockups de `takab-docs/design/` como si fueran el producto.

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
>
> ### ⏸️ EN ESPERA por decisión — [`D-20`](DECISIONES-MAURICIO.md#d-20) (2026-08-17)
>
> **No se contrata abogado hoy.** El documento queda **escrito y listo para enviar**; se activa el
> día que un cliente institucional pregunte. La razón: el gasto no desbloquea una sola línea de
> código, y con [`D-16`](DECISIONES-MAURICIO.md#d-16) comprometiendo dominio y Twilio, el dinero va
> donde hay un tercero **ya esperando**.
>
> **El riesgo aceptado, dicho sin adornos:** el reloj arranca el día de la pregunta, y una opinión
> escrita en responsabilidad de producto no se entrega en 48 h. **El ahorro de hoy se paga en
> calendario del cliente**, en mitad de una venta.
>
> **Lo que queda colgando:** [`D-07`](DECISIONES-MAURICIO.md#d-07) (cripto-borrado) es *postura por
> defecto sujeta a esta revisión*. Se implementó igual —`T-2.150`, mergeada— pero **no está
> validada**: sigue abierto si un número cifrado es dato personal mientras exista la clave.
>
> **El gatillo que la revive** (los tres, escritos para no depender de acordarse): un cliente
> pregunta por el marco o la privacidad · aparece un ARCO real sobre un `subject_ref` por teléfono ·
> el sistema empieza a **afirmar** un marco propio en vez de citar el del cliente.

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
> **✅ El dominio ya está COMPRADO: `takabailert.com`**
> ([`D-12`](DECISIONES-MAURICIO.md#d-12), enmendada el 2026-08-21). Ya no es el paso 0 de nada:
> existe.
>
> **Y conviene saber qué cambió respecto a lo que decía esta viñeta.** `D-12` había elegido un
> `.mx` precisamente por este trámite —Meta mira el dominio al verificar el negocio—. Con el `.com`
> **no se pierde capacidad: se pierde señal.** Meta acepta `.com` sin problema, porque la
> verificación la hace con **documentos legales**, no con el TLD. Lo que Meta sí va a pedir es un
> **correo del dominio**, y eso llega con el buzón de §2.9.
>
> **Y una cosa que conviene saber antes de empezar:** si Meta **pausa** la plantilla por calidad,
> **el canal cae solo y queda en cuarentena persistida** (`T-2.77.c`) — no hay que hacer nada, y
> no se martillea la plantilla pausada. Eso ya está resuelto.

### 4.3 · [`T-2.76.a`](TASKS.md) · Cuenta Twilio + número mexicano — **✅ autorizado, un alta y dos usos**
> **✅ Comprometido en [`D-16`](DECISIONES-MAURICIO.md#d-16)** (~$3 USD/mes). Y este trámite
> **vale por dos**: además del canal SMS, ese número es el **teléfono de soporte** del manual de
> operación ([`D-13`](DECISIONES-MAURICIO.md#d-13)), que lleva ~25 menciones apuntando a una casilla
> vacía.
>
> **Por qué Twilio y no tu móvil:** un número de Twilio **se redirige**. El día que rote la guardia
> o cambies de teléfono, el número impreso en el manual del edificio 3 **sigue siendo el correcto**.
> Un móvil personal obliga a reeditar y redistribuir el manual en cada sitio instalado — que en la
> práctica significa que nunca se hace.
>
> **⚠️ La trampa de calendario:** un número mexicano exige **regulatory bundle** en Twilio
> (identificación y comprobante de domicilio), y eso **tarda días**. No es «comprar un número».
>
> **➡️ Al terminar:** rellenar la fila «Soporte TAKAB — teléfono» de
> [`MANUAL-OPERACION-TAKAB.md §1`](MANUAL-OPERACION-TAKAB.md) y la de
> [`ENTREGA-Y-ACEPTACION-TAKAB.md`](ENTREGA-Y-ACEPTACION-TAKAB.md). **No antes**: un número falso
> en un manual de emergencia es peor que una casilla vacía.

### 4.4 · [`T-2.97`](TASKS.md) · `GATE-STORE` · APNs/FCM reales + tono de alerta
> **✅ El tono está decidido: PROPIO, no el oficial de CIRES** —
> [`D-19`](DECISIONES-MAURICIO.md#d-19). Reproducir el tono del SASMEX diría **por el altavoz** lo
> contrario del deslinde que el sistema afirma por escrito, y ya hay precedente medido de esa clase
> de error (`T-2.104`: la app tituló «ALERTA SÍSMICA SASMEX» algo que no lo era). Además elimina un
> plazo externo entero y **no se puede perder después**: un permiso se revoca, un tono propio no.
>
> **Lo que se paga y hay que compensar con diseño:** el tono oficial es el que la gente ya reconoce
> y obedece. El propio tiene que ser **inconfundible**, no una notificación más.
>
> **⏸️ Bloqueado por [`D-16`](DECISIONES-MAURICIO.md#d-16):** sin cuenta Apple Developer
> ($99/año, **no autorizada todavía**) esto no se puede ni empezar.

### 4.5 · [`T-2.98`](TASKS.md) · Entitlement Critical Alerts de Apple
> Apple lo concede caso por caso. **Plazo externo.**
>
> **⏸️ EN ESPERA por [`D-16`](DECISIONES-MAURICIO.md#d-16):** la cuenta Apple Developer no está
> autorizada todavía, y **el reloj del entitlement no arranca hasta que haya cuenta**. Es
> aplazamiento de **calendario** —se suma al final, cuando toque publicar—, no de riesgo. No
> confundirlo con el `G-02` de §3.1, que sí es riesgo.

---

### 4.6 · Buzón `contacto@takabailert.com` + número de WhatsApp de la landing

> **Decidido el 2026-08-25:** el contacto de la landing es correo nuevo + WhatsApp, sin
> formulario. La landing YA enlaza `contacto@takabailert.com`; hasta que el buzón exista, un
> prospecto que escriba recibe un rebote.
>
> ### 📋 QUÉ TIENES QUE HACER — 10 min en Namecheap + una línea de código
> 1. Crea el buzón/alias `contacto@takabailert.com` en Namecheap Private Email (el MX del apex
>    ya apunta ahí; es donde viven `ops@` y `dmarc@`).
> 2. Mándate un correo de prueba desde fuera y contesta desde el buzón.
> 3. Decide el número de WhatsApp para `wa.me` (¿asumes tú el ruido de prospectos ahí?) y ponlo
>    en `landing/src/config.ts` (`WHATSAPP_URL`); con la cadena vacía el botón NO se renderiza
>    a propósito — un canal que no existe no se muestra.

## 5 · CIERRE DEL PROYECTO

### 5.1 · [`T-4.01`](TASKS.md) · Auditoría de cierre final
### 5.2 · [`T-4.03`](TASKS.md) · Traspaso operativo
### 5.3 · [`T-4.04`](TASKS.md) · Aceptación firmada
> El documento está escrito con los campos y las firmas **en blanco**:
> [`ENTREGA-Y-ACEPTACION-TAKAB.md`](ENTREGA-Y-ACEPTACION-TAKAB.md).

---

## Si solo se pueden hacer tres cosas — **reescrito el 2026-08-17**

1. **Comprar el buzón y delegar los NS de `takabailert.com`.** El dominio **ya está comprado** y
   su zona de Route 53 creada (2026-08-21); lo que falta son ~$15/año de buzón y pegar cuatro
   *name servers* en el panel de Namecheap. Sigue siendo **la acción que desatasca dos puntos de
   plazo externo a la vez** —§2.9 (SES) y §4.2 (WhatsApp)— y ahora cuesta la mitad que ayer.
   **Nada más de esta lista tiene esta relación entre esfuerzo y desbloqueo.**
2. **Abrir Twilio y comprar el número mexicano (§4.3).** También vale por dos: canal SMS **y** el
   teléfono de soporte que el manual cita **52 veces** —36 de ellas como la orden literal
   «avisa a soporte»— apuntando a una casilla vacía
   ([`D-13`](DECISIONES-MAURICIO.md#d-13)). Y el *regulatory bundle* mexicano **tarda días**, así
   que arrancarlo tarde cuesta calendario, no dinero.
3. **Acreditar `G-01` esta semana (§3.1).** Veinte minutos, no depende de comprar nada, y
   [`D-21`](DECISIONES-MAURICIO.md#d-21) acaba de soltarlo de la sesión de vida precisamente para
   que dejara de esperar a una obra sin fecha.

> **Lo que salió del podio y por qué, que es la parte que conviene releer:**
>
> - **§4.1 (consulta legal)** encabezaba esta lista y hoy está **en espera por decisión**
>   ([`D-20`](DECISIONES-MAURICIO.md#d-20)). No porque haya dejado de importar: porque el gasto no
>   desbloquea código y el dinero fue a los terceros que ya están esperando. **El riesgo sigue
>   sobre la mesa** — el reloj arranca el día que un cliente pregunte.
> - **La sesión de vida (§3.1)** ya no es *una* cosa: son tres con calendarios distintos, y solo
>   `G-01` está listo. `G-02` es **obra, no prueba**, y su hardware quedó aplazado
>   ([`D-16`](DECISIONES-MAURICIO.md#d-16)) — **eso es deuda de riesgo, no de trámite**: hasta que
>   se construya, un Pi colgado deja el edificio sin sirena.
> - **`GATE-HW 02` (§3.4)** era el puesto 3 y **la premisa estaba corregida desde el 2026-08-16**:
>   re-correrlo no mostraría nada nuevo. Lo que falta ahí es el flujo **03**, que necesita firma de
>   inspector en la consola web.
>
> **Y el patrón de esta pasada, distinto al de las anteriores:** las dos veces anteriores la lista
> se acortó por arriba y lo que quedaba era más caro. Esta vez **no se acortó: se reordenó**. Diez
> decisiones que estaban escondidas dentro de tareas salieron a la luz, y al salir cambiaron cuál
> era la tarea más barata. **Lo que bloqueaba no era el dinero: era que nadie sabía que había que
> elegir.**
