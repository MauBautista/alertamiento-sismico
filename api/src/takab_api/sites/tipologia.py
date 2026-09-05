"""Tipología de inmueble y su banda de umbral de REFERENCIA (T-5.16 · D-28).

**La tipología SUGIERE, no resuelve.** Es la decisión que gobierna este módulo y
la razón de que aquí no haya nada que resuelva un umbral: `banda_de()` devuelve
la banda **de referencia** para que la consola la OFREZCA, y aplicarla escribe
una versión nueva del `rule_set` que hay que publicar y firmar como cualquier
otra. Si el tipo resolviera el umbral, editar el tipo de un sitio desde la
pantalla de flota —un acto de captura— re-armaría el edificio a otra
sensibilidad sin publicar nada. Ver `takab-docs/DECISIONES-MAURICIO.md` D-28.

El catálogo NO se escribe aquí: se lee de `shared/schemas/tipologia_umbral.json`,
que es el mismo fichero del que salen el `CHECK` de la base y el desplegable de
la consola. `api/tests/test_tipologia_umbral.py` compara las cuatro copias por
igualdad, en los dos sentidos.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_CATALOGO = Path(__file__).resolve().parents[4] / "shared" / "schemas" / "tipologia_umbral.json"


@lru_cache(maxsize=1)
def catalogo() -> dict[str, Any]:
    """El catálogo completo, tal cual lo declara el contrato compartido."""
    return json.loads(_CATALOGO.read_text(encoding="utf-8"))


def _tipos() -> list[dict[str, Any]]:
    return catalogo()["tipos"]


#: Valores admitidos de `sites.building_type`, en el orden del catálogo.
TIPOS: tuple[str, ...] = tuple(t["value"] for t in _tipos())

#: Banda de referencia por tipo. Solo los tipos que TIENEN una publicada: un tipo
#: sin banda no aparece aquí, y por eso `banda_de` devuelve `None` en vez de
#: prestarle la de otro.
BANDAS: dict[str, tuple[float, float]] = {
    t["value"]: (t["banda"]["pga_watch_g"], t["banda"]["pga_trip_g"])
    for t in _tipos()
    if t["banda"] is not None
}


def banda_de(tipo: str | None) -> tuple[float, float] | None:
    """`(pga_watch_g, pga_trip_g)` de referencia, o `None` si no hay publicada.

    `None` es la respuesta correcta y NO un fallo: el blueprint publica banda
    para tres tipologías y no para las demás. Devolver la de hospital «por
    defecto» es exactamente el defecto que abre `T-5.16` — toda la flota
    corriendo la banda de hospital sin que nadie lo decidiera.
    """
    if tipo is None:
        return None
    return BANDAS.get(tipo)


def etiqueta_de(tipo: str | None) -> str | None:
    """Rótulo legible del tipo, o `None` si no está en el catálogo."""
    for t in _tipos():
        if t["value"] == tipo:
            return str(t["label"])
    return None


def sin_banda_por_que(tipo: str) -> str | None:
    """Por qué ese tipo no trae banda. La ausencia se explica, no se calla."""
    for t in _tipos():
        if t["value"] == tipo and t["banda"] is None:
            return str(t["sin_banda_por_que"])
    return None
