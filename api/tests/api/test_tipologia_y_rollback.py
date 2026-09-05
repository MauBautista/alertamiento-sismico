"""Tipología que SUGIERE y rollback que CREA versión (T-5.16 · D-28).

Las dos aserciones que gobiernan el archivo:

1. **Cambiar el tipo de un sitio NO cambia lo que corre en el gabinete.** El tipo
   se edita desde la pantalla de flota, por alguien que corrige un dato de alta;
   si resolviera el umbral, ese acto de captura re-armaría el edificio a otra
   sensibilidad sin publicar y sin firmar. Se prueba **midiendo el rule_set
   activo antes y después** del cambio de tipo, no leyendo un comentario.
2. **Volver atrás CREA una versión nueva.** Nunca reescribe el histórico, declara
   a cuál vuelve, queda auditado y respeta el conflicto por versión base — que es
   lo mismo que ya exige el PUT, y por la misma razón: dos operadores mirando la
   misma pantalla.
"""

# ruff: noqa: F811
from __future__ import annotations

from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine

_ADMIN = "abcabcab-0000-0000-0000-0000000000f1"


def _tok(role: str = "tenant_admin", tenant: str = au.DB_TENANT_PRIV) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*", user_id=_ADMIN))


async def _sql(sql: str, **p):
    engine = get_engine()
    async with engine.begin() as conn:
        r = await conn.execute(text(sql), p)
        return r.fetchall() if r.returns_rows else []


async def _put(client, config: dict, base: int | None = None):
    cuerpo: dict = {"scope_type": "site", "scope_id": au.DB_SITE_PRIV, "config": config}
    if base is not None:
        cuerpo["base_version"] = base
    return await client.put("/rule-sets", json=cuerpo, headers=_tok())


async def _activo() -> dict:
    filas = await _sql(
        "SELECT version, config, rolled_back_to FROM rule_sets"
        " WHERE scope_type = 'site' AND scope_id = :s AND is_active",
        s=au.DB_SITE_PRIV,
    )
    assert len(filas) == 1, f"debería haber exactamente un activo, hay {len(filas)}"
    return {"version": filas[0][0], "config": filas[0][1], "rolled_back_to": filas[0][2]}


# ───────────────────────────────────────────────────────────── el catálogo


async def test_el_catalogo_sale_por_la_API_declarando_que_solo_SUGIERE(client, base_data):
    r = await client.get("/building-types", headers=_tok())
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["resuelve_umbrales"] is False
    assert len(cuerpo["por_que_no_resuelve"]) >= 3
    assert [t["value"] for t in cuerpo["items"]] == [
        "hospital",
        "industrial",
        "corporativo",
        "universidad",
        "gobierno",
        "otro",
    ]


async def test_el_tipo_sin_banda_dice_por_que_en_vez_de_traer_la_de_hospital(client, base_data):
    """El defecto que abre la ficha: toda la flota corriendo la banda de hospital."""
    cat = (await client.get("/building-types", headers=_tok())).json()
    items = {t["value"]: t for t in cat["items"]}
    assert items["hospital"]["banda"] == {"pga_watch_g": 0.040, "pga_trip_g": 0.060}
    assert items["universidad"]["banda"] is None
    assert len(items["universidad"]["sin_banda_por_que"]) > 60


async def _cuerpo_del_sitio(client, **cambios) -> dict:
    """El sitio tal como está, con los cambios pedidos: `PUT /sites` reemplaza el
    cuerpo entero, así que mandar solo el tipo daría 422 por lo que falta y el
    test pasaría por la razón equivocada."""
    actual = (await client.get(f"/sites/{au.DB_SITE_PRIV}", headers=_tok())).json()
    cuerpo = {
        k: actual[k]
        for k in ("code", "name", "lat", "lon", "timezone", "criticality", "address", "status")
    }
    cuerpo["building_type"] = actual.get("building_type")
    cuerpo["base_row_version"] = actual["row_version"]
    cuerpo.update(cambios)
    return cuerpo


async def test_un_tipo_fuera_del_catalogo_se_rechaza(client, base_data):
    r = await client.put(
        f"/sites/{au.DB_SITE_PRIV}",
        json=await _cuerpo_del_sitio(client, building_type="castillo"),
        headers=_tok(),
    )
    assert r.status_code == 422, r.text


# ─────────────────────────── cambiar el tipo NO cambia lo que corre en el Pi


async def test_cambiar_el_TIPO_no_toca_el_rule_set_activo(client, base_data):
    """La aserción central de `D-28`, medida y no comentada."""
    await _put(client, {"thresholds": {"pga_watch_g": 0.040, "pga_trip_g": 0.060}})
    antes = await _activo()

    r = await client.put(
        f"/sites/{au.DB_SITE_PRIV}",
        json=await _cuerpo_del_sitio(client, building_type="industrial"),
        headers=_tok(),
    )
    assert r.status_code == 200, r.text
    assert r.json()["building_type"] == "industrial", "el cambio de tipo no llegó a guardarse"

    despues = await _activo()
    assert despues == antes, "cambiar el tipo re-armó el edificio sin publicar nada"


# ───────────────────────────────────────────────────────────── el rollback


