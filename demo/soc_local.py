"""SOC local INTERACTIVO: un gabinete real simulado + bridge + DB local.

A diferencia de `demo/run.py` (el guion del hito: 3 gabinetes, criterios
scripted, TRUNCATE entre escenas), esto levanta UN gabinete con la identidad
REAL de la flota (gw-dev-0001 / site-dev / R4F74) y deja el pipeline corriendo
para que la consola web se pueda RECORRER a mano antes de desplegar:

    gabinete (EdgeSupervisor real, panel LAN en :8080)
        └─ spool (≡ IoT Core+SQS, demo/spool.py)
            └─ Bridge (consumer + handlers REALES → Postgres local)

La API, el worker de incidentes y el web dev server corren aparte
(`make soc-local` orquesta todo). Estímulos con la MISMA ruta que el hito:

    curl -X POST http://127.0.0.1:9100/quake         # sismo instrumental
    curl -X POST http://127.0.0.1:9100/sasmex        # cierre del contacto WR-1
    curl -X POST http://127.0.0.1:9100/sasmex/clear  # apertura del contacto
    curl -X POST http://127.0.0.1:9100/wan/off       # corte de WAN (y /wan/on)

NO toca datos existentes (sin reset_state): lo que generes se queda en la DB
local, como pasaría en producción.
"""

from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import threading
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from demo.bridge import Bridge  # noqa: E402

DSN = "postgresql://takab:takab_dev@127.0.0.1:5433/takab"
EDGE_PY = _ROOT / "edge" / ".venv" / "bin" / "python"

# Identidad REAL de la flota (db/seeds/prod_fleet.sql): la consola local se ve
# igual que la desplegada — "Sitio Dev Puebla", no un sitio sim.
THING = "gw-dev-0001"
SITE = "site-dev"
STATION = "R4F74"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-port", type=int, default=9100)
    parser.add_argument("--dashboard-port", type=int, default=8080)
    parser.add_argument(
        "--workdir", default=str(_ROOT / ".local-soc"), help="spool/buffer del gabinete"
    )
    args = parser.parse_args()

    work = Path(args.workdir)
    (work / "cola" / THING).mkdir(parents=True, exist_ok=True)

    gabinete = subprocess.Popen(  # noqa: S603
        [
            str(EDGE_PY),
            str(_ROOT / "demo" / "gabinete.py"),
            "--thing",
            THING,
            "--site",
            SITE,
            "--station",
            STATION,
            "--spool",
            str(work / "cola" / THING),
            "--workdir",
            str(work / "gab" / THING),
            "--control-port",
            str(args.control_port),
            "--dashboard-port",
            str(args.dashboard_port),
        ],
        cwd=str(_ROOT / "edge"),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    ready = gabinete.stdout.readline() if gabinete.stdout else ""
    if '"ready": true' not in ready:
        print(f"el gabinete no arrancó: {ready!r}", file=sys.stderr)
        return 1

    bridge = Bridge([work / "cola" / THING], work / "dlq", DSN)
    bridge.start()

    print("SOC local interactivo listo:")
    print(f"  · Panel LAN del gabinete (T-1.53):  http://127.0.0.1:{args.dashboard_port}")
    print("  · Consola SOC (web dev server):     http://localhost:5173")
    print(f"  · Estímulos:  curl -X POST http://127.0.0.1:{args.control_port}/quake")
    print(f"                curl -X POST http://127.0.0.1:{args.control_port}/sasmex")
    print(f"                curl -X POST http://127.0.0.1:{args.control_port}/sasmex/clear")
    print(f"                curl -X POST http://127.0.0.1:{args.control_port}/wan/off | /wan/on")
    print("  Ctrl+C para apagar el gabinete y el bridge.", flush=True)

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    try:
        stop.wait()
    finally:
        bridge.stop()
        gabinete.terminate()
        gabinete.wait(timeout=5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
