"""[T-8.12 · A-146] Ningún rótulo de `field()` se monta sobre su valor.

`MembretePDF.field()` dibuja el rótulo con `cell(52, …)`, que no envuelve ni
recorta. Ningún test medía el ancho de los rótulos —la guarda de geometría es
ciega al texto—, y el reporte de simulacro ya había pagado este defecto una vez
(«SITIOS SIN GABINETE COMANDABLE», `T-6.16`). Medido en `T-8.12`:

* «CAPTURA DEL INICIO DEL REINGRESO» (custodia del vídeo): 54.4 mm en 52;
* los rótulos del marco normativo del cliente («MARCO AL QUE EL CLIENTE DECLARA
  ESTAR SUJETO»): el doble de la columna;
* «ESTACIONES QUE CONTRIBUYERON» y «ESTACIONES QUE CORROBORARON»: a 1.6 mm del
  valor, que en el papel se leía pegado.

Se mide lo IMPRESO —la caja de cada renglón, `cajas_de_texto.py`—, no una
estimación por número de caracteres, sobre los CUATRO documentos que usan el
membrete y con modelos que llevan todas las secciones con rótulos.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from takab_api import cctv
from takab_api.compliance import CATALOG, ComplianceClaim, ComplianceDocument
from takab_api.dictamen.model import CctvBlock, CctvObjectRow, DictamenRow
from takab_api.dictamen.pdf import render
from takab_api.documentos.hoja import hoja_en_blanco
from takab_api.documentos.membrete import MARGIN, MembretePDF
from takab_api.drill_report import SitioReporte
from takab_api.drill_report import render as render_simulacro
from tests.api.test_drill_report import _rep
from tests.dictamen.test_pdf import _OPENED
from tests.documentos.cajas_de_texto import cajas_impresas
from tests.documentos.test_geometria import _modelo_con_todas_las_figuras

#: Donde empieza el valor es `MARGIN + 52 + c_margin`; el rótulo tiene que acabar
#: al menos 1 mm antes para que se lean como dos cosas.
_TOPE_ROTULO = MARGIN + 52.0 - 1.0


def _informe_completo():  # noqa: ANN202
    m = _modelo_con_todas_las_figuras()
    m.cctv = CctvBlock(
        objetos=[
            CctvObjectRow("captura", papel, "b" * 64, _OPENED, "disponible")
            for papel in cctv.PAPELES
        ]
        + [CctvObjectRow("clip", None, "c" * 64, _OPENED, "PURGADO (retención de vídeo)")],
        t50_s=10.0,
        t90_s=30.0,
        peak_n=40,
        discrepancia="12 personas registradas en el pase de lista y 40 observadas",
        veredicto_reingreso="el reingreso empezó tras el dictamen",
    )
    m.compliance = ComplianceDocument(
        items=tuple(
            ComplianceClaim(key=k, claim=f"Afirmación {k}", reference="Acta 14/03/2026")
            for k in CATALOG
        )
    )
    # Firmado, para que salgan también FIRMÓ y FECHA DE FIRMA.
    m.dictamens = [
        DictamenRow(
            "d-2", "inhabit_monitor", _OPENED, "0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b", "v1", None
        )
    ]
    m.sensors = [
        {"kind": "structural", "model": "RS4D-ULTRA-PROTOTIPO-2026", "mount": "concrete_column"}
    ]
    return m


_LARGO = "Torre Corporativa Reforma 222 · Edificio B Norte · Estacionamiento"

DOCUMENTOS: dict[str, Callable[[], object]] = {
    "informe técnico": lambda: render(_informe_completo(), "technical"),
    "resumen ejecutivo": lambda: render(_informe_completo(), "executive"),
    "reporte de simulacro": lambda: render_simulacro(
        _rep(
            SitioReporte(_LARGO, commandable=True, acked=True, latency_s=4.2),
            SitioReporte(_LARGO, commandable=False, acked=False, latency_s=None),
        )
    ),
    "hoja en blanco": hoja_en_blanco,
}


def _rotulos_impresos(fabrica: Callable[[], object]):  # noqa: ANN202
    """Las cajas de TEXTO que imprimió cada llamada a `field()` en la columna del rótulo.

    Se toman las cajas que aparecen DURANTE la llamada y empiezan antes de la
    columna del valor: casar por texto confundiría el rótulo «EPICENTRO DEL
    MODELO» con la etiqueta «EPICENTRO» del croquis.
    """
    rotulos: list = []
    original = MembretePDF.field
    with cajas_impresas() as cap:

        def espia(self: MembretePDF, label: str, value: str) -> None:
            antes = len(cap.cajas)
            resultado = original(self, label, value)
            if label:
                rotulos.extend(
                    c
                    for c in cap.cajas[antes:]
                    if c.clase == "texto" and c.x0 < MARGIN + 52.0 and c.texto in label
                )
            return resultado

        # ⚠️ La BASE, y se restaura sobre la MISMA clase (ver `espia.py`).
        MembretePDF.field = espia  # type: ignore[method-assign]
        try:
            fabrica()
        finally:
            MembretePDF.field = original  # type: ignore[method-assign]
    return rotulos


@pytest.mark.parametrize("nombre", sorted(DOCUMENTOS))
def test_NINGUN_rotulo_se_monta_sobre_su_VALOR(nombre: str) -> None:
    cajas = _rotulos_impresos(DOCUMENTOS[nombre])
    assert len(cajas) >= 4, f"el barrido no vio los rótulos de {nombre}"
    fuera = sorted(
        {f"«{c.texto}» acaba en {c.x1 - MARGIN:.1f} mm" for c in cajas if c.x1 > _TOPE_ROTULO}
    )
    assert not fuera, (
        f"en {nombre}, rótulos que invaden la columna del valor (tope "
        f"{_TOPE_ROTULO - MARGIN:.1f} mm desde el margen): " + " · ".join(fuera)
    )


def test_un_rotulo_LARGO_envuelve_y_su_valor_queda_ENTERO_al_lado() -> None:
    """No-vacuidad y el caso extremo: un rótulo que ni al cuerpo mínimo cabe."""
    largo = "MARCO AL QUE EL CLIENTE DECLARA ESTAR SUJETO SEGÚN SU PROPIO REGLAMENTO"
    with cajas_impresas() as cap:
        pdf = MembretePDF("TKB-ROTULO", "rótulo largo")
        pdf.add_page()
        pdf.field(largo, "Reglamento de Construcciones, Título Sexto")
        pdf.field("SIGUIENTE", "valor")
        pdf.output()
    trozos = [c for c in cap.textos if c.texto and c.texto in largo]
    assert len(trozos) >= 2, "el rótulo largo no envolvió"
    assert all(c.x1 <= _TOPE_ROTULO for c in trozos)
    valor = next(c for c in cap.textos if c.texto.startswith("Reglamento"))
    assert valor.y0 == pytest.approx(trozos[0].y0, abs=0.6), "el valor no quedó a la altura"
    siguiente = next(c for c in cap.textos if c.texto == "SIGUIENTE")
    assert siguiente.y0 > max(c.y1 for c in trozos), "el campo siguiente pisa al rótulo envuelto"
