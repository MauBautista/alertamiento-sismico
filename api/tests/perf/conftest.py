"""Fixtures de la suite de perf (reexporta env + engine + cliente compartidos).

Solo se instancian cuando la suite corre de verdad (``TAKAB_RUN_PERF=1``); el
``skipif`` del módulo de test evita montar cualquier fixture en la suite normal.
"""

from __future__ import annotations

from _telemetry_fixtures import (  # noqa: F401
    _ts_env,
    telemetry_app,
    telemetry_client,
    ts_engine,
)
