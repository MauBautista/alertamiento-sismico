"""Cuándo empieza a grabar el CCTV — las tres puertas (T-3.11).

Este módulo es **puro**: recibe el `dict` que devuelve `GET /api/status` del panel LAN y
decide. No hace red, no toca disco y no conoce ffmpeg. Está separado del cliente justo
por eso: la parte que puede equivocarse de forma cara es una función que se prueba con un
diccionario, no un bucle con sockets dentro.

POR QUÉ SE SONDEA EN VEZ DE QUE EL EDGE NOS LLAME
─────────────────────────────────────────────────
`B.1` exige que si el CCTV muere, se cuelga o satura la red, **el gabinete no se entere**.
Eso no se consigue con disciplina, se consigue con la **dirección de la dependencia**: el
edge es servidor, nosotros somos clientes. Un cliente que desaparece es invisible para el
servidor; una llamada del edge hacia nosotros, no.

El coste de sondear —hasta ~1 s de retraso en enterarse— **no cuesta nada aquí**, porque el
anillo ya lleva minutos grabando cuando llega la alerta. El disparo no captura el momento:
lo *marca*.

LA PUERTA QUE MÁS IMPORTA, Y NO ES LA OBVIA
───────────────────────────────────────────
El WR-1 tiene un **modo prueba** con el que se ejercita el gabinete sin alertar a nadie
(`T-1.69`), y el embudo del edge suprime en él todo lo que va a la nube. Un CCTV que no
mirase ese flag subiría a S3 **vídeo real de un edificio real con gente dentro** cada vez
que alguien prueba el radio: sin incidente al que atarlo, sin base legal, y con factura.
Es el fallo más caro que este módulo puede tener y por eso es la primera comprobación.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

log = logging.getLogger("takab_edge.cctv")

#: Tiers que merecen clip. Es **el mismo conjunto** que dispara `queue_evidence` en el
#: supervisor, y la coincidencia es deliberada: si un evento merece que se guarde su
#: miniSEED, merece que se guarde lo que se vio. Divergir aquí produciría incidentes con
#: sismograma y sin vídeo, o al revés, sin que nadie supiera por qué.
TIERS_QUE_GRABAN: frozenset[str] = frozenset({"restricted", "evacuate_or_hold"})


@dataclass(frozen=True)
class Disparo:
    """Un evento que merece clip. `event_id` es el mismo `incidents.event_uuid` de la nube."""

    event_id: str
    t0: datetime
    tier: str
    source: str


def _transicion_mas_reciente(status: dict) -> dict | None:
    """La transición de tier más nueva de `events`, o `None`.

    `events` mezcla transiciones de tier con acciones del panel (silenciar, probar sirena);
    solo las primeras traen `to_tier`. Filtrar por esa clave es lo que las distingue, y es
    más robusto que fiarse del orden: la lista ya viene ordenada, pero depender de eso
    haría que un cambio de orden en el panel nos rompiera en silencio.
    """
    eventos = status.get("events")
    if not isinstance(eventos, list):
        return None
    transiciones = [e for e in eventos if isinstance(e, dict) and e.get("to_tier")]
    if not transiciones:
        return None
    return max(transiciones, key=lambda e: str(e.get("at", "")))


def modo_prueba_activo(status: dict) -> bool:
    """¿Está el WR-1 en modo prueba? **Ante la duda, sí.**

    Un `status` sin la sección o con basura dentro se trata como modo prueba activo, o sea
    **no grabar**. Es la dirección segura: dejar de grabar un evento real cuesta un reporte
    sin vídeo; grabar durante una prueba cuesta imágenes de personas subidas a la nube sin
    causa. Los dos son fallos, pero no cuestan lo mismo.
    """
    seccion = status.get("test_mode")
    if not isinstance(seccion, dict):
        return True
    return bool(seccion.get("active", True))


def simulacro_activo(status: dict) -> bool:
    """¿Hay un simulacro en curso? Ante la duda, sí — misma dirección que el modo prueba.

    **Un simulacro NO produce clip en v1, y es una decisión, no un olvido.** Medir cuánto
    tarda la gente en salir durante un simulacro es exactamente para lo que sirve un
    simulacro, así que es el candidato más obvio a activarlo después. Pero `D-14` acota el
    vídeo que sale del inmueble a **eventos confirmados**, y un simulacro no lo es.
    Ampliarlo es una decisión de producto con su propia conversación de privacidad, no algo
    que se cuele por parecerse.
    """
    seccion = status.get("drill")
    if seccion is None:
        return False  # el gabinete no expone simulacros: no hay ninguno que respetar
    if not isinstance(seccion, dict):
        return True
    return bool(seccion.get("active", True))


def disparo_en(status: dict, *, ya_vistos: frozenset[str] = frozenset()) -> Disparo | None:
    """Devuelve el `Disparo` si este `status` merece clip, o `None`.

    Idempotente por `event_id`: sondeamos a 1 Hz y el mismo evento aparece en `events`
    durante minutos. Es la misma disciplina de nonce que usa todo lo que cruza edge→nube.
    """
    if modo_prueba_activo(status):
        return None
    if simulacro_activo(status):
        return None

    transicion = _transicion_mas_reciente(status)
    if transicion is None:
        return None

    tier = str(transicion.get("to_tier") or "")
    if tier not in TIERS_QUE_GRABAN:
        return None

    event_id = str(transicion.get("event_id") or "")
    if not event_id or event_id in ya_vistos:
        return None

    momento = transicion.get("at")
    try:
        t0 = datetime.fromisoformat(str(momento))
    except (TypeError, ValueError):
        log.warning("cctv: transición con marca de tiempo ilegible (%r); se ignora", momento)
        return None

    source = str(transicion.get("source") or "desconocida")
    # NO se filtra por `visual_only`. La política T-2.32 degradó el umbral instrumental a
    # aviso —no mueve relés— pero `queue_evidence` está deliberadamente FUERA de esa puerta:
    # un evento que solo avisa sigue mereciendo evidencia. El vídeo hace lo mismo, y por la
    # misma razón. Si algún día se filtrara aquí, los dos rastros dejarían de casar.
    log.warning("cctv: disparo por %s (tier=%s, event_id=%s)", source, tier, event_id)
    return Disparo(event_id=event_id, t0=t0, tier=tier, source=source)
