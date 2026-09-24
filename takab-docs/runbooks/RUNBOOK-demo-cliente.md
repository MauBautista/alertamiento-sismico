# Runbook · Demostración al cliente

> **Ficha:** [`T-7.07`](../TASKS.md) · **Plan:** [`PLAN-PROTOTIPO-FUNCIONAL §4 · F1`](../PLAN-PROTOTIPO-FUNCIONAL.md)
> **Dueño:** Mauricio · **Necesita:** el WR-1, el gabinete, el Pixel y una persona en la consola
> **Compañera:** [`GUIA-DEMOSTRACION-POR-ROLES.md`](GUIA-DEMOSTRACION-POR-ROLES.md) — el mismo
> ensayo mirado **por rol y por pantalla** en vez de por acto: qué abrir, quién eres en cada
> momento, qué tocas y qué NO puedes tocar. Úsala el día de la demostración; este documento
> es el que dice qué tiene que pasar y cómo se acredita.
> **Guion ejecutable:** `deploy/demo/guion.sh` — y desde `T-7.28`, el ensayo completo
> cronometrado con **`bash deploy/demo/guion.sh --full`**, que recorre los actos en orden,
> mide cada uno, le pregunta a la máquina si pasó lo que promete y saca la tabla del
> § Registro lista para pegar. **Sigue sin accionar nada:** lo físico lo hace la persona.

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
   **`reproduccion`** y cerrarlo, o quedará contando en las métricas del sitio como un sismo que
   no pasó.

   > ⚠️ **`reproduccion`, no `prueba`** — y hasta `T-7.28` este runbook decía `prueba` en dos
   > sitios. Las dos cierran el incidente y ninguna entra en la tasa de falsos positivos, así que
   > equivocarse **no se ve en ningún número**: se ve en lo que el historial dice que pasó.
   > `prueba` es mantenimiento o puesta en marcha; `reproduccion` es exactamente esto, una
   > demostración. El valor se creó en `T-7.14` (`D-33`) **porque una corrida de demostración no
   > cabía en las otras cuatro sin mentir**, y usar `prueba` tira esa distinción justo el día que
   > alguien audite el historial del sitio delante de un cliente.

Esto no es nuevo y no hay que re-descubrirlo: el **Bloque B** de
[`RUNBOOK-gate-hw-movil-y-voceo.md`](RUNBOOK-gate-hw-movil-y-voceo.md) ya lo dejó escrito con su
razón — *una alerta real es la única que abre incidente y dispara notificaciones; el modo prueba
del WR-1 arma el radio **sin publicar a la nube**, que es justo lo que rompe la prueba*. Ese
runbook obliga a avisar antes; este hereda la obligación.

**Y el dato que ordena todo lo demás:** de los cuatro actos, el único que **no se puede repetir en
frío** es el 3. Si el pulso sale mal —enclavado vivo, modo prueba armado, gabinete sin nube— hay
que resetear el gabinete y volver a empezar el acto, con el cliente delante. De ahí el preflight.

---

## Lo que NO debe decirse — **la lista viva**

> [`T-7.28`] El origen es la auditoría [`INFORME-V1-COMERCIAL §3`](../INFORME-V1-COMERCIAL.md),
> que **congela a propósito lo que encontró el 2026-09-02** y por eso no se edita. Ésta es su
> versión operativa: se lee antes de cada demostración y **sí se actualiza**, porque entre aquella
> fecha y hoy se cerraron las fases F1 a F6 enteras y **varias de sus trece filas razonan sobre
> cosas que ya no son verdad**. Una lista de advertencias que envejece hace el daño al revés: te
> deja pidiendo perdón por lo que ya funciona, delante del cliente.
>
> **Aquí ya no se teclea CUÁNTAS son, y ésa es la corrección del 2026-09-22.** Hasta hoy el
> preámbulo decía «**cinco** de sus trece filas» y el cierre «las **ocho** restantes». Cerraba en
> trece, así que la resta no delataba nada — pero el reparto estaba mal por los dos lados: la
> tabla de abajo tenía ya SEIS filas (y una de ellas, la del mini-ShakeMap, **ni siquiera sale
> del §3**), y entre «las ocho que siguen vivas **tal cual**» iba la de la IA, cuyo recambio
> —«la IA está construida y apagada»— este mismo documento acababa de declarar falso **cinco
> líneas más arriba**.
> Un censo que se lleva con un número acaba divergiendo de lo que cuenta. Desde hoy **las trece
> filas están enumeradas una por una** entre las dos listas de esta sección: si una no aparece en
> ninguna, es que nadie la ha mirado, y eso sí se ve.

### Lo que la auditoría prohibía y **ya se puede decir** (verificado el 2026-09-22)

