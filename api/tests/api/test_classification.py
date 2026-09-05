"""Clasificación de incidentes y tasa de falsos positivos (T-5.12).

Lo que fija, y en este orden:

* **Corregir INSERTA, no sustituye.** Quien clasificó mal a las 3 de la mañana no
  puede hacer desaparecer su clasificación: la corrige, y las dos quedan. Es la
  misma disciplina de la cadena de dictámenes, y la base la impone con sus dos
  capas append-only, no la aplicación.
* **`indeterminado` se ELIGE, no es el default.** El endpoint exige el valor. Un
  default silencioso convertiría «nadie lo revisó» en «se revisó y no se supo»,
  que son cosas distintas y solo la primera pide trabajo.
* **Los sin clasificar salen APARTE, no del denominador.** Un porcentaje
  calculado sobre lo clasificado, con lo no clasificado escondido, se lee como
  una medición y es una muestra sesgada por quién tuvo tiempo de revisar.
* **La tasa es `null` y no cero cuando nadie miró.** Un cero afirmaría que no
  hubo falsos positivos.
"""

# ruff: noqa: F811  (fixtures de pytest importadas por nombre)
from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.classification import router as classification_router


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


async def _incidente(*, tenant: str = au.DB_TENANT_PRIV, site: str = au.DB_SITE_PRIV) -> str:
    """Un incidente REAL en la base, para clasificarlo."""
    iid = str(uuid.uuid4())
    await _sql(
        "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, opened_at,"
        " severity, state, trigger)"
        " VALUES (:i, :e, :t, :s, now(), 'critical', 'closed', 'sasmex')",
        i=iid,
        e=str(uuid.uuid4()),
        t=tenant,
        s=site,
    )
    return iid


@pytest.fixture(autouse=True)
async def _limpio():
    yield
    await _sql("DELETE FROM incident_classifications")
    await _sql("DELETE FROM incidents WHERE trigger = 'sasmex' AND severity = 'critical'")


# ───────────────────────────────────────────────────────────── clasificar


async def test_clasificar_deja_la_cadena_con_una_vigente(client, base_data):
    iid = await _incidente()
    r = await client.post(
        f"/incidents/{iid}/classification",
        json={"classification": "falso_positivo", "note": "camión"},
        headers=_token(),
    )
    assert r.status_code == 201, r.text
    assert r.json()["current"] is True

    c = await client.get(f"/incidents/{iid}/classifications", headers=_token())
    assert [x["classification"] for x in c.json()["items"]] == ["falso_positivo"]


async def test_corregir_INSERTA_y_las_dos_quedan(client, base_data):
    """La propiedad que hace de esto evidencia y no una casilla editable."""
    iid = await _incidente()
    primera = (
        await client.post(
            f"/incidents/{iid}/classification",
            json={"classification": "real"},
            headers=_token(),
        )
    ).json()

    r = await client.post(
        f"/incidents/{iid}/classification",
        json={
            "classification": "falso_positivo",
            "note": "revisado: fue un camión",
            "supersedes_id": primera["classification_id"],
        },
        headers=_token(),
    )
    assert r.status_code == 201, r.text

    items = (await client.get(f"/incidents/{iid}/classifications", headers=_token())).json()[
        "items"
    ]
    assert len(items) == 2, "la corrección borró la anterior en vez de sustituirla"
    vigentes = [x for x in items if x["current"]]
    assert len(vigentes) == 1 and vigentes[0]["classification"] == "falso_positivo"


async def test_la_base_impide_reescribir_una_clasificacion(client, base_data):
    """Y no la aplicación: append-only con sus dos capas."""
    iid = await _incidente()
    await client.post(
        f"/incidents/{iid}/classification",
        json={"classification": "real"},
        headers=_token(),
    )
    with pytest.raises(Exception, match="append-only"):
        await _sql("UPDATE incident_classifications SET classification = 'prueba'")


async def test_sustituir_una_clasificacion_de_OTRO_incidente_es_409(client, base_data):
    """Rompería la cadena de los dos. Se rechaza en vez de ignorar el campo."""
    uno, dos = await _incidente(), await _incidente()
    ajena = (
        await client.post(
            f"/incidents/{uno}/classification",
            json={"classification": "real"},
            headers=_token(),
        )
    ).json()
    r = await client.post(
        f"/incidents/{dos}/classification",
        json={"classification": "real", "supersedes_id": ajena["classification_id"]},
        headers=_token(),
    )
    assert r.status_code == 409, r.text