async def test_rollback_CREA_version_nueva_y_declara_a_cual_vuelve(client, base_data):
    v1 = (await _put(client, {"thresholds": {"pga_trip_g": 0.060}})).json()
    await _put(client, {"thresholds": {"pga_trip_g": 0.150}}, base=1)

    r = await client.post(
        f"/rule-sets/{v1['rule_set_id']}/rollback", json={"base_version": 2}, headers=_tok()
    )
    assert r.status_code == 201, r.text
    assert r.json()["version"] == 3, "el rollback tiene que ser una versión MÁS, no una menos"

    activo = await _activo()
    assert activo["version"] == 3
    assert activo["config"]["thresholds"]["pga_trip_g"] == 0.060, "no restauró los valores"
    assert str(activo["rolled_back_to"]) == v1["rule_set_id"]


async def test_el_historico_sobrevive_INTACTO_al_rollback(client, base_data):
    v1 = (await _put(client, {"thresholds": {"pga_trip_g": 0.060}})).json()
    await _put(client, {"thresholds": {"pga_trip_g": 0.150}}, base=1)
    await client.post(
        f"/rule-sets/{v1['rule_set_id']}/rollback", json={"base_version": 2}, headers=_tok()
    )

    versiones = await _sql(
        "SELECT version, config->'thresholds'->>'pga_trip_g' FROM rule_sets"
        " WHERE scope_type = 'site' AND scope_id = :s ORDER BY version",
        s=au.DB_SITE_PRIV,
    )
    assert [(v, t) for v, t in versiones] == [(1, "0.06"), (2, "0.15"), (3, "0.06")]


async def test_el_rollback_respeta_el_conflicto_por_version_base(client, base_data):
    """Dos operadores en la misma pantalla: el segundo no pisa al primero a ciegas."""
    v1 = (await _put(client, {"thresholds": {"pga_trip_g": 0.060}})).json()
    await _put(client, {"thresholds": {"pga_trip_g": 0.150}}, base=1)

    r = await client.post(
        f"/rule-sets/{v1['rule_set_id']}/rollback", json={"base_version": 1}, headers=_tok()
    )
    assert r.status_code == 409, r.text


async def test_el_rollback_NO_resucita_un_secreto_rotado(client, base_data):
    """Restaurar umbrales viejos no puede restaurar una credencial retirada.

    El `config` guarda el secreto del webhook. Volver a una versión anterior
    devolvería el secreto de entonces — que puede haberse rotado justamente
    porque se filtró. Se restaura todo MENOS los secretos, que se conservan los
    vigentes; es la misma regla que ya aplica `merge_secrets` en el PUT.
    """
    v1 = (
        await _put(client, {"notifications": {"webhook": {"url": "https://a", "secret": "viejo"}}})
    ).json()
    await _put(
        client,
        {"notifications": {"webhook": {"url": "https://b", "secret": "vigente"}}},
        base=1,
    )

    await client.post(
        f"/rule-sets/{v1['rule_set_id']}/rollback", json={"base_version": 2}, headers=_tok()
    )
    activo = await _activo()
    assert activo["config"]["notifications"]["webhook"]["url"] == "https://a", "no restauró"
    assert activo["config"]["notifications"]["webhook"]["secret"] == "vigente", (
        "el rollback resucitó un secreto que ya se había rotado"
    )


async def test_el_rollback_queda_AUDITADO(client, base_data):
    v1 = (await _put(client, {"thresholds": {"pga_trip_g": 0.060}})).json()
    await _put(client, {"thresholds": {"pga_trip_g": 0.150}}, base=1)
    await client.post(
        f"/rule-sets/{v1['rule_set_id']}/rollback", json={"base_version": 2}, headers=_tok()
    )

    filas = await _sql(
        "SELECT meta FROM audit_log WHERE verb = 'rule_set_rollback' ORDER BY ts DESC LIMIT 1"
    )
    assert len(filas) == 1, "un rollback sin fila de auditoría es un cambio sin autor"
    meta = filas[0][0]
    assert meta["a_version"] == 1 and meta["desde_version"] == 2


async def test_no_se_puede_volver_a_una_version_de_OTRO_alcance(client, base_data):
    """Un rollback cruzado aplicaría la configuración de un edificio a otro."""
    v1 = (await _put(client, {"thresholds": {"pga_trip_g": 0.060}})).json()
    r = await client.put(
        "/rule-sets",
        json={"scope_type": "tenant", "scope_id": au.DB_TENANT_PRIV, "config": {"x": 1}},
        headers=_tok(),
    )
    assert r.status_code == 201
    otro = r.json()

    mal = await client.post(
        f"/rule-sets/{v1['rule_set_id']}/rollback",
        json={"base_version": otro["version"], "scope_type": "tenant"},
        headers=_tok(),
    )
    assert mal.status_code in (400, 409), mal.text


async def test_quien_no_edita_umbrales_no_puede_volver_atras(client, base_data):
    v1 = (await _put(client, {"thresholds": {"pga_trip_g": 0.060}})).json()
    r = await client.post(
        f"/rule-sets/{v1['rule_set_id']}/rollback",
        json={"base_version": 1},
        headers=_tok("soc_operator"),
    )
    assert r.status_code == 403, r.text
