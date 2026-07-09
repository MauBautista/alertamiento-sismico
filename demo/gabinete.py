"""Un gabinete de la demo: el ``EdgeSupervisor`` REAL en su propio proceso.

No hay atajo alguno en la ruta de protección: `gpio` (reflejo SASMEX in-process),
`rules` (decisión determinista de tier) y `actuators` arrancan como módulos críticos
fail-fast, exactamente como bajo systemd en el Pi. Lo único sustituido es el
transporte a la nube (``SpoolMqttTransport`` en vez de mTLS a IoT Core).

Cada gabinete corre en un PROCESO propio porque `gpiozero.Device.pin_factory` es un
singleton global y los pines BCM del mapa de producción son los mismos para todos:
tres supervisores en un proceso se pisarían los relés entre sí.

Se expone una API de control mínima (localhost) para que el guion de la demo inyecte
estímulos y lea evidencia. **No es código de producto**: el `local_api` del gabinete
real sólo ofrece silencio, self-test y reset, y jamás una inyección de SASMEX.

    python demo/gabinete.py --thing gw-sim-0001 --site site-sim-001 \
        --station SIM001 --spool /tmp/demo/gw-sim-0001 --control-port 9101
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "edge"))

from demo.spool import SpoolMqttTransport  # noqa: E402
from simulators.quake import quake_packets  # noqa: E402
from simulators.rs4d import RS4DSimulator  # noqa: E402
from simulators.wr1 import WR1Simulator  # noqa: E402
from takab_edge.config import EdgeSettings  # noqa: E402
from takab_edge.contracts import ActuatorChannel  # noqa: E402
from takab_edge.supervisor import EdgeSupervisor  # noqa: E402

log = logging.getLogger("demo.gabinete")

#: Los 5 canales que la secuencia de `evacuate_or_hold` debe dejar activados.
CHANNELS = (
    ActuatorChannel.SIREN,
    ActuatorChannel.STROBE,
    ActuatorChannel.GAS_VALVE,
    ActuatorChannel.ELEVATOR,
    ActuatorChannel.DOOR_RETAINER,
)


class Gabinete:
    """Supervisor real + palancas de estímulo para la demo."""

    def __init__(self, args: argparse.Namespace) -> None:
        buffer_root = Path(args.workdir) / "buffer"
        buffer_root.mkdir(parents=True, exist_ok=True)

        self.settings = EdgeSettings(
            dev_mode=True,  # relés mock (no hay hardware; gate #3 abierto)
            tenant_id=args.tenant,
            site_id=args.site,
            gateway_id=args.thing,  # = gateways.serial en el registro
            station=args.station,  # = sensors.serial
            iot_thing=args.thing,  # = meta_principal (identidad del certificado)
            local_api_port=args.dashboard_port,
            cloud_spool_dir=str(Path(args.workdir) / "spool_durable"),
            buffer={"root": str(buffer_root)},
        )
        # Se archivan los LocalEvent publicados para poder re-entregar el mensaje
        # byte-idéntico en C3 y probar la idempotencia del pipeline (ON CONFLICT).
        self.transport = SpoolMqttTransport(
            args.spool,
            thing=args.thing,
            archive_dir=str(Path(args.workdir) / "sent_events"),
            archive_topics=("takab/events",),
        )
        # seedlink_source=None ⇒ ningún ruido de fondo: el sismo entra sólo cuando
        # la demo lo inyecta, y la evidencia es determinista.
        self.sup = EdgeSupervisor(
            self.settings, seedlink_source=None, mqtt_transport=self.transport
        )
        self.sup.build().start()
        self.wr1 = WR1Simulator(self.sup.gpio)
        self._rs4d = RS4DSimulator(station=args.station, sample_rate=self.settings.sample_rate)

    # --- estímulos ---------------------------------------------------------
    def sasmex(self) -> None:
        """Cierre del contacto seco del WR-1 (la MISMA ruta que `when_pressed`)."""
        self.wr1.alert()

    def sasmex_clear(self) -> None:
        self.wr1.clear()

    def quake(self) -> int:
        """Sismo instrumental: ruido → onda P (cautela) → onda S (disparo)."""
        packets = quake_packets(self._rs4d, datetime.now(UTC).replace(tzinfo=UTC))
        for packet in packets:
            self.sup.seedlink.feed(packet)
        return len(packets)

    def wan(self, up: bool) -> None:
        if up:
            self.transport.go_online()
        else:
            self.transport.go_offline()
        self.sup.cloud.set_online(up)

    # --- evidencia ---------------------------------------------------------
    def status(self) -> dict:
        gpio, cloud = self.sup.gpio, self.sup.cloud
        return {
            "thing": self.settings.thing_name,
            "site": self.settings.site_id,
            "sasmex_active": gpio.sasmex_active,
            "siren_sounding": gpio.siren_sounding,
            "reflex_latency_s": gpio.last_reflex_latency_s,
            "relays": {c.value: gpio.is_activated(c) for c in CHANNELS},
            "cloud": {"online": cloud.online, "queued": cloud.queued, "sent": cloud.sent},
        }

    def stop(self) -> None:
        self.sup.stop()


def _handler(gab: Gabinete) -> type[BaseHTTPRequestHandler]:
    actions = {
        "/sasmex": gab.sasmex,
        "/sasmex/clear": gab.sasmex_clear,
        "/quake": gab.quake,
        "/wan/off": lambda: gab.wan(False),
        "/wan/on": lambda: gab.wan(True),
    }

    class Control(BaseHTTPRequestHandler):
        def _send(self, code: int, body: dict) -> None:
            raw = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802 — API de BaseHTTPRequestHandler
            if self.path == "/status":
                self._send(200, gab.status())
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            action = actions.get(self.path)
            if action is None:
                self._send(404, {"error": "not found"})
                return
            result = action()
            self._send(200, {"ok": True, "result": result, **gab.status()})

        def log_message(self, *args: object) -> None:
            pass  # no ensuciar la salida de la demo

    return Control


def main() -> None:
    parser = argparse.ArgumentParser(description="Un gabinete de la demo de Fase 1")
    parser.add_argument("--thing", required=True, help="thing IoT = serial del gateway")
    parser.add_argument("--site", required=True, help="code del sitio (sites.code)")
    parser.add_argument("--station", required=True, help="serial del sensor (sensors.serial)")
    parser.add_argument("--tenant", default="tenant-dev")
    parser.add_argument("--spool", required=True, help="directorio ≡ cola de IoT Core")
    parser.add_argument("--workdir", required=True, help="buffer + spool durable del gabinete")
    parser.add_argument("--control-port", type=int, required=True)
    parser.add_argument("--dashboard-port", type=int, default=0, help="0 = puerto efímero")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(name)s — %(message)s")
    gab = Gabinete(args)
    server = ThreadingHTTPServer(("127.0.0.1", args.control_port), _handler(gab))

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(json.dumps({"ready": True, "thing": args.thing, "port": args.control_port}), flush=True)
    try:
        stop.wait()
    finally:
        server.shutdown()
        gab.stop()


if __name__ == "__main__":
    main()
