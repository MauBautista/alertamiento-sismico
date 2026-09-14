# Runbook · Demostración al cliente

> **Ficha:** [`T-7.07`](../TASKS.md) · **Plan:** [`PLAN-PROTOTIPO-FUNCIONAL §4 · F1`](../PLAN-PROTOTIPO-FUNCIONAL.md)
> **Dueño:** Mauricio · **Necesita:** el WR-1, el gabinete, el Pixel y una persona en la consola
> **Guion ejecutable:** `deploy/demo/guion.sh`

---

## ⚠️ Antes de nada: esto no es un simulacro, es el sistema

Los cuatro actos corren contra el sistema **real**. Eso quiere decir tres cosas que hay que decir
en voz alta antes de empezar, porque una vez empezado ya no se pueden deshacer:

1. **La sirena suena de verdad.** Avisa a quien esté en el edificio y a los vecinos si el relé
   está cableado a la sirena exterior. No es un tono de prueba.
2. **La cascada notifica de verdad.** El correo dice «ALERTA SÍSMICA» y **no lleva la palabra
   simulacro en el asunto**: quien lo reciba va a creer que hubo un sismo. Por eso el preflight se
   niega a arrancar si algún destinatario no es nuestro.
3. **Lo que se enseña queda registrado como un incidente.** Al final hay que clasificarlo como
   `prueba` y cerrarlo, o quedará contando en las métricas del sitio como un sismo que no pasó.

Esto no es nuevo y no hay que re-descubrirlo: el **Bloque B** de
[`RUNBOOK-gate-hw-movil-y-voceo.md`](RUNBOOK-gate-hw-movil-y-voceo.md) ya lo dejó escrito con su
razón — *una alerta real es la única que abre incidente y dispara notificaciones; el modo prueba
del WR-1 arma el radio **sin publicar a la nube**, que es justo lo que rompe la prueba*. Ese
runbook obliga a avisar antes; este hereda la obligación.

**Y el dato que ordena todo lo demás:** de los cuatro actos, el único que **no se puede repetir en
frío** es el 3. Si el pulso sale mal —enclavado vivo, modo prueba armado, gabinete sin nube— hay
que resetear el gabinete y volver a empezar el acto, con el cliente delante. De ahí el preflight.

---

## Precondiciones — **el preflight es la precondición, no una lista que leer**

```bash
AWS_PROFILE=takab-dev bash deploy/demo/guion.sh --preflight
```

Sale `0` solo si **todo** está en orden. Cada ✗ es algo que hace que la demostración falle **sin
dar un error a la vista**, que es justo lo que no se puede permitir delante de un cliente:

| Lo que mira | Por qué, si está mal, no se nota |
|---|---|
| modo prueba del WR-1 **desarmado** | armado, el pulso se queda en el gabinete: suena la sirena y **no publica a la nube**. La consola sigue en reposo y parece que el radio no llegó |
| sin **enclavado** vivo | enganchado de la prueba anterior, el acto 3 no se distingue del acto 2 |
| **relés en reposo** y cadena sana | con un relé ya accionado, el acto 2 no puede enseñar «nada se movió» |
| **sin simulacro** en curso | la consola pintaría la franja de simulacro encima de la demostración |
| el gabinete **ve la nube** | habría sirena y **ningún incidente** en la consola |
| algo que **suene** (relé de sirena o voceo) | el acto 3 no se oiría |
| **modo demostración apagado** ([`D-27`](../DECISIONES-MAURICIO.md)) | suprime comandos firmados y avisos, y todo contesta `201` igual |
| **destinatarios propios** | la cascada le escribiría a un tercero un correo que dice ALERTA SÍSMICA |
| **Pixel por USB, app instalada y token vivo** | el teléfono no recibe nada aunque todo lo demás esté perfecto |
| **sin incidentes abiertos** en el sitio | el acto 4 trabajaría sobre el incidente viejo |

