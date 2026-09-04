"""T-5.10 · Procedencia de la cifra sísmica EXTERNA. La regla y sus cinco estados.

**Con procedencia, o no se pinta.** Ninguna superficie muestra magnitud,
epicentro, profundidad u hora de origen sin decir de qué fuente salió y a qué hora
se le preguntó.

TAKAB mide lo que pasó en un edificio; la magnitud y el epicentro los publica una
fuente oficial. Las dos cosas se leen en la misma pantalla y se confunden con
facilidad, porque **una cifra sin procedencia se lee como propia**.

Esto NO roza el invariante de la cuenta atrás (blueprint §14): aquél prohíbe una
cifra **derivada por nosotros** del contacto seco del receptor. Una cifra externa
CITADA, con su hora de consulta y su estado, es lo que ese invariante contempla
como «fuente nueva y citable».

El vocabulario vive en ``shared/glossary/procedencia.json`` —JSON porque el panel
del gabinete no puede importar nada— y este módulo lo LEE en vez de copiarlo: dos
listas de estados serían dos verdades sobre el mismo hecho.

**Qué pasa HOY con la magnitud, que es la pregunta que esta ficha tenía que
responder** (`T-5.10`, criterio 6): `seismic_events.magnitude` se inserta SIEMPRE
en NULL —el único INSERT del sistema, en ``incident/engine.py``, pone el literal—
porque no hay ingesta de catálogo. El campo **se conserva**, y la rama que pinta
la cifra deja de ser inalcanzable-por-NULL para ser **alcanzable-solo-con-
procedencia**: mientras no haya fuente ni hora de consulta, el estado es
``SIN_DATO_EXTERNO`` y la cifra no se pinta aunque algún día alguien escriba un
número. Retirar el campo habría sido borrar el sitio donde va a aterrizar el dato
cuando `T-5.11` fije el criterio de correlación.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

_GLOSARIO = Path(__file__).resolve().parents[3] / "shared/glossary/procedencia.json"

#: Los cinco estados, por su identificador canónico. Se nombran igual en las tres
#: superficies (panel del gabinete, consola SOC y app móvil).
SIN_DATO_EXTERNO = "sin_dato_externo"
CONSULTANDO = "consultando"
PRELIMINAR = "preliminar"
CONFIRMADO = "confirmado"
SIN_CORRELACION = "sin_correlacion"


@lru_cache(maxsize=1)
def glosario() -> dict:
    """El glosario compartido, leído del JSON. Fuente única de los rótulos."""
    return json.loads(_GLOSARIO.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def estados() -> tuple[str, ...]:
    """Los identificadores, en el orden en que los declara el glosario."""
    return tuple(glosario()["estados"])


def rotulo(estado: str, superficie: str) -> str:
    """El texto de ese estado en esa superficie (``panel``/``consola``/``movil``)."""
    fila = glosario()["estados"].get(estado)
    if fila is None:
        raise ValueError(f"estado de procedencia desconocido: {estado!r}")
    return str(fila[superficie])


def pinta_cifra(estado: str) -> bool:
    """¿Este estado autoriza a mostrar la cifra externa?

    Solo ``preliminar`` y ``confirmado``. Los otros tres son formas distintas de
    no tener el dato, y las tres se pintan con su texto —nunca con un hueco.
    """
    fila = glosario()["estados"].get(estado)
    if fila is None:
        raise ValueError(f"estado de procedencia desconocido: {estado!r}")
    return bool(fila["pinta_cifra"])


@dataclass(frozen=True)
class Procedencia:
    """De dónde salió una cifra externa, y con qué confianza.

    ``estado`` es uno de los cinco. ``fuente`` y ``consultado_en`` son obligatorios
    para los dos estados que pintan cifra, y :func:`de_fila` lo impone: una cifra
    con procedencia incompleta no se pinta, se degrada a ``SIN_DATO_EXTERNO``.
    """

    estado: str
    fuente: str | None = None
    consultado_en: datetime | None = None
    id_en_la_fuente: str | None = None

    @property
    def pinta_cifra(self) -> bool:
        return pinta_cifra(self.estado)


def de_fila(fila: dict | None) -> Procedencia:
    """Traduce una fila de ``reference_earthquakes`` a su procedencia.

    **Degrada, nunca inventa.** Sin fuente o sin hora de consulta el resultado es
    ``SIN_DATO_EXTERNO`` aunque la fila traiga una magnitud: el dato existe pero no
    es citable, y pintarlo sería afirmar una procedencia que no consta. Es la
    situación de TODAS las filas hoy — las trece del seed no tienen `consulted_at`.
    """
    if not fila:
        return Procedencia(SIN_DATO_EXTERNO)
    fuente = fila.get("source")
    consultado = fila.get("consulted_at")
    estado = fila.get("review_status")
    if not fuente or consultado is None or estado not in (PRELIMINAR, CONFIRMADO):
        return Procedencia(SIN_DATO_EXTERNO)
    return Procedencia(
        estado=estado,
        fuente=str(fuente),
        consultado_en=consultado,
        id_en_la_fuente=fila.get("provider_event_id"),
    )
