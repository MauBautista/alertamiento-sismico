"""[T-7.25] Cliente FDSN de USGS. Pregunta, entiende, y cuando no puede lo dice.

FDSN (`fdsnws-event`) es el protocolo estándar de los servicios sismológicos, y
USGS lo sirve en `earthquake.usgs.gov/fdsnws/event/1/query`. Aquí sólo se usa
`format=geojson`.

TRES PROPIEDADES QUE NO SON NEGOCIABLES
───────────────────────────────────────

**1 · Ningún fallo sale de aquí como una excepción cualquiera.** Red, timeout,
5xx, HTML de mantenimiento, JSON roto: todos salen como :class:`SinRespuesta`
**con motivo en castellano**, y ese motivo es literalmente lo que se escribe en
``catalog_consultations.detail``. Es lo que permite declarar ``consultando``
—«pregunté y no me contestó»— en vez de inventar o de callar. Un worker que se
cayera por la red dejaría de mover fases de incidente, que es su trabajo de
verdad (reglas de oro 1 y 4).

**2 · Sin reintentos dentro de la llamada.** El reintento es la pasada siguiente
del worker, y queda ESCRITO en la base (`last_attempt_at`, `attempts`).
Reintentar aquí dentro multiplicaría el timeout dentro del ciclo que sostiene los
dictámenes, y no dejaría rastro de haberlo hecho.

**3 · Tope de bytes MIENTRAS se lee.** La respuesta se acumula en trozos y se
corta al pasar de ``catalog_usgs_max_bytes``. Comprobar el tamaño al final ya
habría pagado la memoria, que es justo lo que el tope existe para no pagar.

**4 · Y un PLAZO de reloj para la llamada entera.** El timeout de `httpx` es
**por operación**: cada trozo que llega reinicia el de lectura. Una fuente que
gotee —un byte cada cinco segundos— no dispara nunca el read timeout y tiene al
worker leyendo indefinidamente, que es peor que el tope de dos minutos que esta
revisión vino a quitar: el bucle que sostiene fases, dictámenes y la actuación
del quórum se quedaría parado sin que nada lo declare. El plazo se cuenta desde
antes de abrir el socket, así que cubre conexión, cabeceras y lectura.

LO QUE ESTE MÓDULO NO HACE
──────────────────────────
No decide si un evento publicado ES el nuestro. Eso lo hace
`forensics/correlacion.py` (`T-5.11`) con su criterio de identidad —ventana
consciente de la distancia, radio al sitio y coherencia PGA/distancia—, y aquí no
se duplica ni una línea de él: la ventana y el radio de la consulta se reciben ya
calculados desde ese mismo `Criterio`. Dos criterios de casamiento serían dos
respuestas distintas a la misma pregunta.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

if TYPE_CHECKING:
    from takab_api.settings import Settings

log = logging.getLogger("takab_api.catalogo")

#: El único proveedor que se consulta hoy. Es el valor del CHECK de
#: ``catalog_consultations.provider`` y de ``reference_earthquakes.source``.
PROVEEDOR = "USGS"

#: La palabra con la que USGS declara que revisó su propia solución. Es la única
#: que concede ``confirmado``; ver :func:`review_status`.
REVISADA = "reviewed"

#: Los dos estados del glosario que pintan cifra (`shared/glossary/procedencia.json`).
#: Se escriben aquí como literales y no se importan de `procedencia` para que este
#: módulo siga siendo probable sin nada más; el censo de que son los mismos cinco
#: lo hace `api/tests/test_procedencia.py` sobre el glosario.
CONFIRMADO = "confirmado"
PRELIMINAR = "preliminar"


class SinRespuesta(Exception):
    """La fuente no devolvió nada utilizable. ``motivo`` se escribe en la base."""

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo


@dataclass(frozen=True)
class EventoPublicado:
    """Un evento tal como lo publica la fuente. Sin interpretar."""

    provider_event_id: str
    origin_time: datetime
    magnitude: float | None
    lat: float
    lon: float
    depth_km: float | None
    place: str
    #: El estado CRUDO que dio la fuente (`reviewed`, `automatic`, …). Se guarda
    #: sin traducir para que la cita diga lo que dijo el proveedor, no lo que
    #: nosotros entendimos.
    estado_en_la_fuente: str
    mag_type: str | None = None

    @property
    def review_status(self) -> str:
        return review_status(self.estado_en_la_fuente)


@dataclass(frozen=True)
class Respuesta:
    """Lo que contestó la fuente, con la URL exacta que se le preguntó.

    La URL no es decoración: es la mitad citable de ``source_ref``. Una cifra
    ajena es citable cuando alguien puede repetir la pregunta.
    """

    url: str
    consultado_en: datetime
    eventos: tuple[EventoPublicado, ...]


def review_status(estado_en_la_fuente: str | None) -> str:
    """Traduce el estado del proveedor al vocabulario del glosario.

    **La duda va hacia `preliminar`.** ``confirmado`` significa «la fuente revisó
    su solución y ésta es la que sostiene», y eso sólo se puede afirmar cuando la
    fuente lo dice con su palabra. Un estado desconocido —uno que USGS añada
    mañana, o una cadena vacía— se cita como ``preliminar``, que es la afirmación
    más débil de las dos: «puede cambiar». Al revés se prometería una revisión
    que nadie hizo.
    """
    return CONFIRMADO if (estado_en_la_fuente or "").strip().lower() == REVISADA else PRELIMINAR


def _instante(ms: object) -> datetime | None:
    """La hora de origen viene en milisegundos desde el epoch, en UTC."""
    if not isinstance(ms, (int, float)) or isinstance(ms, bool):
        return None
    return datetime.fromtimestamp(float(ms) / 1000.0, tz=UTC)


def _numero(valor: object) -> float | None:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return float(valor)


def parsea(payload: object) -> tuple[EventoPublicado, ...]:
    """Los eventos del GeoJSON del FDSN. Levanta ``SinRespuesta`` si no lo es.

    **Una fila mala no cuesta las buenas.** Un evento sin identificador, sin hora
    o sin epicentro se descarta en silencio y el resto entra: sin
    ``provider_event_id`` la fila no tiene identidad y el catálogo la duplicaría
    en la siguiente consulta, y sin coordenadas el criterio de identidad no puede
    ni evaluarla. Lo que no se tolera es que el sobre entero sea otra cosa —un
    HTML de mantenimiento, por ejemplo—: eso no es «cero eventos», es no haber
    obtenido respuesta.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
        raise SinRespuesta("la respuesta no es un GeoJSON de FDSN (sin `features`)")

    eventos: list[EventoPublicado] = []
    for feature in payload["features"]:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties")
        props = props if isinstance(props, dict) else {}
        geom = feature.get("geometry")
        coords = geom.get("coordinates") if isinstance(geom, dict) else None
        # ⚠️ GeoJSON ordena [lon, lat, profundidad]. Invertirlo no da error: da un
        # epicentro en otro hemisferio, que el criterio rechazaría por radio y que
        # se leería como «sin correlación».
        if not isinstance(coords, (list, tuple)) or len(coords) < 2:
            continue
        lon, lat = _numero(coords[0]), _numero(coords[1])
        origen = _instante(props.get("time"))
        ident = str(feature.get("id") or "").strip()
        if not ident or origen is None or lat is None or lon is None:
            continue
        eventos.append(
            EventoPublicado(
                provider_event_id=ident,
                origin_time=origen,
                magnitude=_numero(props.get("mag")),
                lat=lat,
                lon=lon,
                depth_km=_numero(coords[2]) if len(coords) > 2 else None,
                place=str(props.get("place") or "sin lugar declarado por la fuente"),
                estado_en_la_fuente=str(props.get("status") or ""),
                mag_type=str(props.get("magType")) if props.get("magType") else None,
            )
        )
    return tuple(eventos)


