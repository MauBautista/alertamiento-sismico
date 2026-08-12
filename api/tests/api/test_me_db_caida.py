"""T-2.123 · Cómo debe FALLAR ``GET /me`` cuando Postgres no está.

``T-2.114`` ató ``/me`` a la base a propósito (de ahí sale el inmueble del
ocupante) y eso cambió el modo de fallo del arranque de la consola. La decisión
de producto se implementó en el CLIENTE (arranca en degradado y declara que no
puede establecer el alcance); este módulo pone las dos barandillas del SERVIDOR
que hacen que esa decisión siga siendo posible, y que son justo las dos maneras
de relajarla:

1. **``/me`` NO puede devolver 200 con ``enrolled_sites: []``** cuando la base
   no contesta. Sería la "solución" más tentadora —tragarse el error y seguir—
   y es una mentira de las que prohíbe la regla de oro 7: "no tienes inmueble"
   y "no se pudo averiguar tu inmueble" son cosas distintas, y la primera deja
   al ocupante sin pantalla de crisis creyendo que así debe ser.

2. **``/me`` NO puede fallar con 4xx.** El cliente cierra la sesión con el 401
   (token vencido) y sólo con el 401. Un fallo de infraestructura disfrazado de
   problema de credenciales expulsaría al operador al login y le quemaría la
   sesión por una caída de base — la pérdida de pantalla que esta ficha existe
   para evitar.

La base no se "mockea": se apunta el DSN a un puerto cerrado, que es lo que un
Postgres caído le hace de verdad al proceso.
"""

from __future__ import annotations

import httpx
import pytest

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.main import create_app

pytestmark = pytest.mark.anyio

#: DSN sintácticamente válido hacia un puerto que nadie escucha: el intento de
#: conexión se rechaza de inmediato (no cuelga el test).
DSN_SIN_BASE = "postgresql+psycopg://takab:takab_dev@127.0.0.1:1/no_existe"


@pytest.fixture
def sin_base(monkeypatch: pytest.MonkeyPatch):
    """Deja el proceso con la base inalcanzable, y lo devuelve como estaba."""
    monkeypatch.setenv("TAKAB_API_DATABASE_URL", DSN_SIN_BASE)
    deps._reset_caches()
    get_engine.cache_clear()
    yield
    deps._reset_caches()
    get_engine.cache_clear()


def _cliente(app):
    """Cliente que DEVUELVE la excepción del handler como 500, en vez de
    propagarla: es lo que uvicorn le entrega al navegador en producción."""
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    )


async def test_me_con_postgres_caido_no_finge_un_alcance_vacio(sin_base) -> None:
    """CRITERIO · con la base caída ``/me`` NO responde 200.

    Un 200 con ``enrolled_sites: []`` y ``site_scope`` del claim sería un
    alcance INVENTADO: el claim no sabe nada del enrolamiento, y la lista vacía
    afirmaría que el portador no tiene inmueble cuando lo que pasa es que no se
    pudo consultar.
    """
    token = au.make_token("soc_operator", tenant=au.DB_TENANT_PRIV, site_scope="*")
    async with _cliente(create_app()) as client:
        resp = await client.get("/me", headers=au.bearer(token))

    assert resp.status_code != 200, (
        "con Postgres caído /me devolvió 200: se está fingiendo un alcance que "
        "nadie pudo verificar (regla de oro 7)"
    )
    assert resp.status_code >= 500, f"se esperaba un 5xx, llegó {resp.status_code}"


async def test_me_con_postgres_caido_no_parece_un_problema_de_credenciales(sin_base) -> None:
    """CRITERIO · el fallo es 5xx, JAMÁS 401/403.

    El cliente web cierra la sesión con el 401 y sólo con el 401. Si una caída
    de base llegara como 401, el operador perdería la sesión —y la consola— por
    algo que no tiene que ver con su token.
    """
    token = au.make_token("soc_operator", tenant=au.DB_TENANT_PRIV, site_scope="*")
    async with _cliente(create_app()) as client:
        resp = await client.get("/me", headers=au.bearer(token))

    assert resp.status_code not in (401, 403), (
        "una base caída se está reportando como fallo de autorización: el cliente "
        "cerraría la sesión del operador por una caída de infraestructura"
    )
    assert 500 <= resp.status_code < 600


async def test_el_token_invalido_sigue_siendo_401_aunque_no_haya_base(sin_base) -> None:
    """La otra mitad: sin base, un token podrido sigue siendo 401.

    ``get_claims`` no toca la base, así que la verificación del token es previa
    e independiente. Importa que siga así: si una caída de base convirtiera todo
    en 5xx, el degradado del cliente se tragaría también las sesiones vencidas y
    el operador se quedaría reintentando contra un token muerto.
    """
    async with _cliente(create_app()) as client:
        resp = await client.get("/me", headers=au.bearer(au.expired_token()))

    assert resp.status_code == 401, resp.text