| Antes se prohibía porque… | Qué cambió | Qué se puede decir hoy |
|---|---|---|
| en el panel del gabinete los botones de demo **mandaban órdenes reales** | `T-5.01` **cerrada** el 2026-09-02 | se puede enseñar el panel sin el miedo de entonces. **Aun así no toques botones delante del cliente**: el acto 2 vende justamente que nada se movió solo. |
| los sitios simulados eran **visualmente idénticos** a los reales | `T-6.04` **cerrada** el 2026-09-10: `SiteLabel` es la única forma de pintar un nombre de sitio y la marca DEMO llega a todo | se puede enseñar el mapa poblado. La marca la pone el componente, no la memoria de quien enseña. |
| la sección de espectro **salía vacía siempre** porque el worker que archiva la onda no estaba desplegado | `T-7.02` **cerrada** el 2026-09-12 (el worker corre en la nube) y `T-7.38/39` construyeron el espectrograma | el dictamen técnico trae el espectro cuando hay registro archivado. **Sigue sin llamarse «el espectrograma del sismo» a la ligera:** es del registro de ESTE edificio. |
| la magnitud y el epicentro **no se contrastaban** con ninguna fuente | `T-7.25` **cerrada** el 2026-09-21: consulta a USGS con procedencia y hora | se puede decir que el sistema consulta la fuente oficial tras el evento **y que registra qué preguntó y cuándo**. Lo que el sistema afirma sigue siendo lo que midió en el edificio. |
| no había mapa de sacudida — ⚠️ **esta fila NO sale del §3**: allí el mini-ShakeMap sólo aparece en el §5, y se anota para que no entre en el reparto de las trece | `T-7.24` **cerrada** el 2026-09-21 (mini-ShakeMap, `D-08`) | se puede enseñar el mapa por evento. **Y con él llega una prohibición nueva: la de abajo.** |
| «le llega una **notificación** al teléfono» estaba en simulado | **medido en el ensayo del 2026-09-22**: el aviso salió `sent`, no `simulated`; el ARN de FCM sale del terraform y la instancia lo trae | se puede decir que **la notificación a Android es real y se entrega con la pantalla bloqueada**. ⚠️ **iOS sigue en cero**: su *platform application* sólo se crea con la clave de firma de APNs. Y **SMS y WhatsApp siguen simulados** — esa mitad de la fila original no ha cambiado |
| *«La IA nos ayuda a decidir»* iba con el recambio **«la IA está construida y apagada»** | `T-7.26` **cerrada** el 2026-09-22 (`D-37`): encendida en la nube de desarrollo con `google/gemini-2.5-flash-lite`, y redactando prosa de verdad desde esa misma mañana | **del ❌ no se mueve nada: la IA jamás decide.** Lo que ya no se puede decir es el ✅: «está apagada» era prudente el 2026-09-02 y hoy es **falso dos veces** —está encendida y además redacta—. La frase buena es la de la tabla de abajo. **Esta fila estaba hasta hoy entre «las que siguen vivas tal cual»**, que es el daño al revés que esta sección existe para evitar |

### Las filas NUEVAS que F5 y F6 trajeron

| ❌ No decir | Por qué | ✅ Decir en su lugar |
|---|---|---|
| *«Así se sacudió su colonia / esta zona.»* (señalando los anillos del mini-ShakeMap) | Los anillos son **MODELADOS**, no medidos: salen de la ley de atenuación, no de sensores en esas manzanas. `D-08` separa a propósito tres capas que no se mezclan —OBSERVADO (puntos), MODELADO (anillos) y RESIDUO— y `SIN COBERTURA` es un estado, no un hueco. | *«Los puntos son lo que midieron sensores reales. Los anillos son un modelo de cómo se atenúa la sacudida con la distancia, y donde no hay sensores el mapa dice `SIN COBERTURA` en vez de rellenar. Cuantos más edificios, más puntos y menos modelo.»* |
| *«Las fotos del brigadista se quedan aquí.»* | **Falso desde `T-7.26/27`, y hoy la capa está ENCENDIDA en la nube**: si el despliegue tiene la redacción asistida puesta, la imagen del daño sale **fuera de México** hacia OpenRouter y el proveedor del modelo. | *«La fotografía del daño se envía a un proveedor de inteligencia artificial fuera de México para que describa el daño en el informe. Va **sin el sello**: la franja con la hora, la ubicación y el identificador del operador se tapa antes de salir, y el nombre y el teléfono no viajan. La app se lo dice al brigadista en la pantalla donde dispara.»* |
| *«La IA está apagada.»* | Lo estaba el 2026-09-02. **Hoy está encendida en la nube de desarrollo** (`T-7.26`, desplegada el 2026-09-21). La frase pasó de prudente a falsa. | *«La IA está encendida y redacta la prosa del informe. No decide nada: el objeto que produce **no tiene campo donde poner un veredicto**, y hay una prueba que se pone roja si alguien se lo añade. Cuando no puede redactar, el papel lo dice.»* |
| *«El informe siempre trae la prosa redactada.»* | La capa es **fail-open a propósito**: cualquier fallo degrada a determinista y lo declara. Prometer la prosa convierte una degradación honesta en un fallo a la vista del cliente. | *«Si la redacción asistida no contesta, el informe sale igual con el texto determinista y dice por qué. La evidencia nunca se queda sin emitir por un problema de la IA.»* |

### Lo que la auditoría prohibía y **sigue prohibido** (no se ha movido)

Éstas son las filas del [`INFORME-V1-COMERCIAL §3`](../INFORME-V1-COMERCIAL.md) **que no ha
tocado nadie**, enumeradas por su ❌ para poder contarlas de un vistazo contra las trece del
informe (las otras seis están en la tabla de «ya se puede decir»; la del mini-ShakeMap no cuenta
porque no sale del §3):

1. *«El sistema cierra la válvula de gas, retorna los ascensores y libera las puertas.»*
2. *«Si el gabinete se apaga, la sirena suena igual por hardware.»*
3. *«En cuánto tiempo le tardan en acusar sus brigadistas: aquí está el número.»*
4. *«Restauramos la base en menos de una hora, está medido.»*
5. *«El sistema cumple con la norma X.»*
6. *«Sus datos no salen de México / no los comparte con nadie.»*
7. *«Le programo el simulacro y suena solo a las 11:00.»*

Las dos que más cerca están de colarse en esta demostración, con su razón:

- *«Si el gabinete se apaga, la sirena suena igual por hardware.»* — **`G-04` sigue abierto desde
  el hito de la Fase 1.** La ruta eléctrica está diseñada y decidida; no está construida.
