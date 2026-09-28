"""[D-49 · R4] El papel repite el 409 de la confirmación: un daño ROJO que la última
firma humana ya VIO no lo deja «pendiente de firma del inspector».

Estructural ⇒ el inspector firma VERDE (lo vio, queda en ``danos_vistos``) ⇒ fuga
de agua ⇒ AMARILLO de la regla. La API deja confirmar a la brigada; el papel decía
«PENDIENTE DE FIRMA DEL INSPECTOR».
"""

from __future__ import annotations

from datetime import timedelta

from takab_api.dictamen import model as dm
from takab_api.dictamen.model import DanoFila, DictamenRow
from tests.dictamen.test_firma_por_tipo_en_el_papel import _FIRMA, _SUB, _cap
from tests.dictamen.test_pdf import _OPENED


def _dano(rid: str, key: str, minutos: int) -> DanoFila:
    return DanoFila(
        report_id=rid,
        rol="brigadista",
        zona=None,
        categorias=[{"key": key, "severity": "high"}],
        personas_en_riesgo=False,
        notas=None,
        ts=_OPENED + timedelta(minutes=minutos),
    )


def _cadena(vistos: tuple[str, ...] | None) -> list[DictamenRow]:
    return [
        DictamenRow(
            "d-3",
            "inhabit_monitor",
            _OPENED + timedelta(minutes=40),
            None,
            "dictamen-v2",
            "d-2",
            band="amarillo",
        ),
        DictamenRow(
            "d-2",
            "normal_operation",
            _OPENED + timedelta(minutes=20),
            _SUB,
            "dictamen-v2",
            "d-1",
            signature_kind="inspector",
            band="verde",
            danos_vistos=vistos,
        ),
        DictamenRow("d-1", "no_inhabit_inspect", _OPENED, None, "dictamen-v2", None, band="rojo"),
    ]


def test_un_ROJO_ya_visto_por_el_inspector_deja_el_AMARILLO_a_la_brigada() -> None:
    cap = _cap(
        _cadena(("r-1",)), danos=[_dano("r-1", "structural", 3), _dano("r-2", "water_leak", 30)]
    )
    firma = cap.seccion(_FIRMA)
    assert dm.PENDIENTE_CONFIRMACION in firma
    assert dm.PENDIENTE_FIRMA_INSPECTOR not in firma


def test_un_ROJO_que_ninguna_firma_humana_vio_sigue_esperando_al_inspector() -> None:
    cap = _cap(_cadena(()), danos=[_dano("r-1", "structural", 3), _dano("r-2", "water_leak", 30)])
    assert dm.PENDIENTE_FIRMA_INSPECTOR in cap.seccion(_FIRMA)
