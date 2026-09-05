# Runbook · Alta de una cámara de CCTV — **se repite en CADA gabinete**

> **Ficha:** [`T-3.11`](../TASKS.md) / [`T-3.12.d`](../TASKS.md) · **Decisiones:** [`D-24`](../DECISIONES-MAURICIO.md#d-24), [`D-25`](../DECISIONES-MAURICIO.md#d-25), [`D-26`](../DECISIONES-MAURICIO.md#d-26)
> **Dueño:** quien instala · **Duración:** ~40 min por cámara, más una prueba con gente
>
> **Esto no es la puesta en marcha del primer gabinete: es lo que hay que hacer CADA VEZ.**
> Una cámara nueva en un sitio ya vivo vuelve a empezar por el paso 1.

---

## Por qué existe este documento

El software del CCTV está construido y probado, pero **hay cosas que ningún test puede
sustituir** porque dependen de dónde acabe atornillada la cámara. Este runbook las enumera y
—más importante— dice **cómo se comprueba cada una**, porque el modo de fallo de todas ellas
es el mismo y es el peor: **no dan error, dan un número**. Un aforo corrido, un reingreso
fechado mal, un cero que parece un punto de reunión vacío.

> ### La regla que gobierna el documento entero
> **Ninguna casilla se marca por haber hecho el ajuste. Se marca por haber visto el efecto.**
> Poner el huso horario en la pantalla de configuración no es ponerlo en hora: ponerlo en hora
> es ver el sello correcto **quemado en un fotograma**. Los dos son cinco minutos; solo uno de
> ellos sirve de algo.

---

## 0 · Antes de subir la escalera

- [ ] **El CCTV de este gabinete está autorizado a encenderse.** De fábrica está apagado
      ([`D-25`](../DECISIONES-MAURICIO.md#d-25)) y no se enciende hasta que `G-04` esté
      acreditado **en este sitio** y la medición de `B.2` esté hecha. Sin eso, se instala el
      hardware y se deja el software apagado — que es un desenlace legítimo y hay que decirlo
      en el acta.
- [ ] **Hay aviso de videovigilancia visible** en el área. No es burocracia: es la base de que
      la evidencia sirva. Y el aviso **no menciona audio**, porque no se graba
      ([`D-26`](../DECISIONES-MAURICIO.md#d-26)).
- [ ] **La cámara es de las que sabemos manejar**: ONVIF Profile S, RTSP. Si no habla ONVIF,
      hace falta declarar su URL a mano (paso 4) y se pierde la revisión del reloj.

---

## 1 · El montaje — **el ángulo es una decisión técnica, no estética**

Es el paso que más condiciona todo lo demás, y el único que cuesta caro rehacer.

### Elige **picado**, no cenital

| montaje | qué se ve | qué le pasa al detector |
|---|---|---|
| **`picado`** ✅ | el cuerpo entero, desde arriba y de lado | **es el caso bueno** |
| `frontal` | el cuerpo a la altura de la vista | funciona, pero la gente se tapa entre sí |
| `cenital` ⚠️ | cabeza y hombros, a plomo | **el detector pierde mucho** |

> **La razón del aviso sobre el cenital, sin adornos.** Los modelos que usamos —YOLOX, y
> cualquier otro entrenado con COCO— aprendieron «persona» de fotos hechas por personas: casi
> todas a la altura de los ojos. Una vista a plomo es una silueta que ese entrenamiento
> apenas vio, y **no lo vamos a arreglar entrenando por sitio**: la decisión del proyecto es
> que un gabinete nuevo no exige reentrenar nada.
>
> Así que la mitigación es el montaje: **inclina la cámara hasta que se vean los cuerpos**, no
> solo las cabezas. Un picado de unos 20°–40° respecto a la horizontal suele bastar y sigue
> reduciendo que unas personas tapen a otras, que es lo que se buscaba con el cenital.
>
> Si el sitio **obliga** a cenital —techo bajo, no hay dónde más—, sigue adelante, declara
> `cenital` en el paso 4 y **da por hecho que el paso 7 va a salir peor**. Anótalo en el acta:
> es una limitación del emplazamiento, no un defecto del software.

- [ ] Altura y ángulo elegidos; **se ven cuerpos, no solo coronillas**.
- [ ] El **punto de reunión completo** entra en el encuadre. Lo que queda fuera no se cuenta,
      y nadie se entera de que faltaba.
- [ ] **A contraluz no.** Una ventana o una luminaria de frente convierte a la gente en
      siluetas negras y hunde la confianza del detector.
- [ ] Anota el **montaje elegido** (`frontal` / `picado` / `cenital`): hace falta en el paso 4.

---

## 2 · Red

- [ ] **IP fija o reserva DHCP.** La cámara se declara por dirección; si cambia, el gabinete
      deja de grabar y lo dice, pero deja de grabar.
- [ ] Anota **IP, puerto ONVIF** (suele ser el 80) y **puerto RTSP** (554).
- [ ] La cámara **no necesita salir a internet**. Si tu red se lo permite, mejor que no.

---

## 3 · El reloj — **el paso que más barato es y más caro sale**

La cámara **quema la hora en los píxeles**, y esas capturas van al dictamen con su `sha256` y
su cadena de custodia. Un sello que contradice la fecha del incidente hace que el paquete de
evidencia se contradiga a sí mismo.

> **Esto no es hipotético.** La primera cámara del proyecto llegó con el huso de fábrica del
> fabricante (`GMT+08:00`). El gabinete fechaba las **11:57 del 30 de agosto** y la foto decía
> **01:57 del 31**: catorce horas y un día distinto.

- [ ] **Huso horario del sitio** (para México central, `GMT-06:00`).
- [ ] **NTP encendido**, si la cámara lo permite. Sin NTP el reloj deriva y el desfase vuelve
      solo. Ojo: **hay cámaras que no lo exponen** ni por ONVIF ni por web —las de consumo se
      administran desde su app—; si es el caso, anótalo y prevé re-ponerla en hora.
- [ ] **Comprobado en el SELLO**, no en la pantalla de configuración: toma una captura y lee la
      hora impresa en la imagen.

```bash
# Lo que dice la cámara de su propio reloj, y lo que el gabinete opina de ello
python - <<'PY'
from takab_edge.cctv.onvif import reloj_de, revisar_reloj
from datetime import UTC, datetime, timedelta
r = reloj_de("<IP>", 80, "<usuario>", "<clave>")
off = datetime.now().astimezone().utcoffset() or timedelta(0)
for h in revisar_reloj(r, datetime.now(UTC), off.total_seconds()):
    print("HALLAZGO:", h)
PY
```

`takab-cctv` corre esta misma revisión al arrancar y **avisa sin impedir grabar**: el vídeo es
bueno aunque el rótulo mienta, y negarse a grabar cambiaría un rótulo torcido por un incidente
sin vídeo.

---

## 4 · Declarar la cámara en el gabinete

Credenciales **solo por entorno**, nunca en un fichero que se sincronice o se persista — una
URL con usuario y clave es una fuga que **ningún detector de PII del proyecto reconoce**.

```bash
# /etc/takab/edge.env
TAKAB_EDGE_CCTV__ENABLED=true          # solo si el paso 0 lo autorizó
TAKAB_EDGE_CCTV__HOST=192.168.x.y      # descubrimiento por ONVIF
TAKAB_EDGE_CCTV__ONVIF_PORT=80
TAKAB_EDGE_CCTV__PERFIL=substream      # ver el aviso de abajo
TAKAB_EDGE_CCTV_USER=<usuario>         # SOLO entorno
TAKAB_EDGE_CCTV_PASS=<clave>           # SOLO entorno
TAKAB_EDGE_CCTV_KEY=<clave del grant>  # sin ella se graba y se acumula, no se sube
```

- [ ] `uv sync` **con el extra `cctv`** en la máquina que corre `takab-cctv`
      (`EDGE_EXTRAS` en `deploy/edge/deploy.sh`). **`uv sync` poda**: no decidir es desinstalar.
- [ ] **ffmpeg LGPL** en `/opt/takab/bin/ffmpeg` — variante `linuxarm64-lgpl` en el Pi. Ver
      [`PENDIENTES §3.3.a`](../PENDIENTES-MAURICIO.md).
- [ ] Arranca `takab-cctv` y **lee el journal**: las cinco comprobaciones dicen en voz alta qué
      encontraron.

> ### ⚠️ El perfil decide la resolución del conteo, y el goteo no la hereda
> `substream` es el defecto y en cámaras típicas son **640×480**. El conteo de la nube va a
> ocurrir sobre eso. Y hay un detalle que sorprende: **el endpoint de instantánea puede estar
> clavado a la resolución baja aunque le pidas el perfil principal** — medido en la primera
> cámara. Como el goteo es lo único que fecha el **reingreso**, su resolución **no sube
> cambiando `perfil`**. Si en el paso 7 el conteo no aguanta, la salida no es tocar esta
> variable: es acercar o reencuadrar la cámara.

---

## 5 · La zona de conteo

El aforo puede contar **todo el encuadre** o solo un polígono. Con el punto de reunión llenando
el cuadro, sin zona basta; si entra un pasillo por el que la gente solo pasa, el polígono evita
contar tránsito como permanencia.

- [ ] Decidido: **con zona** o **sin zona**.
- [ ] Si lleva zona, el polígono en coordenadas **normalizadas** `[[x,y],…]` con `x`,`y` en
      `0..1`, y **guardado junto al acta del sitio**.

> ### ⚠️ Hueco conocido: la zona y el montaje **no tienen columna en la base**
> Hoy `cameras` no guarda ni el polígono ni el montaje: viajan como parámetros
> (`--zona`, `--montaje`) del analizador. Mientras eso siga así, **el acta del sitio ES la
> fuente de verdad** y hay que guardarla donde no se pierda. Está fichado; no lo resuelve
> este runbook.

---

## 6 · Privacidad y retención

- [ ] Aviso de videovigilancia **colocado y fotografiado** (la foto va al acta).
- [ ] **Sin audio**, y verificado — no basta con confiar:

```bash
ffprobe -v error -show_entries stream=codec_type -of csv=p=0 <un-segmento>.mp4
# tiene que decir `video` y NADA MÁS
```

> El anillo lleva `-an` por [`D-26`](../DECISIONES-MAURICIO.md#d-26). Se comprueba igual,
> porque `-c copy` **no copia el vídeo: copia lo que la cámara mande**, y así fue como el audio
> entró sin que nadie lo decidiera.

- [ ] La retención de vídeo del sitio está declarada y el cliente la conoce.

---

## 7 · La prueba con personas — **la única que acredita el sitio**

Ninguno de los pasos anteriores demuestra que se cuente bien **aquí**. Esto sí, y sin esto el
sitio **no está dado de alta**.

### 7.a · Control positivo

- [ ] Una persona camina despacio por la zona mientras tomas capturas cada pocos segundos.
- [ ] Corre el analizador y comprueba que da **1**:

```bash
python -m takab_cctv --stills <dir> --t0 <instante> \
  --detector onnx:<ruta-al-modelo>.onnx --ffmpeg /opt/takab/bin/ffmpeg \
  --ancho <W> --alto <H> --montaje <picado|cenital|frontal>
```

> Si sale **0** en todos los fotogramas, **no concluyas que el detector no sirve**: comprueba
> primero que el modelo es el que crees y que la entrada le corresponde. Un decodificador mal
> emparejado devuelve cero **sin lanzar**. El propio código lo caza —`ValueError: no le
> corresponde a este modelo`—, pero solo si el número de anclas no cuadra.

### 7.b · Control negativo, y es el que la gente se salta

- [ ] Con la zona **vacía**, toma una decena de capturas y comprueba que da **0** de forma
      sostenida.

> ### El fantasma que vas a encontrar
> En la primera cámara, el falso positivo fue **una sudadera colgada de una silla**: hombros y
> torso a la altura correcta, `0.36` de confianza contra un umbral de `0.35`. **2 de cada 12
> fotogramas** traían un fantasma.
>
> En un punto de reunión hay mochilas, chamarras, sillas y percheros. **Este modo de fallo no
> es una rareza: es el modo de fallo.** Y un aforo inflado exagera la evacuación, que es
> exactamente lo que hace que un reporte deje de creerse.
>
> **Qué hacer:** retira de la zona lo que puedas, y si el fantasma persiste **anótalo en el
> acta con su confianza**. Ese número es el que permite decidir después si a este sitio le hace
> falta un umbral propio — decisión que hoy no está tomada y que no se toma en la escalera.

### 7.c · Varias personas

- [ ] Tres o cuatro personas juntas y separadas. Anota **conteo real contra conteo del
      sistema** en cada caso. Con gente muy junta el conteo baja: es esperable, y saber
      *cuánto* baja aquí es la mitad del valor de esta prueba.

---

## 8 · Acta del sitio — lo que queda escrito

Sin esto, la próxima persona que toque este sitio empieza de cero.

| Dato | Ejemplo |
|---|---|
| Sitio, gabinete y nombre de la cámara | `Puebla-01 / gw-dev-0001 / reunión-norte` |
| IP, puerto ONVIF, perfil y resolución real | `192.168.3.132 · 80 · substream · 640×480` |
| **Montaje declarado** | `picado` |
| Resolución del **goteo** (puede no ser la del perfil) | `640×480` |
| Zona de conteo | `sin zona` o el polígono |
| Modelo y umbral usados | `yolox_nano · 0.35` |
| **Resultado de 7.a / 7.b / 7.c** | `1/1 · 2 de 12 con fantasma (0.36, sudadera) · 4→3` |
| Reloj: huso y si tiene NTP | `GMT-06:00 · sin NTP (la cámara no lo expone)` |
| Foto del aviso de videovigilancia | adjunta |
| Limitaciones del emplazamiento | `contraluz por la tarde` |

---

## Resumen: lo que este runbook existe para impedir

| Se salta… | Y el sistema… |
|---|---|
| el ángulo (paso 1) | cuenta de menos, **y nadie lo nota** |
| el reloj (paso 3) | produce evidencia que se contradice sola |
| el control **negativo** (7.b) | cuenta chamarras como personas |
| el acta (paso 8) | obliga a repetirlo todo la próxima vez |

Los cuatro fallan **hacia un número**, no hacia un error. Por eso se comprueban a mano, una vez
por gabinete, y por eso cada casilla pide **ver el efecto** y no haber hecho el ajuste.