> **Desde la red de desarrollo.** El guion busca el gabinete en `192.168.1.0/24`, que es la red
> donde se va a **instalar**. En casa hay que decirle dónde mirar, y la dirección del Pi **cambia
> por DHCP**:
>
> ```bash
> TAKAB_DEMO_PANEL_URL=http://192.168.3.140:8080 bash deploy/demo/guion.sh --preflight
> ```
>
> Para encontrarlo sin adivinar: `ip neigh` lista los vecinos; contesta en el `8080`.

---

## Acto 1 · El SOC operando normal

**Qué se enseña.** La consola en reposo: el mapa con las estaciones vivas, los indicadores y la
cola vacía. Es el estado que el cliente va a ver el 99,9 % del tiempo, y decirlo en voz alta vale:
*«así se ve un día en que no pasa nada, y esto es lo que queremos que vean casi siempre»*.

**Dónde mirar.** Consola → mapa. El pulso de vida late solo si el dato es **en vivo**; si el
gabinete estuviera mudo, la franja lo diría en vez de pintar un dato viejo como si fuera de ahora.

---

## Acto 2 · Movimiento aislado en el edificio, **sin** señal del WR-1

**Qué se hace.** Mover el sensor con la mano (un golpe seco al lado del Raspberry Shake).

**Qué tiene que pasar — y qué NO:**

- **Panel del gabinete:** el nivel sube a `watch` o `restricted`.
- **Consola:** escena de aviso, con «SOLO AVISO, SIN ACTUACIÓN».
- **Nube:** incidente con origen `local_threshold`.
- **Relés: quietos.** Ninguno se mueve. **Esto es lo que hay que señalar con el dedo**, porque es
  una decisión de diseño y no una limitación: una estación sola **no evacúa un edificio**. Hacen
  falta el SASMEX o tres inmuebles de acuerdo.

**Cómo se comprueba sin creerse el panel:**

```bash
curl -s http://<ip-del-gabinete>:8080/api/status | jq '{tier: .last_tier, relés: [.relays[] | {channel, activated}]}'
```

> ### ⚠️ La consola: lo único de `T-7.08` sin acreditar, y las dos trampas que lo impiden
>
> El 2026-09-12 el ensayo se llevó desde el panel, la nube y el teléfono, y **nadie miró la
> consola**. Es lo único que separa a `F1` de estar cerrada. Pero no basta con tenerla abierta:
> la franja de la consola **se monta solo con `severity === "critical"`**
> (`scene.ts::sceneAlert`), y eso encadena dos condiciones que un golpe flojo no cumple.
>
> **1 · El golpe tiene que disparar DOS canales, no uno.** Solo `evacuate_or_hold` mapea a
> `critical`; `restricted` es `warning` **y no pinta franja**. Y la regla de `rules/__init__.py`
> es por CUENTA de canales, no por el pico de uno:
>
> ```
> trip  = canales con pga ≥ pga_trip_g (0.100 g)  o  pgv ≥ pgv_trip_cms (7 cm/s)
> len(trip) >= 2  → evacuate_or_hold     ← lo único que pinta la franja
> len(trip) == 1  → restricted           ← warning: la consola no enseña nada
> watch           → watch
> ```
>
> Medido el 14-sep con tres golpes reales: uno llegó a `watch` (un canal en vigilancia), otro a
> `restricted` (**disparo en un sensor: ENN**) y ninguno de los dos habría pintado la franja. El
> del 12-sep midió 0.357 g y sí disparó dos o más.
>
> En la práctica: **golpea la superficie sobre la que se apoya el Shake, seco y cerca**, para que
> el choque cargue verticales y horizontales a la vez. Un toque a la carcasa carga un eje y se
> queda en `restricted`.
>
> Compruébalo en el panel ANTES de ir a la consola:
>
> ```bash
> curl -s http://raspberry-cerebro.local:8080/api/status \
>   | jq '{tier: .last_tier, pga_por_canal: [.signal.channels | to_entries[] | {(.key): .value.pga_g}]}'
> ```
>
> `tier` tiene que decir **`evacuate_or_hold`**. Si dice `restricted`, el golpe se quedó corto y
> la consola **no** va a pintar la escena: vuelve a golpear más fuerte antes de ir a mirarla.
>
> **2 · Cierra antes los incidentes `critical` viejos.** `sceneAlert` toma el **primer**
> incidente `critical` de la cola, y la cola va por `opened_at DESC`. El nuevo gana por ser más
> reciente — pero si el golpe se queda corto, la franja mostrará el **SASMEX anterior en rojo**,
> y eso se lee como si el acto 2 hubiera disparado una alerta que no disparó. Ciérralos desde
> triage con su clasificación (`prueba`), que es de dos clics.
>
> **Lo que tiene que decir la franja**, y es la evidencia que cierra la ficha:
> **«AVISO SÍSMICO · UMBRAL INSTRUMENTAL»** con **«EDGE · RS4D · SOLO AVISO, SIN ACTUACIÓN»**
> debajo, **en ÁMBAR y no en rojo** (`data-authorizes="false"`), y **sin la palabra
> «PROTÉJASE»**, que aquí sería prometer una actuación que la política prohíbe. Hazle una
> captura.
>
> El software está desplegado y comprobado —la cadena es `alertHeadline.ts`, tres pruebas la
> defienden y el bundle servido contiene la cadena—; lo que falta es la observación.

