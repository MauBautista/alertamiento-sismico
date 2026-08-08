"""Dónde se VEN las etiquetas de cumplimiento (T-2.82).

"Se ven donde importan, no solo en un formulario" son dos superficies concretas:

- ``GET /incidents/{id}/forensics`` — la fuente ÚNICA de la pantalla de Triage y del
  dictamen PDF. Que la consola y el documento salgan del mismo objeto es lo que
  impide que el papel diga una cosa y la pantalla otra (``forensics/__init__.py``).
- ``GET /sites/{id}/mobile-state`` — la pantalla 1.5 del ocupante. Es la superficie
  más leída de todas y la que pinta el VALOR descartando la clave, así que lo que
  viaja tiene que enmarcarse a sí mismo.
"""

from __future__ import annotations

import json
import os

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.compliance import (
    CATALOG,
    DECLARED_NOTICE,
    DECLARED_SHORT,
    PROVENANCE,
    UNREADABLE_LEGACY,
)
from takab_api.db.engine import get_engine
from takab_api.main import create_app

ZONE = "7d000000-0000-0000-0000-0000000000c1"
OCC = "70000000-0000-0000-0000-00000000cc01"

CLAIM = "Reglamento de Construcciones del DF, Título Sexto"
REFERENCE = "Gaceta Oficial del DF, 29/01/2004, art. 139"
DOC = {
    "version": 1,
    "items": [{"key": "regulatory_framework", "claim": CLAIM, "reference": REFERENCE}],
}


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAKAB_API_AUTH_ISSUER", au.ISSUER)
    monkeypatch.setenv("TAKAB_API_AUTH_AUDIENCE", au.AUDIENCE)
    monkeypatch.setenv("TAKAB_API_AUTH_JWKS_JSON", au.jwks_json())
    au.occupants_env(monkeypatch)
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        monkeypatch.setenv("TAKAB_API_DATABASE_URL", dsn)
    deps._reset_caches()
    get_engine.cache_clear()
    yield
    deps._reset_caches()


async def _labels(labels: dict | None) -> None:
    if labels is None:
        return
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO compliance_labels (tenant_id, labels) "
                "VALUES (CAST(:t AS uuid), CAST(:l AS jsonb)) "
                "ON CONFLICT (tenant_id) DO UPDATE SET labels = EXCLUDED.labels"
            ),
            {"t": au.DB_TENANT_PRIV, "l": json.dumps(labels)},
        )


# --- Forensics: la misma verdad que el PDF -----------------------------------


async def _forensics(incident_id: str, role: str = "inspector") -> dict:
    async with au.client_for(create_app()) as c:
        resp = await c.get(
            f"/incidents/{incident_id}/forensics",
            headers=au.bearer(au.make_token(role, tenant=au.DB_TENANT_PRIV)),
        )
    assert resp.status_code == 200, resp.text
    return resp.json()["compliance"]


async def test_el_forense_sirve_el_marco_declarado_con_su_deslinde(make_incident) -> None:
    """El inspector es QUIEN FIRMA. Ve el marco declarado en la misma pantalla en la
    que firma, y ve quién lo declaró — sin tener acceso a ``/tenants``."""
    inc = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    await _labels(DOC)
    bloque = await _forensics(inc)
    assert bloque["provenance"] == PROVENANCE
    assert bloque["notice"] == DECLARED_NOTICE
    assert bloque["unreadable"] is None
    assert [(i["key"], i["title"], i["claim"], i["reference"]) for i in bloque["items"]] == [
        ("regulatory_framework", CATALOG["regulatory_framework"], CLAIM, REFERENCE)
    ]


async def test_sin_etiquetas_el_forense_sigue_trayendo_el_deslinde(make_incident) -> None:
    """La pantalla que firma nunca se queda sin el marco: vacío se pinta como vacío,
    no como un hueco."""
    inc = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    bloque = await _forensics(inc)
    assert bloque["items"] == []
    assert bloque["unreadable"] is None
    assert bloque["notice"] == DECLARED_NOTICE


async def test_un_registro_ilegible_llega_rotulado_a_la_pantalla_que_firma(
    make_incident,
) -> None:
    inc = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    await _labels({"norma": "Cumplimos la NOM-003-SCT"})
    bloque = await _forensics(inc)
    assert bloque["items"] == []
    assert bloque["unreadable"] == UNREADABLE_LEGACY


async def test_el_forense_de_un_incidente_ajeno_no_filtra_el_marco_del_vecino(
    make_incident,
) -> None:
    """La RLS ya oculta el incidente; el marco del cliente viaja DENTRO de esa misma
    respuesta, así que no puede escaparse por su cuenta."""
    inc = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    await _labels(DOC)
    async with au.client_for(create_app()) as c:
        resp = await c.get(
            f"/incidents/{inc}/forensics",
            headers=au.bearer(au.make_token("tenant_admin", tenant=au.DB_TENANT_PRIV2)),
        )
    assert resp.status_code == 404


