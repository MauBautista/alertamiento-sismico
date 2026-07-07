"""Claims.from_verified: role∈groups, site_scope default-deny, surface."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

import auth_utils as au
from takab_api.auth import ALL_SITES, Claims, decode_verify, scope_filter, select_jwks
from takab_api.auth.tokens import AuthError


def _verified(**over: object) -> dict:
    settings = au.test_settings()
    jwks = select_jwks(settings)
    token = au.make_token(over.pop("role", "soc_operator"), **over)
    return decode_verify(token, settings, jwks)


def test_from_verified_end_to_end() -> None:
    claims = Claims.from_verified(_verified(role="inspector", surface="both"))
    assert claims.role == "inspector"
    assert "inspector" in claims.groups
    assert claims.surface == "both"
    assert claims.tenant_id == au.TENANT_A


def test_role_not_in_groups_raises_401() -> None:
    payload = {
        "sub": "u",
        "cognito:groups": ["occupant"],
        "custom:role": "soc_operator",
        "custom:tenant_id": au.TENANT_A,
        "custom:site_scope": "*",
        "custom:surface": "web",
        "custom:zone_id": "",
    }
    with pytest.raises(AuthError) as excinfo:
        Claims.from_verified(payload)
    assert excinfo.value.status == 401
    assert "role not in groups" in excinfo.value.reason


def _payload(**over: object) -> dict:
    base = {
        "sub": "u",
        "cognito:groups": ["soc_operator"],
        "custom:role": "soc_operator",
        "custom:tenant_id": au.TENANT_A,
        "custom:site_scope": "*",
        "custom:surface": "web",
        "custom:zone_id": "",
    }
    base.update(over)
    return base


def test_site_scope_star_is_all_sites() -> None:
    claims = Claims.from_verified(_payload(**{"custom:site_scope": "*"}))
    assert claims.site_scope is ALL_SITES
    assert scope_filter(claims) is None


def test_site_scope_empty_is_zero_sites() -> None:
    claims = Claims.from_verified(_payload(**{"custom:site_scope": ""}))
    assert claims.site_scope == frozenset()
    assert scope_filter(claims) == frozenset()


def test_site_scope_absent_is_zero_sites() -> None:
    payload = _payload()
    del payload["custom:site_scope"]
    claims = Claims.from_verified(payload)
    assert claims.site_scope == frozenset()


def test_site_scope_csv_is_set() -> None:
    a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    claims = Claims.from_verified(_payload(**{"custom:site_scope": f"{a}, {b}"}))
    assert claims.site_scope == frozenset({a, b})
    assert scope_filter(claims) == frozenset({a, b})


@pytest.mark.parametrize("surface", ["web", "mobile", "both"])
def test_valid_surfaces(surface: str) -> None:
    claims = Claims.from_verified(_payload(**{"custom:surface": surface}))
    assert claims.surface == surface


@pytest.mark.parametrize("surface", ["", "desktop", "WEB"])
def test_invalid_surface_raises_401(surface: str) -> None:
    with pytest.raises(AuthError) as excinfo:
        Claims.from_verified(_payload(**{"custom:surface": surface}))
    assert excinfo.value.status == 401


def test_claims_is_immutable() -> None:
    claims = Claims.from_verified(_payload())
    with pytest.raises(FrozenInstanceError):
        claims.role = "takab_superadmin"  # type: ignore[misc]
