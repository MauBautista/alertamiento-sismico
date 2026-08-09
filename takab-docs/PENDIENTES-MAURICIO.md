# Pendientes de Mauricio — lo que el software no puede cerrar

> **Qué es esto.** El censo de todo lo que está bloqueado en una persona, no en código. Sale de
> `TASKS.md` y **no lo sustituye**: cada punto de aquí enlaza a su ficha, que es donde vive el
> detalle. Esto es la lista de trabajo; aquellas son la especificación.
>
> **Última actualización:** 2026-08-09 · **27 pendientes** · Estado del backlog al escribirlo:
> 234 tareas · 159 `[x]` · 6 `[~]` · 69 `[ ]`, de las cuales **56 son `SOFTWARE`** y las demás
> están aquí.

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

### 1.2 · ¿Qué gana, `empty` o `stale`? — [`T-2.79.d`](TASKS.md)
**La decisión:** cuando **no hay dato** *y* **lo poco que hay está viejo**, ¿la pantalla dice «no
hay» —arriesgando afirmar una ausencia que quizá solo es desconexión— o dice «no lo sé desde las
hh:mm», que es más honesto y menos accionable?

No es un banner: **gobierna toda la consola**. Hoy cada componente lo resuelve por su cuenta, y
esa deriva ya produjo una franja muda y que **ningún panel de la pantalla donde se firma un
dictamen** pueda declarar su dato viejo.

**Desbloquea:** `T-2.79.d`, `T-2.82.a` y `T-2.84.c` — las tres son la misma raíz.

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

### 1.6 · `main` NO tiene protección de rama — 5 minutos en GitHub

**Comprobado con `gh api` el 2026-08-09: el repositorio no tiene branch protection ni rulesets.**
O sea que **hoy ningún job bloquea nada**: el CI corre, se pone rojo, y se puede mergear igual.

Importa ahora más que ayer, porque el barrido de secretos que se acaba de construir **es un
gate** —pone el PR en rojo cuando encuentra una credencial— y **un gate que no bloquea es un
aviso**. Lo mismo vale para los 2118 tests de api, los 1353 de web y los 1071 del edge.

**Qué hacer:** en `Settings → Branches` (o `Rulesets`), exigir como *required status checks* los
jobs `api`, `web`, `edge`, `mobile` y `secretos`.

**Consecuencia colateral que conviene saber:** la matriz de trazabilidad acredita `CUBIERTO`
solo si el test *«lo corre un job que bloquea el merge»*, y hoy modela eso como «está en
`ci.yml` y no es `continue-on-error`». Mientras no haya protección de rama, **el modelo es más
optimista que la realidad**.

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

### 2.1 · Aplicar lo que ya está escrito y sin desplegar
Migraciones **0027 … 0036** y el módulo de identidad. Incluye el `terraform apply` de los tres
statements IAM de las ventanas de mantenimiento ([`T-2.71`](TASKS.md)).

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

1. **Proteger `main` (§1.6).** Cinco minutos, y sin eso **nada de lo demás bloquea nada**: hoy
   los 4 542 tests y el barrido de secretos son un aviso, no un gate.
2. **Las decisiones de §1.1 y §1.2.** Cuestan pensar, no herramientas, y desbloquean cinco fichas
   de software entre las dos.
3. **Arrancar §4.1 y §4.2.** Son las de plazo externo. Todo lo demás se puede acelerar; esto no.

Y en cuanto haya un hueco con el edificio: **la sesión de vida (§3.1)**, que es la que dice si el
producto es real y no espera a nada.
