"""[T-7.13 · D-33] Clasificar con una TERMINAL cierra el incidente, ahí mismo.

Hasta esta ficha la clasificación era **inerte**: se escribía la fila y el
incidente seguía siendo «la alerta» en la consola y en el teléfono del ocupante.
`D-33` la convierte en la vía normal de cierre —el TTL es solo la red de
seguridad—, y la vía normal tiene que notarse al instante: si el operador
clasifica un falso positivo y el banner sigue puesto hasta la siguiente pasada
del worker, el operador vuelve a pulsar.

Lo que se fija aquí:

* **Quién cierra queda escrito.** El cierre del endpoint lo firma el usuario
  (`user:<sub>`), no `system:incident`. Son dos hechos distintos en el timeline y
  confundirlos borra la única traza de que alguien decidió.
* **`real` no cierra**, y **`indeterminado` tampoco**: «se revisó y no se supo»
  es justo el caso que hay que volver a mirar.
* **El censo.** `CIERRA_EL_INCIDENTE` tiene que cubrir el catálogo entero. Una
  clasificación nueva no puede entrar sin que alguien decida si cierra; por
  omisión heredaría «no cierra», que es una decisión tomada por descuido.
* **Idempotente sobre un cerrado**: clasificar otra vez no vuelve a cerrar ni
  revienta contra la máquina de estados (`closed` es terminal).
"""

# ruff: noqa: F811  (fixtures de pytest importadas por nombre)
from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.incident.classification import (
    CIERRA_EL_INCIDENTE,
    CLASIFICACIONES,
    TERMINALES,
)
from takab_api.main import create_app
from takab_api.routers.classification import router as classification_router

# Sin `pytestmark`: `asyncio_mode = auto` ya corre las async, y marcarlas todas
# dejaba las dos pruebas puras del censo con un aviso de pytest en cada corrida.


# ───────────────────────────────────────────────────────────── el censo


def test_el_catalogo_entero_DECLARA_si_cierra() -> None:
    """Sin esto, una clasificación nueva hereda «no cierra» sin que nadie lo decida."""
    assert set(CIERRA_EL_INCIDENTE) == set(CLASIFICACIONES), (
        "clasificaciones sin declarar si cierran: "
        f"{sorted(set(CLASIFICACIONES) - set(CIERRA_EL_INCIDENTE))}; "
        "declaradas y fuera del catálogo: "
        f"{sorted(set(CIERRA_EL_INCIDENTE) - set(CLASIFICACIONES))}"
    )


def test_las_terminales_son_las_de_D_33() -> None:
    assert TERMINALES == frozenset({"falso_positivo", "prueba", "reproduccion"})
    assert "real" not in TERMINALES, "el evento ocurrió: lo cierra el dictamen firmado"
    assert "indeterminado" not in TERMINALES, "es el caso que hay que volver a mirar"


def test_el_catalogo_de_la_CONSOLA_es_el_mismo() -> None:
    """[T-7.14] El espejo de `useClassification.ts`, que hasta aquí podía divergir.

    Son dos listas escritas a mano en dos lenguajes, y el precio de que difieran
    no es cosmético: una casilla de menos deja al operador sin poder clasificar lo
    que la base sí acepta, y una de más le da un 500 contra el CHECK. Mismo
    mecanismo que `bmsChannels.test.ts` al revés (web leyendo `handlers.py`).
    """
    fuente = (
        Path(__file__).resolve().parents[3]
        / "web/src/features/triage/useClassification.ts"
    ).read_text(encoding="utf-8")
    bloque = fuente.split("export const CLASIFICACIONES = [")[1].split("] as const;")[0]
    en_la_consola = re.findall(r'value:\s*"(\w+)"', bloque)
    assert en_la_consola, "el bloque de la consola se movió: sin él este test no mide nada"
    assert en_la_consola == list(CLASIFICACIONES), (
        f"la consola ofrece {en_la_consola} y la base acepta {list(CLASIFICACIONES)}"
    )


# ──────────────────────────────────────────────────────── contra la API


@pytest.fixture
def app() -> FastAPI:
    application = create_app()
    application.include_router(classification_router)
    return application


def _token(role: str = "soc_operator", tenant: str = au.DB_TENANT_PRIV) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*"))


async def _sql(sql: str, **p):
    engine = get_engine()
    async with engine.begin() as conn:
        r = await conn.execute(text(sql), p)
        return r.fetchall() if r.returns_rows else []


