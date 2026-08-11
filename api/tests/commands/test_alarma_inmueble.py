"""[T-2.106] La alarma del inmueble: qué la sostiene, qué la apaga, cuándo caduca.

La decisión de producto (2026-08-09): una activación manual es **alarma del
inmueble, no evacuación sísmica**. Suena la sirena del edificio —que es su
diseño— y la app tiene que anunciarla como tal.

Estas pruebas fijan las DOS funciones puras de la derivación:

- ``suena_la_alarma`` — de qué señal REAL sale «está sonando», y las cuatro
  formas de dejar de sostenerlo (silenciada, sin enlace, relés ilegibles,
  caducada). Default-deny: sin señal, no se afirma nada.
- ``fase_del_sitio`` — la precedencia. **Lo sísmico manda SIEMPRE.** Una alarma
  de inmueble jamás puede tapar una fase sísmica, y en particular un pánico
  JAMÁS puede producir ``alert_active``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from takab_api.commands.alarma_inmueble import (
    AlarmaDelInmueble,
    OrdenSirena,
    fase_del_sitio,
    suena_la_alarma,
)

AHORA = datetime(2026, 8, 10, 14, 32, 0, tzinfo=UTC)
VIGENCIA_S = 1800.0
SIN_ENLACE_S = 300.0


def _orden(
    action: str = "activate",
    *,
    hace_s: float = 60.0,
    relays_state: str | None = "reported",
    gateway_age_s: float | None = 30.0,
) -> OrdenSirena:
    return OrdenSirena(
        action=action,
        issued_at=AHORA - timedelta(seconds=hace_s),
        relays_state=relays_state,
        gateway_age_s=gateway_age_s,
    )


def _suena(orden: OrdenSirena | None) -> datetime | None:
    """El INSTANTE que se anuncia, o None. [T-2.120] La procedencia de la
    afirmación (medida vs. inferida) la fija
    `test_building_alarm_desde_el_acuse.py`; aquí se sigue juzgando QUÉ la
    sostiene, que no cambió."""
    alarma = suena_la_alarma(orden, ahora=AHORA, vigencia_s=VIGENCIA_S, sin_enlace_s=SIN_ENLACE_S)
    return alarma.since if alarma is not None else None


# --- qué SOSTIENE la afirmación -------------------------------------------------


def test_un_activate_ejecutado_sostiene_la_alarma() -> None:
    """La señal es el ACK DE EJECUCIÓN del gabinete (regla de oro 8), y el
    instante que se muestra es el de la orden — un dato real y auditable."""
    orden = _orden("activate", hace_s=90.0)
    assert _suena(orden) == orden.issued_at


def test_sin_orden_no_se_afirma_nada() -> None:
    assert _suena(None) is None


# --- las cuatro formas de DEJAR de sostenerla -----------------------------------


def test_la_ultima_orden_ejecutada_fue_silenciar() -> None:
    """Alguien silenció la sirena por la nube: lo último que tocó el relé fue el
    silencio, así que la app deja de anunciar la alarma."""
    assert _suena(_orden("deactivate")) is None


def test_gabinete_sin_enlace_no_puede_sostener_nada() -> None:
    """El gabinete lleva más de `sin_enlace_s` callado. Cualquier cosa que
    dijéramos de su sirena es un dato congelado pintado como vivo (regla de oro
    7) — misma doctrina que `derive_fleet_state`: SIN ENLACE manda."""
    assert _suena(_orden(gateway_age_s=SIN_ENLACE_S + 1.0)) is None


def test_gabinete_que_jamas_latio_tampoco() -> None:
    assert _suena(_orden(gateway_age_s=None)) is None


def test_reles_ilegibles_desmienten_la_sirena() -> None:
    """`unreadable` es el gabinete diciendo «no pude preguntar quién gobierna los
    pines» (T-2.70.a·B1): con `gpio_owner=gpio` y `takab-gpio` caído ese edificio
    NO tiene sirena. Si el relé no puede afirmarse, la app no dice que suena."""
    assert _suena(_orden(relays_state="unreadable")) is None


def test_los_otros_censos_de_reles_no_desmienten() -> None:
    """`stopped` es ambiguo en firmware ≤1.9.0 y `None` es ausencia de opinión —
    ninguno es un desmentido. Mismo criterio que `fleet_degrade_reasons`, que
    también degrada SÓLO por `unreadable`."""
    assert _suena(_orden(relays_state="stopped")) is not None
    assert _suena(_orden(relays_state=None)) is not None
    assert _suena(_orden(relays_state="reported")) is not None


def test_la_alarma_caduca() -> None:
    """Una alarma sin fin es un dato congelado pintado como vivo. Al filo sigue
    viva; pasada la vigencia, la app deja de afirmarla (no la silencia: deja de
    hablar de ella)."""
    assert _suena(_orden(hace_s=VIGENCIA_S)) is not None
    assert _suena(_orden(hace_s=VIGENCIA_S + 1.0)) is None


def test_una_accion_desconocida_no_afirma_nada() -> None:
    """Default-deny, en la misma dirección que `autoriza_evacuacion`: una acción
    que esta función no entiende jamás enciende una pantalla."""
    assert _suena(_orden("drill_start")) is None
    assert _suena(_orden("accion_del_futuro")) is None


# --- precedencia: LO SÍSMICO MANDA SIEMPRE --------------------------------------


ALARMA = AlarmaDelInmueble(since=AHORA - timedelta(seconds=60), origen="order_inferred")


@pytest.mark.parametrize("sismica", ["alert_active", "shaking_concluded", "reentry_approved"])
def test_lo_sismico_gana_a_la_alarma_del_inmueble(sismica: str) -> None:
    """Ninguna alarma de inmueble puede tapar una fase sísmica: la sirena de un
    pánico no puede robarle la pantalla a una evacuación autorizada."""
    assert fase_del_sitio(sismica, ALARMA) == sismica  # type: ignore[arg-type]


def test_la_alarma_solo_habla_cuando_no_hay_sismo() -> None:
    assert fase_del_sitio("idle", ALARMA) == "building_alarm"
    assert fase_del_sitio("idle", None) == "idle"


def test_un_panico_JAMAS_produce_alert_active() -> None:
    """[criterio 3 de T-2.106, en su forma pura] `alert_active` es la orden de
    evacuación sísmica. Una alarma del inmueble no la produce por ningún camino:
    sin fase sísmica sólo puede devolver `building_alarm`.

    El ancla de arriba abajo (endpoint real, comando real) vive en
    `tests/api/test_panic_quorum.py`; esta la fija en la función.
    """
    for hace_s in (0.0, 1.0, 60.0, VIGENCIA_S):
        alarma = suena_la_alarma(
            _orden(hace_s=hace_s), ahora=AHORA, vigencia_s=VIGENCIA_S, sin_enlace_s=SIN_ENLACE_S
        )
        assert fase_del_sitio("idle", alarma) != "alert_active"
