"""[T-2.70.a·D2/P2] Códec y marcado del transporte de pines.

Dos responsabilidades, y ni una más:

* **El marco.** `AF_UNIX` con `SOCK_STREAM` entrega BYTES, no mensajes: dos
  peticiones pueden llegar pegadas y una puede llegar partida en tres. El marco
  es una longitud de 4 bytes big-endian y un cuerpo JSON UTF-8, con una cota
  explícita (:data:`MAX_MARCO`) para que un `length` corrupto no le pida
  gigabytes al asignador del proceso que toca la sirena.

* **La traducción del contrato.** `GpioSnapshot` y `ChannelOutcome` viajan
  DERIVADOS de su propia declaración (`__dataclass_fields__` + anotaciones
  resueltas), no de una lista escrita a mano. Un campo nuevo se transporta solo;
  un campo de un tipo que este códec no sepa llevar TRUENA al primer viaje, en
  vez de llegar al otro lado convertido en su valor por defecto — que es la forma
  en que un transporte pierde estado en silencio.

**Ninguna dependencia NUEVA — que no es lo mismo que «stdlib puro», y así estaba
escrito.** Este módulo importa `pydantic.BaseModel` (línea de abajo) porque los
contratos del gabinete SON modelos Pydantic y el códec tiene que saber
serializarlos; `takab_edge.contracts` ya lo arrastraba de todos modos. Lo que la
allowlist de D1.3 (`tests/test_gpio_process.py`) garantiza —y sí caza, nombrando
la cadena de imports— es que el proceso mínimo del camino de vida no gane
dependencias que no estén declaradas ahí, no que no tenga ninguna. El rótulo
enfático era falso y llamarlo por su nombre cuesta menos que descubrirlo el día
que alguien se apoye en él. Del resto: `json`, `struct`-libre (`int.to_bytes`) y
`typing` de la stdlib, que es la forma que la regla de oro 4 pide.
"""

from __future__ import annotations

import json
from enum import Enum
from types import UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints

from pydantic import BaseModel

from takab_edge.gpio_link import ChannelOutcome, GpioSnapshot

#: Cota dura del cuerpo de un mensaje. La instantánea completa del gabinete
#: (cinco relés incluidos) ronda los 600 bytes; 256 KiB deja tres órdenes de
#: magnitud de holgura y sigue siendo un tamaño que este proceso puede asignar
#: sin pensárselo. Un `length` mayor NO se cree: se corta la conexión.
MAX_MARCO = 256 * 1024

#: Longitud de la cabecera de marco, en bytes.
CABECERA = 4

#: Campos de `GpioSnapshot` que NO viajan porque se RECALCULAN al llegar, cada
#: uno con su razón. Es una lista de EXCEPCIONES declaradas, no de miembros: todo
#: campo nuevo se transporta por defecto y, si alguien decide que no debe, tiene
#: que escribir aquí por qué (mismo patrón que la allowlist de D1.3).
CAMPOS_RECALCULADOS_AL_LLEGAR: dict[str, str] = {
    "campos_desconocidos": (
        "[T-2.165] lo rellena QUIEN LEE, comparando lo que el dueño dijo saber "
        "con lo que este cliente espera. El dueño no puede declararlo porque no "
        "sabe qué campos conoce el otro lado — de hecho, si lo supiera no habría "
        "problema que resolver."
    ),
    "age_s": (
        "la edad se mide en el reloj de QUIEN LEE, contando desde que la "
        "instantánea llegó. Transportar la edad medida en el reloj del otro "
        "proceso convertiría el tiempo de vuelo en cero y haría que un dato "
        "rancio se leyera como fresco — que es justo lo que este campo existe "
        "para impedir (`time.monotonic()` ni siquiera es comparable entre "
        "procesos)."
    ),
}


class ProtocolError(ValueError):
    """El otro lado dijo algo que este protocolo no puede interpretar.

    Hereda de ``ValueError`` porque eso es lo que era el fallo equivalente
    dentro del proceso (un payload mal formado), y quien lo captura hoy sigue
    capturándolo.
    """


# ---------------------------------------------------------------------------
# Marco
# ---------------------------------------------------------------------------


