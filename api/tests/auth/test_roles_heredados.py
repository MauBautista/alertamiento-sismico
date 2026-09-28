"""T-9.20 · D-42 — siete roles y la VENTANA DE ALIAS de los tres viejos.

Tres contratos, y cada uno tiene su test explícito aquí (no se prueban de rebote
en los ~90 ficheros que usaban ``soc_operator`` como rol genérico):

1. Un token con rol VIEJO y su grupo VIEJO entra **canonizado**: ``Claims.role`` es
   el canónico (matriz, sesión y RLS son las suyas) y ``Claims.role_raw`` guarda lo
   que traía el token, para la bitácora.
2. La antifalsificación se hace sobre lo CRUDO, exactamente como antes de D-42: un
   ``custom:role`` que no está en ``cognito:groups`` es 401 aunque su alias sí esté
   (o al revés). Canonizar antes de comparar abriría una escalada.
3. Con ``roles_heredados_hasta`` en el pasado, el rol viejo es 401 ``rol_retirado``
   — y ANTES que la edad de sesión: un cliente que viera ``sesion_expirada`` le
   diría a la persona «vuelve a entrar», y volver a entrar no lo arregla.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

import auth_utils as au
from takab_api.auth import deps
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
    ALIAS_HEREDADOS,
    CANONICAL_ROLES,
    ETIQUETA,
    ROL_HISTORICO,
    ROL_RETIRADO,
    RolRetirado,
    canonizar,
    enforce_rol_vigente,
    literales_de,
)
from takab_api.auth.tokens import AuthError, decode_verify

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
D42_ALIAS = {
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


def _surface(role: str) -> str:
    return "mobile" if canonizar(role) in {"brigadista", "occupant"} else "web"


# --- el catálogo --------------------------------------------------------------------


def test_los_canonicos_son_los_siete_de_D42() -> None:
    assert tuple(CANONICAL_ROLES) == D42_CANONICOS
    assert dict(ALIAS_HEREDADOS) == D42_ALIAS
    assert dict(ETIQUETA) == D42_ETIQUETAS


def test_la_matriz_y_la_sesion_tienen_EXACTAMENTE_los_siete() -> None:
    assert set(ROLE_ROUTE_MATRIX) == set(D42_CANONICOS)
    assert set(ROLE_ACTION_MATRIX) == set(D42_CANONICOS)
    assert set(SESSION_MAX_AGE_S) == set(D42_CANONICOS)


def test_ningun_alias_apunta_a_otro_alias_ni_a_un_rol_inexistente() -> None:
    for viejo, nuevo in ALIAS_HEREDADOS.items():
        assert viejo not in CANONICAL_ROLES
        assert nuevo in CANONICAL_ROLES


def test_las_etiquetas_historicas_cubren_los_tres_viejos() -> None:
    """El papel de un reporte viejo sigue diciendo el rol con el que se firmó."""
    assert set(ROL_HISTORICO) == set(D42_ALIAS)
    assert all(v.strip() for v in ROL_HISTORICO.values())


def test_el_canonico_hereda_TODO_lo_de_soc_operator_y_security_guard() -> None:
    """Copia A MANO de lo que tenían antes de D-42: nada se pierde para su canónico."""
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


def test_literales_de_brigadista_incluyen_sus_alias() -> None:
    assert set(literales_de("brigadista")) == {"brigadista", "security_guard", "building_admin"}
    assert set(literales_de("tenant_admin")) == {"tenant_admin", "soc_operator"}
    assert literales_de("inspector") == ("inspector",)


# --- Claims.from_verified: canonizar DESPUÉS de comprobar -----------------------------


@pytest.mark.parametrize(("viejo", "nuevo"), sorted(D42_ALIAS.items()))
def test_token_viejo_con_su_grupo_viejo_entra_canonizado(viejo: str, nuevo: str) -> None:
    claims = Claims.from_verified(
        decode_verify(
            au.make_token(viejo, surface=_surface(viejo)),
            au.test_settings(),
            select_jwks(au.test_settings()),
        )
    )
    assert claims.role == nuevo
    assert claims.role_raw == viejo


def test_token_canonico_trae_role_raw_igual() -> None:
    claims = Claims.from_verified(
        decode_verify(
            au.make_token("inspector"), au.test_settings(), select_jwks(au.test_settings())
        )
    )
    assert claims.role == claims.role_raw == "inspector"


@pytest.mark.parametrize(
    ("role", "groups"),
    [
        # el ALIAS del rol crudo está en los grupos, pero el crudo no: es justo lo que
        # se colaría si alguien canonizara ANTES de comparar (revisión de F2)
        ("soc_operator", ["tenant_admin"]),
        ("building_admin", ["brigadista"]),
        # ni el crudo ni su alias están en los grupos
        ("soc_operator", ["brigadista"]),
        ("tenant_admin", ["soc_operator"]),
        ("security_guard", ["brigadista"]),
        ("brigadista", ["security_guard"]),
        ("building_admin", ["brigadista"]),
    ],
)
def test_token_falsificado_es_401_role_not_in_groups(role: str, groups: list[str]) -> None:
    tok = au.make_token(role, **{"cognito:groups": groups})
    with pytest.raises(AuthError, match="role not in groups"):
        Claims.from_verified(
            decode_verify(tok, au.test_settings(), select_jwks(au.test_settings()))
        )


# --- la baja: rol_retirado ------------------------------------------------------------


def test_enforce_rol_vigente_ventana_abierta_por_defecto() -> None:
    c = _claims_de("soc_operator")
    enforce_rol_vigente(c, None, hoy=date(2030, 1, 1))  # no lanza


def test_enforce_rol_vigente_el_dia_de_la_baja_aun_entra() -> None:
    c = _claims_de("soc_operator")
    enforce_rol_vigente(c, date(2026, 10, 1), hoy=date(2026, 10, 1))


def test_enforce_rol_vigente_pasada_la_baja_es_rol_retirado() -> None:
    c = _claims_de("security_guard")
    with pytest.raises(RolRetirado) as exc:
        enforce_rol_vigente(c, date(2026, 10, 1), hoy=date(2026, 10, 2))
    assert exc.value.reason == ROL_RETIRADO == "rol_retirado"
    assert exc.value.status == 401
    assert isinstance(exc.value, AuthError)


def test_enforce_rol_vigente_no_afecta_a_un_canonico() -> None:
    enforce_rol_vigente(_claims_de("tenant_admin"), date(2020, 1, 1), hoy=date(2030, 1, 1))


def _claims_de(role: str) -> Claims:
    return Claims.from_verified(
        decode_verify(
            au.make_token(role, surface=_surface(role)),
            au.test_settings(),
            select_jwks(au.test_settings()),
        )
    )


# --- HTTP: /me ------------------------------------------------------------------------


async def _me(client, token: str):
    return await client.get("/me", headers=au.bearer(token))


async def test_me_con_soc_operator_devuelve_la_matriz_de_tenant_admin(client, db_engine) -> None:
    resp = await _me(client, au.make_token("soc_operator", auth_age=60))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role"] == "tenant_admin"
    assert body["allowed_routes"] == allowed_routes("tenant_admin")
    assert body["allowed_actions"] == allowed_actions("tenant_admin")
    assert body["session_max_age_s"] == SESSION_MAX_AGE_S["tenant_admin"]


async def test_me_con_security_guard_tiene_la_sesion_de_30_dias(client, db_engine) -> None:
    """D-42: el ex-guardia pasa a la sesión del brigadista. A los 2 días (antes, 24 h ⇒
    caducada) sigue dentro."""
    tok = au.make_token("security_guard", surface="mobile", auth_age=2 * DAY)
    resp = await _me(client, tok)
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "brigadista"
    assert resp.json()["session_max_age_s"] == 30 * DAY


async def test_me_falsificado_es_401(client, db_engine) -> None:
    resp = await _me(client, au.make_token("soc_operator", **{"cognito:groups": ["brigadista"]}))
    assert resp.status_code == 401
    resp = await _me(client, au.make_token("tenant_admin", **{"cognito:groups": ["soc_operator"]}))
    assert resp.status_code == 401


def _baja_ayer(monkeypatch: pytest.MonkeyPatch) -> None:
    ayer = (date.today() - timedelta(days=2)).isoformat()
    monkeypatch.setenv("TAKAB_API_ROLES_HEREDADOS_HASTA", ayer)
    deps._reset_caches()


async def test_pasada_la_baja_el_rol_viejo_es_401_rol_retirado(
    client, db_engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _baja_ayer(monkeypatch)
    resp = await _me(client, au.make_token("soc_operator", auth_age=60))
    assert resp.status_code == 401
    assert resp.json()["detail"] == "rol_retirado"
    assert 'error_description="rol_retirado"' in resp.headers["WWW-Authenticate"]


async def test_rol_retirado_va_ANTES_que_la_edad_de_sesion(
    client, db_engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sesión caducada Y rol retirado ⇒ el motivo es ``rol_retirado``: re-entrar con
    el mismo usuario no arregla nada; hay que cambiarle el rol."""
    _baja_ayer(monkeypatch)
    resp = await _me(client, au.make_token("building_admin", surface="mobile", auth_age=40 * DAY))
    assert resp.status_code == 401
    assert resp.json()["detail"] == "rol_retirado"