def _iso(momento: datetime) -> str:
    """FDSN quiere ISO-8601. Se manda SIEMPRE en UTC y con la `Z` explícita."""
    return momento.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def url_de_consulta(
    base_url: str,
    *,
    desde: datetime,
    hasta: datetime,
    lat: float,
    lon: float,
    radio_km: float,
    limite: int,
) -> str:
    """La URL exacta, con la ventana temporal y el círculo geográfico.

    **El círculo ES el criterio, no una aproximación suya.** ``maxradiuskm`` se
    mide epicentro↔punto, y el punto que se manda es el SITIO: exactamente la
    distancia que `forensics/correlacion.py` usa para rechazar por radio. Una
    caja rectangular habría sido un superconjunto del círculo —más datos para el
    mismo resultado— y habría necesitado su propia justificación.

    ⚠️ **El precio, dicho:** lo que la fuente filtra por radio no vuelve, así que
    un sismo de Vanuatu no aparecerá nunca como descarte NOMBRADO con su motivo,
    al contrario que los descartes por tiempo o por coherencia PGA/distancia, que
    sí llegan y sí se nombran. Se acepta porque una consulta global sin acotar
    sobre un feed vivo trae cientos de eventos en cada incidente.
    """
    params = {
        "format": "geojson",
        "starttime": _iso(desde),
        "endtime": _iso(hasta),
        "latitude": f"{lat:g}",
        "longitude": f"{lon:g}",
        "maxradiuskm": f"{radio_km:g}",
        "orderby": "time",
        "limit": str(limite),
    }
    return f"{base_url}?{urlencode(params)}"


