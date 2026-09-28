"""[F3·r3 · D-43] El reingreso con un incidente ABIERTO que autoriza.

Contra ``GET /sites/{id}/mobile-state`` (ocupante):

* **Un bloqueo persistente de OTRO incidente manda.** Con la réplica abierta y un
  VERDE firmado (el sistema lo firma solo a los 300 s), la rama del incidente
  abierto concedía ``reentry_approved`` sin mirar el sismo principal: un ROJO sin
  firmar (daño estructural tardío) o un NO HABITAR firmado quedaban tapados. Medido
  en la ronda 2: ``phase=reentry_approved`` con el principal en ROJO. Las reglas 1 y
  1b son las MISMAS de ``reingreso.py`` (una sola copia).
* **Un AMARILLO sin firmar en el abierto dice ``pendiente_confirmacion``** sin
  cambiar la fase: la app sólo ofrece CONFIRMAR con esa razón, y con la v2 el
  incidente no se cierra hasta el TTL de revisión (6 h).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

import auth_utils as au
from takab_api.dictamen.sistema import SYSTEM_DICTAMEN_SIGNER_UUID
from takab_api.main import create_app
from tests.api.test_dictamen_v2_reingreso_y_danos import _fila
from tests.api.test_reingreso_persistente import (  # noqa: F401  (fixture autouse)
    _cerrar,
    _enrolar,
    _estado,
    _occupants_pool,
    _tier,
)

INSPECTOR = "70000000-0000-0000-0000-00000000aaaa"


async def _replica_verde_del_sistema(make_incident) -> str:
    replica = await make_incident(
        au.DB_TENANT_PRIV,
        au.DB_SITE_PRIV,
        trigger="sasmex",
        opened_at=datetime.now(UTC) - timedelta(minutes=20),
    )
    await _fila(
        replica,
        "normal_operation",
        "verde",
        hace=timedelta(minutes=2),
        firmado_por=SYSTEM_DICTAMEN_SIGNER_UUID,
        kind="system",
    )
    return replica


@pytest.mark.anyio
@pytest.mark.parametrize("principal_cerrado", [True, False], ids=["cerrado", "abierto"])
async def test_ROJO_sin_firmar_del_principal_no_lo_libera_el_VERDE_de_la_replica_abierta(
    base_data, make_incident, principal_cerrado
) -> None:
    principal = await make_incident(
        au.DB_TENANT_PRIV,
        au.DB_SITE_PRIV,
        trigger="sasmex",
        opened_at=datetime.now(UTC) - timedelta(hours=3),
    )
    await _fila(principal, "no_inhabit_inspect", "rojo", hace=timedelta(hours=2))
    if principal_cerrado:
        await _cerrar(principal, hace=timedelta(hours=1))
    replica = await _replica_verde_del_sistema(make_incident)
    await _tier("normal")

    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        estado = await _estado(client)
    assert estado["phase"] == "reentry_blocked", estado
    assert estado["reentry"]["blocked"] is True
    assert estado["reentry"]["reason"] == "pendiente_dictamen"
    assert estado["reentry"]["incident_id"] == principal
    assert estado["reentry"]["incident_id"] != replica


@pytest.mark.anyio
async def test_NO_HABITAR_firmado_del_principal_no_lo_libera_el_VERDE_de_la_replica_abierta(
    base_data, make_incident
) -> None:
    principal = await make_incident(
        au.DB_TENANT_PRIV,
        au.DB_SITE_PRIV,
        trigger="sasmex",
        opened_at=datetime.now(UTC) - timedelta(days=2),
    )
    await _fila(
        principal,
        "no_inhabit_inspect",
        "rojo",
        hace=timedelta(days=1),
        firmado_por=INSPECTOR,
        kind="inspector",
    )
    await _cerrar(principal, hace=timedelta(days=1))
    await _replica_verde_del_sistema(make_incident)
    await _tier("normal")

    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        estado = await _estado(client)
    assert estado["phase"] == "reentry_blocked", estado
    assert estado["reentry"]["blocked"] is True
    assert estado["reentry"]["reason"] == "no_habitable"
    assert estado["reentry"]["incident_id"] == principal
    assert estado["reentry"]["dictamen_signed"] is True


@pytest.mark.anyio
async def test_sin_bloqueo_en_otro_incidente_el_VERDE_de_la_replica_abierta_SI_libera(
    base_data, make_incident
) -> None:
    """El control: la guarda no bloquea de más."""
    replica = await _replica_verde_del_sistema(make_incident)
    await _tier("normal")
    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        estado = await _estado(client)
    assert estado["phase"] == "reentry_approved", estado
    assert estado["reentry"]["incident_id"] == replica
    assert estado["reentry"]["reason"] is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tier", "fase"),
    [("normal", "shaking_concluded"), ("evacuate_or_hold", "alert_active")],
)
async def test_AMARILLO_sin_firmar_en_el_ABIERTO_es_pendiente_confirmacion_sin_tocar_la_fase(
    base_data, make_incident, tier, fase
) -> None:
    inc = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="sasmex")
    await _fila(inc, "inhabit_monitor", "amarillo", hace=timedelta(minutes=1))
    await _tier(tier)
    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        estado = await _estado(client)
    assert estado["phase"] == fase, estado
    assert estado["reentry"]["blocked"] is True
    assert estado["reentry"]["reason"] == "pendiente_confirmacion"
    assert estado["reentry"]["incident_id"] == inc
