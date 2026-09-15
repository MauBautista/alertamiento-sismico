"""Simulador de flota — carga para el load test de ingesta (T-1.17 G1).

Genera Feature1s realistas de ruido para la flota sim fija (SIM001..SIM020, 5 por
gateway gw-sim-0001..0004) y las envía en dos modos:

- ``--mode sqs``: boto3 ``send_message_batch`` directo a la cola, imitando EXACTAMENTE
  el enriquecimiento de la IoT Rule (``meta_principal``/``meta_topic``/``meta_ts_iot``).
  Carga sin costo IoT.
- ``--mode iot``: awsiotsdk con una conexión mTLS por gateway sim (client_id=thing),
  publicando el payload SIN meta_* (la IoT Rule real enriquece). Smoke de extremo a extremo.

Todo payload se valida contra ``shared/schemas/*.schema.json`` antes de enviarse:
si el contrato deriva, el simulador falla ruidosamente (``ContractDriftError``).
Herramienta de desarrollo: boto3/jsonschema viven en el grupo dev de edge, no en el
runtime del gabinete (imports perezosos).
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import random
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Any

from takab_edge.contracts import (
    AlertSource,
    Feature1s,
    HealthSnapshot,
    LocalEvent,
    Tier,
    new_event_id,
)

from simulators.replay import Arribo, Sismo, plan_de_arribos, velocidades
from simulators.replay import Estacion as EstacionDelPlan

# Convención de flota dev (FIJA — ver seeds db/seeds/prod_fleet.sql + sim_fleet.sql)
TENANT_ID = "tenant-dev"
MAX_SITES = 20
STATIONS_PER_GATEWAY = 5
CHANNELS = ("EHZ", "ENZ", "ENN", "ENE")

FEATURES_TOPIC = "takab/features"
HEALTH_TOPIC = "takab/health"
EVENTS_TOPIC = "takab/events"

HEALTH_PERIOD_S = 30.0
QUAKE_WATCH_S = 2.0  # emite el LocalEvent watch a los 2 s de corrida
QUAKE_ESCALATE_S = 5.0  # escalada evacuate_or_hold (mismo event_id) a los 5 s

SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "shared" / "schemas"
SCHEMA_BY_TOPIC = {
    FEATURES_TOPIC: "feature_1s",
    HEALTH_TOPIC: "health_snapshot",
    EVENTS_TOPIC: "local_event",
}


class ContractDriftError(RuntimeError):
    """El payload generado ya no cumple el JSON Schema comprometido."""


@cache
def _validator(schema_name: str):
    from jsonschema import Draft202012Validator  # dep dev — import perezoso

    schema = json.loads((SCHEMAS_DIR / f"{schema_name}.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_payload(topic: str, payload: dict[str, Any]) -> None:
    """Valida el payload (SIN meta_*) contra el schema del topic. Falla ruidosamente."""
    import jsonschema

    schema_name = SCHEMA_BY_TOPIC[topic]
    try:
        _validator(schema_name).validate(payload)
    except jsonschema.ValidationError as exc:
        raise ContractDriftError(
            f"payload de {topic} no conforme a {schema_name}: {exc.message}"
        ) from exc


def station_name(index: int) -> str:
    return f"SIM{index:03d}"


def _station_index(station: str) -> int:
    if not (station.startswith("SIM") and station[3:].isdigit()):
        raise ValueError(f"estación fuera de la convención sim: {station!r}")
    index = int(station[3:])
    if not 1 <= index <= MAX_SITES:
        raise ValueError(f"estación fuera de la flota sim (1..{MAX_SITES}): {station!r}")
    return index


def gateway_for(station: str) -> str:
    """SIM001..SIM005→gw-sim-0001, SIM006..SIM010→gw-sim-0002, ... (5 por gateway EN ORDEN)."""
    gw = (_station_index(station) - 1) // STATIONS_PER_GATEWAY + 1
    return f"gw-sim-{gw:04d}"


def site_for(station: str) -> str:
    """1 sensor por sitio: SIM007 → site-sim-007."""
    return f"site-sim-{_station_index(station):03d}"


@dataclass(frozen=True)
class Estacion:
    """Una estación simulada y a quién pertenece.

    [T-7.11] La convención fija (`SIM001..020`, 5 por gateway, índice→sitio) sigue
    siendo el default, pero la red de demostración no cabe en ella: son tres sitios
    de tres tipos con un gateway cada uno. En vez de estirar la fórmula —que es
    cómo una convención acaba con excepciones dentro— la flota puede venir de un
    fichero, y entonces es un DATO que se lee, no una regla que se adivina.
    """

    station: str
    gateway: str
    site: str
    #: [T-7.15] Dónde está, para saber cuándo le llega la onda. Solo lo necesita
    #: `--replay`; la flota fija de carga no lo lleva y no tiene por qué.
    lat: float | None = None
    lon: float | None = None


def flota_fija(sites: int) -> list[Estacion]:
    """La convención de siempre, intacta: `db/seeds/sim_fleet.sql`."""
    return [
        Estacion(s, gateway_for(s), site_for(s))
        for s in (station_name(i) for i in range(1, sites + 1))
    ]


def flota_de_fichero(ruta: Path) -> tuple[str, list[Estacion]]:
    """`(tenant, estaciones)` de un JSON. Formato:

        {"tenant": "tenant-dev",
         "stations": [{"station": "SIM101", "gateway": "gw-sim-0101",
                       "site": "site-sim-101", "lat": 19.31, "lon": -98.24}, ...]}

    Se validan las tres claves de cada fila: una estación sin gateway publicaría
    con un `thing` vacío y la nube la rechazaría por principal desconocido, que es
    un error mucho más caro de leer que éste.

    [T-7.15] `lat`/`lon` son OPCIONALES aquí y obligatorias en `--replay`: sin
    coordenadas no hay cuándo llega la onda, y el error se da al armar la
    reproducción —con el nombre de la estación— en vez de al leer el fichero.
    """
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    filas = datos.get("stations") or []
    if not filas:
        raise ValueError(f"{ruta}: no declara ninguna estación")
    estaciones = []
    for i, fila in enumerate(filas):
        faltan = [k for k in ("station", "gateway", "site") if not fila.get(k)]
        if faltan:
            raise ValueError(f"{ruta}: estación {i} sin {', '.join(faltan)}")
        estaciones.append(
            Estacion(
                fila["station"],
                fila["gateway"],
                fila["site"],
                lat=fila.get("lat"),
                lon=fila.get("lon"),
            )
        )
    return datos.get("tenant") or TENANT_ID, estaciones


# ═══════════════════════════════════════════════════════════════════════════
# [T-7.15] LA REPRODUCCIÓN: que las estaciones SIENTAN la onda.
# ═══════════════════════════════════════════════════════════════════════════
#
# El plan de arribos lo calcula `simulators/replay.py`, espejo del de la nube
# (`api/src/takab_api/replay/plan.py`) con prueba de igualdad de salida entre los
# dos. Aquí solo se le da FORMA a la feature: antes del arribo, ruido de fondo;
# desde el arribo, el pico que predice ATTEN-LAW, decayendo.
#
# **Determinista, sin RNG.** Una demostración tiene que salir igual dos veces
# seguidas, y una rampa aleatoria no se puede comprobar contra lo que el mapa
# pinta. El ruido de fondo sí es aleatorio: es ruido.

#: Constante de tiempo de la coda. NO es una medición: es la forma que hace
#: legible la demostración —el pico se ve llegar, se sostiene y se apaga en
#: torno al minuto—. Un sismo real no decae en una exponencial limpia.
DECAIMIENTO_S = 20.0

#: Tope del ruido de fondo (`_feature` sortea en 0.8..1.4). La rampa empieza por
#: encima para que el arribo se distinga del ruido, que es lo que la ficha pide:
#: «STA/LTA bajo umbral antes de `t_arribo`».
STA_LTA_FONDO_MAX = 1.4
#: STA/LTA en el pico. Basta con que esté cómodamente sobre cualquier umbral de
#: disparo; el número exacto no decide nada porque estas features no accionan.
STA_LTA_PICO = 9.0
#: Razón PGV/PGA del ruido de fondo, reutilizada en la rampa para que la fila no
#: cambie de forma al llegar la onda.
PGV_POR_PGA = 10.0


@dataclass(frozen=True)
class Reproduccion:
    """El sismo que se reproduce y cuándo le llega a cada estación."""

    catalog_key: str
    sismo: Sismo
    #: Por código de ESTACIÓN (`SIM101`), que es como el simulador la nombra. El
    #: plan de la nube va por sitio porque allí la unidad es el inmueble; aquí la
    #: unidad es el sensor que publica.
    arribos: dict[str, Arribo]

    def arribo_de(self, station: str) -> Arribo | None:
        return self.arribos.get(station)


def reproduccion_de_fichero(ruta: Path, estaciones: list[Estacion]) -> Reproduccion:
    """Arma la reproducción desde un JSON de sismo + las estaciones con coordenadas.

    Formato (ver `edge/simulators/replay_19s.json`)::

        {"catalog_key": "USGS-2017-09-19-PUE", "magnitude": 7.1,
         "lat": 18.5499, "lon": -98.4887, "depth_km": 48.0, "v_s_km_s": 4.0}

    Una estación sin coordenadas es un error **con su nombre**: sin ellas no hay
    cuándo llega la onda, y publicar ruido de fondo mientras el mapa pinta el
    frente pasando por encima sería la peor forma de fallar — parecería que la
    estación no sintió nada.
    """
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    faltan = [k for k in ("catalog_key", "magnitude", "lat", "lon") if datos.get(k) is None]
    if faltan:
        raise ValueError(f"{ruta}: al sismo le falta {', '.join(faltan)}")
    sin_coords = [e.station for e in estaciones if e.lat is None or e.lon is None]
    if sin_coords:
        raise ValueError(
            f"sin lat/lon no se puede reproducir: {', '.join(sorted(sin_coords))}. "
            "Añádelas al fichero de flota (espejo de db/seeds/demo_red.sql)."
        )
    v_p, v_s = velocidades(float(datos.get("v_s_km_s") or 4.0))
    sismo = Sismo(
        catalog_key=datos["catalog_key"],
        magnitude=float(datos["magnitude"]),
        lat=float(datos["lat"]),
        lon=float(datos["lon"]),
        depth_km=None if datos.get("depth_km") is None else float(datos["depth_km"]),
        v_s_km_s=v_s,
        v_p_km_s=v_p,
    )
    plan = plan_de_arribos(
        sismo,
        [
            EstacionDelPlan(e.site, e.station, float(e.lat), float(e.lon))
            for e in estaciones
            if e.lat is not None and e.lon is not None
        ],
    )
    return Reproduccion(
        catalog_key=sismo.catalog_key,
        sismo=sismo,
        arribos={a.site_code: a for a in plan},
    )


def esperar_pulso_wr1(
    url: str,
    *,
    timeout_s: float,
    leer: Callable[[str], dict[str, Any]],
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    periodo_s: float = 0.2,
) -> bool:
    """Sondea el panel del gabinete REAL hasta ver `sasmex_active`. LAN, sin JWT.

    Devuelve `True` si vio el pulso, `False` si venció el plazo. No lanza por un
    fallo de lectura: el panel puede reiniciarse a mitad, y abortar la
    demostración porque una lectura falló sería peor que reintentar.

    ⚠️ Ancla la reproducción al pulso REAL del WR-1, que es lo que hace que la
    coreografía cuadre con lo que el operador acaba de pulsar. Sin esto, el
    simulador y el gabinete cuentan desde instantes distintos y las ondas llegan
    antes o después que la alerta.
    """
    limite = clock() + timeout_s
    while clock() < limite:
        try:
            if leer(url).get("sasmex_active") is True:
                return True
        except Exception:  # noqa: BLE001 - un panel que se reinicia no aborta la demo
            pass
        sleep(periodo_s)
    return False


def leer_panel(url: str, *, timeout_s: float = 2.0) -> dict[str, Any]:
    """Lectura HTTP mínima del panel. `urllib` y no un cliente: cero dependencias."""
    import urllib.request  # noqa: PLC0415 - import perezoso, herramienta de desarrollo

    with urllib.request.urlopen(url, timeout=timeout_s) as r:  # noqa: S310 - URL de la LAN
        return json.loads(r.read().decode("utf-8"))


def enrich(payload: dict[str, Any], topic: str, thing: str, *, ts_ms: int | None = None) -> dict:
    """Imita el enriquecimiento de la IoT Rule (T-1.15): añade EXACTAMENTE 3 claves meta_*.

    No muta el dict de entrada. ``meta_principal`` = thing name del publicador.
    """
    return {
        **payload,
        "meta_principal": thing,
        "meta_topic": topic,
        "meta_ts_iot": int(time.time() * 1000) if ts_ms is None else ts_ms,
    }


@dataclass(frozen=True)
class OutMessage:
    """Mensaje listo para enviar. ``payload`` va SIN meta_* (sqs enriquece al enviar)."""

    topic: str
    thing: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class Summary:
    sent: int
    errors: int
    duration_s: float
    rate_effective: float


class FleetSimulator:
    """Genera los mensajes de cada ventana de 1/rate s para toda la flota.

    ``window_batch(w)`` se llama con ``w`` creciente (0,1,2,...): el estado del
    sismo simulado (--quake) es secuencial. Si la corrida dura <5 s la escalada
    del sismo no llega a emitirse.
    """

    def __init__(
        self,
        *,
        sites: int = MAX_SITES,
        rate: float = 1.0,
        with_health: bool = False,
        quake: str | None = None,
        seed: int | None = None,
        t0: datetime | None = None,
        estaciones: list[Estacion] | None = None,
        tenant: str = TENANT_ID,
        no_events: bool = False,
        replay: Reproduccion | None = None,
    ) -> None:
        if estaciones is None and not 1 <= sites <= MAX_SITES:
            raise ValueError(f"sites debe estar en 1..{MAX_SITES} (flota sim fija)")
        if rate <= 0:
            raise ValueError("rate debe ser > 0")
        # [T-7.11] `--no-events` y `--quake` son incompatibles por definición: el
        # sismo simulado ES un LocalEvent. Pedirlos juntos es pedir dos cosas
        # opuestas, y fallar aquí es mejor que emitir a medias.
        if no_events and quake is not None:
            raise ValueError("--no-events y --quake son incompatibles: el sismo ES un LocalEvent")
        # [T-7.15] Reproducir un sismo histórico y además emitir uno sintético son
        # dos sismos a la vez. El de `--quake` abriría incidentes que la
        # reproducción existe para NO abrir.
        if replay is not None and quake is not None:
            raise ValueError("--replay y --quake son incompatibles: serían dos sismos a la vez")
        self.sites = sites
        self.rate = rate
        self.interval = 1.0 / rate
        self.with_health = with_health
        self.tenant = tenant
        self.no_events = no_events
        self.replay = replay
        flota = estaciones if estaciones is not None else flota_fija(sites)
        self.stations = [e.station for e in flota]
        self._gateway_de = {e.station: e.gateway for e in flota}
        self._sitio_de = {e.station: e.site for e in flota}
        self.gateways = sorted({e.gateway for e in flota})
        if quake is not None:
            if quake not in self.stations:
                raise ValueError(f"--quake {quake} no está entre las estaciones activas")
        self.quake = quake
        self._quake_event_id = new_event_id()
        self._quake_stage = 0  # 0=nada, 1=watch emitido, 2=escalado
        self._rng = random.Random(seed)
        self.t0 = t0 if t0 is not None else datetime.now(UTC)

    def _feature(self, station: str, channel: str, window_start: datetime) -> Feature1s:
        # Ruido de fondo realista: sin disparo (sta_lta<1.5), sin clipping.
        rng = self._rng
        pga = rng.uniform(1e-4, 1e-3)
        return Feature1s(
            station=station,
            channel=channel,
            window_start=window_start,
            pga=pga,
            pgv=rng.uniform(1e-3, 1e-2),
            rms=pga * rng.uniform(0.2, 0.5),
            sta_lta=rng.uniform(0.8, 1.4),
            clipping=False,
            health_score=1.0,
        )

    def _feature_reproducida(
        self, station: str, channel: str, window_start: datetime, elapsed: float
    ) -> Feature1s:
        """La forma de la onda en esta estación. DETERMINISTA: sin RNG.

        Antes del arribo de la S el sitio está en su ruido de fondo; desde el
        arribo, el pico que predice ATTEN-LAW para esta distancia, decayendo con
        la constante de la coda. Una demostración tiene que salir igual dos veces
        seguidas, y una rampa aleatoria no se puede comparar con lo que el mapa
        pinta.
        """
        assert self.replay is not None
        a = self.replay.arribo_de(station)
        if a is None or elapsed < a.t_s_s:
            return self._feature(station, channel, window_start)
        dt = elapsed - a.t_s_s
        atenuacion = math.exp(-dt / DECAIMIENTO_S)
        pga = a.pga_g * atenuacion
        return Feature1s(
            station=station,
            channel=channel,
            window_start=window_start,
            pga=pga,
            pgv=pga * PGV_POR_PGA,
            rms=pga * 0.35,
            # Entre el fondo y el pico, proporcional a lo que queda de sacudida.
            sta_lta=STA_LTA_FONDO_MAX + (STA_LTA_PICO - STA_LTA_FONDO_MAX) * atenuacion,
            clipping=False,
            health_score=1.0,
        )

    def _msg(self, topic: str, thing: str, payload: dict[str, Any]) -> OutMessage:
        # [T-7.11] La invariante del bloque VIII, puesta donde no se puede rodear:
        # por aquí pasa TODO mensaje que sale del simulador. Un `LocalEvent`
        # simulado abre un incidente de verdad, el motor de cuórum forma con
        # estaciones que no midieron nada y la nube manda una alerta real a los
        # teléfonos del sitio. Se LANZA, no se descarta en silencio: un simulador
        # que se traga mensajes esconde el fallo en vez de enseñarlo.
        if self.no_events and topic == EVENTS_TOPIC:
            raise RuntimeError(
                "el simulador tiene --no-events y algo intentó publicar en "
                f"{EVENTS_TOPIC}: un LocalEvent simulado abre incidentes reales"
            )
        validate_payload(topic, payload)
        return OutMessage(topic=topic, thing=thing, payload=payload)

    def _quake_event(self, tier: Tier, created_at: datetime) -> OutMessage:
        assert self.quake is not None
        event = LocalEvent(
            event_id=self._quake_event_id,  # MISMO event_id: prueba la escalada E2E (G3)
            tenant_id=self.tenant,
            site_id=self._sitio_de[self.quake],
            source=AlertSource.THRESHOLD,
            tier=tier,
            created_at=created_at,
        )
        return self._msg(EVENTS_TOPIC, self._gateway_de[self.quake], event.model_dump(mode="json"))

    def window_batch(self, window_index: int) -> list[OutMessage]:
        elapsed = window_index * self.interval
        window_start = self.t0 + timedelta(seconds=elapsed)
        batch: list[OutMessage] = []
        for station in self.stations:
            thing = self._gateway_de[station]
            for channel in CHANNELS:
                feature = (
                    self._feature_reproducida(station, channel, window_start, elapsed)
                    if self.replay is not None
                    else self._feature(station, channel, window_start)
                )
                batch.append(self._msg(FEATURES_TOPIC, thing, feature.model_dump(mode="json")))
        # Heartbeat por gateway cada 30 s (incluye la ventana 0)
        if self.with_health and elapsed % HEALTH_PERIOD_S < self.interval:
            for gateway in self.gateways:
                snapshot = HealthSnapshot(gateway_id=gateway, captured_at=window_start)
                batch.append(self._msg(HEALTH_TOPIC, gateway, snapshot.model_dump(mode="json")))
        if self.quake is not None:
            if self._quake_stage == 0 and elapsed >= QUAKE_WATCH_S:
                batch.append(self._quake_event(Tier.WATCH, window_start))
                self._quake_stage = 1
            elif self._quake_stage == 1 and elapsed >= QUAKE_ESCALATE_S:
                batch.append(self._quake_event(Tier.EVACUATE_OR_HOLD, window_start))
                self._quake_stage = 2
        return batch


Sender = Callable[[list[OutMessage]], tuple[int, int]]


def run_plan(
    sim: FleetSimulator,
    *,
    duration_s: float,
    send: Sender,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Summary:
    """Agenda por ventana anclada al reloj monotónico (sin drift acumulado).

    Cada ventana ``w`` tiene target ``start + w*interval``; si el envío se atrasa
    (backpressure de SQS) no se duerme y la agenda se re-ancla al target siguiente.
    """
    n_windows = max(1, math.ceil(duration_s * sim.rate))
    start = clock()
    sent = errors = 0
    for w in range(n_windows):
        target = start + w * sim.interval
        now = clock()
        if target > now:
            sleep(target - now)
        ok, err = send(sim.window_batch(w))
        sent += ok
        errors += err
    elapsed = max(clock() - start, 1e-9)
    return Summary(sent=sent, errors=errors, duration_s=elapsed, rate_effective=sent / elapsed)


# --- modo sqs ---------------------------------------------------------------

_THROTTLING_CODES = frozenset(
    {"ThrottlingException", "Throttling", "RequestThrottled", "ServiceUnavailable"}
)
_MAX_ATTEMPTS = 5


def make_sqs_sender(client, queue_url: str, sleep: Callable[[float], None] = time.sleep) -> Sender:
    """Lotes de 10 con enriquecimiento imitando la IoT Rule; backoff ante throttling."""
    from botocore.exceptions import ClientError

    def send(messages: list[OutMessage]) -> tuple[int, int]:
        ok = errors = 0
        for chunk_start in range(0, len(messages), 10):
            chunk = messages[chunk_start : chunk_start + 10]
            pending = [
                {"Id": str(i), "MessageBody": json.dumps(enrich(m.payload, m.topic, m.thing))}
                for i, m in enumerate(chunk)
            ]
            for attempt in range(_MAX_ATTEMPTS):
                try:
                    resp = client.send_message_batch(QueueUrl=queue_url, Entries=pending)
                except ClientError as exc:
                    code = exc.response.get("Error", {}).get("Code", "")
                    if code in _THROTTLING_CODES and attempt < _MAX_ATTEMPTS - 1:
                        sleep(min(0.5 * 2**attempt, 8.0))  # backpressure
                        continue
                    errors += len(pending)
                    pending = []
                    break
                ok += len(resp.get("Successful", []))
                failed = resp.get("Failed", [])
                retryable_ids = {f["Id"] for f in failed if not f.get("SenderFault")}
                errors += len(failed) - len(retryable_ids)  # senderFault: no reintentar
                pending = [e for e in pending if e["Id"] in retryable_ids]
                if not pending:
                    break
                sleep(min(0.5 * 2**attempt, 8.0))
            errors += len(pending)  # reintentos agotados
        return ok, errors

    return send


# --- modo spool (el SOC local) ----------------------------------------------


def make_spool_sender(directorio: Path) -> Sender:
    """Deja los mensajes en el spool en disco que sustituye a IoT Core + SQS.

    Es el ÚNICO modo que no habla con AWS, y existe por una razón medida:
    `make soc-local` levanta el sistema entero —supervisor del edge, consumer
    real, handlers, motor de incidentes, consola— sustituyendo **solo** ese
    tramo, y la flota únicamente sabía publicar a SQS o a IoT Core. Sin esto la
    reproducción (`--replay`) no se puede enseñar en un navegador sin desplegar:
    la tabla por estación sale con el arribo TEÓRICO y jamás con el medido, que
    es justo la comparación por la que esa tabla existe (`T-7.17`).

    Enriquece con las MISMAS tres claves `meta_*` que la IoT Rule porque quien
    lee esto es el consumer de producción, que las separa antes de validar
    contra el schema.
    """
    directorio.mkdir(parents=True, exist_ok=True)
    # Contador monótono: ordenar por nombre reproduce el orden de publicación,
    # que es lo que el consumer observa. Mismo contrato que `demo/spool.py`.
    secuencia = itertools.count(1)

    def send(messages: list[OutMessage]) -> tuple[int, int]:
        ok = errors = 0
        for m in messages:
            cuerpo = json.dumps(enrich(m.payload, m.topic, m.thing))
            destino = directorio / f"{next(secuencia):012d}-{uuid.uuid4().hex[:8]}.json"
            # Escribir y renombrar. El consumer lee el directorio en caliente y
            # sólo mira `*.json`: un fichero a medio escribir sería un JSON roto
            # que acaba en la DLQ, y una pérdida silenciosa es peor que un error.
            tmp = destino.with_suffix(".tmp")
            try:
                tmp.write_text(cuerpo, encoding="utf-8")
                os.replace(tmp, destino)
            except OSError:
                tmp.unlink(missing_ok=True)
                errors += 1
                continue
            ok += 1
        return ok, errors

    return send


# --- modo iot ---------------------------------------------------------------


def open_iot_connections(things: list[str], certs_dir: Path, endpoint: str) -> dict:
    """Una conexión mTLS por gateway sim, client_id=thing (certs de provision_gateway.sh)."""
    from awsiot import mqtt_connection_builder  # extra [aws] — import perezoso

    connections = {}
    for thing in things:
        base = certs_dir / thing
        conn = mqtt_connection_builder.mtls_from_path(
            endpoint=endpoint,
            cert_filepath=str(base / "cert.pem"),
            pri_key_filepath=str(base / "key.pem"),
            ca_filepath=str(base / "ca.pem"),
            client_id=thing,
            clean_session=True,
            keep_alive_secs=30,
        )
        conn.connect().result(timeout=15)
        connections[thing] = conn
    return connections


def make_iot_sender(connections: dict) -> Sender:
    """Publica QoS1 el payload SIN meta_* (la IoT Rule real enriquece en la nube)."""
    from awscrt import mqtt

    def send(messages: list[OutMessage]) -> tuple[int, int]:
        futures = []
        for m in messages:
            future, _packet_id = connections[m.thing].publish(
                topic=m.topic,
                payload=json.dumps(m.payload).encode(),
                qos=mqtt.QoS.AT_LEAST_ONCE,
            )
            futures.append(future)
        ok = errors = 0
        for future in futures:
            try:
                future.result(timeout=10)
                ok += 1
            except Exception:
                errors += 1
        return ok, errors

    return send


# --- CLI ---------------------------------------------------------------------


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="fleet",
        description="Simulador de flota sim (SIM001..SIM020) para el load test de ingesta.",
    )
    parser.add_argument("--mode", choices=("sqs", "iot", "spool"), required=True)
    parser.add_argument("--rate", type=float, default=1.0, help="msg/s por canal (default 1.0)")
    parser.add_argument("--sites", type=int, default=MAX_SITES)
    parser.add_argument("--duration-s", type=float, default=60.0)
    parser.add_argument("--queue-url", default=None, help="modo sqs (o env TAKAB_QUEUE_URL)")
    parser.add_argument("--certs-dir", type=Path, default=None, help="modo iot: <dir>/<thing>/")
    parser.add_argument("--endpoint", default=None, help="modo iot (o env TAKAB_IOT_ENDPOINT)")
    parser.add_argument("--profile", default=None, help="perfil boto3 (modo sqs)")
    parser.add_argument(
        "--spool-dir",
        type=Path,
        default=None,
        metavar="RUTA",
        help="modo spool: la cola en disco del SOC local (.local-soc/cola/<thing>)",
    )
    parser.add_argument("--region", default="us-east-2")
    parser.add_argument("--with-health", action="store_true", help="heartbeat cada 30 s/gateway")
    parser.add_argument("--quake", default=None, metavar="SIMxxx", help="watch→evacuate_or_hold")
    parser.add_argument("--seed", type=int, default=None, help="RNG reproducible")
    # [T-7.11] La red de demostración no cabe en la convención fija (SIM001..020,
    # 5 por gateway): son tres sitios de tres tipos con un gateway cada uno.
    parser.add_argument(
        "--stations-file",
        type=Path,
        default=None,
        metavar="RUTA",
        help="JSON con la flota {tenant, stations:[{station,gateway,site}]} en vez de la fija",
    )
    parser.add_argument("--tenant", default=None, help=f"tenant a publicar (def. {TENANT_ID})")
    parser.add_argument(
        "--no-events",
        action="store_true",
        help="PROHÍBE publicar en takab/events (un LocalEvent simulado abre incidentes reales)",
    )
    # [T-7.15] La reproducción: las estaciones SIENTEN la onda de un sismo del
    # catálogo, cada una en su arribo.
    parser.add_argument(
        "--replay",
        type=Path,
        default=None,
        metavar="RUTA",
        help="JSON del sismo a reproducir (ver simulators/replay_19s.json)",
    )
    parser.add_argument(
        "--armar",
        default=None,
        metavar="URL",
        help=(
            "sondea el panel del gabinete REAL hasta ver `sasmex_active` y ancla ahí el t0 "
            "(p. ej. http://raspberry-cerebro.local:8080/api/status)"
        ),
    )
    parser.add_argument(
        "--armar-timeout-s",
        type=float,
        default=300.0,
        help="cuánto esperar el pulso del WR-1 antes de rendirse (def. 300)",
    )
    parser.add_argument(
        "--t0",
        default=None,
        choices=("now",),
        help="disparo MANUAL: empieza la reproducción ya, sin esperar al WR-1",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    # [T-7.11] La flota, de fichero o la fija de siempre.
    estaciones = tenant = None
    if args.stations_file is not None:
        tenant, estaciones = flota_de_fichero(args.stations_file)
    tenant = args.tenant or tenant or TENANT_ID

    # [T-7.15] La reproducción se arma ANTES de abrir conexiones: si las
    # coordenadas faltan o el sismo no cuadra, se falla sin haber publicado nada.
    replay = None
    if args.replay is not None:
        if estaciones is None:
            raise SystemExit(
                "--replay necesita --stations-file: la flota fija no lleva coordenadas"
            )
        replay = reproduccion_de_fichero(args.replay, estaciones)
        print(f"reproducción armada: {replay.catalog_key}")
        for a in sorted(replay.arribos.values(), key=lambda x: x.t_p_s):
            print(f"  {a.site_code:<14} P +{a.t_p_s:5.1f}s  S +{a.t_s_s:5.1f}s  {a.pga_g:.3f} g")

    # El ancla del t0. Con `--armar` se espera al pulso REAL del WR-1: sin eso, el
    # simulador y el gabinete cuentan desde instantes distintos y las ondas llegan
    # antes o después que la alerta que las anuncia.
    if args.armar is not None and args.t0 is None:
        print(f"esperando el pulso del WR-1 en {args.armar} …")
        if not esperar_pulso_wr1(args.armar, timeout_s=args.armar_timeout_s, leer=leer_panel):
            raise SystemExit(
                f"no llegó el pulso en {args.armar_timeout_s:.0f}s: nada que reproducir"
            )
        print("pulso visto: t0 anclado")

    sim = FleetSimulator(
        sites=args.sites,
        rate=args.rate,
        with_health=args.with_health,
        quake=args.quake,
        seed=args.seed,
        estaciones=estaciones,
        tenant=tenant,
        no_events=args.no_events,
        replay=replay,
    )
    connections: dict = {}
    if args.mode == "spool":
        if args.spool_dir is None:
            raise SystemExit("modo spool requiere --spool-dir (la cola que lee el bridge local)")
        send = make_spool_sender(args.spool_dir)
    elif args.mode == "sqs":
        queue_url = args.queue_url or os.environ.get("TAKAB_QUEUE_URL")
        if not queue_url:
            raise SystemExit("modo sqs requiere --queue-url o env TAKAB_QUEUE_URL")
        import boto3  # dep dev — import perezoso

        session = boto3.session.Session(profile_name=args.profile, region_name=args.region)
        send = make_sqs_sender(session.client("sqs"), queue_url)
    else:
        endpoint = args.endpoint or os.environ.get("TAKAB_IOT_ENDPOINT")
        if not endpoint or args.certs_dir is None:
            raise SystemExit("modo iot requiere --certs-dir y --endpoint (o TAKAB_IOT_ENDPOINT)")
        connections = open_iot_connections(sim.gateways, args.certs_dir, endpoint)
        send = make_iot_sender(connections)
    try:
        summary = run_plan(sim, duration_s=args.duration_s, send=send)
    finally:
        for conn in connections.values():
            conn.disconnect().result(timeout=10)
    print(
        f"modo={args.mode} enviados={summary.sent} errores={summary.errors} "
        f"duración={summary.duration_s:.1f}s tasa_efectiva={summary.rate_effective:.1f} msg/s"
    )
    return 0 if summary.errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
