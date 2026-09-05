"""Exporta la matriz RBAC a `shared/fixtures/rbac-matrix.json` (T-5.28).

**Por qué existe.** `web/src/test-utils/meFixtures.ts` se declaraba «espejo SOLO
PARA TESTS de `auth/matrix.py`» y pedía por escrito que se moviera con ella —y
nada lo comprobaba—. Divergió en **trece celdas**, todas en la misma dirección
—la matriz concede, el espejo no—: nueve de CCTV y cuatro de privacidad.

El daño concreto resultó ser NULO (doce de las trece no tienen consumidor en la
web, y la decimotercera gatea un botón que la suite de página no renderiza), y eso
no le quita la razón a la guarda: un permiso en `false` no relaja una aserción,
hace que el componente **no se monte** y el test pase en verde sobre nada. La
próxima acción que se desincronice puede gatear algo que sí se pinte.

Se sigue el patrón que ya funciona en `shared/fixtures/notify-channels.json`: un
hecho de Python que viaja a los tests de la web por un fichero, con un test que
lo ata a su fuente. La diferencia es que aquí el fichero se **genera**, así que
la tabla escrita a mano deja de existir y no puede volver a divergir.

Corre con:  uv run --directory api python scripts/export_rbac_matrix.py
Lo vigila:  api/tests/auth/test_rbac_fixture_es_la_matriz.py  (y `make drift`)
"""

from __future__ import annotations

import json
from pathlib import Path

from takab_api.auth.matrix import (
    ACTIONS,
    ROLE_ACTION_MATRIX,
    ROLE_ROUTE_MATRIX,
    ROUTE_ORDER,
)

DESTINO = Path(__file__).resolve().parents[2] / "shared/fixtures/rbac-matrix.json"

_NOTA = (
    "[T-5.28] GENERADO por api/scripts/export_rbac_matrix.py desde "
    "api/src/takab_api/auth/matrix.py. NO SE EDITA A MANO: la tabla que se editaba a mano "
    "divergio en 13 celdas (9 de CCTV y 4 de privacidad) sin que nada se pusiera rojo. "
    "Lo consume web/src/test-utils/meFixtures.ts (que ya no enumera nada) y lo ata a su "
    "fuente api/tests/auth/test_rbac_fixture_es_la_matriz.py."
)


def matriz() -> dict:
    """La matriz en JSON: rutas en su ORDEN estable y acciones ordenadas."""
    return {
        "nota": _NOTA,
        # El orden importa: `landing.ts` toma la PRIMERA ruta distinta de /building
        # como destino tras el login. Un `sorted()` aquí movería el aterrizaje.
        "route_order": list(ROUTE_ORDER),
        "actions": list(ACTIONS),
        "roles": {
            rol: {
                # Las rutas del rol, EN EL ORDEN de `ROUTE_ORDER` — que es como las
                # sirve `allowed_routes()`. `frozenset` no tiene orden y volcarlo
                # tal cual daría un fichero distinto en cada corrida.
                "routes": [r for r in ROUTE_ORDER if r in ROLE_ROUTE_MATRIX[rol]],
                "actions": {a: bool(ROLE_ACTION_MATRIX[rol][a]) for a in ACTIONS},
            }
            for rol in sorted(ROLE_ACTION_MATRIX)
        },
    }


def main() -> None:
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(
        json.dumps(matriz(), ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print(f"escrito {DESTINO}")


if __name__ == "__main__":
    main()
