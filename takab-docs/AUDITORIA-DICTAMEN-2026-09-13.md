# Auditoría del dictamen · 2026-09-13

> **Qué es esto.** El censo de **lo que el documento oficial afirma y puede ser falso**. Salió de
> la sesión con el WR-1: durante el acto 4 el dictamen firmado se llamó a sí mismo «preliminar»
> cuatro veces, y las cuatro se encontraron de una en una, regenerando el PDF cada vez. Eso es un
> método malo, así que se barrió el generador entero buscando **la misma clase** de defecto:
> **texto escrito a fuego que contradice al dato**.
>
> **Método.** Seis lentes independientes sobre `dictamen/`, `narrative/` y `forensics/`
> —ausencias declaradas con dato presente, calibración y unidades, atribución de la fuente,
> cifras a fuego, la prosa de las seis secciones, y secciones que se pintan vacías—. Cada
> hallazgo pasó por **tres escépticos** con el encargo de refutarlo, cada uno con un ángulo
> distinto: que la cadena llegue de verdad al papel, que el caso que la desmiente sea
> alcanzable, y que no sea una ausencia honesta. **50 propuestos · 32 sobrevivieron · 18
> refutados.** Los 32 se deduplican en **19 defectos distintos** (20 con el `B′` que salió al verificar el `B`) (varias lentes encontraron el
> mismo).
>
> **Lo que NO es un hallazgo, y por eso no está aquí:** que el documento declare lo que le falta.
> «SIN DATO», «SIN CARTOGRAFÍA BASE», «SIN COBERTURA CCTV DECLARADA» son correctos y deliberados.
> El defecto es el contrario: **declarar una ausencia habiendo dato, o afirmar algo que el dato
> desmiente**.

---

## Por qué esto importa más que una errata

El dictamen es el único artefacto del sistema con **peso legal**: lo leen peritos, aseguradoras y
protección civil, y su §10 es una cadena de custodia con hashes. Un documento que se contradice a
sí mismo —o que contradice a la consola sobre el mismo evento— no se discute por el fondo: se
discute por si es fiable. Los tres primeros defectos de esta lista hacen exactamente eso.

---

## 1 · Los que hay que arreglar ANTES de enseñar un PDF a un cliente

### A · La banda de sacudida dice «del inmueble» y usa los umbrales de hospital

`forensics/__init__.py:122` · `dictamen/model.py:331` · `dictamen/pdf.py:446` y `:673`

El papel imprime **«SACUDIDA FUERTE (supera el umbral de actuación del inmueble)»**. Pero
`build_forensics` llama a `felt_band(pga, pgv)` **sin pasar umbrales**, así que clasifica siempre
con `DEFAULT_THRESHOLDS` (0.040 / 0.060 g). La maquinaria para hacerlo bien existe y no se usa:
`felt.thresholds_from_row()`.

**Y el mapa del SOC sí los lee del `rule_set` del sitio** (`queries/telemetry.py:247-250`), con el
comentario escrito de que «el color del mapa y la decisión de disparo tienen que contar la misma
historia». Resultado: para un inmueble industrial con `pga_trip_g = 0.12` y un pico de 0.07 g, **la
consola pinta `normal` y el dictamen firmado afirma que se superó el umbral de actuación de ese
edificio**. No se superó y ningún relé actuó.

> **Está vivo en la demostración:** el gabinete de Puebla declara `pga_trip_g = 0.1`, y el
> documento clasifica con 0.060.

### B · El tiempo de aviso y el disparo de apertura salen de un campo que se REESCRIBE

`narrative/deterministic.py:60` · `dictamen/model.py:338` · `dictamen/pdf.py:470`

`incidents.trigger` no es el disparo de apertura: la ingesta hace `ON CONFLICT (event_uuid) DO
UPDATE` y **lo sobrescribe con el de la última escalada**. La prosa, en cambio, lo presenta como el
origen: *«El incidente se abrió … a partir de un acuse del receptor SASMEX»*, junto a un
`opened_at` que sí es de la primera publicación.

El mismo campo decide el **tiempo de aviso ganado**, así que un incidente **abierto por el SASMEX**
puede acabar imprimiendo «NO CALCULABLE · no aplica: el incidente no se disparó por SASMEX», o al
revés: medir el aviso desde la detección local en uno que sí fue SASMEX.

> **Corrección (misma jornada).** Este informe atribuyó primero a este defecto el «Tiempo de aviso
> ganado: 149.2 s» del reporte del acto 3. **Era falso y se comprobó contra el dato:** ese
> incidente abrió con `trigger='sasmex'`, severidad `warning`, y **nunca se reescribió** (su
> `summary` está vacío). Los 149.2 s son la fórmula haciendo lo que define —pico a las 03:30:32
> menos apertura a las 03:28:03—. El defecto B es **latente**: el `UPDATE` existe y muerde en
> cuanto un incidente escala de fuente. Lo que sí está vivo en ese PDF es el defecto **B′**.

