# Bloque IV — arquitectura (mini-ShakeMap y CCTV)

> **Qué es este documento.** El diseño que [`D-08`](../DECISIONES-MAURICIO.md) encargó y que las
> propias fichas exigen **antes del código**: `T-3.09` dice «arquitectura escrita **antes** del
> código» y `T-3.10` **es** escribir la arquitectura.
>
> **Qué NO es.** No es una derogación ni una autorización para implementar. `D-08` autorizó
> **planificar**; la viñeta `[DIFERIDO · mini-ShakeMap]` de `BLUEPRINT §14` prohíbe **implementar**,
> y sigue en pie. Se deroga —por su nombre y solo ella— **al ejecutar `T-3.09`**, no aquí. Ver §0.
>
> **Estado:** diseño para revisión · **Fecha:** 2026-08-16 · **Fichas:** `T-3.09`, `T-3.10`

---

## 0 · La derogación: qué se toca y qué NO

`BLUEPRINT §14` mezcla dos clases de viñeta, y **la distinción es lo único que impide derogarlas
juntas**:

| Clase | Significa | Ejemplos |
|---|---|---|
| `[DIFERIDO · …]` | aplazada — **se puede retomar derogándola por su nombre** | `mini-ShakeMap` (la única) |
| `[INVARIANTE · …]` | prohibición — **se rechaza sin discusión** | T-MINUS, magnitud preliminar, **streaming crudo continuo**, IA en la ruta de disparo, tocar el Shake OS |

> ### ⚠️ La trampa, y por qué está escrita en tres sitios
> En `CLAUDE.md §8`, el mini-ShakeMap y el **streaming crudo continuo** comparten **una sola
> línea**; en `BLUEPRINT §14` son **viñetas contiguas**. Esa vecindad es exactamente cómo se
> derogan juntas por accidente — y la segunda es la **regla de oro 9**.
>
> **Al ejecutar `T-3.09`: partir el bullet de `CLAUDE.md §8`, no borrarlo.** Y derogar la viñeta
> del mapa **por su clave**, `[DIFERIDO · mini-ShakeMap]`.

**Y hay una guarda que se pondrá roja, a propósito.**
`test_cada_vineta_del_blueprint_14_declara_si_es_prohibicion_o_diferido` exige que §14 **mezcle**
las dos clases (`clases == {"INVARIANTE", "DIFERIDO"}`). Al derogar la única diferida, el conjunto
queda en `{"INVARIANTE"}` y **el test cae**. No es un daño colateral: su propio mensaje dice qué
hacer —«si de verdad ya no queda ninguna de las dos clases, este test sobra»—. Se retira **en el
mismo commit de la derogación**, con la razón escrita, igual que se invirtió el test de monotonía
en `T-2.148`. Un test que fija la conducta vieja, dejado atrás, se convierte en la prueba de que
la nueva está mal.

---

# PARTE A · mini-ShakeMap (`T-3.09`)

## A.1 · Qué es, y sobre todo qué NO es

**Es** un mapa de la sacudida **observada** en los inmuebles instrumentados de un tenant, durante
un evento, para que el SOC vea de un vistazo **dónde sacudió más fuerte** y priorice.

**No es**, y cada negación tiene su ficha detrás:

- **No es un ShakeMap del USGS ni del SSN.** Aquéllos interpolan cientos de estaciones sobre
  regiones. Aquí hay **unidades de estaciones**, y decir «mapa» sin declarar eso sería el mismo
  defecto que `T-2.104`: un nombre que promete más de lo que el dato sostiene.
- **No sustituye al dictamen firmado por un inspector** (misma regla que `T-3.06`). Un color en un
  mapa no reocupa un edificio.
- **No ordena evacuar.** Solo SASMEX o el quórum de ≥3 inmuebles lo hacen.
- **No vive en el edge.** El gabinete tiene un trabajo —el camino de vida— y este no lo es.

## A.2 · La entrada: features, nunca forma de onda

> **Regla de oro 9, intacta.** El mapa se construye de **features** (`pga_g`, `pgv_cms` por sensor
> y evento, que ya se ingieren y ya viven en la nube). **No** exige streaming continuo de waveform
> crudo, y por tanto **no** roza la viñeta `[INVARIANTE · streaming crudo continuo]`.

Lo que ya existe y basta:

| Dato | Dónde vive hoy |
|---|---|
| `pga_g`, `delta_s` por sensor y evento | vista del quórum (`qv`, `queries/events.py`, `forensics.py`) |
| `max_pga_g`, `max_pgv_cms` del incidente | `incidents` |
| Geometría del sitio | `sites.geom` (PostGIS, `geography`) |
| Ley de atenuación | **`ATTEN-LAW v1`**: `log10(PGA_g) = 0.5·M − 2.8 − log10(max(R_hipo_km, 1))` |

