"""[T-9.42 · D-48] Los tres ajustes del informe automático y sus valores de arranque."""

from __future__ import annotations

from takab_api.routers.reports import VARIANTS
from takab_api.settings import Settings


def test_los_valores_por_defecto() -> None:
    s = Settings()
    assert s.informe_ventana_s == 21600.0  # 6 h: no llenar de correos el histórico
    assert s.informe_plazo_s == 1500.0  # 25 min ⇒ el correo llega en ≤ 30
    assert s.informe_variante == "executive"  # es para quien decide


def test_el_plazo_cabe_en_la_ventana() -> None:
    """Un plazo mayor que la ventana haría que el disparo por plazo no saltara nunca."""
    s = Settings()
    assert s.informe_plazo_s < s.informe_ventana_s


def test_la_variante_es_una_que_el_render_conoce() -> None:
    assert Settings().informe_variante in VARIANTS


def test_se_ajustan_por_entorno(monkeypatch) -> None:
    monkeypatch.setenv("TAKAB_API_INFORME_PLAZO_S", "600")
    monkeypatch.setenv("TAKAB_API_INFORME_VARIANTE", "technical")
    s = Settings()
    assert s.informe_plazo_s == 600.0
    assert s.informe_variante == "technical"
