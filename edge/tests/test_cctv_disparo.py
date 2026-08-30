"""Las tres puertas del disparo del CCTV (T-3.11).

La primera —modo prueba del WR-1— es la que más caro sale si falla, y por eso tiene el
test más explícito: sin ella, cada prueba de banco del radio sube vídeo real de un
edificio con gente a S3.
"""

from __future__ import annotations

from datetime import UTC, datetime

from takab_edge.cctv.disparo import (
    TIERS_QUE_GRABAN,
    disparo_en,
    modo_prueba_activo,
    simulacro_activo,
)

T0 = "2026-08-29T12:00:00+00:00"


def _status(**cambios) -> dict:
    base: dict = {
        "test_mode": {"active": False, "remaining_s": 0.0},
        "drill": {"active": False},
        "alert_latched": True,
        "last_tier": "evacuate_or_hold",
        "events": [
            {
                "at": T0,
                "from_tier": "normal",
                "to_tier": "evacuate_or_hold",
                "source": "sasmex",
                "event_id": "ev-aaa",
                "reasons": ["contacto seco WR-1"],
            }
        ],
    }
    base.update(cambios)
    return base


# ------------------------------------------------- puerta 1 · modo prueba WR-1


def test_en_modo_prueba_del_wr1_NO_se_dispara() -> None:
    """El fallo más caro que este módulo puede tener: sin esta puerta, cada prueba del
    radio sube a S3 vídeo real de un edificio real, sin incidente y sin base legal."""
    assert disparo_en(_status(test_mode={"active": True, "remaining_s": 120.0})) is None


def test_un_status_sin_seccion_de_modo_prueba_se_trata_como_prueba_ACTIVA() -> None:
    """Ante la duda, no grabar. Los dos fallos existen, pero no cuestan lo mismo."""
    assert modo_prueba_activo({}) is True
    assert modo_prueba_activo({"test_mode": "basura"}) is True
    s = _status()
    del s["test_mode"]
    assert disparo_en(s) is None


# ----------------------------------------------------- puerta 2 · simulacro


def test_un_simulacro_no_produce_clip_y_es_una_decision() -> None:
    """`D-14` acota el vídeo que sale a eventos CONFIRMADOS, y un simulacro no lo es."""
    assert disparo_en(_status(drill={"active": True})) is None


def test_un_gabinete_que_no_expone_simulacros_no_bloquea_el_disparo() -> None:
    """Ausencia de la sección ≠ simulacro en curso: no hay ninguno que respetar."""
    s = _status()
    del s["drill"]
    assert simulacro_activo(s) is False
    assert disparo_en(s) is not None


# --------------------------------------------------------- puerta 3 · tier


def test_una_transicion_a_normal_no_dispara() -> None:
    s = _status(events=[{"at": T0, "to_tier": "normal", "source": "manual", "event_id": "ev-x"}])
    assert disparo_en(s) is None


def test_watch_no_graba_pero_restricted_y_evacuate_si() -> None:
    """Mismo conjunto que dispara `queue_evidence`: si merece miniSEED, merece vídeo."""
    assert TIERS_QUE_GRABAN == {"restricted", "evacuate_or_hold"}
    for tier in ("normal", "watch"):
        s = _status(
            events=[{"at": T0, "to_tier": tier, "source": "local_threshold", "event_id": "e"}]
        )
        assert disparo_en(s) is None, tier
    for tier in TIERS_QUE_GRABAN:
        s = _status(
            events=[{"at": T0, "to_tier": tier, "source": "local_threshold", "event_id": "e"}]
        )
        assert disparo_en(s) is not None, tier


# ------------------------------------------------------------- lo que SÍ pasa


def test_el_disparo_trae_el_event_id_que_la_nube_va_a_usar() -> None:
    """Es el mismo `incidents.event_uuid`: sin él el clip no se ata a su incidente."""
    d = disparo_en(_status())
    assert d is not None
    assert d.event_id == "ev-aaa"
    assert d.t0 == datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    assert d.source == "sasmex"


def test_una_alerta_visual_only_SI_graba() -> None:
    """T-2.32 degradó el umbral instrumental a aviso —no mueve relés— pero `queue_evidence`
    está deliberadamente fuera de esa puerta. El vídeo hace lo mismo, o los dos rastros
    dejarían de casar."""
    s = _status(
        events=[
            {
                "at": T0,
                "to_tier": "evacuate_or_hold",
                "source": "local_threshold",
                "event_id": "ev-i",
            }
        ]
    )
    d = disparo_en(s)
    assert d is not None and d.source == "local_threshold"


def test_el_mismo_evento_no_dispara_dos_veces() -> None:
    """Se sondea a 1 Hz y el evento vive en `events` durante minutos."""
    assert disparo_en(_status(), ya_vistos=frozenset({"ev-aaa"})) is None


def test_se_elige_la_transicion_MAS_NUEVA_y_no_la_primera_de_la_lista() -> None:
    """Fiarse del orden de la lista haría que un cambio en el panel nos rompiera callados."""
    s = _status(
        events=[
            {
                "at": "2026-08-29T11:00:00+00:00",
                "to_tier": "restricted",
                "source": "s",
                "event_id": "viejo",
            },
            {
                "at": "2026-08-29T13:00:00+00:00",
                "to_tier": "evacuate_or_hold",
                "source": "s",
                "event_id": "nuevo",
            },
        ]
    )
    d = disparo_en(s)
    assert d is not None and d.event_id == "nuevo"


def test_las_acciones_del_panel_no_se_confunden_con_transiciones() -> None:
    """`events` mezcla transiciones con acciones (silenciar, probar sirena); solo las
    primeras traen `to_tier`."""
    s = _status(events=[{"at": T0, "action": "siren_test", "via": "lan"}])
    assert disparo_en(s) is None


def test_una_marca_de_tiempo_ilegible_no_tumba_el_cliente() -> None:
    s = _status(
        events=[{"at": "ayer", "to_tier": "evacuate_or_hold", "source": "s", "event_id": "e"}]
    )
    assert disparo_en(s) is None


def test_una_transicion_sin_event_id_no_dispara() -> None:
    """Sin `event_id` el clip no se puede atar a un incidente ni deduplicar: no sirve."""
    s = _status(events=[{"at": T0, "to_tier": "evacuate_or_hold", "source": "s", "event_id": ""}])
    assert disparo_en(s) is None


def test_un_status_vacio_no_revienta() -> None:
    assert disparo_en({}) is None
