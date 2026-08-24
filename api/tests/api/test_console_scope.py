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
from takab_api.auth import deps
from takab_api.auth.deps import _reset_scope_gaps_for_tests
from takab_api.db.engine import get_engine

pytestmark = pytest.mark.asyncio

#: Rol de consola NO exento, que es donde vive el problema.
ROL = "soc_operator"

#: Los dos lados de `console_scope_enforced`, con nombre en vez de `True/False`.
#:
#: [D-18] Encender la bandera CAMBIA la conducta de tres endpoints, y hasta el
#: 2026-08-22 los tests solo fijaban el lado apagado — así que encenderla ponía la
#: suite en rojo. `D-18`, la ficha `T-2.89` y la fila `RO-5.g` de la matriz decían
#: que eran DOS tests; son TRES (el tercero es el del `scope_gap`: con la bandera
#: encendida `auth/scope.py` devuelve `gap=False` y no se audita nada, así que el
#: `assert n == 1` cae). Ese es justo el rojo que `D-18` quería que no apareciera en
#: mitad de la ventana AWS.
#:
#: **Por qué se PARAMETRIZA en vez de invertirse, que es lo que `D-18` dice.**
#: Invertirlos los dejaría rojos HOY: el valor por defecto sigue —y debe seguir— en
#: `False`, porque la secuencia obligada de `T-2.89` es *recorrer los `scope_gap` →
#: asignar alcance → encender*, y adelantar el encendido en código dejaría a cada
#: `soc_operator` con cero estaciones. Fijando LOS DOS lados, encender la bandera en
#: la ventana A es un cambio de variable de entorno con la suite verde antes y
#: después — que es el espíritu entero de `D-18`, y cubre además el estado del que
#: se sale.
LOS_DOS_LADOS = pytest.mark.parametrize(
    "impuesto", [False, True], ids=["fase-A (hoy)", "impuesto (ventana A)"]
)


@pytest.fixture(autouse=True)
def _clean_gaps() -> None:
    """El dedup de `scope_gap` es por proceso; entre tests hay que soltarlo."""
    _reset_scope_gaps_for_tests()


@pytest.fixture
def bandera(monkeypatch: pytest.MonkeyPatch):
    """Pone `console_scope_enforced` en el valor pedido, para ESTE test.

    `deps._settings()` está cacheada, así que no basta con tocar el entorno: hay que
    soltar la caché o el request seguiría leyendo el valor de antes y el test saldría
    verde midiendo la conducta equivocada. (`routers/me.py` construye `Settings()` en
    caliente y no la necesita, pero el que la necesita es el que filtra.)
    """

    def _poner(valor: bool) -> None:
        monkeypatch.setenv("TAKAB_API_CONSOLE_SCOPE_ENFORCED", "true" if valor else "false")
        deps._reset_caches()

    return _poner


def acotado(*sites: str) -> dict[str, str]:
    return au.bearer(au.make_token(ROL, tenant=au.DB_TENANT_PRIV, site_scope=",".join(sites)))


def sin_scope() -> dict[str, str]:
    """Lo que emite Cognito HOY para un usuario web: el claim no existe."""
    return au.bearer(au.make_token(ROL, tenant=au.DB_TENANT_PRIV, site_scope=""))


def todo() -> dict[str, str]:
    return au.bearer(au.make_token(ROL, tenant=au.DB_TENANT_PRIV, site_scope="*"))


# ---- fase A: la que se despliega ---------------------------------------------


@LOS_DOS_LADOS
async def test_sin_claim_la_consola_ve_todo_o_nada_segun_la_bandera(
    client, base_data, bandera, impuesto: bool
) -> None:
    """El motivo entero del cutover en dos fases, y su otro lado.

    Pide `base_data` a propósito: sin sitios sembrados los dos lados devolverían
    `[]` y el caso impuesto pasaría sin demostrar nada. Con un sitio dentro, el `[]`
    prueba que se filtró.
    """
    bandera(impuesto)
    r = await client.get("/sites", headers=sin_scope())
    assert r.status_code == 200
    if impuesto:
        assert r.json() == [], (
            "con la bandera encendida un rol acotado SIN claim no ve nada: es "
            "default-deny, y es la caída de servicio que la secuencia de T-2.89 "
            "existe para evitar (primero asignar alcance, encender al final)"
        )
    else:
        assert len(r.json()) > 0


