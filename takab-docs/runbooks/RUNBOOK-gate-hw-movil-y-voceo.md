# Runbook · `GATE-HW` móvil + voceo

> **Ficha:** [`T-2.95`](../TASKS.md) · **Pendiente:** [`PENDIENTES-MAURICIO §3.4`](../PENDIENTES-MAURICIO.md)
> **Dueño:** Mauricio · **Necesita:** un dispositivo Android real (el entorno ya está verde)

---

## ⚠️ Corrección de alcance: **re-correr «`GATE-HW 02`» no mostraría la conducta nueva**

§3.4 dice que hay que re-correr el flujo `GATE-HW 02` porque «se acreditó contra la conducta
vieja». **Verificado contra el repositorio el 2026-08-16: la premisa no se sostiene.**

`02-tactico-foto-danos.yaml` es **cámara forense → formulario de daños → Triage**. Su guion no
pulsa el control táctico, no silencia nada y no lee la hoja de acuse. Y no es solo el 02:

> **Ningún flujo de Maestro toca el control táctico.** Los seis flujos —`01a`, `01b`, `02`, `03`,
> `04`, `05a/b/c`— no contienen una sola referencia a silenciar, armar o al estado del relé.

**Lo que esto significa, y es más serio que un flujo mal numerado:** la conducta que introdujeron
`T-2.107` → `T-2.116` → `T-2.120` **no tiene cobertura E2E en dispositivo real**. Está probada
—`ackTracking.test.tsx` conduce la ruta real como una persona y asserta el texto que se lee—, pero
eso corre en CI, no en un teléfono.

**Consecuencia práctica:** re-correr el 02 no está mal, pero **no acredita lo que §3.4 quería
acreditar**. Lo que hace falta es el **Bloque B** de este runbook.

---

## Estado real de los seis flujos

| Flujo | Archivo | Estado | Qué le falta |
|---|---|---|---|
| Toma de crisis | `01a-crisis.yaml` | ✅ acreditado (2026-08-09) | — |
| Check-in de vida | `01b-checkin-sync.yaml` | ✅ acreditado | — |
| Táctico: foto → daños | `02-tactico-foto-danos.yaml` | ✅ acreditado | — |
| **Dictamen → liberación** | `03-dictamen-liberacion.yaml` | ❌ **nunca acreditado** | **firma de un inspector en la consola web** |
| Pánico quórum-de-2 | `04-panico-quorum.yaml` | ✅ acreditado (1.º voto) | el **2.º voto** exige un segundo teléfono |
| Offline-first | `05a/05b/05c` | ✅ acreditado | — |
| **Control táctico / acuse del relé** | *(no existe)* | ❌ **sin flujo** | ver Bloque B |

---

# BLOQUE A · Lo que hay que correr en el teléfono

### A.0 · Preparar (las trampas ya pagadas, no las re-descubras)

```bash
cd mobile/android
./gradlew :app:assembleRelease -PreactNativeArchitectures=arm64-v8a
adb install -r app/build/outputs/apk/release/app-release.apk

export PATH="$HOME/.maestro/bin:$PATH"
cd .. && set -a && . .maestro/.env && set +a
```

| Trampa | Por qué |
|---|---|
| **APK de RELEASE, no dev-client** | todos los flujos empiezan con `clearState`, que borra la config del dev launcher; el flujo muere en `DevLauncherActivity` con un error que apunta a la app en vez de al build |
| **`-PreactNativeArchitectures=arm64-v8a`** | sin eso compila 4 ABIs que ningún teléfono de prueba usa — ×4 el tiempo, y el OOM puede matar la sesión |
| **Siempre por `run.sh`**, nunca `maestro test` | Maestro no hereda el entorno; `env: FOO: ${FOO}` produce la cadena literal `"undefined"` y la teclea en el formulario. Cognito dice «credenciales incorrectas» con las credenciales buenas |
| **El offline por `run-offline.sh`** | **el modo avión de Android no apaga el WiFi**; el script controla el radio |