def consulta(
    settings: Settings,
    *,
    desde: datetime,
    hasta: datetime,
    lat: float,
    lon: float,
    radio_km: float,
    transport: Any | None = None,
    now: datetime | None = None,
) -> Respuesta:
    """Pregunta a USGS por la ventana y el círculo dados.

    Levanta :class:`SinRespuesta` y **nada más**: cualquier excepción del cliente
    HTTP se envuelve con su tipo en el motivo.
    """
    if not settings.catalog_usgs_enabled:
        # Apagado NO devuelve una respuesta vacía: eso sería indistinguible de
        # «la fuente no tiene nada», que es una afirmación sobre el sismo.
        raise SinRespuesta("la consulta a USGS está apagada por configuración")

    try:
        # Perezoso: el camino apagado no paga el cliente HTTP. Y DENTRO de un
        # `try`, que es la propiedad 1 de la cabecera: `httpx` es una dependencia
        # que puede faltar en una imagen recortada, y un `ImportError` suelto
        # subiría hasta el bucle del worker como una excepción cualquiera en vez
        # de salir como `SinRespuesta` con su motivo. El motivo dice lo que pasa
        # de verdad —falta el cliente—, no «la fuente no respondió»: la fuente no
        # tiene nada que ver.
        import httpx  # noqa: PLC0415
    except ImportError as exc:
        raise SinRespuesta("no hay cliente HTTP instalado (httpx) para preguntar") from exc

    url = url_de_consulta(
        settings.catalog_usgs_url,
        desde=desde,
        hasta=hasta,
        lat=lat,
        lon=lon,
        radio_km=radio_km,
        limite=settings.catalog_usgs_limite,
    )
    tope = settings.catalog_usgs_max_bytes
    # El plazo de la llamada ENTERA (propiedad 4). Arranca antes del socket.
    plazo = settings.catalog_usgs_timeout_s
    empezo = time.monotonic()
    kwargs: dict[str, Any] = {"timeout": settings.catalog_usgs_timeout_s}
    if transport is not None:
        kwargs["transport"] = transport

    try:
        with httpx.Client(**kwargs) as client, client.stream("GET", url) as resp:
            if resp.status_code != 200:
                raise SinRespuesta(f"la fuente respondió HTTP {resp.status_code}")
            trozos: list[bytes] = []
            leidos = 0
            for trozo in resp.iter_bytes():
                if time.monotonic() - empezo > plazo:
                    raise SinRespuesta(
                        f"la fuente tardó más de {plazo:g} s en entregar la respuesta"
                    )
                leidos += len(trozo)
                if leidos > tope:
                    raise SinRespuesta(
                        f"la respuesta pasó del tope de {tope} bytes y se cortó al leerla"
                    )
                trozos.append(trozo)
            cuerpo = b"".join(trozos)
    except SinRespuesta:
        raise
    except Exception as exc:  # noqa: BLE001 - la red jamás tumba al worker
        log.warning("catálogo: USGS no contestó (%s)", exc)
        raise SinRespuesta(f"la fuente no respondió ({type(exc).__name__})") from exc

    try:
        payload = json.loads(cuerpo)
    except ValueError as exc:
        raise SinRespuesta("la respuesta de la fuente no es JSON") from exc

    return Respuesta(
        url=url,
        consultado_en=now or datetime.now(tz=UTC),
        eventos=parsea(payload),
    )


def cita(evento: EventoPublicado, url: str) -> str:
    """El texto de ``reference_earthquakes.source_ref``.

    Lleva la URL porque una cifra ajena es citable cuando alguien puede **repetir
    la pregunta**, y el estado crudo del proveedor porque `review_status` es ya
    una traducción nuestra.
    """
    magnitud = "sin magnitud publicada"
    if evento.magnitude is not None:
        magnitud = f"{evento.mag_type or 'M'} {evento.magnitude:g}"
    prof = "prof. desconocida" if evento.depth_km is None else f"prof. {evento.depth_km:g} km"
    # Las coordenadas van rotuladas `lat`/`lon` con su signo y NO con letras de
    # hemisferio: el seed escribe cosas como «-98.4887 W», que leído al pie de la
    # letra es la longitud contraria. Aquí la cita tiene que poder repetirse.
    return (
        f"{PROVEEDOR} FDSN {evento.provider_event_id} ({magnitud}, "
        f"lat {evento.lat:.4f}, lon {evento.lon:.4f}, {prof}) — "
        f"estado en la fuente '{evento.estado_en_la_fuente or 'no declarado'}' — {url}"
    )
