"""Fixtures de los tests del dictamen que tocan la base.

Se REUSAN las de `tests/api/conftest.py` en vez de sembrar otro tenant: los
tenants y sitios compartidos viven en `tests/seed_shared.py` desde `T-2.115`,
precisamente porque cada familia de tests que escribía los suyos hacía que
ganara quien corriese primero.

La mayoría de esta carpeta no toca la base —el render es puro y se prueba sobre
el modelo—, así que las fixtures se piden por nombre y sólo las gastan los tests
que de verdad necesitan un incidente escrito.
"""

from __future__ import annotations

from tests.api.conftest import (  # noqa: F401  (fixtures de pytest, por nombre)
    _auth_env,
    base_data,
    db_engine,
    make_incident,
)
