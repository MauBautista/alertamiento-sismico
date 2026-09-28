"""Fixtures de la suite del informe automático (T-9.42).

Se REUSAN las de `tests/api/conftest.py` (tenants y sitios de `seed_shared`) y la
`app` es `create_app()` a secas: si el endpoint no quedara montado en `main.py`,
esta suite lo diría — añadir aquí el router a mano lo taparía.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from takab_api.main import create_app
from tests.api.conftest import (  # noqa: F401  (fixtures de pytest, por nombre)
    _auth_env,
    base_data,
    client,
    db_engine,
)


@pytest.fixture
def app() -> FastAPI:
    return create_app()
