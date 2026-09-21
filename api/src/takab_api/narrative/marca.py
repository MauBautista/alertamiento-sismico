"""[T-7.27·A] La marca de agua forense va DIBUJADA EN EL PÍXEL, y por eso se tapa.

## El defecto que cierra este módulo

`documentos/fotos.preparar` quita el EXIF —está medido y tiene su prueba— y con eso la
capa narrativa daba por hecho que la fotografía que sale hacia el proveedor no lleva
identificadores. **Es falso, y lo es de la peor manera: por los píxeles.** La cámara
forense del móvil hornea la marca DENTRO del bitmap (`mobile/src/app/camera.tsx`
compone el `View` y `view-shot` lo captura), y entre sus líneas van exactamente los dos
identificadores que la allowlist de texto de `redact.py` existe para retener:

* ``GPS 19.43260, -99.13320`` — las coordenadas del inmueble a cinco decimales
  (`watermark.ts::fmtGps`);
* ``OP 9f1e4a2c · SHA-256`` — los ocho primeros hex del ``sub`` de Cognito del operador
  táctico (`watermark.ts::watermarkLines`).

Re-encodar quita el EXIF y **no quita lo que está pintado encima**. La contradicción era
del sistema consigo mismo: `test_de_la_estacion_vecina_NO_sale…` afirma «"19.43" not in
payload» sobre el JSON mientras la misma petición llevaba esas cifras renderizadas en
una imagen, a un tercero y fuera del país.

## Lo que se hace, y por qué así

La fotografía sale con **la banda inferior TAPADA**. La banda no se adivina: se calcula
con la geometría que el propio móvil declara, y lo que la guarda comprueba no es la
fórmula sino **los píxeles** — `tests/narrative/test_la_marca_no_viaja_en_el_pixel.py`
compone una captura sin marca y la misma con marca, DERIVA qué región cambió y exige que
el tapado la cubra entera. Un tapado por geometría tecleada es el censo ciego de siempre:
el día que la marca se mueva, fallaría en silencio y la fuga volvería.

**La banda se mide sobre el ANCHO, no sobre el alto.** Es la única de las dos dimensiones
que se puede anclar: la marca está dimensionada en `dp` y la única cota dura que existe
sobre los `dp` de un teléfono es el ancho mínimo de pantalla en el que Android da por
soportada una aplicación (``sw320dp``). El alto de la zona capturada depende de cuánto
ocupen los controles debajo del visor y no hay cota ninguna.

**Y lo que no quepa, no se manda.** Si con esta cuenta la banda se comiera más de
`1 - MINIMO_VISIBLE` de la fotografía —una captura cuadrada, una apaisada, un teléfono
fuera del supuesto— no se envía nada y el hueco se declara en los hechos
(`DanoRedactado.fotos_no_adjuntas`). Es la regla que pidió el integrador: si algún píxel
de la marca puede quedar fuera del tapado, la foto no sale.

## Lo que este módulo NO puede afirmar, y hay que decirlo

La escala tipográfica del sistema (`fontScale`) multiplica el alto del texto y **no viaja
con la fotografía**: no hay forma de leerla desde la nube. Por eso `ESCALA_MAXIMA` es el
techo de la plataforma (Android 14 llega al 200 %) y no una medición del aparato: se tapa
como si SIEMPRE estuviera en ese techo. Es deliberadamente generoso —en un teléfono con
la escala de fábrica el tapado se lleva bastante más que la marca— porque la alternativa
es tapar lo justo para el caso típico y filtrar en silencio en el resto.

Tampoco se afirma nada sobre el interlineado exacto de Android: `ALTO_DE_LINEA` es una
cota declarada sobre el espaciado de la tipografía del sistema, no una medición del
render de Android, que no se puede hacer desde aquí. Lo que sí se mide, y es lo que
sostiene la decisión, es que **el tapado contiene a la región que la marca cambia** para
la geometría que el móvil declara.
"""

from __future__ import annotations

import io
import logging
import math
from dataclasses import dataclass

from PIL import Image, ImageDraw

from takab_api.documentos import fotos as fotos_mod

log = logging.getLogger("takab_api.narrative")

# ── la geometría de la marca, con la procedencia de cada número ───────────────

#: Líneas que compone `watermark.ts::watermarkLines`, como máximo. Son cinco fijas
#: («TAKAB AILERT · EVIDENCIA FORENSE», el instante, el GPS, el PGA y la línea del
#: operador) más la advertencia condicional de metadatos retenidos (`T-2.118`).
LINEAS_MAX = 6

#: `fontSize.xs` de `mobile/src/ui/theme.ts`, que sale de `--tk-text-xs`.
TEXTO_DP = 11.0
#: `padding: space[2]` del estilo `watermark` (arriba y abajo).
PADDING_DP = 8.0
#: `gap: 2` entre líneas.
GAP_DP = 2.0
#: `bottom: space[3]`: lo que la caja se separa del borde inferior de la captura.
OFFSET_DP = 12.0

#: Cota del interlineado. Android compone un `Text` sin `lineHeight` explícito con el
#: espaciado recomendado de la tipografía —del orden de 1.2 para Roboto— y aquí se toma
#: 1.4 para que la cuenta siga siendo cierta con otra fuente del sistema. **No es una
#: medición del render de Android**: es un techo declarado, y así se dice.
ALTO_DE_LINEA = 1.4

#: Techo de la escala tipográfica del sistema. El `Text` de la marca no lleva
#: `allowFontScaling={false}`, así que el ajuste de accesibilidad la multiplica; Android
#: 14 llega al 200 %. No viaja con la fotografía: se tapa como si siempre estuviera ahí.
ESCALA_MAXIMA = 2.0

