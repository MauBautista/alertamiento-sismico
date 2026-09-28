"""[D-49] Las reglas finas en la función pura ``reingreso.decide_reingreso``.

R1 (sin calma no se autoriza), R2 (AMARILLO sin confirmar = bloqueo persistente,
sin caducidad, con su precedencia) — la MISMA función para las dos ramas de
``mobile_state`` (con y sin incidente abierto que autorice).
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from takab_api.reingreso import decide_reingreso, en_calma
from tests.test_reingreso import AHORA, LOOKBACK_S, MIN_NODES, VENTANA_FIRMA_S, _inc


def _decide(*incs, abierto=None, tier: str | None = "normal"):
    return decide_reingreso(
        list(incs),
        abierto=abierto,
        tier=tier,
        ahora=AHORA,
        min_nodes=MIN_NODES,
        ventana_firma_s=VENTANA_FIRMA_S,
        lookback_pendiente_s=LOOKBACK_S,
    )


# ── R1 ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("tier", "calma"), [(None, True), ("normal", True), ("watch", False)])
def test_en_calma_es_normal_o_sin_evaluaciones(tier, calma) -> None:
    assert en_calma(tier) is calma


@pytest.mark.parametrize("tier", ["watch", "restricted", "evacuate_or_hold", "manual_only"])
def test_R1_un_cerrado_habitable_firmado_no_autoriza_sin_calma(tier: str) -> None:
    inc = _inc(dictamen="normal_operation", banda="verde", firmado=True)
    r = _decide(inc, tier=tier)
    assert r is not None and r.fase == "reentry_blocked" and r.incidente == inc


@pytest.mark.parametrize("tier", ["watch", "evacuate_or_hold"])
def test_R1_el_abierto_habitable_firmado_deja_mandar_a_la_alerta(tier: str) -> None:
    abierto = _inc(cerrado_hace=None, dictamen="inhabit_monitor", banda="amarillo", firmado=True)
    assert _decide(abierto, abierto=abierto, tier=tier) is None


def test_R1_con_calma_el_abierto_habitable_firmado_autoriza() -> None:
    abierto = _inc(cerrado_hace=None, dictamen="inhabit_monitor", banda="amarillo", firmado=True)
    r = _decide(abierto, abierto=abierto)
    assert r is not None and r.fase == "reentry_approved" and r.incidente == abierto


# ── R2 ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("hace", [timedelta(hours=1), timedelta(days=400)])
def test_R2_un_AMARILLO_sin_confirmar_bloquea_sin_caducidad(hace: timedelta) -> None:
    viejo = _inc(
        abierto_hace=hace + timedelta(hours=2),
        cerrado_hace=hace,
        dictamen="inhabit_monitor",
        banda="amarillo",
        firmado_hace=hace,
    )
    r = _decide(viejo)
    assert (r.fase, r.razon, r.incidente) == ("reentry_blocked", "pendiente_confirmacion", viejo)


def test_R2_una_replica_VERDE_firmada_posterior_no_lo_tapa() -> None:
    principal = _inc(
        abierto_hace=timedelta(hours=5),
        cerrado_hace=timedelta(hours=4),
        dictamen="inhabit_monitor",
        banda="amarillo",
        firmado_hace=timedelta(hours=4),
    )
    replica = _inc(
        abierto_hace=timedelta(hours=2),
        cerrado_hace=timedelta(hours=1),
        dictamen="normal_operation",
        banda="verde",
        firmado=True,
    )
    r = _decide(replica, principal)
    assert (r.razon, r.incidente) == ("pendiente_confirmacion", principal)
    # y con la réplica ABIERTA
    abierta = _inc(cerrado_hace=None, dictamen="normal_operation", banda="verde", firmado=True)
    r = _decide(abierta, principal, abierto=abierta)
    assert r is not None and (r.razon, r.incidente) == ("pendiente_confirmacion", principal)


def test_R2_precedencia_NO_HABITAR_y_ROJO_ganan_al_AMARILLO() -> None:
    amarillo = _inc(dictamen="inhabit_monitor", banda="amarillo", firmado_hace=timedelta(minutes=1))
    rojo = _inc(dictamen="no_inhabit_inspect", banda="rojo", firmado_hace=timedelta(days=3))
    firmado = _inc(dictamen="restricted", firmado=True, firmado_hace=timedelta(days=9))
    assert _decide(amarillo, rojo).incidente == rojo
    assert _decide(amarillo, rojo, firmado).razon == "no_habitable"


def test_R2_una_fila_v1_sin_banda_no_bloquea() -> None:
    viejo = _inc(
        abierto_hace=timedelta(days=60),
        cerrado_hace=timedelta(days=59),
        dictamen="inhabit_monitor",
        banda=None,
    )
    assert _decide(viejo).fase == "idle"


def test_R2_un_AMARILLO_CONFIRMADO_no_bloquea() -> None:
    inc = _inc(dictamen="inhabit_monitor", banda="amarillo", firmado=True)
    assert _decide(inc).fase == "reentry_approved"


# ── R5 (regla 1d) · una petición de inspector sin atender no la tapa una réplica ─


def test_R5_una_ESCALADA_sin_atender_bloquea_sin_caducidad_y_la_replica_no_la_tapa() -> None:
    principal = _inc(
        abierto_hace=timedelta(days=30),
        cerrado_hace=timedelta(days=29),
        dictamen="normal_operation",
        banda="verde",
        escalada=True,
    )
    replica = _inc(
        abierto_hace=timedelta(minutes=20),
        cerrado_hace=timedelta(minutes=1),
        dictamen="normal_operation",
        banda="verde",
        firmado=True,
        firmado_hace=timedelta(minutes=2),
    )
    r = _decide(replica, principal)
    assert (r.fase, r.razon, r.incidente) == ("reentry_blocked", "pendiente_dictamen", principal)
    abierta = _inc(cerrado_hace=None, dictamen="normal_operation", banda="verde", firmado=True)
    r = _decide(abierta, principal, abierto=abierta)
    assert r is not None and (r.razon, r.incidente) == ("pendiente_dictamen", principal)


def test_R5_la_ESCALADA_del_propio_ABIERTO_impide_que_su_firma_habitable_autorice() -> None:
    abierto = _inc(
        cerrado_hace=None, dictamen="normal_operation", banda="verde", firmado=True, escalada=True
    )
    r = _decide(abierto, abierto=abierto)
    assert r is not None and (r.fase, r.razon, r.incidente) == (
        "reentry_blocked",
        "pendiente_dictamen",
        abierto,
    )


def test_R5_precedencia_1_1b_1c_ganan_a_la_escalada() -> None:
    escalado = _inc(dictamen="normal_operation", banda="verde", escalada=True)
    amarillo = _inc(dictamen="inhabit_monitor", banda="amarillo", firmado_hace=timedelta(days=2))
    rojo = _inc(dictamen="no_inhabit_inspect", banda="rojo", firmado_hace=timedelta(days=3))
    firmado = _inc(dictamen="restricted", firmado=True, firmado_hace=timedelta(days=9))
    assert _decide(escalado, amarillo).razon == "pendiente_confirmacion"
    assert _decide(escalado, rojo).incidente == rojo
    assert _decide(escalado, firmado).razon == "no_habitable"


def test_R5_sin_escalada_pendiente_la_replica_VERDE_autoriza() -> None:
    principal = _inc(
        abierto_hace=timedelta(days=2),
        cerrado_hace=timedelta(days=1),
        dictamen="normal_operation",
        banda="verde",
        firmado=True,
    )
    replica = _inc(
        dictamen="normal_operation",
        banda="verde",
        firmado=True,
        firmado_hace=timedelta(minutes=2),
        cerrado_hace=timedelta(minutes=1),
    )
    assert _decide(replica, principal).fase == "reentry_approved"