### B′ · El papel presenta un «aviso ganado» de una sacudida que él mismo mide como leve

`forensics/__init__.py:141` · `dictamen/pdf.py:470`

`_lead_time` toma como «pico» el máximo de la ventana del incidente **haya habido sismo o no**. En
una alerta sin sacudida real —una prueba, una falsa alarma— ese máximo es ruido ambiente, y el
documento imprime un tiempo de aviso ganado como si se hubiera advertido de algo.

> **Está vivo en la demostración, y en la misma página:** el reporte del acto 3 imprime
> «TIEMPO DE AVISO GANADO · 149.2 s» tres líneas debajo de «BANDA · SACUDIDA LEVE (por debajo de
> los umbrales del inmueble)». Se presenta como logro haber avisado de algo que el propio
> documento clasifica como no significativo.

### C · «El valor evaluado fue 0.000 g» cuando no hubo medición

`dictamen/rules.py:93` · `narrative/deterministic.py:133`

La pasada del dictamen sustituye `pga_g=None` por **`0.0`** y graba ese cero en el `basis`. La
prosa solo comprueba `pga is not None`, así que imprime *«El valor evaluado fue 0.000 g frente a un
umbral de no habitar de 0.250 g … no alcanzó ninguno de los dos»* **en un documento cuyo §5 dice
«PGA PICO · SIN DATO»**. Contradice la regla que el propio módulo tiene escrita: *«un dato ausente
produce un literal de ausencia… nunca 0»*.

Peor: si las features llegan tarde, la pasada ya no revisa el incidente (ventana de 300 s) y el
cero **queda congelado** junto a un §5 que sí imprime el pico real.

---

## 2 · Contradicciones internas del documento

| # | Qué afirma el papel | Dónde | Por qué puede ser falso |
|---|---|---|---|
| D | «El veredicto lo produjo el conjunto de reglas» | `deterministic.py:117` | Lo eligió y firmó **una persona**; al firmar se inserta fila nueva con el status del inspector |
| E | «el fundamento no quedó guardado» | `deterministic.py:123` | El inspector **sí** escribió su razón (`basis.notes`) |
| F | «CLIP DISPONIBLE · ANÁLISIS PENDIENTE» | `builder.py:129` | Se decide por que **exista la fila**, no por `purged_at`: un clip ya podado se anuncia como archivado y promete cifras que no llegarán |
| G | «no se observó el inicio del reingreso» | `cctv.py:58` | Se imprime aunque el reingreso **esté registrado** |
| H | «EPICENTRO = CENTROIDE DE LAS ESTACIONES» | `model.py:98` | Se imprime por `event_source == local_quorum` aunque un operador lo haya **relocalizado a mano** |
| I | «Es la misma huella que imprime la variante técnica» | `pdf.py:693` | **Nunca lo es**: folio, onda cruda y `generated_at` entran en el hash. Y el test que debía cazarlo compara `model()` **consigo mismo** |
| J | El ejecutivo: «el sensor no registró aceleración» | `pdf.py:668` | …y la línea siguiente clasifica la sacudida a partir de ese mismo pico |
| K | La custodia: «sin objetos de evidencia archivados» | `pdf.py:544` | La sección siguiente lista el clip con su sha256 |
| L | «no hay onda cruda archivada» | `deterministic.py:103` | Lo único que falló fue **leerla**; el mismo PDF lista el miniSEED con su hash |
| M | «No se detectaron datos ausentes» | `deterministic.py:203` | El documento ya declaró dos ausencias en páginas anteriores |

### 2.1 · Verificación de las diez, contra el código de hoy

Las diez se volvieron a comprobar **en el código**, no en los números de línea de arriba (que ya
se han movido), con una lente por contradicción y **dos escépticos por hallazgo**: uno atacando
que la frase exista y sea alcanzable, otro atacando el arreglo propuesto.

**Resultado: las diez siguen vivas. Ninguna se retiró.** Y el segundo escéptico **refutó el
arreglo ingenuo en las diez**, cada vez por un motivo distinto y concreto. Ese es el hallazgo de
método de esta pasada, y vale más que el censo:

> **El arreglo obvio de una frase que miente suele ser otra frase que miente**, más pequeña. Diez
> de diez. Por eso ninguna de estas entra sin su refutador delante.

