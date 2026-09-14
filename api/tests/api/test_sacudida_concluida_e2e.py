"""[T-7.30] De la transición del gabinete a `shaking_concluded` en el teléfono.

EL DEFECTO, medido el 2026-09-12 con el WR-1 real: tras el pulso, el teléfono se
quedó en la pantalla de crisis **contando**, y hubo que concluir la sacudida a
mano por SQL. La causa tenía dos mitades y ninguna prueba las unía:

* el gabinete no publicaba nada al volver a `normal`
  (`supervisor.py`: ``if decision.tier is Tier.NORMAL: return``), y
* en la nube **ninguna ruta de ingesta escribía `rule_evaluations`** — solo los
  sembradores—, que es justo de donde `mobile_site.py` deriva la fase.

Un sismo real no podía producir `shaking_concluded` jamás.

POR QUÉ ESTE FICHERO Y NO UN TEST MÁS DE HANDLER. La mitad de nube ya tiene sus
pruebas unitarias en `test_ingest_handlers.py`, y la fase tenía las suyas en
`test_mobile_core.py` — pero aquéllas sembraban `rule_evaluations` **a mano, con
un `gateway_id` aleatorio**. Las dos mitades estaban verdes y el producto roto:
lo que faltaba era exactamente la costura. Aquí el mensaje recorre el camino
real —topic → discriminación por `kind` → validación contra el schema
COMPARTIDO que genera el edge → registro de identidad → handler → commit— y la
fase se lee por HTTP, sin un solo INSERT escrito por el test.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from sqlalchemy import text

import auth_utils as au
from conftest import _dsn
from takab_api.contracts.loader import discriminate, kind_for_topic, validate
from takab_api.contracts.meta import split_meta
from takab_api.db.engine import get_engine
from takab_api.ingest.handlers import HANDLERS
from takab_api.ingest.registry import Registry
from takab_api.main import create_app

EVENTS_TOPIC = "takab/events"
THING = "gw-b2sa-0001"
GW = "7b000000-0000-0000-0000-0000000000c1"
BRIG_USER = "70000000-0000-0000-0000-00000000bb30"
SITE_CODE = "B2SA"  # tests/seed_shared.py — el sitio del tenant PRIV
TENANT_CODE = "B2_A"


@pytest.fixture
async def gabinete(base_data) -> None:
    """Un gabinete REGISTRADO en el sitio PRIV: sin él no hay identidad que
    resolver, y la identidad es justo lo que las filas sembradas se inventaban."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) "
                "VALUES (:g, :t, :s, :th, :th) ON CONFLICT (gateway_id) DO NOTHING"
            ),
            {"g": GW, "t": au.DB_TENANT_PRIV, "s": au.DB_SITE_PRIV, "th": THING},
        )


def _mensaje(prev: str, nuevo: str, at: datetime) -> dict:
    """El JSON tal como sale del gabinete, con el enriquecimiento de la IoT Rule."""
    return {
        "kind": "tier_transition",
        "event_id": uuid.uuid4().hex,
        "site_id": SITE_CODE,
        "prev_tier": prev,
        "new_tier": nuevo,
        "source": "sasmex",
        "at": at.isoformat(),
        "pga_g": None,
        "reasons": ["prueba de costura"],
        "meta_principal": THING,
        "meta_topic": EVENTS_TOPIC,
        "meta_ts_iot": int(at.timestamp() * 1000),
    }


def _ingesta(raw: dict) -> None:
    """El camino real de un mensaje, sin atajos: si cualquier eslabón no lo
    reconoce, este test se entera aquí y no en el teléfono."""
    payload, meta = split_meta(raw)
    kind = discriminate(kind_for_topic(meta.topic), payload)
    assert kind == "tier_transition", f"el topic no encamina la transición: {kind!r}"
    validate(kind, payload)  # contra shared/schemas/, lo que el edge genera
    conn = psycopg.connect(_dsn())
    try:
        conn.execute("SET ROLE takab_ingest")  # el rol real del worker
        conn.commit()
        ctx = Registry(lambda: psycopg.connect(_dsn())).resolve(meta.principal)
        assert ctx is not None, "el gabinete no está registrado"
        res = HANDLERS[kind](conn, payload, meta, ctx)
        assert res.is_ok, res.reason
        conn.commit()
    finally:
        conn.close()


@pytest.mark.anyio
async def test_la_sacudida_CONCLUYE_sin_tocar_la_base_a_mano(gabinete, make_incident) -> None:
    """El recorrido entero del acto 3: alerta, sacudida y vuelta a la calma."""
    await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="sasmex")
    url = f"/sites/{au.DB_SITE_PRIV}/mobile-state"
    headers = au.bearer(
        au.make_token(
            "brigadista",
            tenant=au.DB_TENANT_PRIV,
            user_id=BRIG_USER,
            surface="mobile",
            site_scope=au.DB_SITE_PRIV,
        )
    )
    t0 = datetime.now(UTC)
    async with au.client_for(create_app()) as client:
        # 1. El gabinete escala: el teléfono toma la pantalla.
        _ingesta(_mensaje("normal", "evacuate_or_hold", t0))
        assert (await client.get(url, headers=headers)).json()["phase"] == "alert_active"

        # 2. Silencio sostenido: el gabinete publica el cierre del episodio.
        _ingesta(_mensaje("evacuate_or_hold", "normal", t0 + timedelta(seconds=90)))
        estado = (await client.get(url, headers=headers)).json()
        assert estado["phase"] == "shaking_concluded", (
            "el teléfono sigue en crisis: la transición del gabinete no llegó a la fase"
        )
        # El reingreso SIGUE bloqueado: concluir la sacudida no es liberar el
        # inmueble. Eso lo firma un inspector, y es otra fase.
        assert estado["reentry"]["blocked"] is True


@pytest.mark.anyio
async def test_la_fila_lleva_el_GABINETE_que_la_emitió(gabinete) -> None:
    """Los sembradores ponían un `gateway_id` aleatorio. Una fila de auditoría
    con un emisor inventado no sirve para auditar nada — y `rule_evaluations` es
    append-only: lo que se escribe mal se queda mal."""
    _ingesta(_mensaje("normal", "watch", datetime.now(UTC)))
    engine = get_engine()
    async with engine.begin() as conn:
        row = (
            await conn.execute(text("SELECT gateway_id::text, site_id::text FROM rule_evaluations"))
        ).first()
    assert row is not None
    assert (row[0], row[1]) == (GW, au.DB_SITE_PRIV)
