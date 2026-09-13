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

Una fila por ensayo. La captura de cada acto va al directorio de evidencia de la sesión.

| Fecha | Duración | Acto 1 | Acto 2 | Acto 3 (pulso→crisis) | Acto 4 | Incidente | Notas |
|---|---|---|---|---|---|---|---|
| _(pendiente)_ | | | | | | | preflight en verde el 2026-09-12: 13 ✓ · 0 ✗ |

> El preflight se corrió contra el sistema real el **2026-09-12** —gabinete en `192.168.3.140`,
> nube en `cd70e67`, Pixel enrolado— y salió **13 ✓ · 0 • · 0 ✗**: los cuatro actos se pueden
> ejecutar. Lo que falta es la sesión con el radio, que es física.
>
> Ese mismo día se ensayó en seco lo que no necesita el radio:
>
> - **`--check` contra el sistema real**, con el incidente abierto por el arnés de staging: cazó
>   el incidente, derivó la fase de la app y confirmó el push entregado — y marcó en ✗ los relés,
>   que es **lo correcto**, porque nadie tocó el radio. Esa es justo la diferencia entre una
>   demostración que funciona y una que lo parece.
> - **Los dos flujos de Maestro del acto 4**, en el Pixel real: `01a-crisis.yaml` re-acreditado y
>   `03-dictamen-liberacion.yaml` acreditado **por primera vez** (llevaba desde que se escribió
>   sin cargar siquiera). La firma vino del arnés, no de un inspector en la consola: esa mitad
>   sigue pendiente del acto 4 en vivo.
