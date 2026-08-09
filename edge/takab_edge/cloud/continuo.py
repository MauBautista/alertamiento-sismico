"""continuo — qué payload PUEDE cruzar el enlace en continuo y qué no (regla de oro 9).

*Sin streaming de forma de onda cruda.* El waveform crudo (100 sps, 4 canales) no se
sube en continuo; el miniSEED crudo sube a S3 **solo en eventos confirmados**. Es
regla de oro 9 e invariante permanente del `BLUEPRINT §14` — prohibición, no diferido.

Hasta T-2.84.a eso vivía en tres documentos y en ninguna línea de código: añadir un
publicador continuo no rompía nada y se habría descubierto en la factura de AWS. Este
módulo lo convierte en una propiedad **decidible del esquema**, y `CloudConnector` la
impone en la única puerta que hay hacia el broker.

LA PROPIEDAD
------------
    Un payload es publicable EN CONTINUO si y sólo si su tamaño serializado está
    ACOTADO POR SU PROPIO ESQUEMA, con independencia del flujo de muestras.

Lo que NO lo está —y por tanto no puede salir en continuo— es una **serie de
muestras**: un array numérico sin `maxItems`, o un blob crudo (`format: binary` /
`base64`) sin `maxLength`. Su tamaño crece con `sample_rate × duración`; el de un
`HealthSnapshot` o un `Feature1s`, no. `FeatureBatch` lleva la cota escrita en el
esquema (`max_length=256`) y por eso pasa: el lote es grande, pero es FINITO y el
esquema lo dice.

Se eligió el esquema y no el nombre de la clase a propósito: prohibir
`WaveformPacket` por su nombre se rodea renombrándolo, envolviéndolo en otro modelo o
aplanándolo a `list[int]`. Ninguna de las tres rodea al esquema.

LÍMITE DECLARADO
----------------
Un campo `dict` libre (`{"type": "object"}` sin `properties`) **no restringe nada**,
así que este clasificador no puede ver lo que va dentro. En vez de fingir cobertura,
`campos_de_dict_libre()` los enumera para que la suite los ancle uno a uno
(`tests/test_cloud_streaming_crudo.py`).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import BaseModel

#: Tipos JSON Schema que son un NÚMERO. Un array de éstos sin cota es una serie.
_NUMERICOS = frozenset({"integer", "number"})

#: `format` que denota un BLOB crudo aunque el tipo JSON sea `string`: es como
#: pydantic serializa `bytes`, y es la vía obvia para colar un miniSEED entero.
_FORMATOS_DE_BLOB = frozenset({"binary", "base64", "base64url"})

#: Tope de recursión del recorrido del esquema. Los `$ref` ya se cortan por
#: visitados; esto es la red por si un esquema anida sin ciclo hasta el absurdo.
_PROFUNDIDAD_MAX = 24


@lru_cache(maxsize=256)
def serie_de_muestras(modelo: type[BaseModel]) -> str | None:
    """Motivo por el que ``modelo`` NO está acotado por su esquema; ``None`` si lo está.

    El motivo NOMBRA el campo culpable (``WaveformPacket.samples[] — …``): un rechazo
    que no dice cuál es el campo obliga a adivinar, y esto se lee en un log de
    producción a las tres de la mañana.

    Cacheado: se llama en cada `publish` (features a 1 Hz), y `model_json_schema()`
    no es barato. La clave es el TIPO, que es inmutable.

    **Fail-closed y sin lanzar.** Si el esquema no se puede construir —o lo que llega
    ni siquiera es un modelo Pydantic— NO se concede el paso: sin esquema no hay cota
    demostrable, y esta función decide si algo puede salir en continuo hacia AWS. Y no
    propaga la excepción: corre dentro de `publish`, que por la regla de oro 4.2 jamás
    puede lanzar hacia la vía de actuación. Los 24 contratos del árbol construyen su
    esquema sin problema, y el censo de `tests/test_cloud_streaming_crudo.py` lo
    comprueba en cada corrida: un modelo nuevo que no pudiera se vería en CI, no en el Pi.
    """
    constructor = getattr(modelo, "model_json_schema", None)
    if constructor is None:
        nombre = getattr(modelo, "__name__", modelo)
        return f"{nombre} no es un modelo Pydantic: sin esquema no hay cota demostrable"
    try:
        esquema = constructor()
    except Exception as exc:  # noqa: BLE001 — fail-closed: sin esquema no se concede el paso
        return f"{modelo.__name__}: no se pudo construir su esquema ({exc.__class__.__name__})"
    definiciones = esquema.get("$defs", {})
    return _buscar(esquema, definiciones, modelo.__name__, frozenset(), 0)


@lru_cache(maxsize=256)
def campos_de_dict_libre(modelo: type[BaseModel]) -> tuple[str, ...]:
    """Rutas de los campos `dict` SIN esquema — el punto ciego declarado del módulo.

    Un `dict | None` de pydantic se serializa como `{"type": "object"}` pelado: sin
    `properties` y sin `additionalProperties: false` no restringe nada, así que
    `serie_de_muestras()` no puede pronunciarse sobre su contenido. Se enumeran para
    que la suite los ancle en vez de ignorarlos.
    """
    esquema = modelo.model_json_schema()
    definiciones = esquema.get("$defs", {})
    encontrados: list[str] = []
    _buscar_dicts(esquema, definiciones, "", frozenset(), 0, encontrados)
    return tuple(sorted(encontrados))


# --------------------------------------------------------------------- recorrido


def _resolver(nodo: Any, definiciones: dict, vistos: frozenset[str]) -> tuple[dict, frozenset[str]]:
    """Sigue un `$ref` hasta su definición. Devuelve `({}, vistos)` en un ciclo."""
    if not isinstance(nodo, dict):
        return {}, vistos
    ref = nodo.get("$ref")
    if not isinstance(ref, str):
        return nodo, vistos
    nombre = ref.rsplit("/", 1)[-1]
    if nombre in vistos:
        return {}, vistos  # ciclo: ya se inspeccionó esta definición
    return definiciones.get(nombre, {}), vistos | {nombre}


def _es_numerico(items: Any, definiciones: dict, vistos: frozenset[str]) -> bool:
    """¿Los elementos del array son NÚMEROS? (siguiendo `$ref` y uniones)."""
    nodo, vistos = _resolver(items, definiciones, vistos)
    if not isinstance(nodo, dict):
        return False
    if nodo.get("type") in _NUMERICOS:
        return True
    for clave in ("anyOf", "oneOf", "allOf"):
        for sub in nodo.get(clave, ()):
            if _es_numerico(sub, definiciones, vistos):
                return True
    return False


def _buscar(
    nodo: Any, definiciones: dict, ruta: str, vistos: frozenset[str], hondura: int
) -> str | None:
    """Primera serie de muestras alcanzable desde ``nodo``, o ``None``."""
    if hondura > _PROFUNDIDAD_MAX or not isinstance(nodo, dict):
        return None
    nodo, vistos = _resolver(nodo, definiciones, vistos)
    if not nodo:
        return None

    for clave in ("anyOf", "oneOf", "allOf"):
        for sub in nodo.get(clave, ()):
            hallazgo = _buscar(sub, definiciones, ruta, vistos, hondura + 1)
            if hallazgo is not None:
                return hallazgo

    tipo = nodo.get("type")

    if tipo == "array":
        items = nodo.get("items", {})
        # La cota tiene que estar EN EL ESQUEMA. Un array numérico sin `maxItems`
        # crece con el flujo de muestras: eso es waveform crudo, se llame como se llame.
        if "maxItems" not in nodo and _es_numerico(items, definiciones, vistos):
            return f"{ruta}[] — array numérico sin `maxItems` (crece con el flujo de muestras)"
        # Un array ACOTADO de elementos NO acotados sigue sin estarlo: se entra igual.
        return _buscar(items, definiciones, f"{ruta}[]", vistos, hondura + 1)

    if tipo == "string" and nodo.get("format") in _FORMATOS_DE_BLOB and "maxLength" not in nodo:
        return f"{ruta} — blob crudo (`format: {nodo['format']}`) sin `maxLength`"

    for campo, sub in (nodo.get("properties") or {}).items():
        hallazgo = _buscar(sub, definiciones, f"{ruta}.{campo}", vistos, hondura + 1)
        if hallazgo is not None:
            return hallazgo

    return None


def _buscar_dicts(
    nodo: Any,
    definiciones: dict,
    ruta: str,
    vistos: frozenset[str],
    hondura: int,
    salida: list[str],
) -> None:
    if hondura > _PROFUNDIDAD_MAX or not isinstance(nodo, dict):
        return
    nodo, vistos = _resolver(nodo, definiciones, vistos)
    if not nodo:
        return

    for clave in ("anyOf", "oneOf", "allOf"):
        for sub in nodo.get(clave, ()):
            _buscar_dicts(sub, definiciones, ruta, vistos, hondura + 1, salida)

    if nodo.get("type") == "array":
        _buscar_dicts(nodo.get("items", {}), definiciones, f"{ruta}[]", vistos, hondura + 1, salida)
        return

    propiedades = nodo.get("properties")
    if nodo.get("type") == "object" and not propiedades and ruta:
        if nodo.get("additionalProperties") is not False:
            salida.append(ruta.lstrip("."))
        return

    for campo, sub in (propiedades or {}).items():
        _buscar_dicts(sub, definiciones, f"{ruta}.{campo}", vistos, hondura + 1, salida)