**Nada de esto hay que inventarlo.** Es la razón principal por la que este mapa es viable con el
sistema que ya está construido.

## A.3 · El problema real: interpolar con muy pocos puntos

Con 3–10 inmuebles no se puede interpolar una superficie de intensidad y llamarla medición. La
salida honesta **no es negarse a dibujar**: es dibujar **dos capas que no se mezclan**.

```
CAPA 1 · OBSERVADO      puntos, uno por inmueble instrumentado
                        valor = PGA/PGV MEDIDO en ese edificio
                        sin interpolación, sin suavizado

CAPA 2 · ESTIMADO       superficie continua de ATTEN-LAW v1
                        anclada al epicentro y magnitud del SSN
                        es un MODELO, y se pinta como modelo

CAPA 3 · RESIDUO        observado − estimado, POR PUNTO
                        es lo único que dice algo que el modelo no sabía
```

> **La capa 3 es el producto, no un detalle.** Un punto que sacude **el triple** de lo que la ley
> predice para su distancia es la información que justifica el mapa entero: puede ser suelo blando,
> puede ser el edificio, y en los dos casos es lo que un ingeniero necesita ver. La capa 2 sola no
> aporta nada que no se calcule con una regla; la capa 1 sola no se puede leer espacialmente.

**Invariante de presentación, y es `D-01` y la regla de oro 7 aplicadas al mapa:**

- **Jamás se pinta lo estimado con la misma codificación visual que lo medido.** Distinto
  tratamiento, y el dato lo declara: cada valor viaja con su procedencia (`measured` | `modeled`).
- **Fuera del alcance de los sensores se declara `SIN COBERTURA`**, no se extrapola color. Es la
  misma doctrina que `T-3.08` con la deriva de entrepiso: sin dos sensores, no hay número.

## A.4 · Dónde corre: **no** un microservicio nuevo

La viñeta diferida habla del «**microservicio** mini-ShakeMap». Este diseño **no propone uno**, y
la razón es de operación, no de gusto: un servicio más es un despliegue más, una alarma más, un rol
IAM más y una superficie más que puede caerse — y lo que se calcula aquí **no es continuo**.

**Se calcula por evento, en el worker que ya existe**, cuando el incidente se cierra o cuando llega
el catálogo del SSN con la magnitud y el epicentro:

```
evento confirmado
  → features por sensor (ya ingeridas)
  → magnitud/epicentro del SSN (catálogo, T-2.149)
  → cálculo de las 3 capas
  → snapshot persistido por incidente
  → la consola lo LEE; no lo recalcula
```

**Consecuencia deliberada:** el mapa **no es en vivo**. Aparece cuando hay con qué calcularlo, y
mientras tanto **lo dice**. Un mapa que se pinta a medias durante la sacudida es exactamente la
clase de dato que se lee como verdad y no lo es.

> **Dependencia dura:** la capa 2 necesita **magnitud y epicentro**, y eso llega por el catálogo
> del SSN — o sea que `T-3.09` **depende de `T-2.149`**, que hoy está bloqueada. Sin catálogo, el
> mapa se degrada a la capa 1 (puntos medidos) y **lo declara**, en vez de inventar un epicentro.

## A.5 · Criterios que este diseño añade a `T-3.09`

- [ ] Cada valor del mapa viaja con su **procedencia** (`measured` / `modeled`) y la consola las
      pinta **distinto**. Un test sobre el DOM, no sobre la lógica (lección de `T-2.104`).
- [ ] **`SIN COBERTURA`** es un estado propio, no un color pálido.
- [ ] El **residuo** es un campo de primera clase, no un cálculo del frontend.
- [ ] Sin magnitud/epicentro, el mapa **existe degradado y lo declara**; no inventa el modelo.
- [ ] Cero streaming de waveform crudo: el `grep` que lo demuestre va en la ficha.

---

# PARTE B · Arquitectura de CCTV (`T-3.10`)

## B.1 · El invariante, primero

> **El CCTV NUNCA entra en el camino de vida.** No dispara, no inhibe, no retrasa. Si el cliente
> ONVIF muere, se cuelga o satura la red, **el gabinete no se entera** (`T-3.11` ya lo pide). Esto
> es la regla de oro 1 y 4 aplicadas: el proceso que toca sirena, gas y puertas es mínimo y
> auditable, y no comparte destino con un decodificador de vídeo.