### A.1 · Flujo `03` — el único de los seis nunca acreditado

**Es el que cierra el círculo del producto:** consola-firma → push → PDF → reingreso liberado.

Necesita **una persona firmando un dictamen en la consola web** con otro usuario mientras el
flujo corre en el teléfono. No lo puede hacer Maestro y no lo puede hacer una sola persona con
comodidad: conviene tener la consola abierta en otra pantalla antes de empezar.

```bash
make cloud-staging-incident PHASE=conclude
.maestro/run.sh 03-dictamen-liberacion.yaml
```

### A.2 · Regresión de los otros cinco — barato, ya montado

Con el entorno de A.0 puesto, re-correr los cinco acreditados cuesta minutos y vale la pena: la
app cambió desde el 2026-08-09. **El orden importa** — la fase del incidente es precondición:

```bash
.maestro/run.sh 04-panico-quorum.yaml            # no necesita incidente
make cloud-staging-incident PHASE=crisis
.maestro/run.sh 01a-crisis.yaml
make cloud-staging-incident PHASE=conclude
.maestro/run.sh 01b-checkin-sync.yaml
.maestro/run.sh 02-tactico-foto-danos.yaml       # pide el TOTP del táctico
make cloud-staging-incident PHASE=roster
.maestro/run-offline.sh
```

---

# BLOQUE B · El control táctico — **manual, porque no hay flujo**

**Qué se acredita:** que al silenciar durante una alerta vigente, la app **dice la verdad** en vez
de fingir éxito — y nombra **quién** sostiene la sirena.

### B.1 · ⚠️ El modo prueba NO sirve para esto

`/api/test-mode` (T-1.69) arma el WR-1 **sin publicar a la nube**: sin incidente y sin
notificación. Es justo lo que se quiere para probar el WR-1 sin hacer ruido — y **exactamente lo
que rompe esta prueba**, porque sin incidente en la nube la app nunca ve una alerta vigente y la
hoja de acuse no puede llegar a la rama que queremos leer.

> **O sea: esta acreditación exige una alerta REAL.** Y eso trae consecuencias que hay que aceptar
> antes de empezar, no descubrir después:
> - **La sirena suena de verdad** (hoy, por relé; y por jack si activas el Bloque C.1).
> - **Se abre un incidente real en la nube.**
> - **Se disparan las notificaciones reales** que estén configuradas.
>
> Avisa a quien esté cerca y a quien reciba notificaciones.

### B.2 · El escenario, paso a paso

1. **En el teléfono:** entra con el usuario **táctico** (brigadista o seguridad). La hoja de
   control solo existe para esos roles.
2. **En el gabinete:** aserta el contacto de **alerta** del WR-1 — botón de prueba del propio
   receptor. **Sin** armar el modo prueba.
3. **Comprueba que la alerta viaja:** el panel del gabinete (`http://192.168.3.91:8080`) debe
   mostrar `siren_sounding: true`, y la app debe entrar en toma de crisis.
4. **En la app:** abre el control táctico y **silencia**. Desliza para confirmar.
5. **Lee la hoja.** Esto es lo que se acredita.

### B.3 · Lo que debe decir — y las cuatro variantes, porque distinguirlas es el gate

| Lo que ves | Qué significa |
|---|---|
| **«SU DEMANDA SE RETIRÓ · LA SIRENA SIGUE ACTIVA»** | ✅ **lo esperado.** El gabinete acusó el retiro de tu demanda y declara el relé **todavía energizado**. El detalle debe **nombrar quién lo sostiene** — ésa es la parte nueva de `T-2.116` |
| «SIRENA SILENCIADA» | ⚠️ solo es correcto **si la alerta ya cesó**. Con alerta vigente, es el fallo |
| «ESPERANDO CONFIRMACIÓN DEL GABINETE» que no cambia nunca | ❌ es el defecto de `T-2.107` regresando: la app no vuelve a preguntar |
| «EL COMANDO SE EJECUTÓ · LA SIRENA NO QUEDÓ ACTIVA» | ⚠️ el otro lado del mismo hecho — al **activar**, el relé quedó en reposo. Verificar el sitio |

