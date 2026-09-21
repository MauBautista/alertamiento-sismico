"""[T-7.22] Preparar una foto del brigadista para meterla en un documento firmado.

Módulo PURO: entra `bytes`, sale `bytes` y una razón cuando no se pudo. No sabe
de S3, no sabe de PDF y no levanta nunca — se prueba sin red y sin renderizar.

## Las cinco cosas que hace, y por qué cada una

**1. Acota la entrada ANTES de abrirla.** La foto la sube el dispositivo por un
PUT presignado directo a S3 (`routers/_s3.py`), donde no hay tope de tamaño
posible: la API nunca ve esos bytes y el render es lo PRIMERO que los abre. Sin
cota, una bomba de descompresión se decodifica dentro del contenedor que sirve
la consola. Y una bomba que TRIUNFA no levanta ninguna excepción, así que un
`except Exception` no basta: hace falta el límite de píxeles de Pillow.

**2. No le cree a la extensión.** El `s3_key` termina en `.jpg` porque lo puso
quien pidió la URL (`routers/mobile_incident.py`), no porque nadie lo mirara. El
formato se olfatea con Pillow.

**3. Endereza con `exif_transpose`.** MEDIDO: una foto de retrato con
`Orientation=6` entra como 800×600 y sale 600×800. Sin esto, las fotos de un
brigadista —que fotografía de pie— salen tumbadas en el documento que se entrega.

**4. Reencoda SIN pasar `exif=`, y eso es una medida de privacidad, no una
optimización.** MEDIDO: embebiendo el JPEG tal cual, la marca del teléfono y la
cadena de ubicación del EXIF quedan **dentro del PDF**. `damage_reports` lo puede
leer un `gov_operator` (`app_gov_can_see`) y el informe es exportable: eso es
mandarle a un tercero el modelo de teléfono y las coordenadas de quien fotografió.
Reencodar lo quita. Hay prueba propia para que nadie «optimice» al passthrough
para ahorrar CPU y lo reabra sin enterarse.

**5. Acota por BYTES, no solo por píxeles.** Un tope en píxeles NO es un tope de
tamaño: un JPEG de 1024² a calidad 80 va de ~26 KB con contenido plano a
centenares de KB con alta entropía, y seis de ésos hinchan el documento varios
megas. Se baja la calidad por pasos hasta entrar en el presupuesto, y si aun así
no cabe se DECLARA — el papel dice que esa foto no cupo, en vez de entregar un
documento de 4 MB sin avisar.

## Lo que NO hace, a propósito

No verifica el `sha256` declarado: eso lo decide quien llame, porque necesita
saber qué hacer con el desajuste. Y no recorta ni retoca: una foto de evidencia
que se recorta deja de ser la foto.

## El lado que le importa a otra ficha

`1024 px` es el mismo lado al que `D-32` manda redimensionar las fotos que ve la
IA (`T-7.27`). Se comparte a propósito: la capa narrativa PARTE de esta misma
derivada en vez de bajarse otra copia de S3 con otros parámetros.

⚠️ [T-7.27·A] Lo que ya no es cierto —y aquí estaba escrito— es que la huella de lo
impreso sea la de lo que ve el modelo. La fotografía que sale hacia el proveedor
lleva tapada la banda de la marca de agua forense (`narrative/marca.py`), que es
píxel y no metadato, así que sus bytes son otros. La trazabilidad no se pierde: la
procedencia anota las DOS huellas, la de lo enviado y la de lo impreso.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from PIL import Image, ImageOps

#: Lado mayor de la derivada, en píxeles. Compartido con `D-32`/`T-7.27`.
LADO_MAX = 1024

#: Tope de bytes de ENTRADA. Por encima ni se abre: es el único punto del sistema
#: donde alguien mira esos bytes, y abrirlos es lo caro.
MAX_BYTES_ENTRADA = 25 * 1024 * 1024

#: Tope de píxeles a decodificar. Pillow avisa por encima de su propio umbral,
#: pero sólo LEVANTA si se le pone éste. Una imagen de 100 MP son ~300 MB de RGB
#: en vuelo por foto.
MAX_PIXELES = 40_000_000

#: Presupuesto de bytes de la derivada, y la escalera de calidad con la que se
#: alcanza. MEDIDO sobre 1024² con contenido sintético de tres densidades:
#:
#: | contenido            | q80  | q70  | q60  | q50  | q40  |
#: |----------------------|------|------|------|------|------|
#: | liso                 |  25K |  19K |  17K |  16K |  16K |
#: | moderado             | 124K |  84K |  65K |  52K |  42K |
#: | denso                | 202K | 161K | 132K | 116K | 102K |
#:
#: Una fotografía de una grieta o un plafón caído cae entre «moderado» y
#: «denso». El presupuesto se fija en 150 KB para que la escalera se EJERZA con
#: contenido realista en vez de ser decorativa, y la primera calidad es la que da
#: buena lectura en papel.
CALIDADES = (80, 70, 60, 50, 40)
MAX_BYTES_SALIDA = 150 * 1024

#: Fotografías por reporte que entran en el documento. El número es el de `D-32`
#: —tomado prestado, no decidido allí para el PDF: aquélla acota lo que ve la IA—
#: y la razón de compartirlo es más fuerte que el número en sí. Si el PDF derivara
#: su propia copia con otros parámetros, la MISMA fotografía tendría dos huellas
#: derivadas y la «huella de lo impreso» del papel no casaría con la que vio el
#: modelo en `T-7.27`.
MAX_FOTOS_POR_REPORTE = 6

#: Tope de fotografías para el documento ENTERO. Sin él, el tamaño crece con el
#: número de reportes y no hay cota: `report_rate_user_per_min = 6` pasa a
#: proteger un objeto de varios megas. Lo que no cabe se DECLARA.
MAX_BYTES_FOTOS_DOCUMENTO = 4 * 1024 * 1024

#: Razones de que una foto no llegue al papel. Son las que el documento imprime,
#: así que se declaran aquí y no se escriben sueltas en el render.
NO_LEGIBLE = "FORMATO NO LEGIBLE"
DEMASIADO_GRANDE = "ARCHIVO POR ENCIMA DEL TOPE DE LECTURA"
NO_CABE = "NO CABE EN EL PRESUPUESTO DE LA PÁGINA"
#: El documento llegó a su tope global de imágenes antes que a esta foto.
DOCUMENTO_LLENO = "PRESUPUESTO DE IMÁGENES DEL DOCUMENTO AGOTADO"
SIN_BLOB = "BLOB AUSENTE EN EL ALMACÉN DE EVIDENCIA"


@dataclass(frozen=True, slots=True)
class Derivada:
    """Lo impreso, o la razón de que no lo esté. Nunca las dos vacías."""

    #: Los bytes JPEG a embeber. `None` si no se pudo.
    jpeg: bytes | None
    ancho: int | None
    alto: int | None
    #: sha256 de lo IMPRESO. Va al modelo, no los bytes: sin él, dos informes del
    #: mismo incidente con fotografías distintas imprimirían el MISMO
    #: «SHA-256 DEL CONTENIDO» en el pie, que es justo el número que el documento
    #: manda verificar.
    sha256: str | None
    #: Por qué no hay imagen, si es el caso. Se imprime.
    motivo: str | None = None

    @property
    def ok(self) -> bool:
        return self.jpeg is not None


def _fallo(motivo: str) -> Derivada:
    return Derivada(jpeg=None, ancho=None, alto=None, sha256=None, motivo=motivo)


def preparar(crudo: bytes | None) -> Derivada:
    """Deja una foto lista para el papel, o dice por qué no pudo.

    No levanta nunca: una excepción aquí tumbaría la exportación entera por una
    foto ilegible, y el criterio del endpoint es el contrario — un fallo de S3
    degrada la sección, nunca tumba el documento.
    """
    if not crudo:
        return _fallo(SIN_BLOB)
    if len(crudo) > MAX_BYTES_ENTRADA:
        return _fallo(DEMASIADO_GRANDE)

    limite_previo = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = MAX_PIXELES
    try:
        with Image.open(io.BytesIO(crudo)) as im:
            # `exif_transpose` antes de nada: si no, se encoge la foto tumbada y
            # se gira un original que ya perdió resolución.
            enderezada = ImageOps.exif_transpose(im) or im
            enderezada = enderezada.convert("RGB")
            enderezada.thumbnail((LADO_MAX, LADO_MAX), Image.LANCZOS)
            for calidad in CALIDADES:
                buf = io.BytesIO()
                # Sin `exif=`: es lo que deja fuera la marca del teléfono y las
                # coordenadas. Sin `optimize`, que no es determinista entre
                # versiones de libjpeg y este PDF es evidencia.
                enderezada.save(buf, format="JPEG", quality=calidad)
                datos = buf.getvalue()
                if len(datos) <= MAX_BYTES_SALIDA:
                    return Derivada(
                        jpeg=datos,
                        ancho=enderezada.width,
                        alto=enderezada.height,
                        sha256=hashlib.sha256(datos).hexdigest(),
                    )
            return _fallo(NO_CABE)
    except Exception:  # noqa: BLE001 - cualquier cosa ilegible es lo mismo para el papel
        return _fallo(NO_LEGIBLE)
    finally:
        Image.MAX_IMAGE_PIXELS = limite_previo