---

## Acto 3 · El pulso del WR-1

**Qué se hace.** Activar el radio WR-1. El contacto seco cierra el GPIO del gabinete.

**Qué tiene que pasar, y en qué orden:**

1. **La sirena suena** — reflejo local, sin pasar por la nube ni por la red.
2. **La consola abre un incidente** con origen `sasmex`.
3. **El teléfono suena con la pantalla apagada** y abre la pantalla de crisis.

**Cómo se acredita, con el reloj corriendo:**

```bash
# En otra terminal, ANTES de tocar el radio:
AWS_PROFILE=takab-dev bash deploy/demo/guion.sh --check
```

Espera el pulso y afirma las cuatro cosas: incidente `sasmex` **nuevo** (los de antes no cuentan),
la fase que deriva la app (`alert_active`), los relés accionados según el propio gabinete, el acta
del reflejo con su latencia, y que el aviso al teléfono salió de verdad (`sent`, no `simulated`).

**En el Pixel**, con `screenrecord` corriendo para tener el tiempo pulso→crisis:

```bash
adb shell screenrecord --time-limit 60 /sdcard/acto3.mp4 &
# …pulso del WR-1…
adb pull /sdcard/acto3.mp4 acto3.mp4
```

> El teléfono es **personal**: los volcados de pantalla se filtran al paquete de la app
> (`com.takab.ailert`). `uiautomator` **no sirve** en la pantalla de crisis —redibuja el
> cronómetro cada segundo, nunca queda en reposo y falla en silencio—; usa `maestro hierarchy`.

---

## Entre el acto 3 y el acto 4 · **la sacudida se concluye SOLA (y cómo comprobarlo)**

**Ya no hay paso manual** — `T-7.30`, cerrada el 2026-09-13. El gabinete publica la transición de
nivel y la ingesta la persiste en `rule_evaluations`, que es de donde la app deriva «sacudida
concluida». El cierre llega **cuando el suelo lleva `episode_quiet_s` en calma** (90 s de fábrica)
y **nunca con la alerta enclavada**: si dejas el WR-1 pulsado o el enclavado puesto, el teléfono
sigue —correctamente— en crisis.

Lo que se ve en la demostración: tras el pulso el teléfono muestra la instrucción; minuto y medio
después de soltar el radio pasa a «sacudida concluida» con el reingreso **todavía bloqueado**, que
es lo que abre el acto 4.

**Antes de la sesión, comprueba que el gabinete lleva la versión con el arreglo** — si corre una
anterior, el teléfono se queda contando igual que el 2026-09-12:

```bash
ssh takab-pi5 'journalctl -u takab-edge -n 200 | grep -c tier_transition'   # > 0 tras un episodio
```

Si por lo que sea hiciera falta forzarlo (gabinete viejo, ensayo sin radio), el arnés sigue ahí:

