"""T-2.45 · Alcance por sitio en la consola, con cutover en dos fases.

El test que gobierna el diseño es el primero de la fase A: si aplicar el filtro dejara
a un `soc_operator` sin datos, el remedio sería peor que el hueco. Por eso la fase A
distingue "no hay restricción declarada" de "la restricción es: ningún sitio".
"""

from __future__ import annotations

import pytest

from takab_api.auth.claims import ALL_SITES, Claims
from takab_api.auth.scope import SCOPE_EXEMPT_ROLES, console_scope

SITIO_A = "11111111-1111-1111-1111-111111111111"
SITIO_B = "22222222-2222-2222-2222-222222222222"


def claims(role: str, scope) -> Claims:  # noqa: ANN001
    return Claims(
        sub="u-1",
        groups=(role,),
        tenant_id="t-1",
        role=role,
        site_scope=scope,
        zone_id="",
        surface="web",
    )


# ---- roles exentos -----------------------------------------------------------


@pytest.mark.parametrize("role", sorted(SCOPE_EXEMPT_ROLES))
@pytest.mark.parametrize("enforced", [False, True])
def test_los_roles_exentos_nunca_se_filtran(role: str, enforced: bool) -> None:
    s = console_scope(claims(role, frozenset()), enforced=enforced)
    assert s.sites is None
    assert s.gap is False


def test_gov_operator_esta_exento_porque_su_alcance_lo_manda_la_visibilidad() -> None:
    """Acotarlo aquí además duplicaría la autoridad en dos mecanismos distintos."""
    assert "gov_operator" in SCOPE_EXEMPT_ROLES


def test_un_scope_de_asterisco_no_filtra_en_ningun_rol() -> None:
    for enforced in (False, True):
        s = console_scope(claims("soc_operator", ALL_SITES), enforced=enforced)
        assert s.sites is None
        assert s.declared is True
        assert s.gap is False


# ---- fase A (la que se despliega) --------------------------------------------


def test_fase_A_un_claim_vacio_NO_deja_la_consola_en_blanco() -> None:
    """El claim no está aprovisionado para usuarios web: filtrar dejaría a todo
    `soc_operator` con cero sitios en una plataforma de alertamiento."""
    s = console_scope(claims("soc_operator", frozenset()), enforced=False)
    assert s.sites is None
    assert s.enforced is False


def test_fase_A_el_hueco_NO_es_silencioso() -> None:
    s = console_scope(claims("soc_operator", frozenset()), enforced=False)
    assert s.gap is True
    assert s.declared is False


def test_fase_A_un_claim_CON_sitios_se_respeta_desde_ya() -> None:
    """Honrar una restricción declarada es estrictamente más seguro; no hay motivo
    para esperar a la fase B."""
    s = console_scope(claims("soc_operator", frozenset({SITIO_A})), enforced=False)
    assert s.sites == frozenset({SITIO_A})
    assert s.gap is False
    assert s.allows(SITIO_A) is True
    assert s.allows(SITIO_B) is False


# ---- fase B ------------------------------------------------------------------


def test_fase_B_un_claim_vacio_significa_cero_sitios() -> None:
    """Que es lo que el claim significa: default-deny (RBAC §5.2)."""
    s = console_scope(claims("soc_operator", frozenset()), enforced=True)
    assert s.sites == frozenset()
    assert s.enforced is True
    assert s.allows(SITIO_A) is False
    # Y ya no es un hueco: la restricción se está aplicando.
    assert s.gap is False


def test_fase_B_no_cambia_nada_para_un_claim_con_sitios() -> None:
    a = console_scope(claims("inspector", frozenset({SITIO_A})), enforced=False)
    b = console_scope(claims("inspector", frozenset({SITIO_A})), enforced=True)
    assert a.sites == b.sites == frozenset({SITIO_A})


# ---- roles acotados ----------------------------------------------------------


@pytest.mark.parametrize("role", ["soc_operator", "inspector", "building_admin"])
def test_los_roles_de_consola_no_exentos_si_se_acotan(role: str) -> None:
    s = console_scope(claims(role, frozenset({SITIO_B})), enforced=False)
    assert s.sites == frozenset({SITIO_B})
