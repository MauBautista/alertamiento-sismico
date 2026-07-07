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
import json
import math
import os
import random
import time
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

# Convención de flota dev (FIJA — ver seed db/seeds/dev_fleet.sql)
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
    ) -> None:
        if not 1 <= sites <= MAX_SITES:
            raise ValueError(f"sites debe estar en 1..{MAX_SITES} (flota sim fija)")
        if rate <= 0:
            raise ValueError("rate debe ser > 0")
        self.sites = sites
        self.rate = rate
        self.interval = 1.0 / rate
        self.with_health = with_health
        self.stations = [station_name(i) for i in range(1, sites + 1)]
        self.gateways = sorted({gateway_for(s) for s in self.stations})
        if quake is not None:
            _station_index(quake)  # valida convención
            if quake not in self.stations:
                raise ValueError(f"--quake {quake} fuera de los --sites={sites} activos")
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

    def _msg(self, topic: str, thing: str, payload: dict[str, Any]) -> OutMessage:
        validate_payload(topic, payload)
        return OutMessage(topic=topic, thing=thing, payload=payload)

    def _quake_event(self, tier: Tier, created_at: datetime) -> OutMessage:
        assert self.quake is not None
        event = LocalEvent(
            event_id=self._quake_event_id,  # MISMO event_id: prueba la escalada E2E (G3)
            tenant_id=TENANT_ID,
            site_id=site_for(self.quake),
            source=AlertSource.THRESHOLD,
            tier=tier,
            created_at=created_at,
        )
        return self._msg(EVENTS_TOPIC, gateway_for(self.quake), event.model_dump(mode="json"))

    def window_batch(self, window_index: int) -> list[OutMessage]:
        elapsed = window_index * self.interval
        window_start = self.t0 + timedelta(seconds=elapsed)
        batch: list[OutMessage] = []
        for station in self.stations:
            thing = gateway_for(station)
            for channel in CHANNELS:
                feature = self._feature(station, channel, window_start)
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
    parser.add_argument("--mode", choices=("sqs", "iot"), required=True)
    parser.add_argument("--rate", type=float, default=1.0, help="msg/s por canal (default 1.0)")
    parser.add_argument("--sites", type=int, default=MAX_SITES)
    parser.add_argument("--duration-s", type=float, default=60.0)
    parser.add_argument("--queue-url", default=None, help="modo sqs (o env TAKAB_QUEUE_URL)")
    parser.add_argument("--certs-dir", type=Path, default=None, help="modo iot: <dir>/<thing>/")
    parser.add_argument("--endpoint", default=None, help="modo iot (o env TAKAB_IOT_ENDPOINT)")
    parser.add_argument("--profile", default=None, help="perfil boto3 (modo sqs)")
    parser.add_argument("--region", default="us-east-2")
    parser.add_argument("--with-health", action="store_true", help="heartbeat cada 30 s/gateway")
    parser.add_argument("--quake", default=None, metavar="SIMxxx", help="watch→evacuate_or_hold")
    parser.add_argument("--seed", type=int, default=None, help="RNG reproducible")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    sim = FleetSimulator(
        sites=args.sites,
        rate=args.rate,
        with_health=args.with_health,
        quake=args.quake,
        seed=args.seed,
    )
    connections: dict = {}
    if args.mode == "sqs":
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