```bash
AWS_PROFILE=takab-dev bash infra/scripts/seed_staging_incident.sh conclude
```

Y dilo en voz alta delante del cliente, porque se ve: **durante la alerta el brigadista tampoco
puede trabajar** — su teléfono enseña la instrucción, no las pestañas. Desde `T-7.29` tiene un
botón para salir de esa pantalla, con una franja roja que le recuerda que la alerta sigue viva.

---

## Acto 4 · Después de la sacudida

**Qué se enseña, en este orden:**

1. **«Se está haciendo el dictamen»** — la consola declara que está analizando, no finge un
   resultado.
2. **El brigadista** entra en el táctico desde su teléfono y levanta el reporte de daños con foto.
3. **El inspector firma** el dictamen en la consola.
4. **El reporte** se genera con los datos y las imágenes recogidas.

**Cómo se acredita el reporte:**

```bash
AWS_PROFILE=takab-dev bash deploy/demo/guion.sh --reporte
```

No se conforma con que exista una fila: **baja el PDF y cuenta las imágenes que lleva dentro**. Un
reporte sin imagen es un reporte que no enseña nada, y eso no se ve mirando la lista de evidencias.

Los dos flujos de Maestro que cubren esta parte:

```bash
mobile/.maestro/run.sh 01a-crisis.yaml
mobile/.maestro/run.sh 03-dictamen-liberacion.yaml
```

---

## Limpieza — **parte del guion, no del después**

```bash
curl -X POST http://<ip-del-gabinete>:8080/api/reset          # suelta el enclavado
AWS_PROFILE=takab-dev bash infra/scripts/seed_staging_incident.sh reset   # cierra el incidente
```

Y en la consola: **clasificar el incidente como `prueba`**. Sin esto queda contando como un sismo
real en las métricas del sitio, que es exactamente la clase de dato sucio que el sistema promete
no tener.

---

## Registro

**Ensayo completo del 2026-09-12/13 · con el WR-1 real, el gabinete de Puebla y el Pixel 8 Pro.**
Preflight previo: **13 ✓ · 0 • · 0 ✗**.

| Acto | Qué se midió | Resultado |
|---|---|---|
| **1 · SOC en reposo** | panel del gabinete | nivel `normal` · relés `siren` y `strobe` en reposo · nube en línea, RTT **71 ms**, cola 0 · **36 757** paquetes SeedLink con **0 huecos** |
| **2 · Movimiento aislado** | 88 muestras en 90 s | nivel `normal → restricted → evacuate_or_hold` · el golpe midió **0,357 g** en el canal vertical (el máximo de 24 h de ENZ pasó de 0,0036 g a 0,357 g) · incidente `local_threshold` en la nube · **NINGÚN relé se movió** |
| **3 · Pulso del WR-1** | `guion.sh --check` + 240 muestras del panel + registro del teléfono | **6 ✓ · 0 ✗** · SASMEX activo a las 20:59:40.792 · relés `siren` **y** `strobe` accionados · **acta del reflejo: 4,96 ms** (presupuesto 100 ms) · incidente `sasmex` en la nube y fase `alert_active` · push entregado (`sent`) |
| **3 · El teléfono** | pantalla **apagada y bloqueada** | `isLockScreen:true isScreenOn:false` en el instante de la entrega · la app estaba **congelada** por Android y el aviso la descongeló · aviso pintado a las 20:59:43.069 ⇒ **≈ 2,3 s desde el pulso** · canal **`seismic_alert_v2`** (el que salta el No Molestar) |
| **4 · Brigadista** | flujo `02` en el Pixel real | foto forense con marca horneada y reporte de daños · **4 fotos** llegaron a la nube con su SHA-256 en la cadena de custodia |
| **4 · Inspector** | consola, con MFA | dictamen firmado a las 04:28:52Z: `normal_operation`, **sucediendo** al preliminar · push OPS entregado **en el mismo segundo** por el canal `ops` · fase `reentry_approved` · el teléfono leyó el dictamen **35 s después**, solo |
| **4 · Reporte** | `guion.sh --reporte` + render | PDF de 4 páginas · **el SHA-256 del fichero coincide con el que el sistema registró** en su cadena de custodia |

