"""seedlink — validación contra el Raspberry Shake REAL (gate #3).

Se SALTA si el Shake no es alcanzable (así CI, sin hardware, lo omite; en la LAN
del gabinete corre y mide de verdad). Host/estación overridables por entorno.

Hallazgos medidos contra `AM.R4F74` (ringserver OSOP): 100 sps, lag ~0.4 s; el
resume por número de secuencia reproduce el histórico del ring (cero-pérdida).

**El lag NO es un valor estable: oscila en diente de sierra**, y por eso aquí se mide
el MÍNIMO sobre una ventana en vez de una muestra suelta.

Medido el 2026-07-30 sobre una sesión real (una muestra por segundo): el valor salta
entre ~0.3 s y ~2.9 s continuamente. Una muestra tomada «tras 3 paquetes» cae donde
la suerte quiera — se observaron 0.44 s y 5.86 s en la MISMA máquina con minutos de
diferencia. El test asertaba `< 3.0` sobre esa muestra suelta, así que era flaky por
construcción; llevaba meses sin delatarse porque el Shake estaba fuera de la red y el
test se saltaba entero.

El mínimo, en cambio, es estable y significativo: es «cuán fresco llega a estar el
dato», que es lo que el gate #3 pregunta de verdad. Medido a la vez desde el gabinete
(0.32 s) y desde un laptop por WiFi (0.33 s) — prácticamente idéntico, así que la
afirmación no depende de dónde se corra.

El mismo aprendizaje ya estaba en `health/__init__.py` (T-1.65), que subió su umbral
de aviso a 15 s documentando que «con 2.0 s un stream SANO parpadearía DEGRADADO».
Este test se había quedado atrás.
"""

from __future__ import annotations

import os
import socket
import statistics
import threading
import time
from collections.abc import Callable

import pytest
from takab_edge.config import EdgeSettings
from takab_edge.contracts import WaveformPacket, utcnow
from takab_edge.seedlink import ObsPySeedLinkTransport, SeedLinkClient

SHAKE_HOST = os.environ.get("TAKAB_SHAKE_HOST", "192.168.3.92")
SHAKE_PORT = int(os.environ.get("TAKAB_SHAKE_PORT", "18000"))
SHAKE_STATION = os.environ.get("TAKAB_SHAKE_STATION", "R4F74")


def _reachable(host: str, port: int, timeout: float = 0.6) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _reachable(SHAKE_HOST, SHAKE_PORT),
    reason=f"Raspberry Shake no alcanzable en {SHAKE_HOST}:{SHAKE_PORT} (gate #3 hardware)",
)

#: Ventana de muestreo del lag. Con un paquete cada ~2 s deja ~10 mínimos locales del
#: diente de sierra: suficiente para que el mínimo sea reproducible sin alargar la suite.
_VENTANA_LAG_S = 20.0

#: Antigüedad que el dato LLEGA A TENER en su mejor momento. Histórico ~0.4 s; se deja
#: margen de ~7x. No confundir con `LAG_WARN_S` (15 s) de `health`: aquel juzga una
#: muestra suelta en producción y por eso tolera todo el diente de sierra; este juzga
#: el mínimo, que es mucho más exigente.
_LAG_MIN_MAX_S = 3.0


def _wait_until(pred: Callable[[], bool], timeout: float = 25.0) -> bool:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if pred():
            return True
        time.sleep(0.05)
    return pred()


def _transport(channels: list[str] | None = None) -> ObsPySeedLinkTransport:
    return ObsPySeedLinkTransport(
        SHAKE_HOST, SHAKE_PORT, "AM", SHAKE_STATION, "00", channels or ["EHZ"]
    )


def _run_until_first(transport: ObsPySeedLinkTransport) -> WaveformPacket:
    """Corre el transporte hasta el primer paquete y para (síncrono para el test)."""
    got: list[WaveformPacket] = []
    stop = threading.Event()

    def emit(packet: WaveformPacket) -> None:
        got.append(packet)
        stop.set()

    thread = threading.Thread(target=transport.run, args=(emit, stop), daemon=True)
    thread.start()
    assert _wait_until(lambda: bool(got)), "el Shake no entregó ningún paquete"
    stop.set()
    thread.join(timeout=5)
    return got[0]


def test_real_shake_streams_100sps():
    """El Shake entrega a 100 sps y el stream se sostiene sin reconectar."""
    client = SeedLinkClient(EdgeSettings(), transport=_transport())
    got: list[WaveformPacket] = []
    client.on_packet(got.append)
    client.start()
    try:
        assert _wait_until(lambda: len(got) >= 3), "el Shake no entregó 3 paquetes"
    finally:
        client.stop()
    assert all(p.sample_rate == 100.0 for p in got), "sample rate del Shake ≠ 100 sps"
    assert client.reconnects == 0


def test_lag_del_shake_llega_a_ser_bajo(capsys):
    """Gate #3: el dato del sismógrafo LLEGA A TENER <3 s de antigüedad.

    Se juzga el MÍNIMO de una ventana, no una muestra suelta: el lag oscila en diente
    de sierra (~0.3-2.9 s medidos) y una muestra al azar hace el test flaky — asertar
    sobre ella daba 0.44 s o 5.86 s en la misma máquina según el momento.
    """
    client = SeedLinkClient(EdgeSettings(), transport=_transport())
    client.on_packet(lambda _p: None)
    client.start()
    muestras: list[float] = []
    try:
        fin = time.perf_counter() + _VENTANA_LAG_S
        while time.perf_counter() < fin:
            time.sleep(0.5)
            if client.last_lag_s is not None:
                muestras.append(client.last_lag_s)
    finally:
        client.stop()

    assert muestras, "el Shake no entregó ni una medición de lag"
    minimo = min(muestras)
    # Se imprimen las tres: si esto falla algún día, el reporte ya trae la forma de la
    # distribución y no hay que reproducirlo a ciegas para saber qué pasó.
    with capsys.disabled():
        print(
            f"\n  lag en {_VENTANA_LAG_S:.0f}s: min={minimo:.2f}s "
            f"mediana={statistics.median(muestras):.2f}s max={max(muestras):.2f}s"
        )
    assert minimo < _LAG_MIN_MAX_S, (
        f"el dato nunca bajó de {minimo:.2f}s en {_VENTANA_LAG_S:.0f}s "
        f"(histórico ~0.4s en R4F74): el stream llega tarde, no es ruido del muestreo"
    )
    assert client.reconnects == 0


def test_real_shake_backfills_via_seqnum_resume():
    # Cero-pérdida: reanudar desde un seqnum pasado reproduce el histórico del ring.
    transport = _transport()
    first = _run_until_first(transport)
    resume_seq = transport._resume_seq
    assert resume_seq >= 0
    time.sleep(8)  # deja avanzar el tiempo real ~8 s

    transport._resume_seq = resume_seq  # forzar reanudación desde el pasado
    resumed = _run_until_first(transport)
    # `age_s > 6` prueba el backfill: el paquete reanudado es de ~hace 8 s (no del
    # presente). El resume por seqnum entrega el paquete siguiente al seqnum pedido
    # (unos segundos tras `first`), así que no se afina más el offset exacto.
    age_s = (utcnow() - resumed.starttime).total_seconds()
    assert age_s > 6, f"el resume por seqnum no hizo backfill (age={age_s:.1f}s)"
    assert resumed.starttime >= first.starttime  # reanuda desde ≥ el punto pedido, no antes
