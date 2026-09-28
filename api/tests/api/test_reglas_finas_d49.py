"""[D-49] Reglas finas del dictamen automático, contra los endpoints reales.

* **R1 · el reingreso no se autoriza con el edificio moviéndose.** Ninguna firma
  (sistema, confirmación, inspector) produce ``reentry_approved`` si el último tier
  del sitio no es ``normal``; y la brigada no confirma un AMARILLO hasta la calma
  (409). Medido en la ronda 3: un brigadista confirmaba en ``evacuate_or_hold`` y
  el ocupante leía REINGRESO AUTORIZADO en plena sacudida.
* **R2 · un AMARILLO sin confirmar es un bloqueo persistente.** De cualquier
  incidente que cuente, sin caducidad: el VERDE del sistema en la réplica no lo tapa.
* **R4 · la firma humana vale para la evidencia que vio.** Al firmar/confirmar se
  guarda ``basis.danos_vistos`` DENTRO del lock; el 409 «requiere inspector» sólo
  cuenta daños ROJOS que la última firma humana no vio.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
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

BRIGADISTA = "abcabcab-0000-0000-0000-0000000000b1"
INSPECTOR = "70000000-0000-0000-0000-00000000aaaa"


def _tok(role: str, user: str) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=au.DB_TENANT_PRIV, site_scope="*", user_id=user))


async def _dano(iid: str, *keys: str) -> str:
    async with get_engine().begin() as conn:
        return str(
            (
                await conn.execute(
                    text(
                        "INSERT INTO damage_reports (tenant_id, incident_id, site_id, user_sub, "
                        "categories) VALUES (:t, CAST(:i AS uuid), :s, :u, CAST(:c AS jsonb)) "
                        "RETURNING report_id"
                    ),
                    {
                        "t": au.DB_TENANT_PRIV,
                        "i": iid,
                        "s": au.DB_SITE_PRIV,
                        "u": str(uuid.uuid4()),
                        "c": json.dumps([{"key": k, "severity": "high"} for k in keys]),
                    },
                )
            ).scalar_one()
        )


# ── R1 ─────────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_R1_la_brigada_NO_confirma_un_AMARILLO_con_el_edificio_moviendose(
    base_data, make_incident
) -> None:
    inc = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="sasmex")
    head = await _fila(inc, "inhabit_monitor", "amarillo", hace=timedelta(minutes=1))
    await _tier("evacuate_or_hold")
    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        resp = await client.post(
            f"/incidents/{inc}/dictamens/{head}/confirm", headers=_tok("brigadista", BRIGADISTA)
        )
        assert resp.status_code == 409, resp.text
        assert "calma" in resp.json()["detail"]
        estado = await _estado(client)
    assert estado["phase"] != "reentry_approved", estado


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["confirmation", "inspector", "system"])
async def test_R1_una_firma_habitable_en_el_ABIERTO_no_autoriza_sin_calma(
    base_data, make_incident, kind
) -> None:
    inc = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="sasmex")
    firmante = SYSTEM_DICTAMEN_SIGNER_UUID if kind == "system" else INSPECTOR
    status, band = (
        ("normal_operation", "verde") if kind == "system" else ("inhabit_monitor", "amarillo")
    )
    await _fila(inc, status, band, hace=timedelta(minutes=1), firmado_por=firmante, kind=kind)
    await _tier("evacuate_or_hold")
    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        estado = await _estado(client)
    assert estado["phase"] == "alert_active", estado


@pytest.mark.anyio
async def test_R1_una_firma_habitable_de_un_CERRADO_no_autoriza_sin_calma(
    base_data, make_incident
) -> None:
    inc = await make_incident(
        au.DB_TENANT_PRIV,
        au.DB_SITE_PRIV,
        trigger="sasmex",
        opened_at=datetime.now(UTC) - timedelta(hours=2),
    )
    await _fila(
        inc,
        "normal_operation",
        "verde",
        hace=timedelta(minutes=30),
        firmado_por=INSPECTOR,
        kind="inspector",
    )
    await _cerrar(inc, hace=timedelta(minutes=20))
    await _tier("restricted")
    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        estado = await _estado(client)
    assert estado["phase"] == "reentry_blocked", estado
    assert estado["reentry"]["blocked"] is True


# ── R2 ─────────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
@pytest.mark.parametrize("cerrados", [False, True], ids=["abiertos", "cerrados"])
async def test_R2_AMARILLO_sin_confirmar_del_principal_no_lo_tapa_el_VERDE_de_la_replica(
    base_data, make_incident, cerrados
) -> None:
    principal = await make_incident(
        au.DB_TENANT_PRIV,
        au.DB_SITE_PRIV,
        trigger="sasmex",
        opened_at=datetime.now(UTC) - timedelta(hours=2),
    )
    await _fila(principal, "inhabit_monitor", "amarillo", hace=timedelta(hours=1))
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
    if cerrados:
        await _cerrar(principal, hace=timedelta(minutes=50))
        await _cerrar(replica, hace=timedelta(minutes=1))
    await _tier("normal")
    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        estado = await _estado(client)
    assert estado["phase"] == "reentry_blocked", estado
    assert estado["reentry"]["reason"] == "pendiente_confirmacion"
    assert estado["reentry"]["incident_id"] == principal


# ── R4 ─────────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_R4_la_firma_del_inspector_guarda_los_danos_que_vio(base_data, make_incident) -> None:
    inc = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="sasmex")
    rep = await _dano(inc, "structural")
    async with au.client_for(create_app()) as client:
        resp = await client.post(
            f"/incidents/{inc}/dictamens",
            json={"status": "normal_operation"},
            headers=_tok("inspector", INSPECTOR),
        )
    assert resp.status_code == 201, resp.text
    assert resp.json()["basis"]["danos_vistos"] == [rep]


@pytest.mark.anyio
async def test_R4_un_dano_ROJO_ya_visto_por_el_inspector_no_impide_confirmar(
    base_data, make_incident
) -> None:
    """Estructural ⇒ el inspector firma VERDE (lo vio) ⇒ fuga de agua ⇒ AMARILLO de la
    regla. Antes: 409 «requiere inspector» para siempre (callejón sin salida). Y la
    confirmación guarda los dos reportes como vistos."""
    inc = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="sasmex")
    rojo = await _dano(inc, "structural")
    async with au.client_for(create_app()) as client:
        firma = await client.post(
            f"/incidents/{inc}/dictamens",
            json={"status": "normal_operation"},
            headers=_tok("inspector", INSPECTOR),
        )
        assert firma.status_code == 201, firma.text
        agua = await _dano(inc, "water_leak")
        head = await _fila(inc, "inhabit_monitor", "amarillo", hace=timedelta(seconds=-1))
        resp = await client.post(
            f"/incidents/{inc}/dictamens/{head}/confirm", headers=_tok("brigadista", BRIGADISTA)
        )
    assert resp.status_code == 201, resp.text
    assert sorted(resp.json()["basis"]["danos_vistos"]) == sorted([rojo, agua])


@pytest.mark.anyio
async def test_R4_un_dano_ROJO_que_ninguna_firma_humana_vio_SI_impide_confirmar(
    base_data, make_incident
) -> None:
    inc = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="sasmex")
    async with au.client_for(create_app()) as client:
        firma = await client.post(
            f"/incidents/{inc}/dictamens",
            json={"status": "normal_operation"},
            headers=_tok("inspector", INSPECTOR),
        )
        assert firma.status_code == 201, firma.text
        await _dano(inc, "structural")
        head = await _fila(inc, "inhabit_monitor", "amarillo", hace=timedelta(seconds=-1))
        resp = await client.post(
            f"/incidents/{inc}/dictamens/{head}/confirm", headers=_tok("brigadista", BRIGADISTA)
        )
    assert resp.status_code == 409, resp.text
    assert "inspector" in resp.json()["detail"]


# ── R5 · una petición de inspector sin atender no la tapa una réplica ─────────


async def _escalar(iid: str, *, hace: timedelta) -> None:
    """La brigada pide un inspector (``dictamen_request``) hace ``hace``."""
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO incident_actions (incident_id, tenant_id, kind, actor, payload, ts) "
                "VALUES (CAST(:i AS uuid), :t, 'dictamen_request', 'user:brigada', "
                "CAST('{}' AS jsonb), :ts)"
            ),
            {"i": iid, "t": au.DB_TENANT_PRIV, "ts": datetime.now(UTC) - hace},
        )


async def _escenario_r5(make_incident, *, cerrados: bool) -> tuple[str, str]:
    """El de la ronda 4: principal con VERDE sin firmar hace 1 h y réplica con el
    VERDE que firmó el sistema hace 2 min; tier ``normal``."""
    principal = await make_incident(
        au.DB_TENANT_PRIV,
        au.DB_SITE_PRIV,
        trigger="sasmex",
        opened_at=datetime.now(UTC) - timedelta(hours=2),
    )
    await _fila(principal, "normal_operation", "verde", hace=timedelta(hours=1))
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
    if cerrados:
        await _cerrar(principal, hace=timedelta(minutes=50))
        await _cerrar(replica, hace=timedelta(minutes=1))
    await _tier("normal")
    return principal, replica


@pytest.mark.anyio
@pytest.mark.parametrize("cerrados", [False, True], ids=["abiertos", "cerrados"])
async def test_R5_la_ESCALADA_sin_atender_del_principal_no_la_tapa_el_VERDE_de_la_replica(
    base_data, make_incident, cerrados
) -> None:
    principal, _ = await _escenario_r5(make_incident, cerrados=cerrados)
    await _escalar(principal, hace=timedelta(minutes=40))
    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        estado = await _estado(client)
    assert estado["phase"] == "reentry_blocked", estado
    assert estado["reentry"]["reason"] == "pendiente_dictamen"
    assert estado["reentry"]["incident_id"] == principal


@pytest.mark.anyio
@pytest.mark.parametrize("cerrados", [False, True], ids=["abiertos", "cerrados"])
@pytest.mark.parametrize(
    ("kind", "quien"),
    [("confirmation", BRIGADISTA), ("inspector", INSPECTOR), (None, INSPECTOR)],
    ids=["confirmacion", "inspector", "historica_sin_tipo"],
)
async def test_R5_una_firma_HUMANA_posterior_atiende_la_escalada(
    base_data, make_incident, cerrados, kind, quien
) -> None:
    principal, _ = await _escenario_r5(make_incident, cerrados=cerrados)
    await _escalar(principal, hace=timedelta(minutes=40))
    await _fila(
        principal,
        "normal_operation",
        "verde",
        hace=timedelta(minutes=30),
        firmado_por=quien,
        kind=kind,
    )
    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        estado = await _estado(client)
    assert estado["phase"] == "reentry_approved", estado


@pytest.mark.anyio
@pytest.mark.parametrize("cerrados", [False, True], ids=["abiertos", "cerrados"])
async def test_R5_una_escalada_ANTERIOR_a_la_firma_humana_no_bloquea_y_una_POSTERIOR_si(
    base_data, make_incident, cerrados
) -> None:
    principal, _ = await _escenario_r5(make_incident, cerrados=cerrados)
    await _escalar(principal, hace=timedelta(minutes=45))
    await _fila(
        principal,
        "normal_operation",
        "verde",
        hace=timedelta(minutes=30),
        firmado_por=INSPECTOR,
        kind="inspector",
    )
    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        antes = await _estado(client)
        assert antes["phase"] == "reentry_approved", antes
        # Otra petición DESPUÉS de la firma: la del sistema en la réplica no la atiende.
        await _escalar(principal, hace=timedelta(minutes=10))
        despues = await _estado(client)
    assert despues["phase"] == "reentry_blocked", despues
    assert despues["reentry"]["reason"] == "pendiente_dictamen"
    assert despues["reentry"]["incident_id"] == principal