> **La frase puede llegar por dos caminos, y solo uno es el que este gate acredita.** Si el acuse
> trae `channel_state` —lo que `T-2.116` añadió y el gabinete ya envía—, el mensaje sale del
> **estado medido del relé** y el detalle nombra quién lo sostiene. Si no lo trajera, hay un
> respaldo antiguo que la deduce de «hay alerta vigente en el sitio». **Los dos dicen el mismo
> titular.** Para saber cuál viste, mira el detalle: si no nombra quién sostiene la sirena, estás
> en el respaldo — y entonces `T-2.116` no está llegando al teléfono.

### B.4 · Limpiar después

Cierra la alerta enclavada desde el panel del gabinete (`/api/reset`) y cierra el incidente en la
consola. Si no, el gabinete queda enclavado y el siguiente que mire el SOC verá una emergencia.

---

# BLOQUE C · Voceo — **bloqueado en dos cosas distintas**

### C.1 · 🎁 Lo que puedes encender HOY, sin comprar ni grabar nada

Hay **dos interruptores de audio distintos**, y se confunden con facilidad:

| Interruptor | Qué hace | Qué exige |
|---|---|---|
| `audio_siren_enabled` | **sirena por el jack de 3.5 mm** cuando el relé de sirena suena | **nada** — el WAV va empaquetado |
| `audio_enabled` | **voceo hablado** (mensajes de voz) | **dos WAV grabados** |

**El primero se puede encender ya.** Da una sirena audible por el jack sin comprar hardware y sin
grabar nada, mientras la sirena de relé de verdad espera al Bloque C del runbook de la sesión de
vida. Sigue siendo **ADVISORY**: la sirena de **relé** es y será la primaria.

```
TAKAB_EDGE_AUDIO_SIREN_ENABLED=true   en /etc/takab/edge.env
→ deploy/edge/deploy.sh takab-pi5
```

> **Y ahora es barato de verdad:** desde el traspaso del dueño de los pines
> ([`D-04`](../DECISIONES-MAURICIO.md)), reiniciar `takab-edge` **no mueve un solo relé**.

### C.2 · El voceo hablado — lo que falta

**Dos cosas, y ninguna es código:**

1. **Hardware:** DAC / amplificador / bocina montados. *(El «cerebro» es un Pi 4 **con** jack de
   3.5 mm, así que no hace falta DAC USB ni HAT I2S para empezar — sí un amplificador y una bocina
   con potencia útil.)*
2. **Las dos grabaciones.** `audio_sismo_path` y `audio_simulacro_path` están **vacíos**. Los WAV
   que hay en el repositorio —`siren.wav` y `prueba.wav`— **no son estos mensajes**: son el tono de
   sirena y el de autoprueba.

> ### ⚠️ La trampa de encender el voceo antes de tiempo
> Con `audio_enabled=true`, **ambos archivos deben existir al arrancar**. Encenderlo sin las dos
> grabaciones deja al gabinete fallando al arranque. Enciéndelo **después** de copiar los WAV, no
> antes.

**Y el criterio de aceptación que importa, del `T-2.95`:** el mensaje de sismo y el de simulacro
tienen que ser **distinguibles a oído**, no solo por `sha256`. Una persona bajo una sacudida no
compara hashes: oye una frase y decide si sale del edificio. Grábalos con textos claramente
distintos, no dos variantes de lo mismo.

---

## Registro

| Prueba | Fecha | Dispositivo | OK |
|---|---|---|---|
| `03` dictamen → liberación | | | |
| Control táctico · «SU DEMANDA SE RETIRÓ» con detalle que nombra al sostenedor | | | |
| Regresión `01a`, `01b`, `02`, `04`, `05` | | | |
| 2.º voto del quórum (segundo teléfono) | | | |
| Sirena por jack audible (C.1) | | | |
| Voceo: sismo y simulacro distinguibles a oído | | | |
