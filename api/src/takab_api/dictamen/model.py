"""Modelo del dictamen (T-2.41): PURO, sin fpdf ni DB.

Separar el modelo del render permite probar el CONTENIDO —que es donde puede haber una
mentira— sin abrir un PDF. La regla que gobierna todo el módulo: **un dato ausente
produce un literal de ausencia con su razón, nunca 0, nunca cadena vacía, nunca un
guion suelto.** Un "0.000 g" en un dictamen que acabará ante Protección Civil no es un
detalle de formato.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from takab_api.compliance import ComplianceDocument
from takab_api.dictamen.duracion import Duracion
from takab_api.dictamen.espectrograma import Espectrograma
from takab_api.documentos.huella import content_sha256 as huella_de_contenido

# [T-7.24] El vocabulario del mapa se IMPORTA, no se copia: `calculo` es lógica
# pura (sin base, sin red, sin reloj) y copiar aquí sus cuatro estados daría dos
# definiciones de `pendiente` que acabarían divergiendo. Se importa el módulo
# entero, y no sus nombres, para no meter constantes ajenas en `vars(model)` —
# que es de donde el censo de avisos impresos deriva qué hay que comprobar.
from takab_api.shakemap import calculo as _shk

STATUS_LABELS: dict[str, str] = {
    "no_inhabit_inspect": "NO HABITAR · INSPECCIÓN",
    "inhabit_monitor": "HABITAR · MONITOREO",
    "normal_operation": "OPERACIÓN NORMAL",
    "restricted": "ACCESO RESTRINGIDO",
}

#: Qué hacer con cada veredicto. Tabla FIJA, no generada: son instrucciones de
#: seguridad y no pueden depender de nada que varíe entre dos ejecuciones.
STATUS_ACTIONS: dict[str, tuple[str, ...]] = {
    "no_inhabit_inspect": (
        "No reingresar al inmueble hasta contar con inspección estructural.",
        "Mantener el perímetro y las rutas de evacuación despejadas.",
        "Solicitar evaluación de un ingeniero estructural con responsiva.",
    ),
    "restricted": (
        "Restringir el acceso a las zonas señaladas por el responsable del inmueble.",
        "Documentar daños visibles antes de mover nada.",
        "Programar inspección estructural.",
    ),
    "inhabit_monitor": (
        "Se puede ocupar el inmueble; mantener vigilancia de daños visibles.",
        "Reportar grietas nuevas, puertas que dejan de cerrar o ruidos estructurales.",
        "Conservar la evidencia de este evento para la próxima revisión.",
    ),
    "normal_operation": (
        "Operación normal.",
        "Sin acciones adicionales derivadas de este evento.",
    ),
}

#: [T-7.33] Lo que el deslinde afirma SIEMPRE, firmado o no. La frase que
#: describe el ESTADO del documento no vive aquí: se deriva de si hay firma
#: (`pdf._closing`), porque escrita a fuego llamaba PRELIMINAR a un dictamen
#: firmado, en la misma página en la que el banner decía FIRMADO.
DISCLAIMER = (
    "No sustituye la evaluación estructural formal ni certifica reingreso "
    "seguro sin firma de ingeniería."
)

#: Las dos primeras frases del deslinde, según el documento tenga firma o no.
DISCLAIMER_ESTADO = {
    False: "Dictamen operativo PRELIMINAR generado por TAKAB Ailert a partir de "
    "evidencia instrumental.",
    True: "Dictamen operativo FIRMADO por inspector, sobre evidencia instrumental de TAKAB Ailert.",
}

TS_FMT = "%Y-%m-%d %H:%M:%S UTC"

#: Rótulos de ausencia. Existen como constantes para que un test pueda exigirlos y
#: para que no se cuele un "—" suelto que no explica nada.
ABSENT = "SIN DATO"
NO_CALIBRATION = (
    "SIN FUENTE DE CALIBRACIÓN DECLARADA · las aceleraciones y velocidades de este "
    "documento son valores RELATIVOS del sensor, no unidades físicas."
)
NO_SPECTRUM = (
    "ANÁLISIS ESPECTRAL NO DISPONIBLE. Requiere la forma de onda cruda; el "
    "sistema no la transmite en continuo (solo sube a evidencia en eventos "
    "confirmados). Este incidente no tiene miniSEED archivado."
)
#: [T-7.38·L] El caso que `NO_SPECTRUM` trataba como el mismo: SÍ consta un objeto
#: miniSEED en la cadena de custodia —la §12 (CADENA DE CUSTODIA) de este documento
#: imprime su sha256— y lo que falló fue LEERLO. Decir «no tiene miniSEED archivado»
#: ahí es falso, y lo desmiente el propio papel cuarenta líneas más abajo.
ONDA_NO_LEIDA = (
    "ANÁLISIS ESPECTRAL NO DISPONIBLE. Consta un objeto miniSEED registrado en la cadena "
    "de custodia de este incidente, con su sha256 impreso en este mismo documento; esta "
    "exportación no obtuvo traza de él. Que el objeto esté registrado no garantiza que "
    "siga siendo recuperable ni legible."
)
NO_GEOMETRY = "SIN GEOMETRÍA REGISTRADA · no se puede dibujar el croquis del evento."
#: [T-7.22] La misma ausencia, en la otra figura. Se dice aparte y no se
#: reutiliza `NO_GEOMETRY` porque aquélla nombra el croquis del evento: leerla
#: bajo «RED DE ESTACIONES» haría pensar que falló el dibujo de otra sección.
SIN_GEOMETRIA_DE_RED = (
    "SIN GEOMETRÍA REGISTRADA PARA LA RED · ninguna estación tiene coordenadas "
    "y no se puede situar el mapa. La tabla de arribos que sigue no depende de esto."
)
#: [T-3.12.c] Los tres estados del CCTV. Se distinguen porque significan cosas OPUESTAS y
#: se leerían igual si el reporte solo dijera «sin datos».
NO_CCTV = (
    "SIN COBERTURA CCTV DECLARADA · este sitio no tiene cámara configurada. La ausencia "
    "de análisis de evacuación en este documento no indica que nadie evacuara."
)
CCTV_SIN_CLIP = (
    "CÁMARA DECLARADA · sin clip para este incidente. Grabó o no grabó, pero el vídeo no "
    "llegó a la nube: revísese el gabinete antes de leer esto como «no hubo evacuación»."
)
CCTV_PENDIENTE = (
    "CLIP DISPONIBLE · ANÁLISIS PENDIENTE. El vídeo está archivado y todavía no se ha "
    "contado: las cifras de evacuación llegarán en una versión posterior del documento."
)
CCTV_PURGADO_SIN_ANALISIS = (
    "CLIP PURGADO POR RETENCIÓN · SIN ANÁLISIS. El vídeo se destruyó al vencer su plazo de "
    "retención y no consta conteo de evacuación para este incidente. Permanece la custodia "
    "—sha256 y ventana— en la lista siguiente."
)
CCTV_PARCIALMENTE_PURGADO = (
    "CLIP PARCIALMENTE PURGADO POR RETENCIÓN · ANÁLISIS PENDIENTE. Parte del vídeo de este "
    "incidente se destruyó al vencer su plazo de retención; lo que queda no se ha contado. "
    "La lista siguiente dice de cada objeto si sigue archivado."
)
CCTV_PURGADO = "PURGADO (retención de vídeo)"
EPICENTRO_REUBICADO = (
    "EPICENTRO REUBICADO A MANO POR UN OPERADOR. No es el centroide de las estaciones ni "
    "una localización sísmica calculada."
)
#: La trazabilidad se AÑADE, y solo cuando consta aquí: un evento de red es
#: COMPARTIDO entre inmuebles, así que la acción puede vivir en el incidente de otro.
#: Afirmar «consta en la bitácora» sin mirarla haría que el papel contradijera a su
#: propia §13 (CRONOLOGÍA DEL INCIDENTE).
EPICENTRO_REUBICADO_AQUI = " La reubicación consta en la bitácora de este incidente."
EPICENTRO_REUBICADO_EN_LA_RED = (
    " La reubicó un operador de la red sobre el evento compartido; no consta en la "
    "bitácora de este incidente."
)
CENTROID_NOTE = (
    "EPICENTRO = CENTROIDE DE LAS ESTACIONES QUE DETECTARON EL SISMO. No es una "
    "localización sísmica: está entre las estaciones, no en la falla."
)
SKETCH_NOTE = "SIN CARTOGRAFÍA BASE · PROYECCIÓN EQUIRECTANGULAR LOCAL"
ENVELOPE_NOTE = (
    "ENVOLVENTE DE PICO POR SEGUNDO (1 Hz). NO es la forma de onda cruda: el sistema "
    "no transmite el crudo en continuo."
)
#: [T-5.07] Aviso de asistencia automatizada. Vivía como literal dentro de
#: `pdf.py`, así que el censo de avisos impresos —que se DERIVA de este módulo— no
#: podía verlo, y era justo el aviso con la regla más fácil de romper: **solo debe
#: salir cuando la prosa NO la escribió el proveedor determinista**. El render le
#: añade la versión del rule_set; lo que se fija aquí es la frase que un lector
#: reconoce.
NARRATIVE_AI_NOTE = (
    "Las secciones en prosa se redactaron con asistencia automatizada. El "
    "VEREDICTO y todos los valores medidos de este documento son deterministas"
)

#: [T-7.22] La leyenda que un documento firmado NO puede callarse. El evento de
#: una reproducción trae el epicentro y la magnitud de un sismo HISTÓRICO: sin
#: esta frase, el papel afirma con todas las letras que el 19-S de 2017 ocurrió
#: hoy en este inmueble. Es el riesgo residual que `db/schema.sql` deja escrito
#: al lado de `meta.reproduccion`, y la consola ya lo rotula — el papel no.
#:
#: Va como TEXTO del cuerpo, no como rótulo dentro del dibujo: la meta de F4
#: exige encontrar «REPRODUCCIÓN» extrayendo el texto del PDF, y lo que se pinta
#: dentro de una figura se extrae mal o no se extrae.
REPRODUCCION_NOTE = (
    "REPRODUCCIÓN: este incidente se construyó sobre un sismo HISTÓRICO del "
    "catálogo para ensayo. El epicentro, la magnitud y los arribos son los de "
    "aquel evento; la sacudida de este inmueble NO ocurrió."
)

#: [T-7.22] Cuando la bitácora del incidente está vacía. No es lo mismo que
#: «no pasó nada»: `incident_actions` recoge lo que hicieron el gabinete, la nube
#: y las personas, y que no haya ni una fila es un hecho sobre el incidente que
#: merece decirse —y que en un incidente con sirena disparada sería un defecto—.
SIN_CRONOLOGIA = (
    "SIN ACCIONES REGISTRADAS PARA ESTE INCIDENTE: ni el gabinete, ni la nube, ni "
    "ninguna persona dejaron constancia de una acción en la bitácora."
)

#: [T-7.22] El recuento de verbos que el documento no supo traducir. Marcar las
#: filas no basta: quien audita tiene que poder saber de un vistazo cuánto de la
#: cronología se entrega sin rotular.
#:
#: El número va al FINAL y no delante a propósito: con el recuento por delante la
#: frase habría que declinarla («1 acciones») y un documento firmado no puede
#: permitirse esa errata. Así la constante es una sola y vale para cualquier
#: cantidad.
CRONOLOGIA_SIN_ROTULO = (
    "Hay acciones sin rótulo declarado: se imprimen con su identificador técnico y su "
    "significado está en el registro de la consola. Filas afectadas: "
)

#: [T-7.22] Cuando nadie reportó daños desde el táctico. No es «el edificio está
#: bien»: es que nadie entró a mirarlo, o que quien entró no reportó. Un hueco
#: mudo aquí se lee como «sin daños», que es una afirmación que este documento no
#: puede hacer.
SIN_DANOS = (
    "SIN REPORTES DE DAÑOS DESDE EL TÁCTICO. La ausencia de reportes NO significa "
    "que el inmueble esté sin daños: significa que nadie registró una inspección."
)

#: [T-7.22] `D-32` manda que el brigadista aparezca por ROL, nunca por nombre. Si
#: la asignación ya no existe se dice, en vez de rellenar con «brigadista» por
#: costumbre: quien firma el documento no puede afirmar un rol que no consta.
ROL_NO_RESUELTO = "rol no resuelto en el padrón del inmueble"

#: [T-7.22] Lo más importante que puede decir un reporte de campo. No puede
#: quedarse como una casilla más de la tabla de categorías.
PERSONAS_EN_RIESGO = (
    "PERSONAS EN RIESGO REPORTADAS EN ESTE PUNTO por quien hizo la inspección. "
    "Este documento no verifica ese reporte: lo registra tal como se recibió."
)

#: [T-7.22] Un reporte con fotografías y sin categorías es válido —el brigadista
#: fotografió y no clasificó— y el papel lo dice en vez de dejar la tabla ausente.
SIN_CATEGORIAS = (
    "Este reporte no clasificó el daño por categorías; lo que sigue son sus "
    "observaciones y fotografías tal como se recibieron."
)

#: [T-7.22] El recuento de fotografías que NO entraron. Entregar seis de once sin
#: decirlo es recortar la evidencia en silencio. El número va al final por la
#: misma razón que en la cronología: para no tener que declinar la frase.
FOTOS_OMITIDAS = (
    "Este reporte tiene más fotografías de las que el documento imprime; el resto "
    "queda en el expediente de evidencia. Impresas: "
)

#: [T-7.22 · reescrito en T-7.24] Qué se reporta de la sacudida, y qué NO.
#:
#: ⚠️ **Este aviso dejó de ser cierto el 2026-09-20 y por eso se reescribe.** Decía
#: «el cálculo está DIFERIDO y su ficha es T-7.24», y `T-7.24` es justamente la
#: ficha que derogó la viñeta `[DIFERIDO · mini-ShakeMap]` de `blueprint §14` y
#: construyó el mapa. Un papel firmado que anuncia como diferido algo que imprime
#: dos secciones más abajo se desmiente a sí mismo — la familia de defectos que
#: costó `T-7.34`, `T-7.38` y `T-7.39`.
#:
#: Lo que se conserva intacto, porque **sigue siendo verdad y está impreso en
#: documentos ya firmados**: TAKAB no reporta intensidad macrosísmica ni
#: isosistas. Eso no cambió con el mapa y no puede cambiar derivándolo de la PGA
#: de un sensor: la MMI es una intensidad construida con efectos observados, y
#: sacarla de la aceleración de una estación sería prometer más de lo que el dato
#: sostiene (`T-2.104`). Lo que sí se reporta ahora se dice en positivo y con su
#: procedencia, que es lo que el aviso viejo no podía decir porque no existía: la
#: sacudida **medida** en cada inmueble, la que el modelo de atenuación
#: **predice** a esa distancia, y el **residuo** entre las dos.
#:
#: La historia anterior a esto, para que no se reescriba en círculos: el texto
#: original decía «TAKAB no las calcula», categórico, y hubo que cambiarlo cuando
#: se planificó el mapa.
NO_MMI = (
    "No se reporta intensidad macrosísmica (MMI) ni isosistas: son intensidades "
    "construidas con efectos observados y no se derivan de la aceleración de un "
    "sensor. Lo que este documento reporta es la sacudida MEDIDA por el sensor "
    "del propio inmueble."
)

#: [T-7.24 · 2ª vuelta] Lo que el papel añade **sólo cuando de verdad lo añade**.
#:
#: ⚠️ Esta frase vivía dentro de :data:`NO_MMI`, y por eso el documento se
#: desmentía a sí mismo en su caso NORMAL. Medido el 2026-09-21 con el espía del
#: render sobre el pericial de un incidente sin snapshot: la §5 imprimía «lo que
#: este documento reporta es … la que el modelo de atenuación predice a su
#: distancia, y el residuo entre ambas» y tres secciones más abajo el MISMO
#: documento imprimía «MAPA DE LA SACUDIDA NO CALCULADO TODAVÍA». El mapa se
#: calcula POR EVENTO, así que ése no es un caso raro: es el estado por defecto.
#:
#: Es la familia exacta que costó `T-7.34`, `T-7.38` y `T-7.39`, invertida: antes
#: el papel anunciaba como diferido lo que imprimía; así anunciaba como impreso lo
#: que no había calculado. Por eso se separa y se imprime **derivado de lo que la
#: sección del mapa va a poder imprimir** (`pdf._reporta_modelo_y_residuo`), no de
#: una intención escrita a mano.
MODELO_Y_RESIDUO = (
    "Añade además, para cada inmueble instrumentado, la sacudida que el modelo de "
    "atenuación PREDICE a su distancia y el residuo entre las dos."
)

#: [T-7.24] La CABECERA de la leyenda del mapa de la sacudida.
#:
#: Sale sólo cuando hay figura, y va ANTES que ella. Es el invariante de
#: presentación de `D-08 · §A.3` escrito en el papel: jamás la misma codificación
#: visual para lo medido y lo modelado. Sin esta frase, un anillo y un punto en la
#: misma figura se leen como dos medidas de lo mismo.
#:
#: ⚠️ **Y es sólo la cabecera desde la 2ª vuelta de `T-7.24`.** Antes era una
#: frase cerrada que describía el disco, el anillo y la cruz, y se imprimía
#: entera pasara lo que pasara: medido el 2026-09-21, un documento DEGRADADO —sin
#: capa modelada y sin epicentro— prometía «ANILLO DISCONTINUO …» y «La cruz es el
#: epicentro» sobre una figura que no dibujaba ni una cosa ni la otra, y un
#: documento SIN COORDENADAS la imprimía sobre el hueco donde no hay figura
#: ninguna. Una leyenda que nombra símbolos ausentes enseña a leer una figura que
#: no está. Cada símbolo es ahora una pieza propia y `pdf._leyenda_del_mapa` las
#: elige **por lo que la figura dibuja**, no por lo que se quiso dibujar.
SHAKEMAP_LEYENDA = (
    "CÓMO SE LEE ESTA FIGURA — en este documento lo MEDIDO y lo MODELADO nunca comparten "
    "codificación; lo que sigue nombra únicamente los símbolos que ESTA figura dibuja:"
)

#: [T-7.24] Pieza de leyenda: el inmueble que SÍ midió.
LEYENDA_DISCO = "DISCO LLENO = SACUDIDA MEDIDA por el sensor de ese inmueble."

#: [T-7.24 · 2ª vuelta] Pieza de leyenda: el inmueble que NO publicó.
#:
#: ⚠️ Existe porque la figura pintaba **disco lleno** a un inmueble mudo mientras
#: la tabla de debajo decía «SIN DATO» de ese mismo inmueble, y la leyenda define
#: el disco lleno como «SACUDIDA MEDIDA». Medido el 2026-09-21 con el fixture del
#: lector, que trae un punto sin `pga_g`: la figura afirmaba lo que la tabla
#: negaba. Es la regla de oro 7 en la tinta — `SacudidaFila.pga_g` ya documenta
#: que `None` **no es 0 g**, y el dibujo lo estaba convirtiendo en una medición.
LEYENDA_SIN_DATO = (
    "CÍRCULO VACÍO = ese inmueble instrumentado NO publicó medida en la ventana; es "
    "una AUSENCIA, no un cero."
)

#: [T-7.24] Pieza de leyenda: la capa modelada. Se nombra sólo si se dibuja.
LEYENDA_ANILLO = (
    "ANILLO DISCONTINUO = lo que el modelo de atenuación PREDICE a esa distancia; es "
    "un modelo, no una medición, y por eso se dibuja distinto. Los anillos son el "
    "modelo, no medidas de los puntos por los que pasan."
)

#: [T-7.24] Pieza de leyenda: el epicentro. Se nombra sólo si se dibuja.
LEYENDA_CRUZ = "LA CRUZ es el epicentro citado para este incidente."

#: [T-7.24] Qué NO afirma la figura fuera del alcance de los sensores.
#:
#: `SIN COBERTURA` no es un estado del mapa: es una propiedad del espacio, y la
#: declara quien pinta (misma doctrina que `T-3.08` con la deriva de entrepiso —
#: sin dos sensores no hay número, y aquí sin inmueble cerca no hay medición).
#:
#: La coletilla sobre los anillos se fue a :data:`LEYENDA_ANILLO`: afirmaba algo
#: de una capa que en el caso degradado no se dibuja.
SHAKEMAP_SIN_COBERTURA = (
    "FUERA DEL RADIO DE COBERTURA ESTE DOCUMENTO NO AFIRMA NADA: donde no hay un "
    "inmueble instrumentado cerca no se extrapola ni se colorea, se dice SIN "
    "COBERTURA."
)

#: [T-7.24] El worker todavía no ha pasado. Es una condición NORMAL del sistema
#: —el mapa no es en vivo, se calcula por evento— y se declara en vez de dejar el
#: hueco (regla de oro 7). Un hueco aquí se leería como «no sacudió en ninguna
#: parte», que es lo contrario de lo que el resto del documento dice.
SHAKEMAP_PENDIENTE = (
    "MAPA DE LA SACUDIDA NO CALCULADO TODAVÍA: se calcula por evento, no en vivo. "
    "Esto no afirma nada sobre cuánto sacudió; sólo que al generar este documento "
    "el cálculo aún no había corrido."
)

#: [T-7.24 · 2ª vuelta] El snapshot NO SE PUDO LEER. **No es lo mismo que
#: `pendiente`** y por eso no se reusa aquella frase: «todavía no ha corrido el
#: cálculo» es una afirmación sobre el incidente, y ésta es una afirmación sobre
#: ESTE documento.
#:
#: Existe porque la lectura del mapa era la única del builder que NO era
#: best-effort, con la doctrina contraria escrita cinco líneas más arriba en
#: `_cctv_block` («un fallo leyendo el CCTV no puede impedir que se genere el
#: dictamen»). Medido el 2026-09-21 renombrando `incident_shakemap` dentro de una
#: transacción con rollback: `build_model` moría con `UndefinedTable` y el
#: inmueble se quedaba **sin dictamen**, que es el documento que autoriza
#: reocupar un edificio. Un anexo no puede costar el dictamen.
SHAKEMAP_NO_LEIDO = (
    "MAPA DE LA SACUDIDA NO DISPONIBLE al generar este documento: el cálculo pudo "
    "haber corrido, pero su lectura falló y el resto del dictamen no se detiene por "
    "un anexo. Esto no afirma nada sobre cuánto sacudió."
)

#: [T-7.24] Ningún inmueble instrumentado midió en la ventana. Distinto del
#: anterior y de lo contrario: aquí el cálculo SÍ corrió y no encontró nada que
#: medir. Los dos se leerían igual si el papel dijera sólo «sin datos».
SHAKEMAP_SIN_DATOS = (
    "NINGÚN INMUEBLE INSTRUMENTADO REGISTRÓ SACUDIDA EN LA VENTANA DE ESTE "
    "INCIDENTE: el cálculo corrió y no encontró medidas. No es lo mismo que «no "
    "sacudió»: puede no haber gabinete cerca, o no haber publicado."
)

#: [T-7.24] Hay medidas pero no hay con qué modelarlas, así que no se modela. El
#: mapa existe DEGRADADO y lo dice (`design/BLOQUE-IV-ARQUITECTURA.md §A.5`), en
#: vez de inventar un epicentro para poder pintar la capa bonita.
#:
#: ⚠️ **Qué FALTA ya no se escribe aquí, se deriva** (`pdf._falta_para_modelar`).
#: La frase decía «sin epicentro y magnitud citados» y se imprimía tal cual con el
#: epicentro CITADO dos líneas más arriba — que es justo el caso que el criterio
#: de la ficha llama «degradado y declarado cuando no hay magnitud». Medido el
#: 2026-09-21 sobre la fixture que monta ese caso, `tests/dictamen/
#: test_mapa_de_la_sacudida.py::_degradado_sin_magnitud(sin_epicentro=False)`
#: —`epicentro_lat=16.80`, `epicentro_lon=-99.50`, `epicentro_magnitud=None`—: el
#: papel imprimía «EPICENTRO DEL MODELO · 16.80, -99.50 · SIN DATO · SSN ·
#: confirmado» y justo debajo «sin epicentro y magnitud citados». Un aviso que el
#: campo de al lado desmiente enseña a ignorar el aviso. Se nombra la fixture y no
#: sólo los tres parámetros porque la PROCEDENCIA no está entre ellos y sale de
#: ella: esta cita decía «preliminar», que con esos parámetros no sale. (Un
#: epicentro `preliminar` sí existe en el repositorio —lo siembra
#: `tests/shakemap/test_pasada.py` desde un `review_status` del catálogo—, pero
#: ése no llega al papel; lo demás que dice «preliminar» es el estado del
#: DOCUMENTO, que es otra cosa.)
SHAKEMAP_DEGRADADO = (
    "MAPA DEGRADADO: no se dibuja la capa modelada ni se calcula el residuo. Lo que "
    "sigue son las medidas de los inmuebles, sin nada con qué compararlas. FALTA:"
)

#: [T-7.24 · 3ª vuelta] El modelo SÍ corrió y aun así no hay un solo anillo que
#: dibujar. **No es el caso degradado y no puede compartir su frase**, que dice
#: «ni se calcula el residuo … sin nada con qué compararlas» mientras la tabla de
#: debajo imprime la columna MODELO y el RESIDUO.
#:
#: No es un caso de laboratorio: es el que el propio repositorio acredita en
#: `tests/shakemap/test_calculo.py`, en
#: `test_un_anillo_que_no_corta_la_superficie_no_se_publica_pero_se_DECLARA`
#: —con el foco a 48 km, los dos niveles de la banda de un M5.0 sólo se
#: alcanzarían bajo la superficie— y `calculo.calcula` lo devuelve como
#: `completo`, porque hay medida, epicentro y magnitud: la capa 2 no es lo que
#: define el estado. Medido el 2026-09-21 por la ruta entera (cálculo → forma
#: persistida → lectura → builder → render): el papel imprimía «DEGRADADO · sólo
#: medido · el snapshot se declara «completo»» y acusaba de incoherente a un
#: snapshot coherente, y acto seguido negaba el residuo que imprimía (+1.35).
SHAKEMAP_SIN_ANILLOS = (
    "SIN ANILLOS QUE DIBUJAR, Y CON MODELO: la ley se aplicó —lo que predice para "
    "cada inmueble y el residuo están en la tabla—, pero ninguno de sus niveles se "
    "puede dibujar como anillo sobre este mapa. NIVELES SUPRIMIDOS:"
)

#: [T-7.24] Hay medidas y no hay ni una coordenada con la que situarlas. La tabla
#: sigue —los números no dependen de la geometría—, la figura no. Mismo criterio
#: que `SIN_GEOMETRIA_DE_RED` en la §7: un marco vacío parece un fallo de
#: impresión y se lee como «no hay inmuebles».
SHAKEMAP_SIN_GEOMETRIA = (
    "SIN COORDENADAS NO SE PUEDE DIBUJAR EL MAPA DE LA SACUDIDA: los inmuebles que "
    "midieron no tienen geometría registrada. Las medidas siguen en la tabla; lo "
    "que falta es dónde situarlas."
)

#: [T-5.11] Lo que se imprime cuando NINGÚN sismo del catálogo es éste y no había
#: siquiera candidatos en la ventana.
#:
#: ⚠️ [T-7.25] Y **sólo** en ese caso: es una afirmación sobre el sismo que
#: exonera al catálogo de referencia, así que sólo puede firmarse cuando la
#: fuente CONTESTÓ **y nada suyo es éste**. Los otros CUATRO desenlaces sin
#: acierto tienen frase propia: :data:`SIN_CONSULTA_A_FUENTE_EXTERNA` (no se
#: preguntó), :data:`CONSULTA_EXTERNA_EN_VUELO` (no contestaron) y
#: :data:`CORRELACION_EN_DISPUTA` (contestaron, correlacionaron, y el criterio de
#: identidad de este documento no lo reconoce — `preliminar` y `confirmado`).
#: Los cinco salían por aquí.
#:
#: Decía «SIN COINCIDENCIA EN CATÁLOGO», que
#: sonaba a fallo de búsqueda; lo que afirma es un HECHO sobre el evento —el
#: catálogo no tiene un sismo compatible, probablemente porque fue local y
#: pequeño—, y es el mismo vocabulario que el estado `sin_correlacion` del
#: glosario compartido (`shared/glossary/procedencia.json`, T-5.10).
SIN_CORRELACION_EN_CATALOGO = (
    "SIN CORRELACIÓN EN EL CATÁLOGO DE REFERENCIA: ningún sismo publicado "
    "satisface el criterio de identidad con este incidente."
)


#: [T-7.25] Lo que el papel imprime mientras la pregunta a la fuente externa
#: SIGUE EN VUELO —o cuando un timeout la dejó sin contestar—, en vez de
#: :data:`SIN_CORRELACION_EN_CATALOGO`.
#:
#: Es EL defecto que la ficha existe para eliminar, sobreviviendo en la
#: superficie más cara del producto: con la consulta sin respuesta el dictamen
#: firmaba «ningún sismo publicado satisface el criterio de identidad con este
#: incidente», que es una afirmación sobre el sismo. Lo cierto era que **nadie
#: había contestado todavía**. Las dos frases se parecen y no dicen lo mismo: la
#: primera exonera al catálogo, la segunda deja la pregunta abierta — y ésta va
#: debajo de una firma que no se puede retirar.
CONSULTA_EXTERNA_EN_VUELO = (
    "CONSULTA EN CURSO A LA FUENTE EXTERNA: todavía no hay respuesta, así que este "
    "documento NO afirma que no exista un sismo publicado compatible con este incidente."
)

#: [T-7.25] Lo que el papel imprime cuando a este incidente **no se le preguntó
#: a nadie**, en vez de :data:`SIN_CORRELACION_EN_CATALOGO`.
#:
#: Es la otra mitad del mismo defecto, y la que sobrevivió a la primera vuelta de
#: la ficha. Los tres hechos son distintos y el documento tiene que separarlos:
#:
#: * **no se preguntó** — esta frase;
#: * **se preguntó y no contestaron** — :data:`CONSULTA_EXTERNA_EN_VUELO`;
#: * **contestaron y ninguno casa** — :data:`SIN_CORRELACION_EN_CATALOGO`;
#: * **correlacionó, preliminar** — :data:`CORRELACION_EN_DISPUTA`;
#: * **correlacionó, confirmado** — :data:`CORRELACION_EN_DISPUTA`, con el rótulo
#:   del glosario que los separa: una solución que la fuente puede cambiar no
#:   pesa lo mismo que una que ya revisó.
#:
#: Son CINCO, no tres, y son exactamente los cinco estados de
#: `shared/glossary/procedencia.json`: la guarda los DERIVA de ahí
#: (`tests/dictamen/test_catalog_line.py`) en vez de enumerarlos, porque
#: enumerados ya divergieron una vez — los dos últimos nacieron sin línea.
#:
#: Imprimir el tercero cuando lo cierto es el primero es afirmar bajo firma algo
#: que nadie comprobó: exonera al catálogo de referencia sin haberlo interrogado.
#: Y es el caso NORMAL hoy, porque la consulta automática se despliega apagada.
SIN_CONSULTA_A_FUENTE_EXTERNA = (
    "NO SE CONSULTÓ NINGUNA FUENTE EXTERNA para este incidente: este documento no "
    "afirma ni niega que exista un sismo publicado compatible con él."
)

#: [T-7.25] Lo que el papel imprime cuando **la consulta correlacionó y el
#: criterio de identidad de este documento no**, en vez de
#: :data:`SIN_CORRELACION_EN_CATALOGO`.
#:
#: Es el CUARTO y el QUINTO hecho de la lista de arriba —`preliminar` y
#: `confirmado` sin acierto—, y era la misma mentira que los otros dos con otro
#: disfraz: `catalog_consultations.outcome = 'correlacionado'` escrito en la
#: base, la fila del catálogo citable, y el papel imprimiendo «ningún sismo
#: publicado satisface el criterio de identidad con este incidente». Medido: sin
#: descartes la línea salía `None` —y el PDF rellena el hueco con esa frase— y
#: con descartes salía literalmente «SIN CORRELACIÓN · … ninguno es éste», que es
#: la misma afirmación escrita a mano.
#:
#: Los dos procedimientos son distintos a propósito y pueden discrepar sin que
#: ninguno esté roto: el worker le pregunta a la fuente viva por una ventana y un
#: radio, y el ensamblado forense vuelve a decidir la IDENTIDAD contra lo que hay
#: en la tabla (`forensics/correlacion.py`). Una poda, un refresco que corrigió
#: la hora de origen en la fuente o dos lecturas separadas en el tiempo bastan
#: para separarlos. Lo que no puede pasar es que el papel **elija** el desenlace
#: más tranquilizador de los dos y lo firme: la discrepancia se declara, y quien
#: lea el dictamen sabe que hay dos respuestas y cuál dio cada procedimiento.
CORRELACION_EN_DISPUTA = (
    "CORRELACIÓN EN DISPUTA: la consulta a la fuente externa SÍ correlacionó este "
    "incidente con un sismo publicado, y el criterio de identidad de este documento "
    "no lo reconoce entre los candidatos de su ventana. Este documento NO afirma que "
    "no exista un sismo publicado compatible, y tampoco cita una cifra cuya identidad "
    "no puede sostener."
)

#: [T-7.25] El suelo de la línea de correlación: un estado de procedencia que
#: este documento no sabe traducir.
#:
#: No es defensa contra lo imposible: aquí caía ANTES todo lo que no fuera
#: `sin_dato_externo` ni `consultando` —incluidos los dos estados que sí pintan
#: cifra—, y lo que caía se imprimía como «SIN CORRELACIÓN». Un sexto estado
#: añadido al glosario compartido heredaría ese destino en silencio. Con esta
#: frase, lo que el papel no sabe traducir se DECLARA sin exonerar a nadie, y la
#: guarda derivada de `pr.estados()` lo caza en la primera corrida.
ESTADO_DE_CONSULTA_NO_INTERPRETABLE = (
    "ESTADO DE CONSULTA NO INTERPRETABLE: este documento no sabe traducir el estado de "
    "procedencia registrado para este incidente, así que no afirma ni niega que exista "
    "un sismo publicado compatible con él."
)

#: [T-7.25] Lo que el papel dice cuando el modelo no trae la línea de fuentes.
#: No es un «ok» de relleno: declara que no consta, que es lo único cierto.
FUENTES_EXTERNAS_SIN_CONSTANCIA = "No consta en este documento qué fuentes externas se consultaron."

#: [T-7.25] Por qué el SSN no aparece nunca aquí, dicho en el papel y no sólo en
#: el código. Un lector que vea «USGS» y no vea «SSN» supondrá que el SSN falló,
#: y la razón es otra: su ingesta automática está DECIDIDA (`D-06`) y lo que
#: sigue abierto es la ATRIBUCIÓN de sus cifras. Imprimir aquí una magnitud del
#: SSN sin poder citarla como la fuente exige sería exactamente la cifra sin
#: procedencia que este documento no admite (`T-5.10`).
SSN_NO_SE_CONSULTA = (
    "El SSN no se consulta: la atribución de sus cifras está sin cerrar y este "
    "documento no imprime una cifra ajena que no pueda citar."
)


def fuentes_line(consulta_usgs_encendida: bool) -> str:
    """Qué fuentes externas puede consultar este despliegue, y cuál no y por qué.

    Se DERIVA de la configuración y no se escribe a fuego: con la consulta
    apagada —que es como se despliega hoy— decir «consultadas: USGS» sería
    afirmar una llamada que nadie hizo. El desenlace por incidente lo dice la
    línea de CORRELACIÓN CON CATÁLOGO, que es otra cosa: aquí se declara a quién
    se PUEDE preguntar.
    """
    quien = (
        "USGS (FDSN)"
        if consulta_usgs_encendida
        else "NINGUNA — la consulta automática a USGS está apagada en este despliegue"
    )
    return f"{quien}. {SSN_NO_SE_CONSULTA}"


def num(value: object, digits: int = 3, unit: str = "") -> str:
    """Número con unidad, o el literal de ausencia. Nunca 0 por defecto."""
    if value is None:
        return ABSENT
    text = f"{float(value):.{digits}f}"
    return f"{text} {unit}".strip()


@dataclass(frozen=True, slots=True)
class ChannelRow:
    channel: str
    peak_pga_g: float | None
    peak_pgv_cms: float | None
    peak_rms: float | None
    peak_stalta: float | None
    energy_sum: float | None
    clipped: bool
    samples: int
    peak_ts: datetime | None


@dataclass(frozen=True, slots=True)
class DictamenRow:
    dictamen_id: str
    status: str
    created_at: datetime
    signed_by: str | None
    rule_set_version: str
    supersedes: str | None


@dataclass(frozen=True, slots=True)
class VoteRow:
    label: str
    delta_s: float | None
    pga_g: float | None
    counted: bool


@dataclass(frozen=True, slots=True)
class EstacionFila:
    """[T-7.17] Una estación de la red frente a este incidente, en el papel.

    Lleva lo MEDIDO y lo ESPERADO juntos, y `None` donde no hay dato en vez de un
    cero: un `0.0 g` impreso en un dictamen firmado es una afirmación de que la
    estación midió calma, y no es lo mismo que no haber medido.
    """

    site_name: str
    site_code: str
    sensor_code: str | None
    dist_km: float | None
    t_teorico_s: float | None
    t_medido_s: float | None
    peak_pga_g: float | None
    tier: str | None

    #: [T-7.22] Dónde está, para poder dibujarla. `None` en las dos o en
    #: ninguna: media coordenada no sitúa nada, y el mapa declara la ausencia en
    #: vez de colocar el punto en el meridiano cero.
    lat: float | None = None
    lon: float | None = None

    #: [T-7.22] El umbral contra el que se decidió «sobre umbral», CON su
    #: procedencia. La tabla imprimía el pico a secas: sin el umbral al lado, un
    #: `0.0123 g` no dice si esa estación se movió mucho o poco, y sin la
    #: procedencia el número parece del edificio aunque sea el de referencia
    #: —que es la razón por la que `T-7.35` añadió `umbral_origen`—.
    umbral_pga_g: float | None = None
    umbral_origen: str | None = None


@dataclass(frozen=True, slots=True)
class FotoFila:
    """[T-7.22] Una fotografía del reporte de daños, tal como llega al papel.

    **Tres huellas y no una, y la distinción no es pedantería.**

    * `sha256_declarado` es lo que dijo el DISPOSITIVO al registrar la evidencia
      (`POST /evidence`), y el servidor nunca lo verificó — por eso existe
      `POST /evidence/{id}/verify` como operación aparte.
    * `sha256_medido` es lo que el servidor calculó del blob al leerlo para
      imprimirlo. Es gratis: el render tiene que bajar los bytes de todos modos.
    * `sha256_impreso` es el de la DERIVADA redimensionada, que es lo que el
      lector tiene delante.

    Rotular el primero como «huella del original» junto a una portada que manda
    hacer `sha256sum` repetiría la clase de defecto de `T-5.26`: un dato
    inverificable presentado como verificable. Y un desajuste entre el declarado y
    el medido es lo más importante que esta sección puede decir de una foto de
    evidencia, así que se imprime.
    """

    evidence_id: str
    sha256_declarado: str
    sha256_medido: str | None = None
    sha256_impreso: str | None = None
    ancho: int | None = None
    alto: int | None = None
    #: Por qué no se imprime, si es el caso. Nunca un hueco mudo.
    motivo: str | None = None
    #: Los bytes JPEG a embeber. **No entran crudos en `content_sha256`**: ver
    #: `documentos/huella.para_la_huella`. Su `sha256_impreso` sí, que identifica el
    #: contenido sin arrastrar megabytes por el serializador en cada llamada.
    jpeg: bytes | None = None


@dataclass(frozen=True, slots=True)
class DanoFila:
    """[T-7.22] Un reporte de daños del brigadista.

    `rol` y no nombre: lo fija `D-32` («el brigadista aparece por **rol**, nunca
    por nombre») y es lo único que este documento necesita para que la observación
    tenga procedencia. `None` cuando la asignación ya no existe — se declara, no se
    rellena con «brigadista» por costumbre.
    """

    report_id: str
    rol: str | None
    zona: str | None
    #: `[{key, severity, note?}]` tal como lo escribió la app.
    categorias: list[dict]
    personas_en_riesgo: bool
    notas: str | None
    ts: datetime
    fotos: list[FotoFila] = field(default_factory=list)
    #: Cuántas fotografías tiene el reporte MÁS ALLÁ del tope del documento. Se
    #: imprime: entregar seis de once sin decirlo es recortar la evidencia en
    #: silencio.
    fotos_omitidas: int = 0


@dataclass(frozen=True, slots=True)
class ActionRow:
    ts: datetime
    kind: str
    actor: str


@dataclass(frozen=True, slots=True)
class EvidenceRow:
    kind: str
    sha256: str | None
    created_at: datetime | None


@dataclass
class CctvObjectRow:
    """Un clip o una captura, para la cadena de custodia.

    Conserva `sha256` y fecha **aunque el objeto ya no exista**: es lo que permite que el
    documento siga siendo verificable después de que la retención de vídeo haga su trabajo.
    Por eso `estado` es un campo y no se deriva de la presencia de la fila.
    """

    tipo: str  # clip | captura
    papel: str | None  # pre/egress/peak/reentry para capturas; None para clips
    sha256: str | None
    momento: datetime | None
    estado: str  # "disponible" | CCTV_PURGADO


@dataclass
class CctvBlock:
    """Lo que la sección de CCTV del reporte afirma. Sin métricas sigue siendo útil: la
    cadena de custodia y el estado son parte del documento aunque nadie haya contado."""

    estado: str = NO_CCTV
    objetos: list[CctvObjectRow] = field(default_factory=list)
    t50_s: float | None = None
    t90_s: float | None = None
    peak_n: int | None = None
    correlacion: str | None = None
    veredicto_reingreso: str | None = None
    #: `True` ⇒ la sección lo dice en un recuadro, no en una celda de tabla.
    reingreso_antes_del_dictamen: bool = False
    discrepancia: str | None = None


@dataclass(frozen=True, slots=True)
class SacudidaFila:
    """Un inmueble instrumentado en el mapa de la sacudida: lo medido y lo modelado.

    **Las dos cifras viven en la misma fila a propósito.** Un pico suelto no dice
    si es mucho o poco para esa distancia; el modelo solo no dice nada que no
    calcule una regla de tres. Lo que informa es la diferencia, y por eso el
    residuo es un campo y no una resta que haga quien lea.
    """

    site_code: str
    site_name: str
    lat: float | None
    lon: float | None
    #: MEDIDO. `None` = ese gabinete no publicó nada en la ventana. **No es 0 g**:
    #: un cero por un silencio afirmaría que no se movió (regla de oro 7).
    pga_g: float | None
    pgv_cms: float | None
    #: Distancia epicentral. `None` sin epicentro citado.
    dist_km: float | None
    #: MODELADO por `ATTEN-LAW v1` a esa distancia. `None` = no se modeló.
    pga_g_modelada: float | None
    #: `log10(medida / modelada)`. Positivo = sacudió MÁS de lo que la ley predice
    #: ahí, que es el producto de todo esto: puede ser suelo blando, puede ser el
    #: edificio, y en los dos casos es lo que un ingeniero necesita ver.
    residuo_log10: float | None
    #: ¿Es el inmueble de ESTE dictamen? Se dibuja distinto: es el sujeto del
    #: documento, no un testigo.
    propio: bool = False


@dataclass(frozen=True, slots=True)
class AnilloFila:
    """Un nivel de PGA constante del modelo, con el radio al que cae.

    Se guarda como NÚMEROS —no como vértices— porque el círculo es geometría
    derivada: materializarlo aquí sería guardar un dibujo en vez de un modelo, y
    un dibujo hecho a una latitud no vale a otra.
    """

    pga_g: float
    radio_km: float
    #: Qué umbral de ESTE sistema es ese nivel (`pga_watch_g`…). No es una escala
    #: inventada: son los números con que el gabinete ya decide.
    umbral: str


@dataclass(frozen=True, slots=True)
class NivelFueraFila:
    """Un nivel del modelo que la capa 2 **no dibuja**, y por qué.

    [T-7.24 · 3ª vuelta] Llega al papel porque sin él la sección no puede decir
    la razón VERDADERA de que no haya anillos, y decía una falsa: con el foco más
    hondo que el nivel —el caso que `tests/shakemap/test_calculo.py` acredita con
    el M5.0 a 48 km— el documento imprimía «FALTA: la capa modelada del snapshot,
    pese a estar citados el epicentro y la magnitud» mientras la tabla de debajo
    imprimía la columna MODELO y el RESIDUO de ese mismo modelo. No faltaba nada:
    los dos niveles quedaron bajo la superficie, y el snapshot lo dice.

    `motivo` es el vocabulario cerrado de `shakemap.calculo.MOTIVOS_FUERA`, que
    trae también la frase con que se imprime: aquí no se escribe ninguna.
    """

    umbral: str
    pga_g: float
    motivo: str


@dataclass
class ShakemapBlock:
    """[T-7.24] El mapa de la sacudida de este incidente, tal como el papel lo afirma.

    Lo llena el builder leyendo el snapshot **por la función de lectura que expone
    `takab_api.shakemap.lectura`**, la misma que sirve al endpoint. Que sea la
    misma no es aseo: si el papel y la pantalla leyeran cada uno a su manera
    acabarían discrepando sobre el mismo sismo, y aquí el que discrepa lleva una
    firma debajo — el mismo razonamiento que el marco normativo y el CCTV.

    El estado por defecto es `pendiente` y no «vacío»: un modelo construido a mano
    no tiene mapa calculado, y eso es exactamente lo que el papel debe decir.
    """

    #: `completo` · `solo_observado` · `sin_datos` · `pendiente`. El vocabulario
    #: es el de `takab_api.shakemap.calculo`, importado y no copiado.
    estado: str = _shk.ESTADO_PENDIENTE
    #: Con qué ley se modeló (`ATTEN-LAW v1`), o `None` si no se modeló. Se
    #: imprime para que un dictamen viejo diga con qué ley se hizo, no con la de
    #: hoy.
    ley: str | None = None
    calculado_en: datetime | None = None
    #: Radio de representatividad de un inmueble instrumentado, en km. Es el
    #: número que hace verificable el `SIN COBERTURA`.
    cobertura_km: float | None = None
    epicentro_lat: float | None = None
    epicentro_lon: float | None = None
    epicentro_magnitud: float | None = None
    #: Quién localizó el epicentro y con qué estado de procedencia. Sin esto, el
    #: centroide de nuestro propio cuórum se confundiría con la solución de una
    #: agencia.
    epicentro_fuente: str | None = None
    epicentro_procedencia: str | None = None
    puntos: list[SacudidaFila] = field(default_factory=list)
    anillos: list[AnilloFila] = field(default_factory=list)
    #: [T-7.24 · 3ª vuelta] Los niveles que el modelo consideró y NO pudo
    #: dibujar, con su motivo. El builder los tiraba, y sin ellos la sección
    #: tenía que inventarse por qué no hay anillos. Vacío no es «se dibujaron
    #: todos»: también es un snapshot que no los declara.
    fuera_de_alcance: list[NivelFueraFila] = field(default_factory=list)
    #: [T-7.24 · 2ª vuelta] Por qué NO se pudo leer el snapshot. `None` = se leyó
    #: (con mapa o sin él). Lo pone el builder, que lee best-effort igual que el
    #: CCTV y el miniSEED: un anexo ilegible degrada su sección, no el documento.
    #: Se distingue de `pendiente` a propósito — «no ha corrido» y «no lo pude
    #: leer» son dos hechos distintos sobre el mismo incidente.
    fallo_de_lectura: str | None = None


#: [T-7.36] Rótulos de celda del disparo. La versión en PROSA vive en
#: `narrative/deterministic._TRIGGER_TEXT`; ésta es la corta, para portada y
#: resumen. Son dos registros distintos del mismo hecho, no dos verdades.
TRIGGER_LABELS = {
    "sasmex": "SASMEX",
    "local_threshold": "umbral local",
    "quorum": "cuórum de red",
    "manual": "activación manual",
    "drill": "simulacro",
}


def disparo_line(opened_trigger: str, trigger: str) -> str:
    """[T-7.36] Qué ABRIÓ el incidente y, si no es lo mismo, a qué escaló.

    La portada y el resumen ejecutivo salen de aquí para que no puedan discrepar
    entre sí sobre el mismo incidente — el mismo criterio que `umbral_line`.

    La escalada NO se esconde: sustituir una frase falsa («se abrió por el
    cuórum») por una incompleta («se abrió por SASMEX», callando que el cuórum
    corroboró) sería cambiar de defecto. Y el cuórum es justo lo que autoriza a
    evacuar.
    """
    abrio = TRIGGER_LABELS.get(opened_trigger, opened_trigger) or "SIN DATO"
    if not trigger or trigger == opened_trigger:
        return abrio
    return f"{abrio} · escaló a {TRIGGER_LABELS.get(trigger, trigger)}"


@dataclass
class ReportModel:
    """Todo lo que el dictamen puede afirmar. Nada se calcula durante el render."""

    folio: str
    incident_id: str
    site_name: str
    site_code: str
    site_criticality: str | None
    site_lat: float | None
    site_lon: float | None
    opened_at: datetime
    closed_at: datetime | None
    severity: str
    #: La escalada VIGENTE. La ingesta la sobrescribe (`ON CONFLICT DO UPDATE`).
    trigger: str
    #: [T-7.36] Con qué se ABRIÓ. Lo estampa la base y es inmutable. Es lo que la
    #: prosa tiene que decir: «se abrió por X» con el disparo de la última escalada
    #: es falso en cuanto un incidente escala, y es el mismo campo del que sale el
    #: tiempo de aviso ganado.
    opened_trigger: str
    state: str
    event_id: str | None
    event_source: str | None
    epicenter_lat: float | None
    epicenter_lon: float | None

    verdict_status: str | None
    verdict_label: str
    verdict_signed: bool
    rule_set_version: str | None

    peak_pga_g: float | None
    peak_pgv_cms: float | None
    peak_ts: datetime | None
    felt_band: str
    # [T-7.35] Contra qué números se clasificó `felt_band` y de quién son. Con
    # default para no romper los modelos que aún no lo traen; la línea del papel
    # lo declara como «banda de referencia» cuando falta.
    felt_thresholds: dict | None
    calibrated: bool
    lead_time_s: float | None
    lead_time_reason: str | None
    station_count: int
    catalog_line: str | None
    generated_at: datetime

    #: [T-7.38·H] ¿Movió un operador el epicentro a mano? Sale de
    #: `seismic_events.meta ? 'manual_override'`. Con esto puesto, el papel NO puede
    #: seguir llamándolo «centroide de las estaciones»: es un punto humano.
    #: [T-7.51] El incidente se cerró y NADIE registró la hora. Declara la
    #: ausencia en vez de que el papel la disimule: sin esto, el campo CIERRE
    #: imprimía «EN CURSO» de un incidente cerrado, que es el papel
    #: desmintiendo al dato — la clase de defecto de `T-7.38`/`T-7.42`/`T-7.43`.
    cierre_sin_hora: bool = False
    #: [T-7.25] A qué fuentes externas puede preguntar este despliegue, y por
    #: qué el SSN no está entre ellas. Con default para no romper los modelos
    #: que aún no lo traen; el papel declara entonces que no consta.
    fuentes_externas: str = FUENTES_EXTERNAS_SIN_CONSTANCIA
    epicenter_relocated: bool = False

    channels: list[ChannelRow] = field(default_factory=list)
    dictamens: list[DictamenRow] = field(default_factory=list)
    votes: list[VoteRow] = field(default_factory=list)
    actions: list[ActionRow] = field(default_factory=list)
    evidence: list[EvidenceRow] = field(default_factory=list)
    sensors: list[dict] = field(default_factory=list)
    peers: list[dict] = field(default_factory=list)
    #: Serie 1 Hz por canal: `{canal: [(ts, pga_g, clipping), …]}`.
    series: dict[str, list[tuple[datetime, float | None, bool]]] = field(default_factory=dict)
    #: Forma de onda cruda decodificada del miniSEED, si lo hubo.
    raw_waveform: dict[str, list[int]] = field(default_factory=dict)
    raw_sample_rate: float | None = None
    #: Espectro de amplitud del canal dominante: `(frecuencias_hz, amplitudes)`.
    spectrum: tuple[list[float], list[float]] | None = None
    spectrum_peak_hz: float | None = None
    #: [T-5.23] Espectrograma del MISMO canal dominante: tiempo × frecuencia, con
    #: escala RELATIVA. `None` cuando no hubo traza de la que calcularlo — y eso
    #: se declara con el mismo texto de ausencia que la onda cruda, no con un hueco.
    spectrogram: Espectrograma | None = None
    #: [T-3.14] Duración instrumental **medida** de la sacudida: D5-95 sobre la Intensidad
    #: de Arias del canal dominante. `None` cuando no se pudo medir — que NO es lo mismo
    #: que cero, y el reporte lo dice con palabras.
    shaking_duration: Duracion | None = None
    #: Por qué no hay onda cruda ni espectro, si es el caso.
    raw_unavailable_reason: str | None = None
    #: `basis` del dictamen vigente (T-2.42): qué umbral, con qué valor, de qué versión
    #: de reglas. Es lo que hace auditable el "por qué este veredicto" de la prosa.
    verdict_basis: dict = field(default_factory=dict)
    #: [T-7.17] La red de estaciones: qué midió cada una y qué le tocaba. Entra en
    #: ``content_sha256`` como todo lo demás — cambiar lo que el documento afirma
    #: sobre lo que midió otro inmueble tiene que mover la huella.
    estaciones: list[EstacionFila] = field(default_factory=list)
    #: Desde dónde se cuentan los arribos de arriba (`event` u `incident`). Sin
    #: declararlo, dos dictámenes con anclas distintas se comparan como si
    #: midieran lo mismo.
    estaciones_ancla: str = "incident"
    #: [T-7.22] ¿El evento enlazado es una reproducción de un sismo histórico?
    #:
    #: Se DERIVA de `seismic_events.meta->'reproduccion'` —lo que escribe el
    #: propio replay— y no de `incident_classifications.classification`, que la
    #: pone una PERSONA y que la reproducción no escribe. Las dos compiten: un
    #: incidente real clasificado a mano como reproducción no llevaría el rótulo,
    #: y uno vestido por el replay lo llevaría sin que nadie lo clasificara. Se
    #: elige la del evento porque es la misma que lee la consola, y papel y
    #: pantalla no pueden discrepar sobre si lo que se enseña ocurrió.
    reproduccion: bool = False
    #: Prosa opcional (T-2.42). El veredicto NO sale de aquí.
    narrative: list[tuple[str, str]] = field(default_factory=list)
    narrative_provider: str | None = None
    narrative_degraded: str | None = None
    #: [T-2.82] Marco normativo DECLARADO por el cliente (``compliance_labels``). Es
    #: la única parte del documento que TAKAB no midió ni verificó, y por eso viaja
    #: como documento con su propio estado de legibilidad en vez de como lista suelta.
    #: Entra en ``content_sha256``: cambiar lo que el dictamen afirma tiene que mover
    #: la huella. ⚠️ [T-7.43] La razón NO es «para poder comparar dos exportaciones»
    #: —eso no se puede y ya no se promete—: es que el número identifica ESTA
    #: exportación, y un campo que no lo moviera quedaría fuera de esa identidad.
    #: Lo vigila el censo derivado, no esta nota.
    compliance: ComplianceDocument = field(default_factory=ComplianceDocument)
    #: [T-3.12.c] CCTV: analítica de evacuación y cadena de custodia del vídeo. Entra en
    #: ``content_sha256`` como todo lo demás — cambiar lo que el documento afirma sobre
    #: cuánto tardó la gente en salir tiene que mover la huella.
    cctv: CctvBlock = field(default_factory=CctvBlock)

    #: [T-7.22] Los reportes de daños del brigadista, con sus fotografías. Entran
    #: en ``content_sha256`` como todo lo demás — sus HUELLAS, no sus bytes.
    danos: list[DanoFila] = field(default_factory=list)

    #: [T-7.24] El mapa de la sacudida. Entra en ``content_sha256`` como todo lo
    #: demás, y aquí importa especialmente: el residuo de un inmueble es una
    #: afirmación sobre cuánto sacudió comparado con lo previsible, y cambiarla
    #: tiene que mover la huella del documento que la firma.
    shakemap: ShakemapBlock = field(default_factory=ShakemapBlock)

    def content_sha256(self) -> str:
        """Huella del CONTENIDO (no del archivo): identifica qué se afirmó.

        El sha256 del PDF no puede imprimirse dentro de sí mismo; éste sí, y desde
        `T-7.42` va en la portada Y en el pie de todas las páginas.

        ⚠️ **La segunda frase de este docstring prometía «comparar dos
        exportaciones del mismo incidente sin abrirlas», y es FALSA**: medido en
        `T-7.43`, `generated_at` es campo del modelo, así que dos exportaciones
        separadas por un segundo dan huellas distintas y nunca coinciden. Se retira
        la promesa en vez de dejarla: elegir entre sacar `generated_at` del payload
        o decir qué identifica este número de verdad **es `T-7.43`**, y no se
        adelanta aquí. Lo que sí se puede decir hoy es lo que este número identifica
        con certeza: una exportación concreta. El del simulacro sí es estable
        (`drill_report.ReporteSimulacro.content_sha256`), porque su modelo no tiene
        reloj de generación.
        """
        return huella_de_contenido(self)


#: [T-5.26] Lo que se imprime donde va la huella de un objeto de evidencia.
#:
#: Existe como función —y no como un `or` en el sitio del render— porque la
#: regla que encierra es la que estuvo rota: el sha256 se imprimía a **32 de 64**
#: caracteres (y a 16 en la custodia del vídeo) mientras la portada del mismo
#: documento instruye verificarlo con `sha256sum`. Con medio hash no se puede, y
#: un dato inverificable presentado como verificable es peor que no imprimirlo:
#: quien lo intente concluirá que la evidencia está corrupta.
#:
#: No había razón de espacio: 64 hex miden 108.7 mm de los 133.9 que deja la
#: columna del PDF, así que caben en una sola línea.
SIN_HASH = "sin hash"


def huella_de_custodia(sha: str | None) -> str:
    """El sha256 ENTERO, o la ausencia declarada. Nunca un trozo."""
    return sha or SIN_HASH


# [T-7.35] El rótulo dice la BANDA, no de quién es el umbral.
#
# Decía «supera el umbral de actuación del inmueble» y afirmaba dos cosas que el
# documento no comprobaba: que el umbral era el de ese edificio —se clasificaba
# con la banda de fábrica— y que superarlo acciona algo, cuando desde `T-2.32`
# una detección instrumental sola NO mueve un relé. Los números y su procedencia
# los imprime `umbral_line()` en la línea de debajo, que es donde se pueden
# verificar.
FELT_LABELS: dict[str, str] = {
    "trip": "SACUDIDA FUERTE (supera el umbral de disparo)",
    "watch": "SACUDIDA MODERADA (supera el umbral de vigilancia)",
    "normal": "SACUDIDA LEVE (por debajo de los umbrales)",
    "unknown": "SIN MEDICIÓN DE SACUDIDA",
}


def umbral_line(u) -> str:  # noqa: ANN001 - felt.UmbralComparacion (import circular si se anota)
    """Contra qué números se clasificó la sacudida, y de dónde salieron.

    Va debajo de la BANDA porque es lo que la hace verificable: sin esta línea,
    «SACUDIDA FUERTE» es una palabra sin escala. Con `origen == 'referencia'` se
    DICE que son los de fábrica en vez de fingir que son los del edificio.
    """
    th = u.thresholds
    numeros = (
        f"PGA {th.pga_watch_g:.3f}/{th.pga_trip_g:.3f} g · "
        f"PGV {th.pgv_watch_cms:.1f}/{th.pgv_trip_cms:.1f} cm/s"
    )
    if u.origen == "inmueble":
        version = f" v{u.rule_set_version}" if u.rule_set_version is not None else ""
        return f"{numeros} · umbrales del inmueble{version}, vigentes en la apertura"
    return (
        f"{numeros} · banda de referencia: no consta configuración del inmueble "
        "anterior al incidente"
    )


LEAD_REASONS: dict[str, str] = {
    "not_sasmex": "no aplica: el incidente no se disparó por SASMEX",
    "no_peak": "no hubo pico medido en la ventana del incidente",
    "peak_before_alert": "el pico precedió a la alerta",
    # [T-7.35] No hubo sacudida que avisar: el pico de la ventana no superó el
    # umbral de vigilancia del inmueble. Presentar segundos de «aviso ganado»
    # sobre ruido ambiente es presumir un logro que no ocurrió.
    "sin_sacudida": "no aplica: la sacudida no superó el umbral de vigilancia del inmueble",
}


def cierre_text(closed_at: datetime | None, state: str, cierre_sin_hora: bool, fmt: str) -> str:
    """[T-7.51] Qué dice el papel en el campo CIERRE. Tres casos, no dos.

    Decía `"EN CURSO"` siempre que `closed_at` fuera nulo — y en la nube dev
    había TRES incidentes con `state='closed'` y la hora en nulo, así que **el
    dictamen pericial de un incidente cerrado afirmaba que seguía abierto**.

    El tercer caso no se rellena con una hora inventada: se DECLARA. La hora real
    de aquellos cierres no existe en ninguna parte, y fabricarla contaminaría la
    tabla de la que cuelga este documento — es la doctrina que `T-7.42` y
    `T-7.43` acaban de imponer en este mismo papel.
    """
    if closed_at is not None:
        return f"{closed_at:{fmt}}"
    if state == "closed":
        return "CERRADO · HORA DE CIERRE NO REGISTRADA"
    return "EN CURSO"


def lead_time_text(seconds: float | None, reason: str | None) -> str:
    """Tiempo de aviso ganado, o su ausencia explicada. Jamás '0 s' por defecto."""
    if seconds is not None:
        return f"{seconds:.1f} s"
    return f"NO CALCULABLE · {LEAD_REASONS.get(reason or '', reason or 'razón no registrada')}"