async def test_pasada_la_baja_el_canonico_sigue_entrando(
    client, db_engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _baja_ayer(monkeypatch)
    resp = await _me(client, au.make_token("tenant_admin", auth_age=60))
    assert resp.status_code == 200, resp.text


def test_settings_roles_heredados_hasta_por_defecto_None() -> None:
    assert au.test_settings().roles_heredados_hasta is None


async def test_dev_token_con_rol_viejo_entra_canonizado(client, db_engine) -> None:
    """``/dev/token`` sigue aceptando un rol viejo (con su grupo viejo): es como se
    ensaya la ventana en local y en los E2E sin Cognito."""
    tok = (
        await client.post(
            "/dev/token",
            json={"role": "building_admin", "tenant_id": au.TENANT_A, "surface": "mobile"},
        )
    ).json()["id_token"]
    resp = await _me(client, tok)
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "brigadista"


def test_la_fecha_de_baja_se_cuenta_en_hora_de_MEXICO(monkeypatch: pytest.MonkeyPatch) -> None:
    """El día «hasta» lo escribe una persona en México. El 27 a las 20:00 hora local
    ya es día 28 en UTC: con la fecha de UTC la baja se adelantaba seis horas."""
    from datetime import UTC, datetime

    from takab_api.auth import roles

    instante = datetime(2026, 9, 28, 2, 0, tzinfo=UTC)  # 27-sep 20:00 en CDMX

    class _Reloj(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return instante.astimezone(tz) if tz else instante

    monkeypatch.setattr(roles, "datetime", _Reloj)
    claims = Claims.from_verified(
        decode_verify(
            au.make_token("soc_operator"), au.test_settings(), select_jwks(au.test_settings())
        )
    )
    roles.enforce_rol_vigente(claims, date(2026, 9, 27))  # todavía es el 27 en México
    with pytest.raises(roles.RolRetirado):
        roles.enforce_rol_vigente(claims, date(2026, 9, 26))


def test_la_variable_de_baja_VACIA_es_ventana_abierta(monkeypatch: pytest.MonkeyPatch) -> None:
    """Presente pero vacía (plantilla .env, terraform) no puede tumbar la API al arrancar."""
    from takab_api.settings import Settings

    monkeypatch.setenv("TAKAB_API_ROLES_HEREDADOS_HASTA", "")
    assert Settings().roles_heredados_hasta is None
