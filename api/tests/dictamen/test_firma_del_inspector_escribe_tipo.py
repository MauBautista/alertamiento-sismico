"""La firma del inspector declara QUIÉN firmó y en qué banda (T-9.31 · D-43).

Desde la 0073 ``signed_by`` sólo dice «firmado»; quién lo hizo va en
``signature_kind``. Una firma del inspector sin ``signature_kind`` sería
indistinguible de una fila histórica.
"""

from __future__ import annotations

import pytest

from takab_api.queries import dictamens as q


@pytest.mark.parametrize(
    ("status", "band"),
    [
        ("normal_operation", "verde"),
        ("inhabit_monitor", "amarillo"),
        ("restricted", "rojo"),
        ("no_inhabit_inspect", "rojo"),
    ],
)
def test_el_insert_de_la_firma_lleva_tipo_inspector_y_banda(status: str, band: str) -> None:
    stmt, params = q.insert_dictamen(
        tenant_id="t", incident_id="i", status=status, basis="{}", signed_by="u", supersedes=None
    )
    sql = str(stmt)
    assert "signature_kind" in sql and "band" in sql
    assert params["signature_kind"] == "inspector"
    assert params["band"] == band