| # | Estado | La trampa que encontró el escéptico del arreglo |
|---|---|---|
| D | VIVO · impreso en el PDF de la demostración | La prueba propuesta (`"lo produjo el conjunto de reglas" not in texto`) sale ROJA contra el arreglo bueno si la frase nueva reusa el giro; y la rama firmada **calla la cadena de dictámenes** que la §9 del mismo papel sí enseña |
| E | VIVO | La señal no puede ser «hay `notes`»: `rules.py` mete `notes` enlatado en TODO dictamen automático. Hace falta la conjunción **firmado Y nota no vacía**, y el booleano nuevo no puede viajar al proveedor remoto sin su prueba en la allowlist |
| F | VIVO · latente | El corte es de **tres** ramas, no dos: «algunos clips podados» es un estado propio, y hoy recae en «el vídeo está archivado». Además `purged_at` acredita ese clip, no los `cctv_stills`, que se podan con otro plazo |
| G | VIVO · latente | La frase nueva no puede pronunciarse sobre si hay dictamen firmado: el Lambda ni siquiera recibe esa hora. O se calcula la latencia **en lectura** (el builder ya trae la firma), o el papel solo puede declarar que falta el término calculado |
| H | VIVO · latente | El aviso de reubicación no puede afirmar que consta en la bitácora: el evento es **compartido entre inmuebles** y la acción puede vivir en el incidente de otro. Dos frases, no una, y dos censos que dar de alta por su nombre |
| I | VIVO · latente | El texto propuesto manda al lector a la bitácora de auditoría, donde `content_sha256` **no tiene pantalla** y el inspector no entra. Y el comentario del código sigue enseñando la mentira al siguiente que lo lea |
| J | VIVO · latente | El modelo **sí** tiene la procedencia (`verdict_basis.evidence.pga_source`). El defecto de fondo es que hay **dos** procedencias en el mismo documento —la congelada en el `basis` y la que `build_forensics` recalcula al renderizar— y regenerar las separa |
| K | VIVO · latente | «fuera del material de vídeo» implica que el vídeo **está** archivado, que es justo lo que F dice que puede ser falso. Y la remisión «§11» sería un número tecleado en otra función: los 14 números de sección son literales independientes |
| L | VIVO · la frase está impresa en el PDF de la demostración | La guarda va en el **punto de impresión** (`pdf._raw_section`), no en un call site del builder: hay DOS literales que no consultan `m.evidence`, y arreglar uno deja el otro. Y el hecho nuevo obliga a subir el conteo declarado de la allowlist |
| M | VIVO · la frase está impresa, y la página ya declara una ausencia | Condicionar sobre `t90_s is None` inventa una ausencia: «análisis disponible» con `t90_s` NULL es un camino real. Y la línea del `basis` afirmaría un «dictamen vigente» inexistente |

Lo accionable está en **`T-7.38`**. `C` (§1) se arregla ahí también: es la misma clase de defecto y
toca los mismos ficheros.

---

## 3 · Gráficas que no dicen lo que parecen

- **El espectro y el espectrograma se calculan sobre el minuto ANTERIOR al sismo** (`pdf.py:330`).
- **La onda cruda se dibuja sin quitar la continua y con el cero abajo** (`pdf.py:257`): sale una
  línea plana bajo una etiqueta «±3.86e+06 cuentas». Ya hay precedente medido en el proyecto —el
  waveform crudo **trae** continua.
- **La barra de escala del croquis se recorta y conserva su rótulo en km** (`pdf.py:184`): quien
  mida sobre el papel mide mal.
- **«· 100 sps ·» escrito a fuego** (`model.py:104`, `pdf.py:248`) mientras la §8 imprime la tasa
  **declarada** del sensor.

---

## 4 · Lo que esta auditoría NO miró

- El **contenido** de los cálculos (si el PGA está bien medido) — solo si el papel afirma de ellos
  algo que el dato desmienta.
- La variante **ejecutiva** más allá de los cuatro puntos citados.
- El PDF de **simulacro**, que es otro documento.
- Nada fuera de `dictamen/`, `narrative/` y `forensics/`.

## 5 · Cómo se reproduce

El barrido es un workflow de 156 agentes (seis lentes × hallazgos × tres escépticos). Su guion y su
bitácora quedan en el directorio de la sesión; el veredicto por hallazgo incluye cuántos escépticos
lo refutaron, y **nada con 2 o 3 refutaciones entró en esta lista**.

El hallazgo **A** se re-verificó a mano antes de escribir esto: `grep -n "felt_band"` sobre
`forensics/__init__.py` enseña la llamada de dos argumentos, y `felt.py:63-67` enseña que el
tercero —`thresholds`— tiene default.