async def test_no_hay_default_silencioso(client, base_data):
    """Omitir la clasificación NO cae en `indeterminado`: es 422."""
    iid = await _incidente()
    r = await client.post(f"/incidents/{iid}/classification", json={}, headers=_token())
    assert r.status_code == 422, r.text


async def test_una_clasificacion_fuera_del_catalogo_se_rechaza(client, base_data):
    iid = await _incidente()
    r = await client.post(
        f"/incidents/{iid}/classification",
        json={"classification": "mas_o_menos"},
        headers=_token(),
    )
    assert r.status_code == 422


@pytest.mark.parametrize("role", ["inspector", "gov_operator"])
async def test_roles_sin_la_accion_403(client, base_data, role):
    iid = await _incidente()
    r = await client.post(
        f"/incidents/{iid}/classification",
        json={"classification": "real"},
        headers=_token(role),
    )
    assert r.status_code == 403


async def test_un_incidente_de_otro_cliente_es_404_no_403(client, base_data):
    """«No existe» y «no es tuyo» se contestan igual: si no, esta ruta serviría
    para averiguar si un incidente ajeno existe."""
    ajeno = await _incidente(tenant=au.DB_TENANT_PRIV2, site=au.DB_SITE_PRIV2)
    r = await client.get(f"/incidents/{ajeno}/classifications", headers=_token())
    assert r.status_code == 404


# ─────────────────────────────────────────────────────────────── la tasa


async def test_los_sin_clasificar_salen_APARTE_y_no_del_denominador(client, base_data):
    """El defecto que este test impide: un 0 % precioso calculado sobre los tres
    que a alguien le dio tiempo de revisar, con noventa escondidos."""
    clasificado = await _incidente()
    await _incidente()  # nadie lo miró
    await _incidente()  # ni éste
    await client.post(
        f"/incidents/{clasificado}/classification",
        json={"classification": "falso_positivo"},
        headers=_token(),
    )

    s = (await client.get("/classification-stats", headers=_token())).json()
    assert s["total"] == 3
    assert s["unclassified"] == 2
    assert s["by_classification"]["falso_positivo"] == 1
    assert s["false_positive_rate"] == 1.0


async def test_sin_nada_clasificado_la_tasa_es_NULL_y_no_cero(client, base_data):
    """Un cero afirmaría que no hubo falsos positivos. Lo que pasa es que nadie
    miró, y son cosas distintas."""
    await _incidente()
    s = (await client.get("/classification-stats", headers=_token())).json()
    assert s["total"] == 1
    assert s["unclassified"] == 1
    assert s["false_positive_rate"] is None


async def test_una_prueba_no_cuenta_en_el_denominador(client, base_data):
    """Un incidente provocado a propósito no dice nada sobre si el sistema molesta."""
    prueba, falso = await _incidente(), await _incidente()
    await client.post(
        f"/incidents/{prueba}/classification",
        json={"classification": "prueba"},
        headers=_token(),
    )
    await client.post(
        f"/incidents/{falso}/classification",
        json={"classification": "falso_positivo"},
        headers=_token(),
    )
    s = (await client.get("/classification-stats", headers=_token())).json()
    # 1 falso / (1 falso + 0 reales + 0 indeterminados) = 1.0; la prueba no entra.
    assert s["false_positive_rate"] == 1.0
    assert s["by_classification"]["prueba"] == 1


async def test_la_tasa_usa_la_clasificacion_VIGENTE_no_la_primera(client, base_data):
    iid = await _incidente()
    primera = (
        await client.post(
            f"/incidents/{iid}/classification",
            json={"classification": "falso_positivo"},
            headers=_token(),
        )
    ).json()
    await client.post(
        f"/incidents/{iid}/classification",
        json={"classification": "real", "supersedes_id": primera["classification_id"]},
        headers=_token(),
    )
    s = (await client.get("/classification-stats", headers=_token())).json()
    assert s["by_classification"]["real"] == 1
    assert s["by_classification"]["falso_positivo"] == 0
    assert s["false_positive_rate"] == 0.0


async def test_la_tasa_no_ve_los_incidentes_de_otro_cliente(client, base_data):
    """El aislamiento lo impone la RLS, no un filtro de aplicación."""
    await _incidente(tenant=au.DB_TENANT_PRIV2, site=au.DB_SITE_PRIV2)
    s = (await client.get("/classification-stats", headers=_token())).json()
    assert s["total"] == 0
