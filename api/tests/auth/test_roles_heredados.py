"""T-9.81 · D-42 — la BAJA de los tres roles viejos (antes: su ventana de alias, T-9.20).

``migrar_roles_7.py --verify`` dio cero: nadie tiene ya rol ni grupo viejo. Con eso la
ventana se cerró en el código, no con una fecha:

1. Un token con ``soc_operator``, ``security_guard`` o ``building_admin`` es SIEMPRE 401
   ``rol_retirado`` (WS: 4401 con ese motivo, ``tests/ws/test_ws_rol_retirado.py``),
   sin fecha que lo abra, y ANTES que la edad de sesión: un cliente que viera
   ``sesion_expirada`` le diría a la persona «vuelve a entrar», y volver a entrar con
   el mismo rol no lo arregla.
2. La antifalsificación no cambia: un ``custom:role`` que no está en ``cognito:groups``
   sigue siendo «role not in groups», se comprueba PRIMERO.
3. La historia no se reescribe: ``ROL_HISTORICO`` sigue rotulando las filas viejas.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

import auth_utils as au
from takab_api.auth import deps, roles
from takab_api.auth.claims import Claims
from takab_api.auth.jwks import select_jwks
from takab_api.auth.matrix import (
    ROLE_ACTION_MATRIX,
    ROLE_ROUTE_MATRIX,
    SESSION_MAX_AGE_S,
    allowed_actions,
    allowed_routes,
)
from takab_api.auth.roles import (
    CANONICAL_ROLES,
    ETIQUETA,
    HEREDERO_HISTORICO,
    ROL_HISTORICO,
    ROL_RETIRADO,
    ROLES_RETIRADOS,
    RolRetirado,
    literales_de,
)
from takab_api.auth.tokens import AuthError, decode_verify
from takab_api.settings import Settings

DAY = 86_400

#: D-42 tal como la tomó Mauricio. Copia A MANO a propósito.
D42_CANONICOS = (
    "takab_superadmin",
    "takab_support",
    "tenant_admin",
    "gov_operator",
    "inspector",
    "brigadista",
    "occupant",
)
D42_RETIRADOS = {"soc_operator", "security_guard", "building_admin"}
D42_HEREDERO = {
    "soc_operator": "tenant_admin",
    "security_guard": "brigadista",
    "building_admin": "brigadista",
}
D42_ETIQUETAS = {
    "takab_superadmin": "SUPERADMIN TAKAB",
    "takab_support": "SOPORTE TAKAB",
    "tenant_admin": "ADMINISTRADOR",
    "gov_operator": "GOBIERNO",
    "inspector": "INSPECTOR",
    "brigadista": "BRIGADISTA",
    "occupant": "OCUPANTE",
}
VIEJOS = sorted(D42_RETIRADOS)


def _surface(role: str) -> str:
    return "mobile" if role in {"brigadista", "occupant", "security_guard"} else "web"


def _verificado(role: str, **kw) -> dict:
    kw.setdefault("surface", _surface(role))
    return decode_verify(
        au.make_token(role, **kw), au.test_settings(), select_jwks(au.test_settings())
    )


# --- el catálogo --------------------------------------------------------------------


def test_los_canonicos_son_los_siete_de_D42() -> None:
    assert tuple(CANONICAL_ROLES) == D42_CANONICOS
    assert dict(ETIQUETA) == D42_ETIQUETAS


def test_los_retirados_son_los_tres_de_D42() -> None:
    assert set(ROLES_RETIRADOS) == D42_RETIRADOS
    assert not set(ROLES_RETIRADOS) & set(CANONICAL_ROLES)


def test_la_matriz_y_la_sesion_tienen_EXACTAMENTE_los_siete() -> None:
    assert set(ROLE_ROUTE_MATRIX) == set(D42_CANONICOS)
    assert set(ROLE_ACTION_MATRIX) == set(D42_CANONICOS)
    assert set(SESSION_MAX_AGE_S) == set(D42_CANONICOS)


def test_las_etiquetas_historicas_cubren_los_tres_retirados() -> None:
    """El papel de un reporte viejo sigue diciendo el rol con el que se firmó."""
    assert set(ROL_HISTORICO) == D42_RETIRADOS
    assert all(v.strip() for v in ROL_HISTORICO.values())


def test_la_traduccion_de_tokens_ya_no_existe() -> None:
    """[T-9.81] Ni ``canonizar`` ni la palanca de fecha: si alguien las resucitara, un
    token viejo volvería a entrar con los permisos de su heredero."""
    for nombre in ("ALIAS_HEREDADOS", "canonizar", "es_heredado", "enforce_rol_vigente"):
        assert not hasattr(roles, nombre), nombre
    assert "role_raw" not in Claims.__dataclass_fields__
    assert "roles_heredados_hasta" not in Settings.model_fields


def test_el_heredero_historico_es_el_de_D42_y_solo_nombra_canonicos() -> None:
    """Solo para FILTRAR filas guardadas (``literales_de``), jamás para un token."""
    assert dict(HEREDERO_HISTORICO) == D42_HEREDERO
    assert set(HEREDERO_HISTORICO.values()) <= set(CANONICAL_ROLES)


def test_el_canonico_hereda_TODO_lo_de_soc_operator_y_security_guard() -> None:
    """Copia A MANO de lo que tenían antes de D-42: nada se perdió para su canónico."""
    soc_rutas = {"/console", "/fleet", "/triage", "/building"}
    soc_acciones = {
        "classify_incident",
        "ack_incident",
        "relocate_epicenter",
        "request_dictamen",
        "cctv_read",
        "cctv_video",
    }
    guardia = {
        "checkin_submit",
        "roster_read",
        "damage_report_submit",
        "evidence_upload",
        "siren_silence",
        "manual_activate",
        "dictamen_read",
        "panel_read",
        "movement_alert",
    }
    assert soc_rutas <= set(allowed_routes("tenant_admin"))
    ta = {a for a, v in allowed_actions("tenant_admin").items() if v}
    assert soc_acciones <= ta
    br = {a for a, v in allowed_actions("brigadista").items() if v}
    assert guardia <= br


def test_tenant_admin_gana_generate_report() -> None:
    assert allowed_actions("tenant_admin")["generate_report"] is True


def test_literales_de_brigadista_incluyen_sus_literales_viejos() -> None:
    assert set(literales_de("brigadista")) == {"brigadista", "security_guard", "building_admin"}
    assert set(literales_de("tenant_admin")) == {"tenant_admin", "soc_operator"}
    assert literales_de("inspector") == ("inspector",)


# --- Claims.from_verified: el rol viejo es rol_retirado --------------------------------


@pytest.mark.parametrize("viejo", VIEJOS)
def test_token_viejo_con_su_grupo_viejo_es_rol_retirado(viejo: str) -> None:
    with pytest.raises(RolRetirado) as exc:
        Claims.from_verified(_verificado(viejo))
    assert exc.value.reason == ROL_RETIRADO == "rol_retirado"
    assert exc.value.status == 401
    assert isinstance(exc.value, AuthError)


def test_token_canonico_entra_con_su_rol() -> None:
    assert Claims.from_verified(_verificado("inspector")).role == "inspector"


@pytest.mark.parametrize(
    ("role", "groups"),
    [
        # el heredero del rol crudo está en los grupos, pero el crudo no
        ("soc_operator", ["tenant_admin"]),
        ("building_admin", ["brigadista"]),
        ("soc_operator", ["brigadista"]),
        ("tenant_admin", ["soc_operator"]),
        ("security_guard", ["brigadista"]),
        ("brigadista", ["security_guard"]),
    ],
)
def test_token_falsificado_es_401_role_not_in_groups(role: str, groups: list[str]) -> None:
    tok = au.make_token(role, **{"cognito:groups": groups})
    with pytest.raises(AuthError, match="role not in groups"):
        Claims.from_verified(
            decode_verify(tok, au.test_settings(), select_jwks(au.test_settings()))
        )


# --- HTTP: /me ------------------------------------------------------------------------


async def _me(client, token: str):
    return await client.get("/me", headers=au.bearer(token))


@pytest.mark.parametrize("viejo", VIEJOS)
async def test_me_con_rol_viejo_es_401_rol_retirado(client, db_engine, viejo: str) -> None:
    resp = await _me(client, au.make_token(viejo, surface=_surface(viejo), auth_age=60))
    assert resp.status_code == 401
    assert resp.json()["detail"] == "rol_retirado"
    assert 'error_description="rol_retirado"' in resp.headers["WWW-Authenticate"]


@pytest.mark.parametrize("dias", [-3650, -1, 0, 1, 3650])
async def test_rol_retirado_con_CUALQUIER_fecha_en_la_variable_vieja(
    client, db_engine, monkeypatch: pytest.MonkeyPatch, dias: int
) -> None:
    """La variable ``TAKAB_API_ROLES_HEREDADOS_HASTA`` que quede en un ``.env`` viejo ya
    no abre nada, ni en el pasado ni en el futuro (ni tumba la API al arrancar)."""
    monkeypatch.setenv(
        "TAKAB_API_ROLES_HEREDADOS_HASTA", (date.today() + timedelta(days=dias)).isoformat()
    )
    deps._reset_caches()
    resp = await _me(client, au.make_token("soc_operator", auth_age=60))
    assert resp.status_code == 401
    assert resp.json()["detail"] == "rol_retirado"


async def test_rol_retirado_va_ANTES_que_la_edad_de_sesion(client, db_engine) -> None:
    """Sesión caducada Y rol retirado ⇒ el motivo es ``rol_retirado``: re-entrar con
    el mismo usuario no arregla nada; hay que cambiarle el rol."""
    resp = await _me(client, au.make_token("building_admin", surface="mobile", auth_age=40 * DAY))
    assert resp.status_code == 401
    assert resp.json()["detail"] == "rol_retirado"


async def test_el_canonico_sigue_entrando(client, db_engine) -> None:
    resp = await _me(client, au.make_token("tenant_admin", auth_age=60))
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "tenant_admin"


async def test_me_falsificado_es_401_generico(client, db_engine) -> None:
    resp = await _me(client, au.make_token("soc_operator", **{"cognito:groups": ["brigadista"]}))
    assert resp.status_code == 401
    assert resp.json()["detail"] == "role not in groups"
    resp = await _me(client, au.make_token("tenant_admin", **{"cognito:groups": ["soc_operator"]}))
    assert resp.status_code == 401


async def test_dev_token_con_rol_viejo_es_rol_retirado(client, db_engine) -> None:
    """``/dev/token`` sigue firmando lo que se le pida (es como se ensaya en local sin
    Cognito), pero el token que sale con un rol viejo ya no entra."""
    tok = (
        await client.post(
            "/dev/token",
            json={"role": "building_admin", "tenant_id": au.TENANT_A, "surface": "mobile"},
        )
    ).json()["id_token"]
    resp = await _me(client, tok)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "rol_retirado"
