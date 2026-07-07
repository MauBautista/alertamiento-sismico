"""Contract-test: las features crudas SOLO se leen por la vista segura (G2).

Estático: ningún módulo de la API nombra la hypertable base cruda ``waveform_
features_1s`` (salvo el sufijo ``_secure``). Único escritor legítimo permitido:
el handler de ingesta (``ingest/handlers.py``, BYPASSRLS) — es la ruta de
ESCRITURA del pipeline, no la superficie de LECTURA de la API.

Runtime: ejecutando el builder real por ``get_tenant_conn``, el tenant A ve su
sitio y NO ve el de B (la vista security_barrier hace JOIN a ``sites`` con RLS).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from takab_api.db.session import SessionCtx, get_tenant_conn
from takab_api.queries.telemetry import select_features

_SRC = Path(__file__).resolve().parents[2] / "src" / "takab_api"
# Identificador base cruda NO seguido de ``_secure``.
_BASE = re.compile(r"waveform_features_1s(?!_secure)")
# Componentes INTERNOS de RED (BYPASSRLS), no la superficie de LECTURA de la API:
#  - ingest/handlers.py (T-1.17): ruta de ESCRITURA del pipeline.
#  - incident/engine.py (T-1.19): correlación del quórum: LEE el pico de PGA por
#    sensor de toda la red. La vista `_secure` corre con el contexto RLS de su owner
#    (no security_invoker) y devuelve 0 filas en una lectura cross-tenant → el motor
#    debe leer la base directamente (la hypertable no lleva RLS; el aislamiento de la
#    API lo da la vista + el REVOKE a takab_app, no aplicable a un lector de red).
#  - dictamen/service.py (T-1.20): pasada del dictamen preliminar en el MISMO
#    worker BYPASSRLS: lee el pico de PGA con el mismo patrón que el engine.
_ALLOW = {
    _SRC / "ingest" / "handlers.py",
    _SRC / "incident" / "engine.py",
    _SRC / "dictamen" / "service.py",
}


def test_read_surface_never_names_base_table() -> None:
    offenders: list[str] = []
    for py in _SRC.rglob("*.py"):
        if py in _ALLOW:
            continue
        text = py.read_text(encoding="utf-8")
        for match in _BASE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{py.relative_to(_SRC)}:{line}")
    assert not offenders, f"tabla base cruda referenciada fuera de la ingesta: {offenders}"


def test_telemetry_queries_use_secure_view() -> None:
    # Refuerzo positivo: el builder de features nombra explícitamente la vista.
    src = (_SRC / "queries" / "telemetry.py").read_text(encoding="utf-8")
    assert "waveform_features_1s_secure" in src


def _range() -> tuple[str, str]:
    now = datetime.now(UTC)
    return (now - timedelta(hours=1)).isoformat(), (now + timedelta(minutes=1)).isoformat()


async def test_features_isolated_by_tenant(seed) -> None:
    frm, to = _range()

    def _q(site_id: str):
        return select_features(site_id=site_id, from_ts=frm, to_ts=to, channel=None)

    async with get_tenant_conn(
        SessionCtx(tenant_id=seed.priv_a, role="soc_operator", user_id="u")
    ) as conn:
        own = (await conn.execute(*_q(seed.site_a))).all()
        other = (await conn.execute(*_q(seed.site_b))).all()
    assert own, "el tenant A ve las features de su propio sitio"
    assert other == [], "el tenant A NO ve las features del sitio de B"


async def test_features_isolated_reverse(seed) -> None:
    frm, to = _range()

    def _q(site_id: str):
        return select_features(site_id=site_id, from_ts=frm, to_ts=to, channel=None)

    async with get_tenant_conn(
        SessionCtx(tenant_id=seed.priv_b, role="soc_operator", user_id="u")
    ) as conn:
        own = (await conn.execute(*_q(seed.site_b))).all()
        other = (await conn.execute(*_q(seed.site_a))).all()
    assert own, "el tenant B ve su propio sitio"
    assert other == [], "el tenant B NO ve el sitio de A"
