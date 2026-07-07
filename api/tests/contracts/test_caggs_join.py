"""Contract-test: los caggs ``site_metrics_1m|1h`` SIEMPRE con JOIN sites (G2).

Estático: en ``queries/*.py`` todo string literal que mencione un cagg debe
co-ocurrir con ``JOIN sites`` en el MISMO literal (el JOIN a ``sites`` con RLS es
el ÚNICO filtro de tenant — los caggs no llevan RLS). Se escanean literales de
Python vía AST (los comentarios no cuentan; el SQL sí).

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
_CAGG = re.compile(r"site_metrics_1[mh]")


def test_caggs_never_selected_without_join_sites() -> None:
    offenders: list[str] = []
    for py in _QUERIES.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                literal = node.value
                if _CAGG.search(literal) and "join sites" not in literal.lower():
                    offenders.append(f"{py.name}:{node.lineno} -> {literal[:60]!r}")
    assert not offenders, f"cagg sin JOIN sites en el mismo statement: {offenders}"


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