@LOS_DOS_LADOS
async def test_el_hueco_se_audita_una_vez_y_deja_de_existir_al_imponerlo(
    client, bandera, impuesto: bool
) -> None:
    """Auditable pero no ruidoso: la regla de oro 10 es por transición, no por
    request, y `audit_log` no se poda nunca (regla 11).

    **Este es el tercer test que la ficha `T-2.89` no cuenta.** Con la bandera
    encendida ya no hay hueco que auditar —`console_scope()` devuelve `gap=False`—,
    así que lo correcto es CERO filas, no una. Y esa es la señal que dice cuándo se
    puede encender: `scope_gap` deja de aparecer cuando todo el mundo tiene alcance.
    """
    bandera(impuesto)
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
    esperado = 0 if impuesto else 1
    assert n == esperado, (
        "impuesto ⇒ no hay hueco que auditar (el alcance vacío YA filtra); "
        "en fase A el hueco se audita una vez por usuario y proceso, no por request"
    )


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


#: Segundo sitio del MISMO tenant, para que `*` tenga algo que no acotar.
SITE_PRIV_EXTRA = "7a000000-0000-0000-0000-0000000000a2"


@pytest.fixture
async def dos_sitios(base_data) -> None:
    """Un segundo sitio en `DB_TENANT_PRIV`.

    Hasta el 2026-08-22 `test_el_asterisco_no_acota` afirmaba `len > 1` sobre sitios
    que sembraban OTROS módulos, así que el fichero salía verde en la suite completa
    y rojo por su cuenta — el veredicto dependía del orden de recolección, que es el
    defecto que `T-2.115` ya pagó una vez. Sembrar aquí lo que este test necesita lo
    vuelve autosuficiente sin tocar a nadie.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
                "(:sid, :tid, 'B2SA2', 'Sitio', "
                "ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography) "
                "ON CONFLICT (site_id) DO NOTHING"
            ),
            {"sid": SITE_PRIV_EXTRA, "tid": au.DB_TENANT_PRIV},
        )


async def test_el_asterisco_no_acota(client, dos_sitios) -> None:
    r = await client.get("/sites", headers=todo())
    ids = {s["site_id"] for s in r.json()}
    assert {au.DB_SITE_PRIV, SITE_PRIV_EXTRA} <= ids, (
        "`*` no acota: tiene que traer los DOS sitios del tenant. Compararlo contra "
        "un conteo suelto hacía que el veredicto dependiera de qué más hubiera en la "
        "base, que es como este test llevaba pasando."
    )


# ---- lo que la UI declara ----------------------------------------------------


@LOS_DOS_LADOS
async def test_me_dice_si_el_servidor_esta_filtrando_de_verdad(
    client, bandera, impuesto: bool
) -> None:
    """La insignia de alcance no puede afirmar un filtro que el servidor no aplica —
    ni negar uno que sí aplica, que es el lado nuevo. `web/src/auth/useSiteScope.ts`
    pinta la insignia con esto: mentir aquí es la regla de oro 7 en la cara del
    operador."""
    bandera(impuesto)
    r = await client.get("/me", headers=sin_scope())
    assert r.json()["console_scope_enforced"] is impuesto

    # Con claim aprovisionado el filtro se aplica DESDE YA, con bandera o sin ella:
    # lo que la bandera decide es solo qué hacer con quien no tiene claim.
    r = await client.get("/me", headers=acotado(au.DB_SITE_PRIV))
    body = r.json()
    assert body["console_scope_enforced"] is True
    assert body["site_scope"] == [au.DB_SITE_PRIV]
