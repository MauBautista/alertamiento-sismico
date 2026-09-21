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

#: [T-7.25] Los DESENLACES que el worker de consulta puede registrar en
#: ``catalog_consultations.outcome``. No son estados de procedencia: son lo que
#: le pasó al INTENTO, y de ellos —más la fila que casó— se deriva el estado.
#: Viven aquí y no en `catalogo/consulta.py` porque son el otro extremo de la
#: misma máquina: dos listas serían dos verdades sobre el mismo hecho.
#:
#: ``DESENLACE_SIN_CORRELACION`` es literalmente la misma palabra que el estado
#: ``SIN_CORRELACION``, y a propósito: es el mismo hecho contado desde los dos
#: lados —«la consulta terminó sin casar» y «este evento no tiene correlación en
#: el catálogo»—. Dos palabras habrían obligado a traducir entre ellas.
DESENLACE_CORRELACIONADO = "correlacionado"
DESENLACE_SIN_CORRELACION = SIN_CORRELACION
DESENLACE_SIN_RESPUESTA = "sin_respuesta"

#: Espejo del CHECK de `catalog_consultations.outcome`. Lo compara con el DDL
#: `api/tests/catalogo/test_procedencia_de_consulta.py`.
DESENLACES = (
    DESENLACE_CORRELACIONADO,
    DESENLACE_SIN_CORRELACION,
    DESENLACE_SIN_RESPUESTA,
)


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


def de_consulta(consulta: dict | None, fila: dict | None) -> Procedencia:
    """[T-7.25] El estado, derivado del INTENTO de consulta y de la fila que casó.

    Hasta esta ficha ``CONSULTANDO`` era **inalcanzable**: :func:`de_fila` deriva
    el estado de una fila de ``reference_earthquakes``, y mientras la pregunta
    está en vuelo esa fila no existe. Así que «pregunté y no me contestó» —un
    timeout, un 5xx, un worker que murió a mitad— se leía igual que «nadie
    preguntó nunca», que es exactamente la confusión que el glosario nombra.

    ``consulta`` es una fila de ``catalog_consultations`` y ``fila`` es la de
    ``reference_earthquakes`` que la correlación dio por buena (o ``None``).

    Las cuatro ramas, y por qué están en este orden:

    1. **Sin intento** ⇒ se cae a :func:`de_fila`, y sin fila eso es
       ``SIN_DATO_EXTERNO``: **nadie preguntó**. Es la conducta de antes de esta
       ficha y con la consulta apagada —el defecto— es la de todos los
       incidentes. No es lo mismo que ``SIN_CORRELACION``, que afirma algo sobre
       el catálogo, y el llamador de `forensics` las confundía: entraba aquí
       sólo cuando HABÍA fila, así que un incidente sin consultar se publicaba
       como «se preguntó y ninguno es éste».
    2. **Sin ``answered_at``** ⇒ ``CONSULTANDO``. Es el ÚNICO bit que separa
       «no contestó» de un desenlace, y va antes que mirar ``outcome`` porque un
       intento en vuelo no tiene desenlace que mirar.
    3. **Contestó y nada suyo es éste** ⇒ ``SIN_CORRELACION``, con la hora de la
       respuesta: es un hecho sobre el evento, no una ausencia de datos.
    4. **Contestó y casó** ⇒ manda la FILA. Casar no concede procedencia: si la
       fila no trae fuente y hora de consulta, :func:`de_fila` la degrada al
       silencio igual que siempre (regla de `T-5.10`).

    ⚠️ **La cuarta rama depende de que el llamador traiga la fila.** El único
    llamador de producción le pasaba siempre ``fila=None``, así que un incidente
    con ``outcome='correlacionado'`` escrito en la base salía a la superficie
    como ``sin_dato_externo`` —«nadie preguntó»— que es lo contrario de lo que
    había pasado. Hoy la fila viaja en el mismo `SELECT` que la consulta
    (`queries/forensics.py::_CATALOG_CONSULTATION`).
    """
    if not consulta:
        return de_fila(fila)
    fuente = consulta.get("provider")
    fuente = str(fuente) if fuente else None
    if consulta.get("answered_at") is None:
        return Procedencia(CONSULTANDO, fuente=fuente, consultado_en=consulta.get("asked_at"))
    if consulta.get("outcome") == DESENLACE_SIN_CORRELACION:
        return Procedencia(
            SIN_CORRELACION, fuente=fuente, consultado_en=consulta.get("answered_at")
        )
    return de_fila(fila)