#: Ancho de pantalla, en `dp`, por debajo del cual Android no da por soportada una
#: aplicación de teléfono (`sw320dp`). Es la única cota dura que permite convertir `dp`
#: a píxeles sin conocer el aparato: cuanto más estrecha se supone la pantalla, más
#: píxeles por `dp` y más generoso el tapado.
ANCHO_MINIMO_DP = 320.0

#: Alto de la banda en `dp`, DERIVADO de todo lo anterior. Tecleado se quedaría viejo en
#: cuanto la marca ganara una línea — que es exactamente lo que le pasó en `T-2.118`.
ALTO_BANDA_DP = (
    OFFSET_DP
    + 2 * PADDING_DP
    + LINEAS_MAX * TEXTO_DP * ESCALA_MAXIMA * ALTO_DE_LINEA
    + (LINEAS_MAX - 1) * GAP_DP
)

#: Lo que hay que tapar, en fracción del ANCHO de la imagen. Ver el docstring del módulo
#: para por qué el ancho y no el alto.
FRACCION_DEL_ANCHO = ALTO_BANDA_DP / ANCHO_MINIMO_DP

#: Fracción del alto que tiene que QUEDAR a la vista para que valga la pena mandar la
#: fotografía. Por debajo no se manda: una captura apaisada o cuadrada —que esta cámara
#: no debería producir, porque la app está fijada en vertical (`mobile/app.json`)— saldría
#: casi entera tapada, y mandar una franja negra a un tercero es pagar la fuga potencial
#: sin recibir nada a cambio.
MINIMO_VISIBLE = 0.4

#: Tinta del tapado. Opaca y plana: no se difumina ni se pixela nada, porque un
#: difuminado deja legible lo que tapa a poco que alguien lo realce.
TINTA = (0, 0, 0)

#: Por qué una fotografía no llegó a salir. Son CÓDIGOS cortos —no frases de librería—
#: porque acaban en el log y en la cuenta de `fotos_no_adjuntas`.
BANDA_NO_CABE = "la banda de la marca se comería la fotografía"
NO_LEGIBLE = "la derivada no se pudo abrir para tapar la marca"
NO_ADELGAZA = "la fotografía tapada no baja del peso permitido"


@dataclass(frozen=True, slots=True)
class Tapada:
    """La fotografía lista para salir, o la razón de que no salga. Nunca las dos."""

    #: Los bytes que VIAJAN. `None` si no se pudo tapar.
    jpeg: bytes | None
    #: Alto de la banda tapada, en píxeles. Es lo que la guarda contrasta contra la
    #: región que la marca cambia de verdad.
    alto_banda_px: int | None
    motivo: str | None = None

    @property
    def ok(self) -> bool:
        return self.jpeg is not None


def _fallo(motivo: str) -> Tapada:
    return Tapada(jpeg=None, alto_banda_px=None, motivo=motivo)


def alto_de_la_banda(ancho_px: int) -> int:
    """Cuántos píxeles hay que tapar desde abajo, para una imagen de este ancho."""
    return math.ceil(FRACCION_DEL_ANCHO * ancho_px)


def tapar_banda_forense(jpeg: bytes | None) -> Tapada:
    """Tapa la banda de la marca de agua. No levanta nunca.

    El re-encodado es inevitable —pintar encima es cambiar los píxeles— y con él la
    fotografía que ve el modelo **deja de tener la huella que publica el papel**. Eso no
    se esconde: `redact.ImagenAdjunta` lleva las DOS huellas y la procedencia registra la
    de lo que salió, que es la única que alguien puede verificar contra el tercero.

    Se exige además que la tapada **no pese más que la impresa ni más que el techo por
    fotografía** (`documentos/fotos.MAX_BYTES_SALIDA`): el presupuesto de bytes de
    `redact.imagenes_de` se cobra sobre lo que viaja, y una tapada más gorda que su
    original volvería a dejar el peso de la petición sin cota por arriba. Lo segundo no
    es redundante: un blob que pasó la verificación de derivada puede ser legítimo y
    pesar el triple de lo que `preparar` produce —lo hace cualquier JPEG de 1024 px
    guardado a calidad 100— y el techo por foto es lo único que lo acota.
    """
    if not jpeg:
        return _fallo(NO_LEGIBLE)
    try:
        with Image.open(io.BytesIO(jpeg)) as abierta:
            plana = abierta.convert("RGB")
        ancho, alto = plana.size
        banda = alto_de_la_banda(ancho)
        if banda > alto * (1.0 - MINIMO_VISIBLE):
            return _fallo(BANDA_NO_CABE)
        ImageDraw.Draw(plana).rectangle((0, alto - banda, ancho, alto), fill=TINTA)
        techo = min(len(jpeg), fotos_mod.MAX_BYTES_SALIDA)
        for calidad in fotos_mod.CALIDADES:
            buf = io.BytesIO()
            # Sin `exif=` y sin `optimize`, por las dos razones de `documentos/fotos.py`:
            # lo primero es la medida de privacidad, lo segundo que esto es evidencia y
            # `optimize` no es determinista entre versiones de libjpeg.
            plana.save(buf, format="JPEG", quality=calidad)
            datos = buf.getvalue()
            if len(datos) <= techo:
                return Tapada(jpeg=datos, alto_banda_px=banda)
        return _fallo(NO_ADELGAZA)
    except Exception:  # noqa: BLE001 - lo que no se puede tapar, no sale
        return _fallo(NO_LEGIBLE)