## B.2 · La decisión que NO se puede tomar sin medir

`T-3.10` pide «mismo Pi o hardware separado, **con la medición que la sostiene**». **Esa medición
no existe todavía, y este diseño no la inventa.** Lo que sí fija es **la regla de decisión** y
**qué hay que medir**, para que la respuesta no dependa de quién opine:

**Qué medir, en el Pi 4 real y con el gabinete haciendo su trabajo normal:**

1. **Línea base**: CPU, RAM y I/O con `takab-gpio` + `takab-edge` corriendo y SeedLink al día.
2. **Con el cliente ONVIF**: lo mismo, con N cámaras al perfil objetivo.
3. **Lo único que decide**: la **latencia del reflejo SASMEX→relé** bajo esa carga, contra su
   presupuesto de **100 ms** (`reflex_budget_s`, ya instrumentado y visible en `/api/status`).

**La regla de decisión, escrita antes de ver el número para que no se acomode al resultado:**

```
si el reflejo bajo carga de CCTV se mantiene MUY por debajo de 100 ms
   (referencia actual sin CCTV: 6.65 ms y 4.16 ms)
   ⇒ mismo Pi, con límites duros (B.3)

si se acerca al presupuesto, o la varianza crece
   ⇒ HARDWARE SEPARADO, sin discusión
```

> **Y el sesgo del que hay que protegerse:** «va justo pero cabe» es la respuesta que ahorra
> dinero, y es la que compromete el camino de vida. El margen actual es de **dos órdenes de
> magnitud**; gastarlo en vídeo es cambiarlo por lo único que el sistema no puede permitirse.

## B.3 · Los límites, si acaba en el mismo Pi

No son recomendaciones: son la condición.

| Límite | Cómo |
|---|---|
| CPU acotada | `CPUQuota=` en la unidad systemd del cliente ONVIF |
| Memoria acotada | `MemoryMax=`, con OOM del *cliente*, nunca del gabinete |
| Prioridad | el cliente **cede** ante `takab-gpio` (`Nice=`, y `takab-gpio` con prioridad de tiempo real si hiciera falta) |
| Aislamiento de fallo | proceso propio, `Restart=` propio; su caída no toca a nadie |
| Red | el vídeo **no comparte** cola con la telemetría del gabinete |

## B.4 · PII de vídeo — lo más sensible de todo el Bloque IV

El vídeo de un inmueble es **el dato más invasivo que este sistema tocaría nunca**, y encaja con
la Fase 2.8 (privacidad) que ya existe:

- **Retención por defecto: la mínima que sirva al propósito**, y declarada por sitio. El vídeo
  **no** hereda la exención de poda de la evidencia (regla de oro 11): esa exención es para
  auditoría y dictámenes, **no** para imágenes de personas.
- **Acceso por rol**, y más estrecho que el resto: ver vídeo **no** es ver telemetría.
- **Todo acceso deja rastro en `audit_log`.** Quién miró, qué cámara, cuándo.
- **Aviso de privacidad y base legal** — va a la consulta de `§4.1`, junto con la ubicación de
  personas del pase de lista. Es la misma familia de pregunta.

> **Y una que conviene decidir antes de construir, no después:** si el aforo por cámara
> (`T-3.12`) se calcula **en el borde y solo viaja el número**, el sistema deja de transportar
> imágenes de personas — y casi toda esta sección se simplifica. **Ésa es la arquitectura que
> este diseño recomienda**: procesar en el sitio, subir el conteo, y que el vídeo salga del
> inmueble **solo** bajo una acción explícita y auditada.

## B.5 · Criterios que este diseño añade a `T-3.10`

- [ ] La medición de B.2 **corrida en el Pi real**, con la regla de decisión aplicada **después**
      de verla y la conclusión escrita con su número.
- [ ] Los límites de B.3 en la unidad systemd, con test de artefacto (como `takab-gpio`).
- [ ] La política de retención de vídeo **declarada y distinta** de la exención de la evidencia.
- [ ] `T-3.12` decide si el aforo viaja como número o como imagen — **antes** de `T-3.11`.

---

## Lo que este documento deja pendiente a propósito

| | Por qué |
|---|---|
| La derogación de `[DIFERIDO · mini-ShakeMap]` | `D-08` autorizó planificar, no implementar. Va con `T-3.09` |
| El número de B.2 | exige el Pi real con carga; inventarlo sería peor que no tenerlo |
| El aviso de privacidad del vídeo | va a la consulta de `§4.1` |
| `T-2.149` (catálogo SSN) | la capa 2 del mapa depende de él, y hoy está bloqueada |
