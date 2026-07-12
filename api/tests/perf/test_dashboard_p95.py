"""Suite de rendimiento del dashboard SOC (T-1.22 · G6). EXCLUIDA de la suite normal.

Requiere una DB DEDICADA ya migrada y ``TAKAB_RUN_PERF=1`` (el ``skipif`` de módulo
la salta en cualquier otro caso — nunca siembra millones de filas en un PR). Correr:

    createdb takab_perf
    DATABASE_URL=postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab_perf \\
        uv run alembic upgrade head
    TAKAB_RUN_PERF=1 \\
    DATABASE_URL=postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab_perf \\
        uv run pytest -m perf tests/perf -q -s

Verifica (a) p95 < 200 ms en 50 requests calientes por query de dashboard y
(b) que la query de 90 días escanea el cagg ``site_metrics_1h`` (materialized
hypertable), nunca la hypertable cruda de features.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.db.session import SessionCtx, get_tenant_conn
from takab_api.queries.telemetry import select_metrics

_RUN = os.environ.get("TAKAB_RUN_PERF") == "1"
pytestmark = [
    pytest.mark.perf,
    pytest.mark.skipif(not _RUN, reason="perf desactivado (usa TAKAB_RUN_PERF=1 + DB dedicada)"),
]

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seed_timeseries.py"
_P95_BUDGET_S = 0.200
_HOT_REQUESTS = 50
_WARMUP = 5


def _dsn() -> str:
    return os.environ["DATABASE_URL"]


def _load_seeder():
    spec = importlib.util.spec_from_file_location("seed_timeseries", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Registrar antes de exec: el dataclass con `from __future__ annotations` resuelve
    # sus anotaciones vía sys.modules[__module__].
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def perf_seed(ts_engine):
    """Siembra ~90 días (features + caggs + incidentes) en la DB dedicada."""
    seeder = _load_seeder()
    return seeder.seed(_dsn())


def _p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]


async def _measure(telemetry_client, url: str, headers: dict[str, str]) -> float:
    for _ in range(_WARMUP):
        assert (await telemetry_client.get(url, headers=headers)).status_code == 200
    samples: list[float] = []
    for _ in range(_HOT_REQUESTS):
        start = time.perf_counter()
        resp = await telemetry_client.get(url, headers=headers)
        samples.append(time.perf_counter() - start)
        assert resp.status_code == 200, resp.text
    return _p95(samples)


async def test_dashboard_queries_p95_under_budget(telemetry_client, perf_seed) -> None:
    tenant = perf_seed.tenant_ids[0]
    site = perf_seed.dense_site_id
    headers = au.bearer(au.make_token("soc_operator", tenant=tenant, site_scope="*", surface="web"))
    now = datetime.now(UTC)
    # Sufijo Z (no '+00:00') para embeber el offset en el query string sin encoding.
    d90 = (now - timedelta(days=90)).isoformat().replace("+00:00", "Z")
    d1 = (now - timedelta(hours=24)).isoformat().replace("+00:00", "Z")
    to = now.isoformat().replace("+00:00", "Z")

    urls = {
        "map/state": "/telemetry/map/state",
        "metrics-90d-1h": f"/telemetry/sites/{site}/metrics?bucket=1h&from={d90}&to={to}",
        "metrics-24h-1m": f"/telemetry/sites/{site}/metrics?bucket=1m&from={d1}&to={to}",
        "features-10min": f"/telemetry/sites/{site}/features",
    }
    results = {name: await _measure(telemetry_client, url, headers) for name, url in urls.items()}
    for name, p95 in results.items():
        print(f"p95 {name}: {p95 * 1000:.1f} ms")  # noqa: T201 — informe de perf
    slow = {n: round(p * 1000, 1) for n, p in results.items() if p >= _P95_BUDGET_S}
    assert not slow, f"p95 sobre presupuesto (200 ms): {slow}"


async def test_90d_query_scans_cagg_not_raw_hypertable(telemetry_client, perf_seed) -> None:
    tenant = perf_seed.tenant_ids[0]
    site = perf_seed.dense_site_id
    now = datetime.now(UTC)
    stmt, params = select_metrics(
        bucket="1h",
        site_id=site,
        from_ts=(now - timedelta(days=90)).isoformat(),
        to_ts=now.isoformat(),
    )
    explain = text("EXPLAIN (FORMAT JSON) " + stmt.text)
    async with get_tenant_conn(
        SessionCtx(tenant_id=tenant, role="soc_operator", user_id="u")
    ) as conn:
        row = (await conn.execute(explain, params)).scalar_one()
    plan = json.dumps(row).lower()
    assert "_materialized_hypertable" in plan or "site_metrics_1h" in plan, plan
    assert "waveform_features_1s" not in plan, "la query de 90d NO debe tocar el crudo 1 s"
