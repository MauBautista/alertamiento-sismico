"""T-5.28 · El fichero que la web usa ES la matriz, y no una copia que se le parece.

`web/src/test-utils/meFixtures.ts` se declaraba «espejo SOLO PARA TESTS de
`auth/matrix.py`» y pedía **por escrito** que se moviera con ella. Nada lo
comprobaba, y divergió en **trece celdas** (nueve de CCTV y cuatro de privacidad),
todas en la misma dirección: la matriz concede y el espejo no.

Por qué no es cosmético: un permiso en `false` no relaja una aserción — hace que
el componente que lo gatea **no se monte**, y el test pasa en verde sobre una
población vacía. Esta vez no llegó a costar nada, porque esas trece acciones casi
no tienen consumidor en la consola; pero es el modo de fallo que un espejo a mano
trae de serie, y se descubrió de casualidad: `soc_operator` —el rol principal de
la consola— no tenía el permiso que `T-5.12` necesitaba.

Desde esta ficha la tabla escrita a mano **ya no existe**: la web deriva sus
fixtures de `shared/fixtures/rbac-matrix.json`, y este test ata ese fichero a la
matriz de Python **por igualdad**. Mover la matriz sin regenerar el JSON pone esto
rojo; y `make drift` lo caza también en CI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from takab_api.auth.matrix import (
    ACTIONS,
    ROLE_ACTION_MATRIX,
    ROLE_ROUTE_MATRIX,
    ROUTE_ORDER,
)

_FIXTURE = Path(__file__).resolve().parents[3] / "shared/fixtures/rbac-matrix.json"


@pytest.fixture(scope="module")
def fichero() -> dict:
    assert _FIXTURE.exists(), (
        f"falta {_FIXTURE}: regenéralo con "
        "`uv run --directory api python scripts/export_rbac_matrix.py`"
    )
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


_COMO_REGENERAR = (
    "El fichero que consume la web se separó de la matriz. Regenéralo con "
    "`uv run --directory api python scripts/export_rbac_matrix.py` y MIRA QUÉ TESTS "
    "DE WEB cambian de veredicto: un permiso que pasa a `true` monta componentes que "
    "hasta ahora nadie renderizaba."
)


def test_los_mismos_roles(fichero: dict) -> None:
    assert set(fichero["roles"]) == set(ROLE_ACTION_MATRIX), _COMO_REGENERAR


def test_las_mismas_acciones_en_el_mismo_orden(fichero: dict) -> None:
    assert fichero["actions"] == list(ACTIONS), _COMO_REGENERAR


def test_las_rutas_conservan_su_ORDEN(fichero: dict) -> None:
    """No es cosmética: `landing.ts` toma la PRIMERA ruta distinta de `/building`
    como destino tras el login. Un orden distinto cambia dónde aterriza cada rol."""
    assert fichero["route_order"] == list(ROUTE_ORDER), _COMO_REGENERAR
    for rol, datos in fichero["roles"].items():
        esperado = [r for r in ROUTE_ORDER if r in ROLE_ROUTE_MATRIX[rol]]
        assert datos["routes"] == esperado, f"{rol}: rutas fuera de orden. {_COMO_REGENERAR}"


def test_CELDA_A_CELDA_por_igualdad(fichero: dict) -> None:
    """La comparación que faltaba. Por igualdad y no por contención: un espejo que
    solo comprueba «lo que declara `true` es `true`» deja pasar exactamente el
    fallo que hubo — permisos de más en la matriz que el espejo tiene en `false`."""
    divergentes = [
        f"{rol}.{accion}: matriz={ROLE_ACTION_MATRIX[rol][accion]} "
        f"fichero={fichero['roles'][rol]['actions'].get(accion)}"
        for rol in ROLE_ACTION_MATRIX
        for accion in ACTIONS
        if fichero["roles"][rol]["actions"].get(accion) != ROLE_ACTION_MATRIX[rol][accion]
    ]
    detalle = "\n".join(divergentes)
    assert not divergentes, f"{len(divergentes)} celda(s) divergen. {_COMO_REGENERAR}\n{detalle}"


def test_el_censo_declara_SU_TAMAÑO(fichero: dict) -> None:
    """Guarda de no-vacuidad: un analizador ciego compara cero contra cero y pasa.

    Los tres números van escritos: si mañana se añade un rol o una acción, esto se
    pone rojo y alguien tiene que mirar a quién se le concede — que es exactamente
    la conversación que la divergencia de trece celdas se saltó durante meses.
    """
    assert len(ROLE_ACTION_MATRIX) == 10, "cambió el número de roles"
    assert len(ACTIONS) == 36, "cambió el número de acciones"
    assert len(ROUTE_ORDER) == 6, "cambió el número de rutas"

    celdas = len(ROLE_ACTION_MATRIX) * len(ACTIONS)
    assert celdas == 360, "el producto no cuadra: el censo no está comparando la matriz entera"
    # Y el fichero tiene las mismas: si estuviera vacío, el test de arriba
    # compararía `None != False` y sería el único en enterarse.
    assert sum(len(r["actions"]) for r in fichero["roles"].values()) == celdas