# --- Móvil: lo que lee el ocupante bajo "REINGRESO PROHIBIDO" ----------------


async def _mobile_state() -> dict:
    """Ocupante enrolado en el sitio PRIV → su ``mobile-state``."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO zones (zone_id, tenant_id, site_id, name, level_code, evac_policy) "
                "VALUES (:z, :t, :s, 'P1-A', 'P1', 'shelter') ON CONFLICT DO NOTHING"
            ),
            {"z": ZONE, "t": au.DB_TENANT_PRIV, "s": au.DB_SITE_PRIV},
        )
        await conn.execute(
            text(
                "INSERT INTO site_enrollment_codes (code, tenant_id, site_id, zone_id, active) "
                "VALUES ('CODE-T282', :t, :s, :z, true) ON CONFLICT DO NOTHING"
            ),
            {"t": au.DB_TENANT_PRIV, "s": au.DB_SITE_PRIV, "z": ZONE},
        )
    token = au.occupant_token(tenant=au.DB_TENANT_PRIV, user_id=OCC)
    async with au.client_for(create_app()) as c:
        await c.post("/me/enrollment", json={"code": "CODE-T282"}, headers=au.bearer(token))
        resp = await c.get(f"/sites/{au.DB_SITE_PRIV}/mobile-state", headers=au.bearer(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_el_movil_recibe_la_afirmacion_YA_ENMARCADA(base_data: None) -> None:
    """``ReentryBlockedView`` pinta el valor y descarta la clave. Si el valor no dijera
    quién lo afirma, el ocupante leería una afirmación normativa desnuda bajo un
    letrero rojo de "REINGRESO PROHIBIDO"."""
    await _labels(DOC)
    etiquetas = (await _mobile_state())["compliance_labels"]
    assert etiquetas == {
        "regulatory_framework": (f"{CATALOG['regulatory_framework']}: {CLAIM} · {DECLARED_SHORT}")
    }


async def test_sin_etiquetas_el_movil_no_recibe_NADA_normativo(base_data: None) -> None:
    """Vacío ⇒ nada (§2.1-C). Un aviso inventado aquí sería el literal normativo
    hardcodeado que la spec prohíbe."""
    assert (await _mobile_state())["compliance_labels"] == {}


async def test_un_registro_ilegible_se_anuncia_en_el_movil(base_data: None) -> None:
    await _labels({"norma": "Cumplimos la NOM-003-SCT"})
    etiquetas = (await _mobile_state())["compliance_labels"]
    assert list(etiquetas) == ["_ilegible"]
    assert etiquetas["_ilegible"] == UNREADABLE_LEGACY


async def test_el_movil_nunca_recibe_el_texto_crudo_del_cliente(base_data: None) -> None:
    """La comprobación que caza un ``dict(labels)`` de vuelta: el string suelto que el
    operador tecleó no puede salir tal cual por el cable."""
    await _labels(DOC)
    etiquetas = (await _mobile_state())["compliance_labels"]
    assert CLAIM not in etiquetas.values()
    assert all(valor.endswith(DECLARED_SHORT) for valor in etiquetas.values())


# ---------------------------------------------------------------------------
# El contrato publicado tiene que prometer lo mismo que el docstring
# ---------------------------------------------------------------------------
#
# `ComplianceDocOut` declara por escrito: «Documento del cliente + su marco. Nunca sale
# uno sin el otro.» Pero todos sus campos llevan default, y un campo con default NO es
# `required` en el esquema de serialización — así que el OpenAPI publicado decía que
# `provenance` y `notice` **pueden faltar**.
#
# No es cosmético: de ahí salen los tipos TS del SDK. El cliente generado los daba como
# `string | undefined`, y la consola tuvo que escribir su propio tipo a mano afirmando
# que siempre vienen. Dos verdades sobre el mismo cable, y la de la consola era la
# correcta — la que mentía era la que se publica.


def test_el_marco_declarado_viaja_ENTERO_o_no_viaja() -> None:
    """Cada campo de `ComplianceDocOut` es `required` en el esquema de RESPUESTA.

    Derivado, no enumerado: se compara el conjunto de propiedades contra el de
    requeridos. Un campo nuevo con default entra solo en la comprobación, que es lo
    que impide que el contrato vuelva a prometer menos de lo que el servidor cumple.
    """
    from takab_api.schemas.compliance import ComplianceDocOut

    esquema = ComplianceDocOut.model_json_schema(mode="serialization")
    faltan = sorted(set(esquema["properties"]) - set(esquema.get("required", [])))
    assert not faltan, (
        f"el contrato publica como opcionales campos que el servidor SIEMPRE manda: {faltan}. "
        "El docstring de ComplianceDocOut promete que el documento y su marco no se "
        "separan; el esquema tiene que prometer lo mismo, o el SDK generado obliga a "
        "cada consumidor a inventarse su propio tipo."
    )