- *«El sistema cierra la válvula de gas, retorna los ascensores y libera las puertas.»* — en la
  unidad de referencia están cableados **sirena y estrobo**. Lo demás se acredita canal por canal
  en la puesta en marcha de cada inmueble.

**Y las dos MITADES que siguen prohibidas de filas que la tabla de arriba da por superadas.** Se
apuntan aquí porque son justo lo que se pierde al mover una fila entera de cubo:

- De *«Le llega un SMS / un WhatsApp / una notificación al teléfono»* sólo se ha caído la
  notificación, **y sólo en Android**: **SMS y WhatsApp siguen simulados**, e **iOS sigue en
  cero** hasta que exista la clave de firma de APNs.
- De *«La IA nos ayuda a decidir»* sólo se ha caído el ✅: **la IA sigue sin decidir nada**, por
  diseño, y hay una prueba que se pone roja el día que alguien le añada un campo de veredicto.

---

## Precondiciones — **el preflight es la precondición, no una lista que leer**

```bash
AWS_PROFILE=takab-dev bash deploy/demo/guion.sh --preflight
```

Sale `0` cuando **no hay ningún ✗**. Cada ✗ es algo que hace que la demostración falle **sin dar
un error a la vista**, que es justo lo que no se puede permitir delante de un cliente — y por eso
un ✗ **aborta** el ensayo de `--full` antes de que nadie toque el radio.

> ⚠️ **Aquí ponía «sale `0` solo si TODO está en orden», y era falso.** No todo lo que mira es un
> ✗: hay comprobaciones que salen en **ámbar (`•`)**, y el ámbar **no cambia el código de salida
> ni detiene nada** — en `deploy/demo/guion.sh`, `aviso()` incrementa `AVISOS` y no `ROJOS`, y
> `full()` sólo aborta con `[ "$ROJOS" -gt "$ACTO_R0" ]`. La columna del medio dice cuál es cuál,
> porque la diferencia es exactamente lo que se ve o no se ve con el cliente delante.

| Lo que mira | Si está mal | Por qué, si está mal, no se nota |
|---|---|---|
| modo prueba del WR-1 **desarmado** | ✗ | armado, el pulso se queda en el gabinete: suena la sirena y **no publica a la nube**. La consola sigue en reposo y parece que el radio no llegó |
| sin **enclavado** vivo | ✗ | enganchado de la prueba anterior, el acto 3 no se distingue del acto 2 |
| **relés en reposo** y cadena sana | ✗ | con un relé ya accionado, el acto 2 no puede enseñar «nada se movió» |
| **sin simulacro** en curso | ✗ | la consola pintaría la franja de simulacro encima de la demostración |
| el gabinete **ve la nube** | ✗ | habría sirena y **ningún incidente** en la consola |
| algo que **suene** (relé de sirena o voceo) | ✗ | el acto 3 no se oiría. El `•` de esta fila no es un fallo: **declara** que el voceo por el jack está encendido y que va a sonar por el altavoz del gabinete |
| **modo demostración apagado** ([`D-27`](../DECISIONES-MAURICIO.md)) | ✗ | suprime comandos firmados y avisos, y todo contesta `201` igual |
| **destinatarios propios** | ✗ · pero **`•`** si el sitio no tiene cascada | con terceros, la cascada le escribiría a alguien de fuera un correo que dice ALERTA SÍSMICA. **Sin cascada ninguna sale ámbar y no detiene**, y entonces el acto 3 no le escribe a nadie: si la cascada es parte de lo que se enseña, este `•` hay que tratarlo como un ✗ |
| **Pixel por USB, app instalada y token vivo** | ✗ | el teléfono no recibe nada aunque todo lo demás esté perfecto |
| **sin incidentes abiertos** en el sitio | **`•`** — avisa y **sigue** | el acto 4 trabajaría sobre el incidente viejo… **y el preflight sale `0` igual**. Junto con el de la cascada, es el ámbar que puede arruinar un acto entero, así que **léelo tú**: el guion no te va a parar por él |

> **La red.** El guion busca el gabinete en `192.168.1.0/24`, que es la red donde se va a
> **instalar** — y donde los dos dispositivos están desde el 2026-09-21: el cerebro en
> `192.168.1.142` (`raspberry-cerebro.local`) y el Shake en `192.168.1.141` (`rs.local`).
> **No hace falta decirle dónde mirar**: se le pregunta por NOMBRE y ahí se acaba el problema.
>
> Desde otra red —o si la resolución por mDNS falla— hay que darle la dirección a mano, y la del
> Pi **cambia por DHCP**:
>
> ```bash
> TAKAB_DEMO_PANEL_URL=http://<ip-del-pi>:8080 bash deploy/demo/guion.sh --preflight
> ```
>
> Para encontrarlo sin adivinar: `getent hosts raspberry-cerebro.local`, y si eso no resuelve,
> `ip neigh` lista los vecinos; contesta en el `8080`.

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

> ⚠️ **Con 2 minutos de calma después del acto 2** (desde que el panel volvió a `normal`). El
> gabinete cierra el episodio tras 90 s sin movimiento (`T-7.49`); antes de eso, el WR-1 hereda
> la identidad del golpe y la nube ESCALA el incidente del acto 2 en vez de abrir uno SASMEX.
> Pasó en el ensayo 2, con 81 s: ver el Registro. `guion.sh` lo avisa y, si pasa, lo diagnostica.

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

⚠️ **El arnés YA NO SIRVE PARA ESTO, y son dos razones.** La primera es que dejó de hacer falta:
`T-7.30` hizo que la nube se entere sola de que la sacudida terminó (ver la nota del final de este
runbook). La segunda es que **desde `T-7.52` el arnés aborta contra el sitio de Puebla**: su sitio
por defecto es ahora el del arnés, y `guarda.sql` rechaza cualquier sitio que tenga un gabinete —
sin bandera que la salte. Correrlo aquí cerraba incidentes de operación, que es el defecto que
`T-7.51` destapó.

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

