"""Fixtures del endpoint del mini-ShakeMap.

Se REUSAN las de `tests/api/conftest.py` en vez de sembrar otro tenant: los
tenants y sitios compartidos viven en `tests/seed_shared.py` desde `T-2.115`,
precisamente porque cada familia de tests que escribía los suyos hacía que
ganara quien corriese primero.

La `app` sí es propia, y con `create_app()` a secas: si el router del ShakeMap no
estuviera registrado en `main.py`, esta suite lo diría — que es justo lo que se
quiere comprobar. Añadirlo aquí a mano lo taparía.
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
