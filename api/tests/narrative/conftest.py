"""Fixtures prestadas de `tests/api` para el ÚNICO test de esta carpeta que
necesita la nube entera (T-7.26).

`narrative_generated` es el registro de procedencia de la IA y **no tenía ni una
prueba**: para medirlo hace falta el router real escribiendo en `audit_log`, no un
doble. Se importan por nombre —y no con un `import *`— para que se vea exactamente
qué arrastra esta carpeta: el entorno de auth (autouse), el engine con su
`TRUNCATE` de cierre, la siembra y los dos constructores de filas.

`app` NO se importa a propósito: el de `tests/api` monta los routers de B2 y aquí
hace falta el de reports. Lo define el módulo que lo usa y pytest resuelve primero
el del módulo.
"""

from __future__ import annotations

from tests.api.conftest import (  # noqa: F401 - fixtures, se usan por nombre
    _auth_env,
    base_data,
    client,
    db_engine,
    make_dictamen,
    make_incident,
)