> ⚠️ **El paso 4 puede quedarse callado casi medio minuto, y desde hoy más que antes.** El tope
> de la redacción asistida subió de **8 s a 30 s** el 2026-09-22
> ([`D-37`](../DECISIONES-MAURICIO.md)) porque con 8 s el dictamen **con fotografías se cortaba
> siempre** —y es el único en el que alguien lee la prosa—. Con seis fotografías se midieron
> **13,7 s** de mediana y **20,6 s** el peor viaje (cinco muestras: el p95 y el máximo son el
> mismo dato, así que la cola no está caracterizada). Y **son DOS viajes bajo el mismo tope**, no
> uno: el catálogo de modelos, que se pide en **toda** exportación, y la generación; el catálogo
> se recuerda por proceso, así que **la primera exportación después de cada despliegue lo paga
> entero**.
>
> Dilo antes de que lo pregunten —*«está redactando el informe; tarda unos segundos»*—, porque
> treinta segundos de pantalla quieta con un cliente delante se leen como que se colgó. Si se
> pasa del tope, el papel **sale igual** con el texto determinista y **lo declara en su pie**:
> eso es el `Plan B · B3`, no un fallo.

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
curl -X POST -H "X-Takab-Pin: <PIN>" http://<ip-del-gabinete>:8080/api/reset   # suelta el enclavado (sin el PIN: 401; mejor el botón CERRAR ALERTA del panel)
```

Y en la consola: **clasificar como `reproduccion` TODOS los incidentes que abrió la corrida** (ver
el aviso de la cabecera: `prueba` también cierra, pero dice otra cosa). Eso es lo que los cierra, y
es la vía correcta: deja `closed_at`, escribe la acción y audita el verbo. Sin esto quedan contando
como sismos reales en las métricas del sitio, que es exactamente la clase de dato sucio que el
sistema promete no tener.

⚠️ **Son al menos DOS, y hasta hoy aquí ponía «el incidente», en singular.** Una corrida completa
abre el aviso instrumental del **acto 2** (`local_threshold`) **y** el pulso del **acto 3**
(`sasmex`): el ensayo del 2026-09-22 abrió exactamente esos dos y el § Registro sólo nombró el del
acto 3, así que el del acto 2 se quedó sin clasificar, contando como un evento instrumental real.
No se ve —nadie echa de menos un incidente que el guion nunca nombró— y `deploy/demo/guion.sh`
también lo dice en singular en su limpieza («clasifica el incidente»). **La lista no te la da el
guion: sácala de la cola del sitio en la consola** antes de dar la sesión por terminada.

> Si se te pasan, el TTL de revisión (`incident_review_ttl_s`, 6 h de fábrica) los cierra solos con
> causa `review_ttl`. La tabla es append-only, así que clasificarlos después sigue funcionando; lo
> que se pierde es la traza de que los cerró **una persona**, que es justo lo que se enseña cuando
> alguien audita el historial del sitio.

⚠️ **Aquí había un `seed_staging_incident.sh reset` y se quitó** (`T-7.52`). Ese arnés es de los
E2E móviles, no de la demostración, y cerraba **todos** los incidentes abiertos del sitio sin hora
de cierre — el defecto de `T-7.51`, cuyo síntoma era un dictamen pericial diciendo «EN CURSO» de un
incidente cerrado. Desde `T-7.52` abortaría de todas formas: el arnés no escribe sobre un sitio con
gabinete.

---

## Plan B · qué hacer cuando algo se cae **en medio**

> [`T-7.28`] Cuatro caídas, las cuatro medidas en este repositorio, con lo que sigue funcionando
> y la frase con la que se cuenta. **La regla que las gobierna a todas:** decirlo tú antes de que
> lo pregunten. Una demostración en la que se cae algo y el que la conduce lo nombra es una
> demostración de un sistema honesto; la misma caída descubierta por el cliente es otra cosa.

### B1 · Se cae internet

**Lo que sigue funcionando, y es lo que hay que enseñar:** todo lo que importa. Es la regla de oro
2 y no es una promesa, es la arquitectura: `SASMEX → relé` es 100 % local y **no pasa por la nube
ni por internet**, así que el acto 3 —la sirena— sale igual. El gabinete sigue detectando,
sigue accionando y sigue guardando.

**Lo que se cae:** la consola no ve nada nuevo, no hay aviso al teléfono y no hay PDF.

**Qué hacer:** llevar la demostración **al panel del gabinete**, que cuenta la historia entera sin
nube. El propio panel declara la caída (`cloud.online`, y `cloud.queued` con lo que lleva esperando
en la cola), o sea que el argumento se enseña **con la pantalla delante** en vez de contarse.

> «Acabamos de perder internet. Miren lo que NO se detuvo: el radio entró, el relé cerró y la
> sirena sonó, sin salir del edificio. Lo que está en pausa es la coordinación — el gabinete tiene
> N mensajes en cola y los va a entregar cuando vuelva la línea, sin duplicar ninguno, porque cada
> uno lleva su identificador.»

### B2 · No llega el aviso al teléfono

**Lo que sigue funcionando:** la app **en primer plano sondea sola**, y no es un apaño: en crisis
pregunta cada **5 s** (`CRISIS_POLL_MS`), la lista de brigada cada **15 s** y el panel cada **30 s**.
Con el teléfono desbloqueado y la app abierta, el acto 3 se ve igual.

**Qué hacer:** abrir la app **antes** del pulso y dejarla en pantalla. Y decir qué se perdió: lo
que no ocurrió es la entrega con la pantalla apagada, que es la mitad buena del acto.

> «Este teléfono ya tenía la app abierta. Lo que acaban de ver es el estado llegando por consulta.
> Lo que hoy no les puedo enseñar es el aviso entrando con la pantalla bloqueada — está construido
> y medido (2,3 s desde el pulso, el 12 de septiembre), pero hoy este aparato no lo recibió.»

### B3 · No hay IA

**Lo que sigue funcionando: el documento entero.** La capa narrativa **no decide nada** —no
clasifica, no firma, no cambia una alerta— así que sin ella el dictamen sale completo, con su
veredicto y todos sus números, sólo que con la prosa determinista.

**Y no hay que explicarlo: el papel lo dice.** Imprime `NARRATIVA DEGRADADA · <razón>`, y la
razón manda a mirar **TRES** sitios distintos — no dos, como decía este runbook hasta el
2026-09-22:

| Lo que imprime el pie del dictamen | Qué pasó | Dónde se mira |
|---|---|---|
| «el proveedor de redacción **no respondió** (`<excepción>`)» | no hubo respuesta: no llegó a contestar | la red, el cable |
| «el proveedor de redacción **no aceptó la clave** (`HTTP 401`)» | contestó, y lo que contestó es que la credencial no vale | permisos y cuota **en OpenRouter** |
| «redacción asistida encendida pero **la clave no se pudo leer** (`<código>`)» | **ni siquiera se salió a la red** | **dentro del secreto**, no en el proveedor |

La tercera es la que faltaba, y es justo la que mordió. Su código es **`ClaveSinForma`**: el
secreto trae `api_key`, pero su valor no tiene forma de clave — el marcador de posición
`sk-or-...` de la documentación, pegado tal cual. Por la misma rama salen **`SecretoSinApiKey`**
(el secreto se leyó y no trae `api_key`) y el código de AWS, p. ej. **`AccessDeniedException`**
(el rol no puede leer el secreto).

⚠️ **Por qué importa la distinción, con el hecho que la pagó.** Hasta `T-7.26` (2026-09-22) el
tercer caso salía **disfrazado del segundo**: el marcador de posición provocaba un 401 real de
OpenRouter y el papel decía «no aceptó la clave» — cierto, y apuntando al sitio equivocado. La
capa narrativa llevaba **desde el 2026-09-21 sin redactar un solo párrafo** y este runbook
mandaba a revisar permisos y cuotas del proveedor mientras el problema estaba dentro del secreto.
Y no lo delataban las dos superficies que deberían: el censo comprueba que el secreto **exista** y
que el rol pueda **leerlo**, no lo que hay dentro.

> «La redacción asistida no contestó, y el informe lo dice en su pie. Fíjense en lo que no cambió:
> el veredicto, la clasificación y las cifras son los mismos. La IA aquí redacta; no decide. Hay
> una prueba en el repositorio que se pone roja el día que alguien intente cambiar eso.»

### B4 · El mapa sale vacío (no cargan los tiles)

**Lo que sigue funcionando:** la consola cae a un **estilo local** (`FALLBACK_STYLE`) y el mapa se
dibuja sin depender de la red: los sitios, los anillos y el muro siguen ahí.

**⚠️ La trampa, medida en el código:** el respaldo **sólo entra si el estilo inicial NUNCA cargó**.
Un tile que falle a media sesión no borra el mapa ya dibujado —eso es deliberado—, pero tampoco
dispara el respaldo. O sea que si abres la consola con red y la pierdes después, el mapa se queda
como está; si la abres sin red, cae al respaldo solo.

**Qué hacer:** **abrir la consola antes de que entre el cliente.** Si el mapa aparece vacío,
**recargar** — es lo que engancha el respaldo. Nunca quedarse mirando a ver si vuelve.

---

## Registro

### Ensayo **1 de 2** · 2026-09-22 · corrida `20260922T180248Z` — `29 ✓ · 0 ✗`

**Primera corrida cronometrada de `guion.sh --full`** (`T-7.28`), con el WR-1 real, el gabinete
de Puebla y el Pixel. Preflight: **13 ✓**.

| Acto | Duración | Veredicto | Qué midió la máquina |
|---|---|---|---|
| 0 · Preflight | 0:07 | ✓ | 13 ✓ |
| 1 · El SOC operando normal | 0:59 | ✓ | nivel `normal` · relés en reposo · **135 910 paquetes / 0 huecos** |
| 2 · Movimiento aislado, SIN señal del WR-1 | 1:45 | ✓ | incidente `d5af54e5` · **0 actuaciones** |
| 3 · El pulso del WR-1 | 9:44 | ✓ | 6 ✓ · 0 ✗ |
| 4 · Después de la sacudida | 46:57 | ✓ | 3 ✓ · 0 ✗ |

> **De qué reloj son estas duraciones.** De la máquina que corrió `guion.sh --full`, y son
> tiempos de **representación**: cuánto se tardó en ejecutar cada acto delante de quien miraba.
> **No son latencias del sistema** — ésas las mide el propio sistema y están en las filas de
> abajo.

**Lo que el sistema midió de sí mismo:**

- **Acta del reflejo: 0,22 ms** (presupuesto 100 ms). ⚠️ El 2026-09-12 fueron **4,96 ms**, así
  que son **22× más rápido de un día para otro**. Pasa de sobra en los dos casos, pero una
  mejora de ese orden sin un cambio que la explique **merece una segunda medición antes de
  citarse ante un cliente**: si resultara un artefacto, es justo el número que luego nadie
  puede defender.
- **Relés `siren` y `strobe` accionados**, acusados por el propio gabinete.
- **La app derivó `phase=alert_active`** — la pantalla de crisis es lo que tocaba.
- **El aviso al teléfono salió `sent`, no `simulated`.** Ver abajo: esto cambia lo que se puede
  prometer.
- **PDF de 7 páginas con 2 imágenes distintas**, sobre un incidente con **1 fotografía** de
  brigada (`report-technical-20260922T185707Z.pdf`).

**Cronología que el panel conserva:**

```
18:04:53  normal → watch              (local_threshold)  ┐ acto 2
18:05:02  watch  → normal                                 │ dos golpes
18:05:03  normal → watch                                  │
18:05:08  watch  → normal                                 ┘
18:14:13  normal → evacuate_or_hold   (sasmex)            ← acto 3 · el pulso
18:14:13  evacuate_or_hold → normal   (local_threshold)
22:24:00  ACCIÓN reset (vía lan)
```

#### Lo que esta corrida enseñó, y hay que tener delante en la segunda

**⚠️ Dura una hora, y eso no cabe en una demostración.** 59 minutos en total, y **47 de ellos
son el acto 4** — la foto en el Pixel, el dictamen firmado en la consola y la generación del
PDF. Ningún cliente espera cuarenta y siete minutos. Para la presentación real hay que
**pre-cargar** parte del acto 4 (tener el reporte de daños ya subido y el incidente listo para
firmar) y enseñar en vivo sólo la firma y el PDF. El acto 3, que es el que vende, tardó **9:44**.

**⚠️ El acto 2 sólo llegó a `watch`, dos veces.** No a `restricted` ni a `evacuate_or_hold`. El
acto funcionó y abrió su incidente, pero el escalón es el más bajo: el ensayo del 2026-09-12
llegó a `evacuate_or_hold` con **0,357 g**. Si la demostración busca impacto, **el golpe tiene
que ser más seco** — y conviene ensayarlo antes, no descubrirlo con el cliente delante.

**⚠️ La limpieza se hizo a las 22:24**, más de cuatro horas después del pulso. El runbook dice
que es **parte del guion, no del después**. No rompió nada —el estado quedó correcto— pero un
enclavado vivo durante horas es exactamente lo que el preflight del día siguiente habría
cazado en rojo.

**✅ Y una buena que cambia la lista de «lo que NO debe decirse»:** el push llegó **`sent`**, no
`simulated`. El ARN de FCM sale del terraform y la instancia lo trae, así que **la notificación
a Android es real**. La fila de la lista que dice «le llega una notificación al teléfono» era
cierta como advertencia en septiembre y ha dejado de serlo para Android — iOS sigue en cero,
porque su *platform application* sólo se crea con la clave de firma de APNs.

**Pendiente de esta corrida — son DOS incidentes, no uno.** Esta línea decía «el incidente
`b420daaa`» y se quedaba corta: la corrida abrió también el del **acto 2**, que está en la tabla
de aquí arriba. Los dos seguían **`in_review` y SIN CLASIFICAR** el 2026-09-22. ✅ **Clasificados
los dos como `reproduccion` por Mauricio desde la consola** (lo confirmó el 2026-09-24):

| Incidente | De dónde salió | Cómo se clasifica |
|---|---|---|
| `d5af54e5-b01b-44b8-81e4-3851c71eb9f6` | acto 2 · `local_threshold` · `watch` | `reproduccion` |
| `b420daaa-84d1-4bf2-95d4-e328fc0ead92` | acto 3 · `sasmex` · `critical` | `reproduccion` |

> El TTL de revisión (6 h) los cierra solos con causa `review_ttl` si nadie llega antes.
> Clasificarlos después sigue funcionando —la tabla es append-only—, pero se pierde la traza de
> que los cerró una persona.

---

### Ensayo **2 de 2** · 2026-09-24 · acto 3 en ✗ **por el orden de los actos, no por una avería**

**Ensayo del 2026-09-24T20:07:28Z · corrida `20260924T195548Z`.**

| Acto | Duración | Veredicto | Qué midió la máquina |
|---|---|---|---|
| 0 · Preflight | 0:08 | ✓ | 13 ✓ |
| 1 · El SOC operando normal | 1:52 | ✓ | nivel normal · relés en reposo · 451244 paquetes/310 huecos |
| 2 · Movimiento aislado, SIN señal del WR-1 | 0:34 | ✓ | incidente 431c6fc9 · 0 actuaciones |
| 3 · El pulso del WR-1 | 2:06 | ✗ | 0 ✓ · 1 ✗ |
| 4 · Después de la sacudida | 7:00 | ✓ | 3 ✓ · 0 ✗ |

**Por qué el acto 3 salió en ✗** (del registro de transiciones del panel, `GET /api/status`):

| UTC | Transición | `event_id` |
|---|---|---|
| 19:58:00 | acto 2 · `normal → watch` (`local_threshold`, PGA 0,029 en `ENN`) | `39d73508…` |
| 19:58:02 | `watch → normal` | — |
| 19:59:23 | acto 3 · `normal → evacuate_or_hold` (**`sasmex`**) | **`39d73508…`, el MISMO** |

El WR-1 se pulsó **81 s** después de que el golpe volviera a `normal`, y el gabinete cierra el
episodio tras **90 s** de calma (`episode_quiet_s`, `T-7.49`): le puso al pulso la identidad del
golpe. La nube hace UPSERT por esa identidad y **escaló** el incidente del acto 2 (`431c6fc9`) a
SASMEX —severidad y disparador—, sin abrir otro ni cambiar su apertura. `--check` busca un
incidente `sasmex` ABIERTO después de empezar el acto, no lo encontró y cortó ahí: no llegó a medir
la fase de la app ni el push. **El Pixel sí mostró la crisis** (lo vio Mauricio).
Consecuencia: esta corrida dejó **un solo incidente**, `431c6fc9`, no dos.

**Lo que ese orden arrastra, y que un cliente vería** (del PDF
`evidencia/report-technical-20260924T200614Z-…pdf`, 7 páginas):

- **Sin push nuevo al escalar.** La cronología (§13) trae las notificaciones del golpe (19:58:00,
  correo y push) y ninguna a las 19:59:23. Con el teléfono bloqueado, el SASMEX no lo despierta.
- **La prosa de la IA atribuye la sirena al umbral local** y no nombra SASMEX; y afirma que el
  veredicto fue «operación normal porque el evento no fue originado por SASMEX» — una causa que no
  existe y que desmiente la portada («escaló a SASMEX»). Un lector concluiría que una estación sola
  acciona la sirena, que es justo lo que `T-2.32` prohíbe.
- Menores, del papel: el arribo «−2,6 s» (negativo, sin explicar), `pue-pruebas-01` encima de
  `site-dev` en el mapa de la red, la escala «0.0152355 km» del croquis, y fragmentos de UUID en
  QUIÉN (`OPERADOR a1ebe580`, `push:parallel:<uuid>`).

**Arreglado el mismo día, en el guion:** avisa de los 2 minutos antes del acto 3 y, si el pulso se
suma al incidente anterior, lo dice con esas palabras en vez de «el pulso no viajó (¿modo prueba
armado? ¿gabinete sin nube?)», que eran dos causas falsas (`test_guion_demo.py`). Lo demás es
producto y va a fichas después de la presentación.

#### Latencia del aviso, medida el mismo día · pulso → teléfono

«Cuando activo el WR-1 tarda en aparecer la alarma». Tres pulsos más (incidentes `12d89fef`,
`fae5691b` y el de las 23:46 UTC, **los tres clasificados `prueba`**), con el panel del gabinete, la
base y el log de Android del Pixel (reloj corregido: el Pixel iba +1,6 s):

| Tramo | Medido |
|---|---|
| pulso → incidente abierto en la nube | **0,23 s** |
| pulso → push y correos `sent` | **0,40 s** (las tres veces, 0,13–0,17 s tras abrir) |
| pulso → push **en el Pixel bloqueado** (canal `seismic_alert_v2`) | **1,4 s** |
| pulso → **suena** | **1,6 s** (`buzz=0`: sonido sí, vibración NO) |
| pulso → correo en Gmail | 4,4–6,3 s |

**Lo que hacía «tardar»: el Pixel no tenía push.** Sólo UN teléfono de Puebla tenía token (el Galaxy),
y la app, sin push, se entera por su poll: **5 s con incidente vivo, 30 s en reposo**. La causa es de
producto: el token FCM es del APARATO y la RLS `pt_self` (por `user_sub`) impide que el SIGUIENTE
usuario del mismo teléfono lo registre (`ON CONFLICT` → «new row violates row-level security
policy»); la app, best-effort, calla. Cambiar de rol en el Pixel lo dejaba sin push. Para hoy se
borró la fila vieja y el Pixel quedó registrado como el ocupante de Puebla: **no cambiar de usuario en
el Pixel antes del acto 3**. El arreglo de producto va después de la presentación.

**Y lo que el acto 3 NO hace hoy:** con la pantalla apagada, el teléfono suena y deja la notificación,
pero **no enciende la pantalla ni abre la crisis solo** (la pantalla se encendió a los 27 s porque se
tocó). La instrucción aparece al abrir la app. Dilo así: «suena y avisa en segundo y medio».

**CERRAR ALERTA perdía el segundo clic** (0 de 10 en Chromium): el panel recreaba sus botones en cada
fotograma mientras la orden estaba armada. Arreglado (PR #282, 10 de 10) y desplegado al gabinete el
mismo día; el cierre de las 23:48:37 UTC entró a la primera.

Lo que esta segunda corrida tenía que resolver, sacado de lo que enseñó la primera — y qué dio:

- [x] **El acto 4 no puede durar 47 minutos.** **7:00** en esta corrida, con el reporte de daños
      desde el Pixel, la firma del inspector y el PDF.
- [ ] **El golpe del acto 2 tiene que pasar de `watch`.** Sigue en `watch`: el panel registró
      PGA 0,029 en UN canal (`ENN`, «cautela en 1 sensor(es)»). La franja exige **dos canales**
      sobre el disparo: hay que golpear más seco y mirar `tier` en el panel antes de seguir.
- [~] **La limpieza va dentro del guion.** CERRAR ALERTA llegó entre 15 y 35 min después del pulso
      (a las 20:14 UTC seguía enclavada con la sirena energizada; a las 20:34, ya no), y el incidente de la corrida es UNO, `431c6fc9`
      (por la escalada del acto 3): ✅ **clasificado `reproduccion`** por Mauricio el mismo día.
- [x] **Segunda medición del acta del reflejo:** **0,18 ms** (`latencies.reflex_s` del panel tras
      el pulso, presupuesto 100 ms). Cuadra con los 0,22 ms de la corrida 1: el valor raro era el
      de 4,96 ms. Aun así se cita como «muy por debajo de 100 ms», no con decimales.
- [x] **Prosa redactada, no `NARRATIVA DEGRADADA`:** el PDF lleva `Narrativa: openrouter` y las
      seis secciones «REDACTADO CON ASISTENCIA DE IA». ⚠️ Pero en ESTA corrida la prosa atribuye
      la sirena al umbral local (ver arriba): la capa redacta, y redacta sobre un incidente mal
      formado por el orden de los actos.

---

### Ensayo completo · 2026-09-12/13

**Con el WR-1 real, el gabinete de Puebla y el Pixel 8 Pro.** Preflight previo:
**13 ✓ · 0 • · 0 ✗**.

> Esto era un párrafo en negrita y no un encabezado, porque hasta el 2026-09-22 era lo único que
> había en el § Registro y no hacía falta titularlo. Al insertarse encima la corrida 1, sus dos
> acreditaciones del 14 de septiembre quedaron colgando del ensayo de **hoy** —ocho días
> después— para quien navegue por encabezados. De ahí el título, y de ahí que lo que le sigue
> baje un nivel.

| Acto | Qué se midió | Resultado |
|---|---|---|
| **1 · SOC en reposo** | panel del gabinete | nivel `normal` · relés `siren` y `strobe` en reposo · nube en línea, RTT **71 ms**, cola 0 · **36 757** paquetes SeedLink con **0 huecos** |
| **2 · Movimiento aislado** | 88 muestras en 90 s | nivel `normal → restricted → evacuate_or_hold` · el golpe midió **0,357 g** en el canal vertical (el máximo de 24 h de ENZ pasó de 0,0036 g a 0,357 g) · incidente `local_threshold` en la nube · **NINGÚN relé se movió** |
| **3 · Pulso del WR-1** | `guion.sh --check` + 240 muestras del panel + registro del teléfono | **6 ✓ · 0 ✗** · SASMEX activo a las 20:59:40.792 · relés `siren` **y** `strobe` accionados · **acta del reflejo: 4,96 ms** (presupuesto 100 ms) · incidente `sasmex` en la nube y fase `alert_active` · push entregado (`sent`) |
| **3 · El teléfono** | pantalla **apagada y bloqueada** | `isLockScreen:true isScreenOn:false` en el instante de la entrega · la app estaba **congelada** por Android y el aviso la descongeló · aviso pintado a las 20:59:43.069 ⇒ **≈ 2,3 s desde el pulso** · canal **`seismic_alert_v2`** (el que salta el No Molestar) |
| **4 · Brigadista** | flujo `02` en el Pixel real | foto forense con marca horneada y reporte de daños · **4 fotos** llegaron a la nube con su SHA-256 en la cadena de custodia |
| **4 · Inspector** | consola, con MFA | dictamen firmado a las 04:28:52Z: `normal_operation`, **sucediendo** al preliminar · push OPS entregado **en el mismo segundo** por el canal `ops` · fase `reentry_approved` · el teléfono leyó el dictamen **35 s después**, solo |
| **4 · Reporte** | `guion.sh --reporte` + render | PDF de 4 páginas · **el SHA-256 del fichero coincide con el que el sistema registró** en su cadena de custodia |

#### Acreditación posterior · **el acto 2 en la CONSOLA** (2026-09-14) — con esto cierra `F1`

Lo único que le faltaba al acto 2: el 12-sep el ensayo se llevó desde el panel, la nube y el
teléfono, y nadie miró la consola. Se repitió con la consola delante, y **hicieron falta tres
golpes** porque la condición no es el pico de un canal sino la cuenta:

| hora UTC | qué hizo el gabinete | severidad | ¿franja en la consola? |
|---|---|---|---|
| 19:47:14 | `normal → watch → restricted` · disparo en **1** sensor (ENN) | `warning` | no |
| 19:53:11 | `normal → watch` · cautela en 1 sensor | `watch` | no |
| **19:56:40** | `normal → restricted → evacuate_or_hold` · **disparo confirmado por 2 sensores: EHZ, ENN** | **`critical`** | **sí, en ámbar** |

Pico del bueno: **EHZ 0.1265 g** a las 19:56:33. Incidente
`c7f31753-16dc-452b-8956-4f4b5e4a7ffb`, `local_threshold` en `trigger` y en `opened_trigger`, el
más reciente de la cola. **La bitácora de actuación quedó vacía: ningún relé se movió.**

Y el mismo episodio acreditó `T-7.30` sobre un evento **instrumental**, no solo sobre el WR-1:
`rule_evaluations` recogió la escalada y publicó el cierre a las **19:58:12**, 92 s después.

#### Acreditación posterior · **la sacudida se concluye sola** (2026-09-14)

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

#### Lo que este ensayo NO midió, y hay que decirlo

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

En [`evidencia/`](evidencia/) hay **TRES** PDF del acto 4, y son éstos:

| Fichero | Qué es |
|---|---|
| `report-technical-20260913T050713Z.pdf` | el dictamen firmado del acto 4, tal como salió |
| `report-technical-20260913T140829Z.pdf` | el mismo, ya con la firma y el encabezado corregidos |
| `report-technical-20260914T033755Z.pdf` | el que se barrió entero buscando la misma clase de defecto — de ahí salieron las 19 contradicciones de `T-7.34` |

⚠️ **Aquí ponía «los cuatro PDF» y enumeraba uno que no existe.** La enumeración empezaba por «el
primero sin firma», y ese fichero **nunca se comiteó**: sobre la carpeta, `git log --diff-filter=A`
da tres altas y `--diff-filter=D` no da ninguna baja. O sea que la §Evidencia prometía un rastro
que no se podía enseñar, que es el mismo defecto que el resto de este documento persigue: un censo
tecleado a mano que diverge de lo que hay.

**Y falta uno.** El PDF de la corrida 1 —`report-technical-20260922T185707Z.pdf`, el de 7 páginas
con 2 imágenes que cita el § Registro— **no está en el repositorio**. Hasta que se comitee, de esa
corrida sólo queda su fila en la tabla, y con ella no se puede afirmar si la prosa salió redactada
o degradada.