### Acreditación posterior · **la sacudida se concluye sola** (2026-09-14)

Lo que el 12-sep hubo que forzar por SQL. Con `T-7.30` desplegada (nube `41ccc36`, gabinete
`20260914T070224Z-41ccc36`) y un **segundo pulso real del WR-1**:

| Instante (UTC) | Qué |
|---|---|
| `07:13:33.696` | el motor sube `normal → evacuate_or_hold` por el WR-1 |
| `07:13:34.004` | **fila en `rule_evaluations`**: `normal → evacuate_or_hold`, `sasmex`, episodio `feb1993ab…` |
| `07:13:34.035` | el motor devuelve `normal` **339 ms después del pulso** — y esa transición **NO se publica** |
| `07:13:34.14` | incidente `sasmex` · `critical` · `opened_trigger = sasmex` · push y correos `sent` |
| `~07:17:13` | se cancela la alerta: **el enclavado suelta y solo entonces arranca el reloj** |
| `07:18:43.496` | **fila de cierre**: `evacuate_or_hold → normal`, **mismo episodio** `feb1993ab…` |

Fase que deriva la app en ese punto: **`shaking_concluded`**, con el reingreso todavía bloqueado.
DLQ de eventos a **0** — la ingesta reconoce el contrato nuevo. **Dos filas, no tres**: el `normal`
de los 339 ms habría sacado al ocupante de «EVACÚE» antes de la onda S, y es justo lo que la
asimetría del seguidor de episodio impide.

**Flujos de Maestro, en el Pixel real:** `01a-crisis` re-acreditado · `02-tactico-foto-danos` en verde ·
**`03-dictamen-liberacion` acreditado por primera vez desde que se escribió** (no cargaba: llevaba un
`timeout:` dentro de un `assertVisible` y Maestro rechazaba el fichero entero).

### Lo que este ensayo NO midió, y hay que decirlo

- **El tiempo pulso → pantalla de crisis.** Se midió pulso → **aviso** (≈ 2,3 s). Cuando llegó el
  push el teléfono estaba **sin sesión**, así que la pantalla de crisis se comprobó después de
  entrar: «ALERTA SÍSMICA SASMEX · EVACÚE AHORA · ZONA PB-A · FUENTE · SASMEX WR-1». Para el
  ensayo con cliente, **el ocupante tiene que estar dentro de la app antes de empezar**.
- **La firma del dictamen se repitió tres veces.** El sistema hace lo correcto —generar el reporte
  **no** firma, la bitácora lo separa— pero la §9 del PDF acaba mostrando tres filas `FIRMADO`
  idénticas. Ante un cliente eso invita a preguntar por qué. **Firmar una vez y regenerar las
  veces que haga falta.**
- **Hubo que concluir la sacudida a mano** (`seed_staging_incident.sh conclude`) para que el
  teléfono saliera de la crisis. No es un tropiezo del ensayo: es el defecto `T-7.30` —la nube no
  recibe las transiciones de nivel—, y hasta que se cierre ese paso es parte del guion.
  **CERRADO el 2026-09-13**: el gabinete publica ahora la transición y la ingesta la escribe. El
  cierre exige silencio sostenido y no ocurre con el enclavado puesto — a propósito: publicar el
  `normal` crudo habría sacado al ocupante de «EVACÚE» un segundo después de la alerta, antes de
  la onda S.

### Evidencia

Los cuatro PDF generados durante el acto 4 están versionados en
[`evidencia/`](evidencia/) — cada uno es el «antes» de una corrección: el primero sin firma, el
segundo con la firma y el encabezado aún diciendo PRELIMINAR, el tercero ya coherente, y el cuarto
(`20260914T033755Z`) el que se barrió entero buscando la misma clase de defecto — de ahí salieron
las 19 contradicciones de `T-7.34`.

