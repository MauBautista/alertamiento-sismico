"""T-2.45 · El alcance por sitio, ejercido contra los endpoints reales.

`tests/auth/test_console_scope.py` prueba la decisión; esto prueba que la decisión
LLEGA a las seis superficies de consola. Sin este archivo, la función podría estar
perfecta y la consola seguir enseñando todo el tenant.
"""

from __future__ import annotations

import jwt
import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.auth.deps import _reset_scope_gaps_for_tests
from takab_api.db.engine import get_engine

pytestmark = pytest.mark.asyncio

#: Rol de consola NO exento, que es donde vive el problema.
ROL = "soc_operator"


@pytest.fixture(autouse=True)
def _clean_gaps() -> None:
    """El dedup de `scope_gap` es por proceso; entre tests hay que soltarlo."""
    _reset_scope_gaps_for_tests()


def acotado(*sites: str) -> dict[str, str]:
    return au.bearer(au.make_token(ROL, tenant=au.DB_TENANT_PRIV, site_scope=",".join(sites)))


def sin_scope() -> dict[str, str]:
    """Lo que emite Cognito HOY para un usuario web: el claim no existe."""
    return au.bearer(au.make_token(ROL, tenant=au.DB_TENANT_PRIV, site_scope=""))


def todo() -> dict[str, str]:
    return au.bearer(au.make_token(ROL, tenant=au.DB_TENANT_PRIV, site_scope="*"))


# ---- fase A: la que se despliega ---------------------------------------------


async def test_fase_A_sin_claim_la_consola_NO_se_queda_en_blanco(client) -> None:
    """El motivo entero del cutover en dos fases."""
    r = await client.get("/sites", headers=sin_scope())
    assert r.status_code == 200
    assert len(r.json()) > 0


async def test_fase_A_el_hueco_queda_auditado_una_sola_vez(client) -> None:
    """Auditable pero no ruidoso: la regla de oro 10 es por transición, no por
    request, y `audit_log` no se poda nunca (regla 11)."""
    token = au.make_token(ROL, tenant=au.DB_TENANT_PRIV, site_scope="")
    sub = jwt.decode(token, options={"verify_signature": False})["sub"]
    headers = au.bearer(token)
    for _ in range(3):
        await client.get("/sites", headers=headers)

    engine = get_engine()
    async with engine.begin() as conn:
        n = await conn.scalar(
            text("SELECT count(*) FROM audit_log WHERE verb = 'scope_gap' AND actor = :a"),
            {"a": f"user:{sub}"},
        )
    assert n == 1, "el hueco se audita una vez por usuario y proceso, no por request"


# ---- el claim aprovisionado SÍ acota, desde ya -------------------------------


async def test_sites_solo_devuelve_los_del_alcance(client) -> None:
    r = await client.get("/sites", headers=acotado(au.DB_SITE_PRIV))
    assert r.status_code == 200
    ids = {s["site_id"] for s in r.json()}
    assert ids == {au.DB_SITE_PRIV}


async def test_el_mapa_solo_pinta_los_del_alcance(client) -> None:
    r = await client.get("/telemetry/map/state", headers=acotado(au.DB_SITE_PRIV))
    assert r.status_code == 200
    assert {s["site_id"] for s in r.json()["sites"]} <= {au.DB_SITE_PRIV}


async def test_la_flota_solo_lista_los_gabinetes_del_alcance(client) -> None:
    r = await client.get("/fleet/gateways", headers=acotado(au.DB_SITE_PRIV))
    assert r.status_code == 200
    assert all(g["site_id"] == au.DB_SITE_PRIV for g in r.json())


async def test_los_incidentes_se_acotan(client, make_incident) -> None:
    await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    r = await client.get("/incidents", headers=acotado(au.DB_SITE_PRIV))
    assert r.status_code == 200
    assert all(i["site_id"] == au.DB_SITE_PRIV for i in r.json()["items"])


async def test_un_alcance_ajeno_no_devuelve_nada_del_tenant(client) -> None:
    """Un site_id que existe en OTRO tenant no filtra nada hacia dentro."""
    r = await client.get("/sites", headers=acotado(au.DB_SITE_PRIV2))
    assert r.status_code == 200
    assert r.json() == []


# ---- fuera de alcance ⇒ 404, nunca 403 ---------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/sites/{sid}",
        "/telemetry/sites/{sid}/features",
        "/telemetry/sites/{sid}/features/by-channel",
        "/telemetry/sites/{sid}/metrics",
    ],
)
async def test_fuera_de_alcance_es_404_no_403(client, path: str) -> None:
    """Un 403 confirmaría que el sitio existe; el 404 no dice nada."""
    headers = acotado(au.DB_SITE_PRIV2)  # alcance a un sitio que NO es el pedido
    r = await client.get(path.format(sid=au.DB_SITE_PRIV), headers=headers)
    assert r.status_code == 404, r.text


async def test_dentro_del_alcance_el_mismo_endpoint_responde(client) -> None:
    """Contraprueba: el 404 de arriba es por alcance, no porque el endpoint no exista."""
    r = await client.get(f"/sites/{au.DB_SITE_PRIV}", headers=acotado(au.DB_SITE_PRIV))
    assert r.status_code == 200


# ---- exentos -----------------------------------------------------------------


async def test_un_superadmin_no_se_acota_aunque_traiga_scope(client) -> None:
    tok = au.bearer(
        au.make_token("takab_superadmin", tenant=au.DB_TENANT_PRIV, site_scope=au.DB_SITE_PRIV2)
    )
    r = await client.get(f"/sites/{au.DB_SITE_PRIV}", headers=tok)
    assert r.status_code == 200


async def test_el_asterisco_no_acota(client) -> None:
    r = await client.get("/sites", headers=todo())
    assert len(r.json()) > 1


# ---- lo que la UI declara ----------------------------------------------------


async def test_me_dice_si_el_servidor_esta_filtrando_de_verdad(client) -> None:
    """La insignia de alcance no puede afirmar un filtro que el servidor no aplica."""
    r = await client.get("/me", headers=sin_scope())
    assert r.json()["console_scope_enforced"] is False

    r = await client.get("/me", headers=acotado(au.DB_SITE_PRIV))
    body = r.json()
    assert body["console_scope_enforced"] is True
    assert body["site_scope"] == [au.DB_SITE_PRIV]
