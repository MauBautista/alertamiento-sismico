"""Contract-test: los caggs ``site_metrics_1m|1h`` solo por la vista ``*_secure``.

Estático (espejo de ``test_waveform_view``): en ``queries/*.py`` NINGÚN literal
nombra el cagg BASE (``site_metrics_1[mh]`` no seguido de ``_secure``) — la
superficie de lectura pasa siempre por las vistas ``*_secure`` (security_barrier
+ JOIN a ``sites`` con RLS). El cagg base tiene el SELECT revocado a takab_app
(migración 0008), así que un ``SELECT`` directo ni siquiera tendría permiso.

Runtime: ejecutando el builder por ``get_tenant_conn``, el tenant A no ve las
métricas de B, y ``gov_operator`` solo ve las de tenants ``gov_shared``.
"""

from __future__ import annotations

import ast
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from takab_api.db.session import SessionCtx, get_tenant_conn
from takab_api.queries.telemetry import select_metrics

_QUERIES = Path(__file__).resolve().parents[2] / "src" / "takab_api" / "queries"
# cagg BASE = ``site_metrics_1m|1h`` NO seguido de ``_secure``.
_BASE_CAGG = re.compile(r"site_metrics_1[mh](?!_secure)")


def test_base_caggs_never_named_in_read_surface() -> None:
    offenders: list[str] = []
    for py in _QUERIES.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if _BASE_CAGG.search(node.value):
                    offenders.append(f"{py.name}:{node.lineno} -> {node.value[:60]!r}")
    assert not offenders, (
        f"cagg base (sin RLS) nombrado en la superficie de lectura: {offenders} — "
        "usar la vista *_secure"
    )


def _range() -> tuple[str, str]:
    now = datetime.now(UTC)
    return (now - timedelta(hours=2)).isoformat(), (now + timedelta(minutes=1)).isoformat()


def _q(site_id: str):
    frm, to = _range()
    return select_metrics(bucket="1m", site_id=site_id, from_ts=frm, to_ts=to)


async def test_metrics_isolated_by_tenant(seed) -> None:
    async with get_tenant_conn(
        SessionCtx(tenant_id=seed.priv_a, role="soc_operator", user_id="u")
    ) as conn:
        own = (await conn.execute(*_q(seed.site_a))).all()
        other = (await conn.execute(*_q(seed.site_b))).all()
    assert own, "el tenant A ve las métricas de su sitio"
    assert other == [], "el tenant A NO ve las métricas del sitio de B (cagg + JOIN sites)"


async def test_gov_operator_sees_only_gov_shared(seed) -> None:
    # gov con un tenant de agencia (no cliente): su visibilidad depende SOLO de la
    # rama gov_shared de la política de sites, no de tenant_id = app_tenant_id().
    async with get_tenant_conn(
        SessionCtx(tenant_id=seed.agency, role="gov_operator", user_id="u")
    ) as conn:
        gov_site = (await conn.execute(*_q(seed.site_g))).all()
        priv_site = (await conn.execute(*_q(seed.site_a))).all()
    assert gov_site, "gov_operator ve el sitio gov_shared"
    assert priv_site == [], "gov_operator NO ve un sitio private"
