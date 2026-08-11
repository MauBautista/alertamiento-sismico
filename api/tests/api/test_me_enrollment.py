"""T-2.114 · ``GET /me`` devuelve el inmueble del occupant.

Declarada como hueco por T-2.109. El sitio vigilado del occupant NO viaja en el
claim de Cognito —sale del enrolamiento, que vive en ``user_zone_assignments``—
así que el teléfono era la ÚNICA memoria de a qué edificio pertenece. Por eso
``mySite.ts`` no lo borraba al cerrar sesión: borrarlo dejaba tirado al ocupante
hasta conseguir otro código de alta. Consecuencia: el siguiente usuario del
MISMO teléfono heredaba el edificio del anterior.

Con el sitio en ``/me`` el servidor vuelve a ser la fuente de verdad, el cliente
puede soltar el caché al cerrar sesión y el mismo ocupante lo recupera al
volver a entrar SIN código nuevo.
"""

from __future__ import annotations

import uuid

import pytest

import auth_utils as au
from takab_api.auth import deps
from takab_api.main import create_app
from tests.api.test_mobile_core import ZONE_PRIV, _occ, _seed_zone_and_code

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def _occupants_pool(monkeypatch: pytest.MonkeyPatch):
    au.occupants_env(monkeypatch)
    deps._reset_caches()
    yield
    deps._reset_caches()


async def test_el_occupant_recien_enrolado_ve_su_inmueble_en_me(base_data) -> None:
    """CRITERIO · ``/me`` devuelve el sitio del occupant.

    Antes del enrolamiento la lista está VACÍA (default-deny declarado, no un
    sitio adivinado); después trae el inmueble con su nombre y su zona, que es
    justo lo que el teléfono no debería tener que recordar.
    """
    await _seed_zone_and_code()
    sub = str(uuid.uuid4())
    async with au.client_for(create_app()) as client:
        antes = await client.get("/me", headers=au.bearer(_occ(user_id=sub)))
        assert antes.status_code == 200, antes.text
        assert antes.json()["enrolled_sites"] == []

        alta = await client.post(
            "/me/enrollment", json={"code": "CODE-P10"}, headers=au.bearer(_occ(user_id=sub))
        )
        assert alta.status_code == 200, alta.text

        despues = await client.get("/me", headers=au.bearer(_occ(user_id=sub)))
        assert despues.status_code == 200, despues.text
        sitios = despues.json()["enrolled_sites"]

    assert len(sitios) == 1
    assert sitios[0]["site_id"] == au.DB_SITE_PRIV
    assert sitios[0]["site_name"]
    assert sitios[0]["zone_id"] == ZONE_PRIV
    assert sitios[0]["role"] == "occupant"


async def test_dos_ocupantes_distintos_no_comparten_inmueble(base_data) -> None:
    """CRITERIO (lado servidor) del "mismo teléfono, dos usuarios": cada token
    recibe SU enrolamiento, jamás el del portador anterior. Es lo que permite al
    cliente tirar el caché al cerrar sesión sin dejar tirado a nadie."""
    await _seed_zone_and_code()
    enrolado = str(uuid.uuid4())
    recien_llegado = str(uuid.uuid4())
    async with au.client_for(create_app()) as client:
        await client.post(
            "/me/enrollment", json={"code": "CODE-P10"}, headers=au.bearer(_occ(user_id=enrolado))
        )
        uno = await client.get("/me", headers=au.bearer(_occ(user_id=enrolado)))
        dos = await client.get("/me", headers=au.bearer(_occ(user_id=recien_llegado)))

    assert [s["site_id"] for s in uno.json()["enrolled_sites"]] == [au.DB_SITE_PRIV]
    assert dos.json()["enrolled_sites"] == [], (
        "el segundo usuario NO hereda el edificio del primero"
    )


async def test_volver_a_entrar_recupera_el_inmueble_sin_codigo_nuevo(base_data) -> None:
    """El mismo ocupante que cerró sesión vuelve y ``/me`` le devuelve su
    edificio: no hace falta otro código de alta. Ésta es la razón por la que
    ahora SÍ se puede soltar el caché del teléfono."""
    await _seed_zone_and_code()
    sub = str(uuid.uuid4())
    async with au.client_for(create_app()) as client:
        await client.post(
            "/me/enrollment", json={"code": "CODE-P10"}, headers=au.bearer(_occ(user_id=sub))
        )
        # "Cerrar sesión y volver a entrar" = un token nuevo del mismo sujeto.
        vuelta = await client.get("/me", headers=au.bearer(_occ(user_id=sub)))

    assert [s["site_id"] for s in vuelta.json()["enrolled_sites"]] == [au.DB_SITE_PRIV]


async def test_el_enrolamiento_de_otro_tenant_no_se_ve(base_data) -> None:
    """Regla de oro 5: el mismo ``sub`` con un token de OTRO tenant no ve el
    enrolamiento (RLS ``uza_read`` filtra por ``app_tenant_id()``)."""
    await _seed_zone_and_code()
    sub = str(uuid.uuid4())
    async with au.client_for(create_app()) as client:
        await client.post(
            "/me/enrollment", json={"code": "CODE-P10"}, headers=au.bearer(_occ(user_id=sub))
        )
        otro = await client.get(
            "/me", headers=au.bearer(_occ(user_id=sub, tenant=au.DB_TENANT_PRIV2))
        )

    assert otro.status_code == 200
    assert otro.json()["enrolled_sites"] == []


async def test_un_rol_de_consola_sin_enrolamiento_no_rompe(base_data) -> None:
    """La consola no se enrola por código: lista vacía y contrato intacto (el
    alcance de consola sigue viniendo de ``site_scope``)."""
    async with au.client_for(create_app()) as client:
        resp = await client.get(
            "/me",
            headers=au.bearer(
                au.make_token("soc_operator", tenant=au.DB_TENANT_PRIV, site_scope="*")
            ),
        )
    assert resp.status_code == 200
    assert resp.json()["enrolled_sites"] == []
    assert resp.json()["site_scope"] == "*"
