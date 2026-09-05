"""El icono de la página de acuse va EMBEBIDO, y llega entero.

La API no expone rutas estáticas, así que un `<link rel=icon href="/algo.png">`
apuntaría a una ruta que no existe —o peor, al SPA, que devolvería su `index.html`
con 200 y un `Content-Type` de HTML—. Por eso el icono viaja como `data:` dentro
de la propia página. Es la misma familia de defecto que cazó
`test_acuse_formulario_alcanzable.py`: la página se pinta, y lo que cuelga de ella
apunta a otro sitio.

Lo que se comprueba es que el blob **decodifica a un PNG de verdad**, no solo que
la cadena esté. Un base64 truncado al editar deja el atributo puesto y el icono
roto, y eso no se ve en ninguna prueba de la ruta.
"""

from __future__ import annotations

import base64
import re

from takab_api.routers import ops_alerts

_PNG_MAGICO = b"\x89PNG\r\n\x1a\n"


def _icono_embebido() -> bytes:
    hallado = re.search(
        r'<link rel="icon" href="data:image/png;base64,([A-Za-z0-9+/=]+)">',
        ops_alerts._PAGINA,
    )
    assert hallado is not None, "la página de acuse no lleva icono embebido"
    return base64.b64decode(hallado.group(1), validate=True)


def test_el_icono_es_un_png_valido_y_completo() -> None:
    crudo = _icono_embebido()
    assert crudo[:8] == _PNG_MAGICO, "el base64 no decodifica a un PNG"
    ancho = int.from_bytes(crudo[16:20], "big")
    alto = int.from_bytes(crudo[20:24], "big")
    assert (ancho, alto) == (16, 16), f"el icono mide {ancho}x{alto}"
    # El bloque IEND cierra el PNG: si el base64 se truncó, no está.
    assert crudo.rstrip().endswith(b"IEND\xaeB`\x82"), "el PNG llegó truncado"


def test_el_icono_no_se_pide_por_una_ruta_que_la_api_no_sirve() -> None:
    """Ningún `href` de icono puede ser una ruta: la API no sirve estáticos."""
    for href in re.findall(r'<link rel="icon" href="([^"]+)"', ops_alerts._PAGINA):
        assert href.startswith("data:"), f"icono por ruta, y la API no la sirve: {href}"


def test_la_pagina_nombra_el_producto() -> None:
    assert "<title>TAKAB Ailert · acuse de guardia</title>" in ops_alerts._PAGINA
