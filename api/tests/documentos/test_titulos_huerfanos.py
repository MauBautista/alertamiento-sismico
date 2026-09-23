"""[T-8.12 · 2ª vuelta] Ningún título de sección se queda SOLO al pie de su página.

`section()` pintaba el título donde estuviera el cursor, y lo que venía detrás
—una tabla, un párrafo, una figura— decidía por su cuenta si saltaba de página.
Resultado, visto en el papel: «7. RED DE ESTACIONES» al pie de la página 2 con el
40 % de la hoja en blanco y su mapa en la 3, y —NUEVO en T-8.12, porque las filas
de la cronología ocupan dos renglones (UTC + local)— «13. CRONOLOGÍA DEL
INCIDENTE» al pie de la 3 con su tabla entera en la 4. Ninguna guarda lo veía:
las de geometría miden solapes y el pie, y un título huérfano no pisa nada.

## Cómo se mide

Con los dos espías que ya existen, a la vez: `espia_del_render` dice qué títulos
se emitieron y en qué orden; `cajas_impresas` dice en qué página cayó cada renglón
e imagen. Un título es huérfano si lo PRIMERO que se imprime después de él en el
cuerpo (sin cabecera ni pie) cae en otra página. Las figuras vectoriales no dejan
caja, pero si saltan de página arrastran con ellas el texto que las sigue, que sí
la deja.

El barrido desplaza el documento renglón a renglón (más o menos acciones en la
cronología) para que cada título caiga, en algún caso, cerca del pie.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from takab_api.dictamen.model import ActionRow
from takab_api.dictamen.pdf import render
from takab_api.documentos import membrete
from tests.dictamen.test_fotos_en_el_papel import _dano, _foto
from tests.dictamen.test_pdf import _OPENED, model
from tests.documentos.cajas_de_texto import cajas_impresas
from tests.documentos.espia import espia_del_render
from tests.documentos.test_geometria import _modelo_con_todas_las_figuras


def _huerfanos(m, variante: str = "technical") -> list[str]:  # noqa: ANN001 - ReportModel
    with espia_del_render() as esp, cajas_impresas() as cap:
        render(m, variante)
    rotulos = [f"{n}. {t}" if n else t for n, t in zip(esp.numeros, esp.titulos, strict=True)]
    assert rotulos, "el render no emitió ningún título: la guarda aprobaría sobre la nada"
    tope = membrete.PAGE_H - membrete.PIE_MM + 0.5
    cuerpo = [c for c in cap.cajas if c.y0 >= membrete.CUERPO_Y - 1 and c.y1 <= tope]
    huerfanos: list[str] = []
    i = 0
    for rotulo in rotulos:
        while i < len(cuerpo) and not (cuerpo[i].clase == "texto" and cuerpo[i].texto == rotulo):
            i += 1
        assert i < len(cuerpo), f"no encuentro impreso el título {rotulo!r}"
        titulo = cuerpo[i]
        siguiente = cuerpo[i + 1] if i + 1 < len(cuerpo) else None
        if siguiente is None or siguiente.pagina != titulo.pagina:
            huerfanos.append(f"{rotulo!r} (pág. {titulo.pagina}, y = {titulo.y1:.0f} mm)")
        i += 1
    return huerfanos


def _acciones(n: int) -> list[ActionRow]:
    return [ActionRow(_OPENED + timedelta(seconds=i), "siren_on", "system:edge") for i in range(n)]


@pytest.mark.parametrize("n", range(0, 26))
def test_NINGUN_titulo_del_tecnico_se_queda_solo_al_pie(n: int) -> None:
    assert not _huerfanos(model(actions=_acciones(n)))


@pytest.mark.parametrize("n", range(0, 26, 2))
def test_NINGUN_titulo_se_queda_solo_con_UNA_foto_por_reporte(n: int) -> None:
    """El caso que el verificador vio: 06-una-foto, pág. 3, «13. CRONOLOGÍA»."""
    danos = [_dano([_foto(3)]), _dano([_foto(5)], report_id="d-2")]
    assert not _huerfanos(model(actions=_acciones(n), danos=danos))


@pytest.mark.parametrize("n", range(0, 26, 2))
def test_NINGUN_titulo_se_queda_solo_con_TODAS_las_figuras(n: int) -> None:
    from dataclasses import replace  # noqa: PLC0415

    assert not _huerfanos(replace(_modelo_con_todas_las_figuras(), actions=_acciones(n)))


@pytest.mark.parametrize("n", range(0, 26, 5))
def test_NINGUN_titulo_del_EJECUTIVO_se_queda_solo_al_pie(n: int) -> None:
    assert not _huerfanos(model(actions=_acciones(n)), "executive")