def enmarcar(mensaje: dict) -> bytes:
    """Serializa un mensaje a `[longitud:4][json]`."""
    cuerpo = json.dumps(mensaje, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(cuerpo) > MAX_MARCO:
        raise ProtocolError(
            f"mensaje de {len(cuerpo)} bytes por encima de la cota del transporte "
            f"({MAX_MARCO}); el estado del gabinete no puede ocupar tanto"
        )
    return len(cuerpo).to_bytes(CABECERA, "big") + cuerpo


class Desenmarcador:
    """Reensambla mensajes de un flujo de bytes. Uno por conexión y dirección."""

    __slots__ = ("_buffer",)

    def __init__(self) -> None:
        self._buffer = bytearray()

    @property
    def a_medias(self) -> int:
        """Bytes de un marco INCOMPLETO retenidos. `0` = no hay nada a medias.

        Lo lee el corte del cliente ocioso del servidor: «abrió, mandó media
        trama y se calló» y «suscriptor sano que no tiene nada que decir» se ven
        idénticos desde el socket, y sólo el primero merece que le cierren.
        """
        return len(self._buffer)

    def alimentar(self, datos: bytes) -> list[dict]:
        """Añade lo recibido y devuelve los mensajes COMPLETOS que ya haya."""
        self._buffer.extend(datos)
        mensajes: list[dict] = []
        while True:
            if len(self._buffer) < CABECERA:
                return mensajes
            largo = int.from_bytes(self._buffer[:CABECERA], "big")
            if largo > MAX_MARCO:
                raise ProtocolError(
                    f"marco de {largo} bytes por encima de la cota ({MAX_MARCO}): "
                    "o el otro lado habla otro protocolo, o el flujo se corrompió"
                )
            if len(self._buffer) < CABECERA + largo:
                return mensajes
            crudo = bytes(self._buffer[CABECERA : CABECERA + largo])
            del self._buffer[: CABECERA + largo]
            try:
                mensaje = json.loads(crudo)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ProtocolError(f"cuerpo de marco ilegible: {exc}") from exc
            if not isinstance(mensaje, dict):
                raise ProtocolError(f"marco que no es un objeto: {type(mensaje).__name__}")
            mensajes.append(mensaje)


# ---------------------------------------------------------------------------
# Contrato ↔ JSON, DERIVADO de la declaración del contrato
# ---------------------------------------------------------------------------


def _a_json(valor: Any) -> Any:
    """Valor de contrato → JSON. Truena ante lo que no sepa llevar."""
    if valor is None or isinstance(valor, (bool, int, float, str)):
        return valor.value if isinstance(valor, Enum) else valor
    if isinstance(valor, Enum):
        return valor.value
    if isinstance(valor, BaseModel):
        return valor.model_dump(mode="json")
    if isinstance(valor, (tuple, list)):
        return [_a_json(elemento) for elemento in valor]
    raise ProtocolError(
        f"el códec del transporte de pines no sabe llevar un {type(valor).__name__}. "
        "Declara cómo viaja antes de meterlo en el contrato del gabinete: un tipo "
        "que no viaja llega al otro lado como su valor por defecto, en silencio."
    )


def _desde_json(anotacion: Any, valor: Any) -> Any:
    """JSON → valor de contrato, guiado por la ANOTACIÓN del campo."""
    origen = get_origin(anotacion)
    if origen in (Union, UnionType):
        opciones = [a for a in get_args(anotacion) if a is not type(None)]
        if valor is None:
            return None
        if len(opciones) != 1:
            raise ProtocolError(f"unión ambigua en el contrato: {anotacion}")
        return _desde_json(opciones[0], valor)
    if origen in (tuple, list):
        args = get_args(anotacion)
        elemento = args[0] if args else Any
        secuencia = [_desde_json(elemento, v) for v in valor]
        return tuple(secuencia) if origen is tuple else secuencia
    if isinstance(anotacion, type):
        if issubclass(anotacion, Enum):
            return anotacion(valor)
        if issubclass(anotacion, BaseModel):
            return anotacion.model_validate(valor)
        if anotacion is bool:
            return bool(valor)
        if anotacion in (int, float, str):
            return anotacion(valor)
    raise ProtocolError(f"el códec no sabe reconstruir un {anotacion!r}")


def _campos_transportados(clase: type, excepciones: dict[str, str]) -> dict[str, Any]:
    """`{campo: anotación resuelta}` de lo que SÍ viaja."""
    pistas = get_type_hints(clase)
    return {
        nombre: pistas[nombre] for nombre in clase.__dataclass_fields__ if nombre not in excepciones
    }


#: [T-2.165] Clave con la que el dueño DECLARA qué campos conoce.
#:
#: No es un número de versión, y la diferencia es el fondo de la ficha. Una
#: versión obliga a mantener a mano un registro de «qué campos existían en la N»
#: — un censo enumerado, que en esta casa acaba divergiendo—. La lista de campos
#: la deriva el propio dueño de su `__dataclass_fields__`: siempre dice la
#: verdad sobre sí mismo y no hay tabla que actualizar.
CLAVE_CAMPOS_DEL_DUENO = "_campos"


def _neutro(tipo: object) -> object:
    """Qué valor lleva un campo que el dueño no supo decir.

    **Su valor no significa nada, y por eso puede ser cualquiera**: el nombre del
    campo queda en `GpioSnapshot.campos_desconocidos`, que es lo que lo separa de
    un dato medido. Existe sólo porque el dataclass es `frozen` y hay que
    construirlo con algo — no porque este número o este booleano describan al
    gabinete.

    Se deriva de la anotación en vez de leerse de una tabla: un campo nuevo entra
    solo, y si su tipo no está contemplado se LANZA en vez de inventar. Un tipo
    que nadie mapeó es una decisión pendiente, no un `None`.
    """
    texto = str(tipo)
    if "None" in texto:
        return None
    if texto.startswith("bool") or texto == "<class 'bool'>":
        return False
    if texto.startswith("float") or texto == "<class 'float'>":
        return 0.0
    if texto.startswith("int") or texto == "<class 'int'>":
        return 0
    if "tuple" in texto:
        return ()
    if "str" in texto:
        return ""
    raise ProtocolError(
        f"un campo del snapshot es de un tipo que el códec no sabe neutralizar "
        f"({tipo!r}): decide qué significa 'el dueño no lo sabe' antes de añadirlo"
    )


def instantanea_a_json(snap: GpioSnapshot) -> dict:
    """`GpioSnapshot` → dict JSON-able (todo campo salvo los declarados).

    [T-2.165] Viaja además la lista de campos que ESTE dueño conoce, para que el
    otro lado pueda distinguir «no lo mandó porque no lo conoce» de «dijo que lo
    mandaría y no está».
    """
    campos = _campos_transportados(GpioSnapshot, CAMPOS_RECALCULADOS_AL_LLEGAR)
    datos = {nombre: _a_json(getattr(snap, nombre)) for nombre in campos}
    datos[CLAVE_CAMPOS_DEL_DUENO] = sorted(campos)
    return datos


def instantanea_desde_json(datos: dict, *, edad_s: float) -> GpioSnapshot:
    """dict → `GpioSnapshot`, con la EDAD medida por quien lee.

    [T-2.165] TRES desenlaces, no dos, porque un campo ausente tiene dos causas
    que piden respuestas opuestas:

    * **El dueño no conoce el campo** (corre una versión anterior a la que lo
      introdujo). No es un contrato roto: es el estado NORMAL de la ventana que
      el layout A/B abre entre activar al cliente y reiniciar al dueño. Se lee lo
      que sí vino y el nombre del que no, en `campos_desconocidos`.
    * **El dueño dijo que lo mandaría y no está.** Eso sí es un contrato roto y
      sigue lanzando: rellenarlo con el default devolvería un gabinete inventado
      —sirena en reposo, relés vacíos— con la firma de un dato medido.
    * **El dueño conoce campos que este cliente no.** El despliegue va al revés
      (dueño más nuevo que su cliente) y también lanza: leer una instantánea que
      no se entiende del todo es peor que no leerla.

    Un dueño ANTERIOR a esta ficha no manda la lista de campos. Entonces no se le
    puede exigir nada: lo que falte se cuenta como desconocido. Es la lectura
    correcta —no puede haber prometido campos que no sabía que existían— y es
    justo el caso que dejó un gabinete ciego el 2026-08-23.
    """
    campos = _campos_transportados(GpioSnapshot, CAMPOS_RECALCULADOS_AL_LLEGAR)
    declarados = datos.get(CLAVE_CAMPOS_DEL_DUENO)

    if declarados is not None:
        if not isinstance(declarados, list) or not all(isinstance(x, str) for x in declarados):
            raise ProtocolError(
                f"la instantánea declaró `{CLAVE_CAMPOS_DEL_DUENO}` y no es una lista "
                f"de nombres: {declarados!r}"
            )
        del_dueno = set(declarados)
        de_mas = sorted(del_dueno - set(campos))
        if de_mas:
            raise ProtocolError(
                f"el dueño de los pines conoce campos que este cliente no ({de_mas}): "
                "corre una versión POSTERIOR. El despliegue va al revés — se activó "
                "al dueño antes que al cliente"
            )
        rotos = sorted(n for n in del_dueno if n not in datos)
        if rotos:
            raise ProtocolError(
                f"el dueño dijo que mandaría {rotos} y no llegaron: es un contrato "
                "roto, no un gabinete en reposo"
            )
        desconocidos = frozenset(n for n in campos if n not in del_dueno)
    else:
        # Dueño anterior a T-2.165: no declara nada, así que no se le exige nada.
        desconocidos = frozenset(n for n in campos if n not in datos)

    valores = {
        nombre: (_neutro(tipo) if nombre in desconocidos else _desde_json(tipo, datos[nombre]))
        for nombre, tipo in campos.items()
    }
    return GpioSnapshot(**valores, age_s=edad_s, campos_desconocidos=desconocidos)


def resultado_a_json(resultado: ChannelOutcome) -> dict:
    return {
        nombre: _a_json(getattr(resultado, nombre))
        for nombre in _campos_transportados(ChannelOutcome, {})
    }


def resultado_desde_json(datos: dict) -> ChannelOutcome:
    campos = _campos_transportados(ChannelOutcome, {})
    faltan = [nombre for nombre in campos if nombre not in datos]
    if faltan:
        raise ProtocolError(f"resultado de canal incompleto: faltan {faltan}")
    return ChannelOutcome(**{n: _desde_json(t, datos[n]) for n, t in campos.items()})