async def _incidente(state: str = "open") -> str:
    iid = str(uuid.uuid4())
    await _sql(
        "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, opened_at,"
        " severity, state, trigger)"
        " VALUES (:i, :e, :t, :s, now(), 'critical', :st, 'sasmex')",
        i=iid,
        e=str(uuid.uuid4()),
        t=au.DB_TENANT_PRIV,
        s=au.DB_SITE_PRIV,
        st=state,
    )
    return iid


async def _estado(iid: str) -> tuple[str, bool]:
    fila = (
        await _sql(
            "SELECT state, closed_at IS NOT NULL AS cerrado FROM incidents WHERE incident_id = :i",
            i=iid,
        )
    )[0]
    return fila.state, fila.cerrado


async def _cierres(iid: str) -> list:
    return await _sql(
        "SELECT actor, payload FROM incident_actions"
        " WHERE incident_id = :i AND kind = 'close' ORDER BY ts",
        i=iid,
    )


@pytest.fixture(autouse=True)
async def _limpio():
    yield
    await _sql("SET session_replication_role = 'replica'")
    await _sql(
        "DELETE FROM incident_actions WHERE incident_id IN"
        " (SELECT incident_id FROM incidents WHERE trigger = 'sasmex' AND severity = 'critical')"
    )
    await _sql("DELETE FROM incident_classifications")
    await _sql("DELETE FROM incidents WHERE trigger = 'sasmex' AND severity = 'critical'")
    await _sql("SET session_replication_role = 'origin'")


async def test_una_TERMINAL_cierra_el_incidente_en_el_acto(client, base_data):
    iid = await _incidente("open")

    r = await client.post(
        f"/incidents/{iid}/classification",
        json={"classification": "falso_positivo", "note": "camión"},
        headers=_token(),
    )
    assert r.status_code == 201, r.text

    estado, cerrado = await _estado(iid)
    assert (estado, cerrado) == ("closed", True)


async def test_el_cierre_lo_firma_QUIEN_clasifico(client, base_data):
    """`user:<sub>` y no `system:incident`: alguien decidió, y eso se lee en el timeline."""
    iid = await _incidente("acked")

    await client.post(
        f"/incidents/{iid}/classification",
        json={"classification": "prueba"},
        headers=_token(),
    )

    cierres = await _cierres(iid)
    assert len(cierres) == 1
    assert cierres[0].actor.startswith("user:"), cierres[0].actor
    assert cierres[0].payload["reason"] == "classification"
    assert cierres[0].payload["classification"] == "prueba"
    assert cierres[0].payload["from"] == "acked"


async def test_REAL_no_cierra_nada(client, base_data):
    iid = await _incidente("in_review")

    r = await client.post(
        f"/incidents/{iid}/classification",
        json={"classification": "real"},
        headers=_token(),
    )
    assert r.status_code == 201, r.text

    assert await _estado(iid) == ("in_review", False)
    assert await _cierres(iid) == []


async def test_INDETERMINADO_no_cierra_nada(client, base_data):
    """«Se revisó y no se supo» deja el registro a la vista: es lo que pide trabajo."""
    iid = await _incidente("in_review")

    await client.post(
        f"/incidents/{iid}/classification",
        json={"classification": "indeterminado"},
        headers=_token(),
    )

    assert await _estado(iid) == ("in_review", False)


async def test_clasificar_otra_vez_un_CERRADO_no_lo_cierra_dos_veces(client, base_data):
    """`closed` es terminal: ni segunda fila de cierre ni 500 de la máquina de estados."""
    iid = await _incidente("open")
    primera = await client.post(
        f"/incidents/{iid}/classification",
        json={"classification": "falso_positivo"},
        headers=_token(),
    )
    assert primera.status_code == 201

    segunda = await client.post(
        f"/incidents/{iid}/classification",
        json={
            "classification": "prueba",
            "supersedes_id": primera.json()["classification_id"],
        },
        headers=_token(),
    )
    assert segunda.status_code == 201, segunda.text

    assert (await _estado(iid))[0] == "closed"
    assert len(await _cierres(iid)) == 1, "el segundo cierre escribió una fila de más"


async def test_corregir_a_REAL_no_REABRE_el_incidente(client, base_data):
    """La corrección queda en la cadena; el registro no vuelve a la alerta.

    Reabrir sería resucitar un banner de evacuación por una corrección de papeleo.
    Lo que se corrige es la clasificación, y el dictamen sigue su curso.
    """
    iid = await _incidente("open")
    primera = await client.post(
        f"/incidents/{iid}/classification",
        json={"classification": "prueba"},
        headers=_token(),
    )

    await client.post(
        f"/incidents/{iid}/classification",
        json={"classification": "real", "supersedes_id": primera.json()["classification_id"]},
        headers=_token(),
    )

    assert (await _estado(iid))[0] == "closed"
