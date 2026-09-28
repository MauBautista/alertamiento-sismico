"""[T-9.30/T-9.32 · D-43] El reingreso y el reporte de daño con el dictamen en bandas.

Contra los endpoints reales:

* ``GET /sites/{id}/mobile-state``: un AMARILLO de la regla SIN firmar deja al que
  está fuera en ``reentry_blocked`` con razón ``pendiente_confirmacion`` (falta que
  alguien lo confirme), no ``pendiente_dictamen``. Un ROJO sin firmar, o una fila
  histórica sin banda, siguen siendo ``pendiente_dictamen``. Confirmarlo por el
  endpoint nuevo lo libera.
* ``POST /incidents/{id}/damage-reports``: sobre un incidente CERRADO se acepta hasta
  72 h desde la apertura (la ventana en la que el worker aún sube la banda por un
  daño tardío) y se rechaza después.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from tests.api.test_reingreso_persistente import (  # noqa: F401  (fixture autouse)
    _cerrar,
    _enrolar,
    _estado,
    _occupants_pool,
)

BRIGADISTA = "70000000-0000-0000-0000-0000000094c1"


def _brig() -> dict[str, str]:
    return au.bearer(
        au.make_token("brigadista", tenant=au.DB_TENANT_PRIV, site_scope="*", user_id=BRIGADISTA)
    )


async def _cabeza(incident_id: str, status: str, band: str | None, *, hace: timedelta) -> str:
    async with get_engine().begin() as conn:
        return str(
            (
                await conn.execute(
                    text(
                        "INSERT INTO dictamens (tenant_id, incident_id, status, basis, band, "
                        "created_at) VALUES (:t, :i, :st, '{}'::jsonb, :b, :at) "
                        "RETURNING dictamen_id"
                    ),
                    {
                        "t": au.DB_TENANT_PRIV,
                        "i": incident_id,
                        "st": status,
                        "b": band,
                        "at": datetime.now(UTC) - hace,
                    },
                )
            ).scalar_one()
        )


# ── reingreso ────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_AMARILLO_sin_firmar_es_PENDIENTE_DE_CONFIRMACION_y_confirmar_lo_libera(
    base_data, make_incident
) -> None:
    inc = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="sasmex")
    cabeza = await _cabeza(inc, "inhabit_monitor", "amarillo", hace=timedelta(hours=2))
    await _cerrar(inc, hace=timedelta(hours=1))

    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        estado = await _estado(client)
        assert estado["phase"] == "reentry_blocked"
        assert estado["reentry"]["reason"] == "pendiente_confirmacion"
        assert estado["reentry"]["incident_id"] == inc

        confirmado = await client.post(
            f"/incidents/{inc}/dictamens/{cabeza}/confirm", headers=_brig()
        )
        assert confirmado.status_code == 201, confirmado.text

        despues = await _estado(client)
        assert despues["phase"] == "reentry_approved"
        assert despues["reentry"]["dictamen_signed"] is True


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "band"),
    [("no_inhabit_inspect", "rojo"), ("inhabit_monitor", None)],
    ids=["rojo-sin-firmar", "historico-sin-banda"],
)
async def test_ROJO_sin_firmar_o_sin_banda_sigue_PENDIENTE_DE_DICTAMEN(
    base_data, make_incident, status, band
) -> None:
    inc = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="sasmex")
    await _cabeza(inc, status, band, hace=timedelta(hours=2))
    await _cerrar(inc, hace=timedelta(hours=1))

    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        estado = await _estado(client)
        assert estado["phase"] == "reentry_blocked"
        assert estado["reentry"]["reason"] == "pendiente_dictamen"


# ── reporte de daño sobre un cerrado ─────────────────────────────────────────────


_REPORTE = {"categories": [{"key": "structural", "severity": "critical"}]}


@pytest.mark.anyio
async def test_reporte_de_dano_sobre_CERRADO_de_menos_de_72_h_se_acepta(
    base_data, make_incident
) -> None:
    inc = await make_incident(
        au.DB_TENANT_PRIV,
        au.DB_SITE_PRIV,
        state="closed",
        opened_at=datetime.now(UTC) - timedelta(hours=71),
    )
    async with au.client_for(create_app()) as client:
        resp = await client.post(f"/incidents/{inc}/damage-reports", json=_REPORTE, headers=_brig())
    assert resp.status_code == 201, resp.text


@pytest.mark.anyio
async def test_reporte_de_dano_sobre_CERRADO_de_mas_de_72_h_se_rechaza(
    base_data, make_incident
) -> None:
    inc = await make_incident(
        au.DB_TENANT_PRIV,
        au.DB_SITE_PRIV,
        state="closed",
        opened_at=datetime.now(UTC) - timedelta(hours=73),
    )
    async with au.client_for(create_app()) as client:
        resp = await client.post(f"/incidents/{inc}/damage-reports", json=_REPORTE, headers=_brig())
    assert resp.status_code == 409, resp.text
    async with get_engine().begin() as conn:
        n = (
            await conn.execute(
                text("SELECT count(*) FROM damage_reports WHERE incident_id = CAST(:i AS uuid)"),
                {"i": inc},
            )
        ).scalar_one()
    assert n == 0


@pytest.mark.anyio
async def test_reporte_de_dano_sobre_ABIERTO_viejo_se_sigue_aceptando(
    base_data, make_incident
) -> None:
    """La cota es para CERRADOS: un incidente vivo se reporta siempre."""
    inc = await make_incident(
        au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=datetime.now(UTC) - timedelta(days=5)
    )
    async with au.client_for(create_app()) as client:
        resp = await client.post(f"/incidents/{inc}/damage-reports", json=_REPORTE, headers=_brig())
    assert resp.status_code == 201, resp.text


# ── F3·r2 · la CABEZA manda en el certificado y en el reingreso ─────────────────


async def _fila(
    incident_id: str,
    status: str,
    band: str | None,
    *,
    hace: timedelta,
    firmado_por: str | None = None,
    kind: str | None = None,
    basis: str = "{}",
) -> str:
    async with get_engine().begin() as conn:
        return str(
            (
                await conn.execute(
                    text(
                        "INSERT INTO dictamens (tenant_id, incident_id, status, basis, band, "
                        "signed_by, signature_kind, created_at) VALUES (:t, :i, :st, "
                        "CAST(:basis AS jsonb), :b, CAST(:by AS uuid), :k, :at) "
                        "RETURNING dictamen_id"
                    ),
                    {
                        "t": au.DB_TENANT_PRIV,
                        "i": incident_id,
                        "st": status,
                        "basis": basis,
                        "b": band,
                        "by": firmado_por,
                        "k": kind,
                        "at": datetime.now(UTC) - hace,
                    },
                )
            ).scalar_one()
        )


@pytest.mark.anyio
async def test_el_certificado_lee_la_CABEZA_tras_una_subida_por_dano_no_es_habitable(
    base_data, make_incident
) -> None:
    from takab_api.dictamen.sistema import SYSTEM_DICTAMEN_SIGNER_UUID

    inc = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="sasmex")
    await _fila(
        inc,
        "normal_operation",
        "verde",
        hace=timedelta(minutes=30),
        firmado_por=SYSTEM_DICTAMEN_SIGNER_UUID,
        kind="system",
    )
    async with au.client_for(create_app()) as client:
        antes = await client.get(f"/incidents/{inc}/dictamen", headers=_brig())
        assert antes.status_code == 200, antes.text
        cert = antes.json()
        assert cert["signed"] is True and cert["habitable"] is True
        assert cert["signature_kind"] == "system" and cert["band"] == "verde"
        assert cert["signed_by"] is None, "el firmante del sistema NUNCA sale como UUID"

        # la prudencia sube sola: ROJO SIN FIRMAR encima de la firma del sistema
        await _fila(inc, "no_inhabit_inspect", "rojo", hace=timedelta(minutes=5))
        despues = await client.get(f"/incidents/{inc}/dictamen", headers=_brig())
        assert despues.status_code == 200, despues.text
        cert = despues.json()
        assert cert["signed"] is False
        assert cert["habitable"] is False
        assert cert["band"] == "rojo"
        assert cert["folio"] is None and cert["signed_by"] is None


@pytest.mark.anyio
async def test_el_certificado_de_una_CONFIRMACION_lleva_el_rol(base_data, make_incident) -> None:
    inc = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="sasmex")
    await _fila(
        inc,
        "inhabit_monitor",
        "amarillo",
        hace=timedelta(minutes=3),
        firmado_por=BRIGADISTA,
        kind="confirmation",
        basis='{"confirmacion": {"rol": "brigadista"}}',
    )
    async with au.client_for(create_app()) as client:
        cert = (await client.get(f"/incidents/{inc}/dictamen", headers=_brig())).json()
    assert cert["signed"] is True and cert["habitable"] is True
    assert cert["signature_kind"] == "confirmation"
    assert cert["confirmed_by_role"] == "brigadista"


@pytest.mark.anyio
async def test_ROJO_sin_firmar_en_un_cerrado_VIEJO_no_lo_tapa_una_replica_VERDE_firmada(
    base_data, make_incident
) -> None:
    """Regla 1b: un daño tardío subió el sismo principal a ROJO (sin firmar); una
    réplica cerrada DESPUÉS con VERDE firmado no puede liberar el reingreso."""
    principal = await make_incident(
        au.DB_TENANT_PRIV,
        au.DB_SITE_PRIV,
        trigger="sasmex",
        opened_at=datetime.now(UTC) - timedelta(days=40),
    )
    # SIN cota de edad: más viejo que la espera del pendiente (30 d)
    await _fila(principal, "no_inhabit_inspect", "rojo", hace=timedelta(days=38))
    await _cerrar(principal, hace=timedelta(days=39))
    replica = await make_incident(
        au.DB_TENANT_PRIV,
        au.DB_SITE_PRIV,
        trigger="sasmex",
        opened_at=datetime.now(UTC) - timedelta(hours=3),
    )
    await _fila(
        replica,
        "normal_operation",
        "verde",
        hace=timedelta(hours=2),
        firmado_por="70000000-0000-0000-0000-00000000aaaa",
        kind="inspector",
    )
    await _cerrar(replica, hace=timedelta(hours=1))

    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        estado = await _estado(client)
    assert estado["phase"] == "reentry_blocked"
    assert estado["reentry"]["reason"] == "pendiente_dictamen"
    assert estado["reentry"]["incident_id"] == principal


@pytest.mark.anyio
async def test_un_historico_v1_sin_banda_sin_firmar_NO_bloquea_para_siempre(
    base_data, make_incident
) -> None:
    """Las filas v1 (band NULL) no entran en la regla 1b: un SASMEX viejo con su
    preliminar sin firmar bloquearía el edificio para siempre."""
    viejo = await make_incident(
        au.DB_TENANT_PRIV,
        au.DB_SITE_PRIV,
        trigger="sasmex",
        opened_at=datetime.now(UTC) - timedelta(days=40),
    )
    await _fila(viejo, "no_inhabit_inspect", None, hace=timedelta(days=38))
    await _cerrar(viejo, hace=timedelta(days=39))
    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        estado = await _estado(client)
    assert estado["phase"] != "reentry_blocked", (estado["phase"], estado.get("reentry"))
