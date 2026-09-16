"""[T-7.22] La foto que entra en un documento firmado, y lo que NO puede llevar dentro.

Módulo puro, así que estas pruebas no tocan S3 ni renderizan un PDF. Lo que fijan,
por orden de lo que costaría equivocarse:

1. **La privacidad no es un efecto colateral de redimensionar.** Hoy el EXIF se
   pierde porque se reencoda; sin una prueba que lo diga, el día que alguien
   «optimice» al passthrough para ahorrar CPU vuelve el agujero — y `damage_reports`
   lo puede leer un `gov_operator`.
2. **Un tope de píxeles no es un tope de bytes.**
3. **La entrada es hostil por construcción**: llega por un PUT presignado directo a
   S3 que nadie inspecciona, y el render es lo primero que la abre.
4. **El determinismo**, porque el PDF es evidencia y su sha256 se registra.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys

import pytest
from PIL import Image

from takab_api.documentos.fotos import (
    CALIDADES,
    DEMASIADO_GRANDE,
    LADO_MAX,
    MAX_BYTES_ENTRADA,
    MAX_BYTES_SALIDA,
    NO_LEGIBLE,
    SIN_BLOB,
    preparar,
)

MARCA = "TAKAB-Pixel8Pro"
#: Sin acentos ni signos altos a propósito: `ImageDescription` se escribe como
#: ASCII y un carácter que no sobreviva al viaje haría fallar la guarda de
#: no-vacuidad por el motivo equivocado.
LUGAR = "GPS 19.4326N 99.1332W domicilio del cliente"


def _foto(w: int = 1600, h: int = 1200, *, exif: bool = True, ruido: int = 5) -> bytes:
    """Una foto sintética REPRODUCIBLE, con el EXIF que pone un teléfono.

    El patrón no es aleatorio: dos corridas tienen que dar los mismos bytes o la
    prueba de determinismo mediría el generador, no el módulo.
    """
    im = Image.new("RGB", (w, h), (120, 90, 60))
    px = im.load()
    for y in range(0, h, ruido):
        for x in range(0, w, ruido):
            px[x, y] = ((x * 7) % 256, (y * 13) % 256, (x + y) % 256)
    buf = io.BytesIO()
    if exif:
        datos = Image.Exif()
        datos[0x010F] = MARCA  # Make
        datos[0x0110] = "Pixel 8 Pro"  # Model
        datos[0x0112] = 6  # Orientation: el teléfono estaba de pie
        datos[0x010E] = LUGAR  # ImageDescription: Pillow lo escribe como ASCII plano
        im.save(buf, format="JPEG", quality=92, exif=datos)
    else:
        im.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


# ───────────────────────────── 0 · las guardas de no-vacuidad, que sostienen el resto


def test_la_foto_de_prueba_SI_lleva_lo_que_hay_que_quitar() -> None:
    """Sin esto, la prueba de privacidad pasaría sobre una foto que nunca tuvo EXIF.

    Es el modo de fallo más barato de cometer y el más difícil de ver: un
    `assert MARCA not in salida` es verde tanto si el módulo limpia como si la
    entrada estaba limpia.
    """
    crudo = _foto()
    assert MARCA.encode() in crudo, "la foto de prueba no lleva la marca del teléfono"
    assert LUGAR.encode() in crudo, "la foto de prueba no lleva la cadena de ubicación"
    assert Image.open(io.BytesIO(crudo)).getexif().get(0x0112) == 6


# ────────────────────────────────────────────────────────────── 1 · privacidad


def test_la_derivada_NO_lleva_la_marca_del_telefono_ni_el_LUGAR() -> None:
    """MEDIDO que el passthrough SÍ los mete en el PDF entregado.

    `damage_reports` lo lee también un `gov_operator` (`app_gov_can_see`) y el
    informe es exportable: embeber el original tal cual es mandarle a un tercero
    el modelo de teléfono y las coordenadas de quien fotografió. Esta prueba es lo
    único que impide que una «optimización» futura lo reabra.
    """
    d = preparar(_foto())
    assert d.ok and d.jpeg is not None
    assert MARCA.encode() not in d.jpeg
    assert LUGAR.encode() not in d.jpeg
    assert b"Exif" not in d.jpeg[:2048], "quedó una cabecera EXIF en la derivada"


def test_la_orientacion_del_EXIF_se_APLICA_antes_de_perderla() -> None:
    """Un brigadista fotografía de pie. Sin `exif_transpose` la evidencia sale
    tumbada — y al quitar el EXIF ya no hay forma de enderezarla después.

    MEDIDO: 1600×1200 con `Orientation=6` tiene que salir más alta que ancha.
    """
    d = preparar(_foto(1600, 1200))
    assert d.ok
    assert d.alto is not None and d.ancho is not None
    assert d.alto > d.ancho, (
        f"la foto de retrato salió {d.ancho}×{d.alto}: se perdió la orientación del EXIF"
    )


def test_sin_orientacion_declarada_NO_se_gira_nada() -> None:
    """El lado negativo: girar una foto que ya estaba derecha es el mismo defecto
    al revés."""
    d = preparar(_foto(1600, 1200, exif=False))
    assert d.ok
    assert d.ancho is not None and d.alto is not None
    assert d.ancho > d.alto


# ──────────────────────────────────────────────── 2 · los topes, en píxeles y en bytes


def test_la_derivada_cabe_en_el_LADO_maximo() -> None:
    d = preparar(_foto(4000, 3000, exif=False))
    assert d.ok
    assert max(d.ancho or 0, d.alto or 0) == LADO_MAX


def test_una_foto_de_ALTA_ENTROPIA_tambien_cabe_en_BYTES() -> None:
    """Un tope de píxeles NO es un tope de tamaño.

    Con ruido en cada píxel, un JPEG de 1024² a calidad 80 se dispara; el módulo
    tiene que bajar la calidad hasta entrar en el presupuesto. Sin esto, seis
    fotos de un solo reporte hinchan el documento varios megas sin que nada avise.
    """
    d = preparar(_foto(2000, 2000, exif=False, ruido=2))
    assert d.ok and d.jpeg is not None
    assert len(d.jpeg) <= MAX_BYTES_SALIDA, (
        f"la derivada pesa {len(d.jpeg)} B y el presupuesto es {MAX_BYTES_SALIDA} B"
    )


def test_el_presupuesto_de_bytes_MUERDE_de_verdad() -> None:
    """Guarda de no-vacuidad del tope: si la primera calidad ya entrara siempre,
    la prueba de arriba no estaría midiendo el escalonado.

    Se comprueba que la foto de alta entropía NO cabría a la primera calidad, que
    es lo que obliga a bajar.
    """
    im = Image.open(io.BytesIO(_foto(2000, 2000, exif=False, ruido=2)))
    im.thumbnail((LADO_MAX, LADO_MAX), Image.LANCZOS)
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="JPEG", quality=CALIDADES[0])
    assert len(buf.getvalue()) > MAX_BYTES_SALIDA, (
        "la foto de prueba ya cabe a la primera calidad: el escalonado no se ejerce "
        "y `test_una_foto_de_ALTA_ENTROPIA_tambien_cabe_en_BYTES` no mide nada"
    )


# ────────────────────────────────────────────── 3 · la entrada es hostil, y no levanta


def test_un_archivo_ENORME_no_se_llega_a_abrir() -> None:
    """Abrir es lo caro. El tope se aplica ANTES de `Image.open`, que es lo que
    convierte una bomba en un rechazo barato."""
    d = preparar(b"\xff\xd8\xff" + b"\x00" * (MAX_BYTES_ENTRADA + 1))
    assert not d.ok
    assert d.motivo == DEMASIADO_GRANDE


@pytest.mark.parametrize(
    "basura",
    [
        pytest.param(b"", id="vacio"),
        pytest.param(b"no soy una imagen", id="texto"),
        pytest.param(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, id="png-truncado"),
    ],
)
def test_una_entrada_ILEGIBLE_se_declara_y_NO_levanta(basura: bytes) -> None:
    """Una excepción aquí tumbaría la exportación entera por una foto rota, y el
    criterio del endpoint es el contrario: degradar la sección, nunca el documento."""
    d = preparar(basura)
    assert not d.ok
    assert d.motivo in (NO_LEGIBLE, SIN_BLOB)


def test_un_blob_AUSENTE_se_distingue_de_uno_ilegible() -> None:
    """No es lo mismo «S3 no lo tiene» que «lo tiene y no se puede leer», y el
    papel imprime cuál de las dos."""
    assert preparar(None).motivo == SIN_BLOB


def test_NO_se_le_cree_a_la_extension() -> None:
    """El `.jpg` del `s3_key` lo puso quien pidió la URL presignada, no un lector.

    Un PNG subido con nombre de JPEG tiene que salir igualmente como JPEG en el
    papel, no rechazarse por una etiqueta.
    """
    im = Image.new("RGB", (900, 700), (10, 120, 200))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    d = preparar(buf.getvalue())
    assert d.ok and d.jpeg is not None
    assert d.jpeg[:3] == b"\xff\xd8\xff", "la derivada no salió como JPEG"


# ───────────────────────────────────────────────────────────── 4 · determinismo


def test_la_misma_foto_da_los_MISMOS_bytes() -> None:
    crudo = _foto()
    a, b = preparar(crudo), preparar(crudo)
    assert a.jpeg == b.jpeg
    assert a.sha256 == b.sha256


def test_dos_fotos_DISTINTAS_dan_huellas_distintas() -> None:
    """Es lo que hace que el `content_sha256` del pie signifique algo: sin huella
    de la derivada en el modelo, dos informes del mismo incidente con fotografías
    distintas imprimirían el MISMO hash — y es el número que el papel manda
    verificar."""
    a = preparar(_foto(1600, 1200, exif=False))
    b = preparar(_foto(1600, 1200, exif=False, ruido=9))
    assert a.ok and b.ok
    assert a.sha256 != b.sha256


def test_el_determinismo_aguanta_ENTRE_PROCESOS() -> None:
    """La prueba de arriba corre en un proceso con Pillow ya cargada.

    Esto es lo que T-7.21 midió para el membrete y lo que aquí importa más,
    porque el encodador JPEG es código nativo: si su salida dependiera del estado
    del proceso, el sha256 de un dictamen no sería reproducible por la
    contraparte que lo verifique.
    """
    guion = (
        "import io,sys,hashlib;"
        "sys.path.insert(0,'src');"
        "from PIL import Image;"
        "from takab_api.documentos.fotos import preparar;"
        "im=Image.new('RGB',(1600,1200),(120,90,60));"
        "px=im.load();"
        "[px.__setitem__((x,y),((x*7)%256,(y*13)%256,(x+y)%256))"
        " for y in range(0,1200,5) for x in range(0,1600,5)];"
        "b=io.BytesIO();im.save(b,format='JPEG',quality=92);"
        "print(preparar(b.getvalue()).sha256)"
    )
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    salidas = {
        subprocess.run(  # noqa: S603
            [sys.executable, "-c", guion], cwd=raiz, capture_output=True, text=True, check=True
        ).stdout.strip()
        for _ in range(2)
    }
    assert len(salidas) == 1, f"dos procesos dieron huellas distintas: {salidas}"
    assert salidas != {""}, "el subproceso no imprimió nada: la prueba está ciega"
