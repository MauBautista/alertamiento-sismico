"""Regresión de infra (regla de oro #5): el app client SPA de Cognito NO deja al
usuario auto-reescribir los anchors de tenancy/rol. Sin ``write_attributes`` acotado,
un usuario autenticado podría fijar su ``custom:tenant_id`` a otro tenant vía
``UpdateUserAttributes`` self-service y leer/escribir el tenant ajeno (fuga total).

El fix vive en Terraform (el client omite todo ``custom:*`` de write_attributes);
``claims.py`` ancla RLS en ``custom:tenant_id`` confiando en ese binding upstream.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# api/tests/auth/ -> repo root en parents[3]; de ahí al módulo identity de Terraform.
_TF = (
    Path(__file__).resolve().parents[3] / "infra" / "terraform" / "modules" / "identity" / "main.tf"
)

# Anchors de seguridad que el propio usuario NUNCA debe poder reescribir.
_ANCHORS = (
    "custom:tenant_id",
    "custom:role",
    "custom:site_scope",
    "custom:zone_id",
    "custom:surface",
)


def _web_client_block() -> str:
    """Texto del recurso ``aws_cognito_user_pool_client`` \"web\" (hasta su cierre)."""
    text = _TF.read_text(encoding="utf-8")
    start = text.index('resource "aws_cognito_user_pool_client" "web"')
    tail = text[start:]
    end = re.search(r"\n}\s*(?:\n|$)", tail)  # primer '}' en columna 0 = fin del recurso
    return tail[: end.end()] if end else tail


def test_web_client_acota_write_attributes() -> None:
    assert "write_attributes" in _web_client_block(), (
        "el app client SPA debe declarar write_attributes (regla de oro #5)"
    )


@pytest.mark.parametrize("anchor", _ANCHORS)
def test_write_attributes_excluye_anchors_de_seguridad(anchor: str) -> None:
    block = _web_client_block()
    match = re.search(r"write_attributes\s*=\s*\[(?P<items>.*?)\]", block, re.DOTALL)
    assert match is not None, "write_attributes debe ser una lista literal"
    assert anchor not in match.group("items"), (
        f"{anchor} no debe ser auto-escribible por el usuario (fuga cross-tenant)"
    )
