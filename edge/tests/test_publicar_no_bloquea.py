"""[T-8.17 · A-078] Publicar a la nube no puede detener la detección.

`CloudConnector.publish()` escribía al spool y, a continuación, **drenaba la cola en
el hilo que publicaba**. Ese hilo es casi siempre el de SeedLink:
`ingest` → `_on_packet` → `_act_and_publish` → `cloud.publish`, y en `watch` o más la
telemetría de 1 Hz también publica desde ahí. El transporte real espera el PUBACK
con `future.result(timeout=10)`.

Con un enlace medio abierto —la conexión TCP sigue dada por buena hasta que el
keepalive de awscrt avisa del corte, unos 30 s— cada publicación bloqueaba hasta
10 s la ingesta y la evaluación de reglas, justo en un sismo. El test que existía
(`test_flush_of_backlog_does_not_block_concurrent_publish`) sólo cubría el caso en
que OTRO hilo ya estaba drenando.

Ahora `publish()` escribe al spool, durable como antes, y despierta al hilo
`cloud-reconnect`, que es el que espera al broker. Si ese hilo no existe —un
conector sin arrancar, sin transporte—, drena quien publica: si no, no lo haría
nadie. El reflejo SASMEX→sirena no pasa por aquí: vive en el dueño de los pines.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime

from simulators.mqtt import FakeMqttTransport
from simulators.quake import quake_packets
from simulators.rs4d import RS4DSimulator
from takab_edge.audit import ActuationCause, ActuationLedger
from takab_edge.cloud import CloudConnector
from takab_edge.config import EdgeSettings
from takab_edge.contracts import ActuatorAction, ActuatorChannel, AlertSource, Tier, TierDecision
from takab_edge.supervisor import AUDIT_TOPIC, EVENTS_TOPIC, EdgeSupervisor

_HILO_DE_LA_NUBE = "cloud-reconnect"


def _hasta(condicion: Callable[[], bool], timeout: float = 3.0) -> bool:
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.01)
    return condicion()


class _MedioAbierto(FakeMqttTransport):
    """El enlace que todavía se da por conectado y por el que no vuelve ningún PUBACK.

    Cada publicación espera `espera_s` y lanza, que es lo que hace
    `future.result(timeout=...)` en el transporte real. `suelta` devuelve los PUBACK.
    """

    def __init__(self, espera_s: float) -> None:
        super().__init__(online=True)
        self.espera_s = espera_s
        self.suelta = threading.Event()
        self.entro = threading.Event()
        self.hilos: list[str] = []

    def publish(self, topic: str, payload: bytes, qos: int = 1, retain: bool = False) -> bool:
        self.hilos.append(threading.current_thread().name)
        self.entro.set()
        if not self.suelta.wait(self.espera_s):
            raise TimeoutError("sin PUBACK del broker")
        return super().publish(topic, payload, qos, retain)


class _SeReanudaSola(FakeMqttTransport):
    """`connect()` no pasa, y la conexión vieja vuelve sola (`_on_resumed` de awscrt)."""

    def __init__(self) -> None:
        super().__init__(online=True)
        self.intentos = 0

    def connect(self) -> None:
        self.intentos += 1
        raise ConnectionError("la conexión nueva no pasa")

    def reanudar(self) -> None:
        self._connected = True


class _QuienPublica(FakeMqttTransport):
    """Un enlace sano que apunta desde qué hilo se le habla."""

    def __init__(self) -> None:
        super().__init__(online=True)
        self.hilos: list[str] = []

    def publish(self, topic: str, payload: bytes, qos: int = 1, retain: bool = False) -> bool:
        self.hilos.append(threading.current_thread().name)
        return super().publish(topic, payload, qos, retain)


def _evento(event_id: str = "EV-ENLACE") -> TierDecision:
    return TierDecision(event_id=event_id, tier=Tier.EVACUATE_OR_HOLD, source=AlertSource.SASMEX)


def _arrancado(settings, tmp_path, transporte) -> CloudConnector:  # noqa: ANN001
    cloud = CloudConnector(settings, transport=transporte, spool_dir=str(tmp_path / "spool"))
    cloud.start()
    assert _hasta(lambda: transporte.connected), "premisa: el hilo de la nube conectó"
    return cloud


# ---------------------------------------------------------------------------
# El conector
# ---------------------------------------------------------------------------


def test_publicar_no_espera_al_broker(settings, tmp_path) -> None:  # noqa: ANN001
    transporte = _MedioAbierto(espera_s=3.0)
    cloud = _arrancado(settings, tmp_path, transporte)
    try:
        t0 = time.monotonic()
        assert cloud.publish(EVENTS_TOPIC, _evento()) is True
        tardo = time.monotonic() - t0

        assert tardo < 0.5, f"publish() esperó {tardo:.1f} s al broker en el hilo del llamador"
        assert transporte.entro.wait(2.0), "nadie intentó mandarlo"
        assert set(transporte.hilos) == {_HILO_DE_LA_NUBE}, transporte.hilos
        # Y no se pierde: en cuanto el broker contesta, sale.
        transporte.suelta.set()
        assert _hasta(lambda: cloud.sent == 1 and cloud.queued == 0)
    finally:
        transporte.suelta.set()
        cloud.stop()


def test_lo_publicado_ya_es_durable_al_volver(settings, tmp_path) -> None:  # noqa: ANN001
    """Lo que no cambia: el spool se escribe ANTES de volver al llamador."""
    transporte = _MedioAbierto(espera_s=3.0)
    cloud = _arrancado(settings, tmp_path, transporte)
    try:
        cloud.publish(EVENTS_TOPIC, _evento())
        assert len(list((tmp_path / "spool").glob("*.json"))) == 1
    finally:
        transporte.suelta.set()
        cloud.stop()


def test_el_evento_sale_al_instante_aunque_el_drenado_duerma(settings, tmp_path) -> None:  # noqa: ANN001
    """El hilo de la nube duerme `cloud_backoff_s` entre drenados. Un evento nuevo
    lo despierta: la push CRISIS no puede esperar al siguiente turno."""
    lento = settings.model_copy(update={"cloud_backoff_s": 30.0})
    transporte = _QuienPublica()
    cloud = _arrancado(lento, tmp_path, transporte)
    try:
        time.sleep(0.1)  # el hilo ya drenó lo vacío y se durmió sus 30 s
        cloud.publish(EVENTS_TOPIC, _evento())
        assert _hasta(lambda: cloud.sent == 1, timeout=1.0), "el evento esperó al turno"
        assert set(transporte.hilos) == {_HILO_DE_LA_NUBE}
    finally:
        cloud.stop()


def test_sin_hilo_de_la_nube_drena_quien_publica(settings, tmp_path) -> None:  # noqa: ANN001
    """Un conector sin arrancar no tiene quien drene: si el llamador no lo hace,
    no lo haría nadie."""
    transporte = _QuienPublica()
    transporte.connect()
    cloud = CloudConnector(settings, transport=transporte, spool_dir=str(tmp_path))
    cloud.publish(EVENTS_TOPIC, _evento())
    assert cloud.sent == 1
    assert transporte.hilos == [threading.current_thread().name]


def test_en_reposo_el_hilo_de_la_nube_no_gira(settings, tmp_path) -> None:  # noqa: ANN001
    """Si el aviso no se baja, `wait()` vuelve al instante para siempre: el hilo
    de la nube se come la CPU que necesita el de SeedLink."""
    lento = settings.model_copy(update={"cloud_backoff_s": 30.0})
    transporte = _QuienPublica()
    cloud = _arrancado(lento, tmp_path, transporte)
    try:
        time.sleep(0.1)
        drenados: list[int] = []
        real = cloud.flush

        def contando() -> int:
            drenados.append(1)
            return real()

        cloud.flush = contando
        cloud.publish(EVENTS_TOPIC, _evento())
        assert _hasta(lambda: cloud.sent == 1, timeout=1.0)
        time.sleep(0.3)
        assert len(drenados) <= 2, f"{len(drenados)} drenados en 0.3 s de reposo"
    finally:
        cloud.stop()


def test_lo_que_llega_justo_despues_de_drenar_no_espera_turno(settings, tmp_path) -> None:  # noqa: ANN001
    """El aviso se baja ANTES de drenar. Bajado después, un evento que llega entre
    el último vistazo a la cola y el `clear()` se queda el turno entero (30 s)."""
    lento = settings.model_copy(update={"cloud_backoff_s": 30.0})
    transporte = _QuienPublica()
    cloud = _arrancado(lento, tmp_path, transporte)
    try:
        time.sleep(0.1)
        real = cloud.flush
        armado = threading.Event()

        def y_justo_despues_otro() -> int:
            n = real()
            if armado.is_set():
                armado.clear()
                cloud.publish(EVENTS_TOPIC, _evento("EV-JUSTO-DESPUES"))
            return n

        cloud.flush = y_justo_despues_otro
        armado.set()
        cloud.publish(EVENTS_TOPIC, _evento("EV-PRIMERO"))
        assert _hasta(lambda: cloud.sent == 2, timeout=1.0), "el segundo esperó el turno"
    finally:
        cloud.stop()


def test_parar_no_espera_el_turno_del_hilo(settings, tmp_path) -> None:  # noqa: ANN001
    lento = settings.model_copy(update={"cloud_backoff_s": 30.0})
    cloud = _arrancado(lento, tmp_path, _QuienPublica())
    time.sleep(0.1)
    hilo = cloud._reconnect_thread
    t0 = time.monotonic()
    cloud.stop()
    assert time.monotonic() - t0 < 1.0
    assert hilo is not None and not hilo.is_alive(), "el hilo de la nube sobrevivió a la parada"


def test_si_el_hilo_de_la_nube_murio_drena_quien_publica_y_lo_grita(
    settings,  # noqa: ANN001
    tmp_path,  # noqa: ANN001
    caplog,  # noqa: ANN001
) -> None:
    transporte = _QuienPublica()
    transporte.connect()
    cloud = CloudConnector(settings, transport=transporte, spool_dir=str(tmp_path))
    muerto = threading.Thread(target=lambda: None)
    muerto.start()
    muerto.join()
    cloud._reconnect_thread = muerto

    cloud.publish(EVENTS_TOPIC, _evento("EV-A"))
    cloud.publish(EVENTS_TOPIC, _evento("EV-B"))

    assert cloud.sent == 2, "sin hilo vivo, si no drena quien publica no drena nadie"
    gritos = [
        r
        for r in caplog.records
        if r.levelno == logging.CRITICAL and "hilo de la nube murió" in r.getMessage()
    ]
    assert len(gritos) == 1


def test_si_el_enlace_vuelve_solo_durante_el_backoff_el_evento_no_lo_espera(
    settings,  # noqa: ANN001
    tmp_path,  # noqa: ANN001
) -> None:
    """awscrt reanuda la conexión cortada mientras el hilo duerme el backoff de un
    `connect()` fallido (10 s aquí, hasta `cloud_backoff_max_s` en el gabinete).
    Antes drenaba quien publicaba; ahora el hilo tiene que enterarse."""
    lento = settings.model_copy(update={"cloud_backoff_s": 5.0})
    transporte = _SeReanudaSola()
    cloud = CloudConnector(lento, transport=transporte, spool_dir=str(tmp_path))
    cloud.start()
    try:
        assert _hasta(lambda: transporte.intentos >= 1), "premisa: el connect falló"
        transporte.reanudar()
        cloud.publish(EVENTS_TOPIC, _evento())
        assert _hasta(lambda: cloud.sent == 1, timeout=1.0), "el evento esperó el backoff"
    finally:
        cloud.stop()


def test_al_reconectar_los_eventos_salen_antes_que_la_bitacora(settings, tmp_path) -> None:  # noqa: ANN001
    """La bitácora sube fila a fila, un PUBACK cada una, desde `_fire_online`. Un
    evento encolado durante el corte no puede ir detrás: llega tarde al quórum."""
    rapido = settings.model_copy(update={"cloud_backoff_s": 0.05})
    transporte = FakeMqttTransport(online=False)
    cloud = CloudConnector(rapido, transport=transporte, spool_dir=str(tmp_path))
    cloud.on_online(lambda: cloud.publish_direct(AUDIT_TOPIC, _evento("FILA-DE-BITACORA")))
    cloud.publish(EVENTS_TOPIC, _evento("EV-DEL-CORTE"))
    cloud.start()
    try:
        transporte._online = True  # vuelve la WAN
        assert _hasta(lambda: len(transporte.published) >= 2)
        temas = [tema for tema, _ in transporte.published]
        assert temas.index(EVENTS_TOPIC) < temas.index(AUDIT_TOPIC), temas
    finally:
        cloud.stop()


def test_la_bitacora_no_hace_esperar_a_la_actuacion_mientras_sube(tmp_path) -> None:  # noqa: ANN001
    """El mismo síntoma por otra puerta. `drain()` corre en el hilo de la nube y
    espera un PUBACK por fila; `record()` está en el camino de la actuación
    (`execute_sequence` → `_record`). Compartían lock."""
    entro = threading.Event()
    suelta = threading.Event()

    def sink_lento(_fila: dict) -> bool:
        entro.set()
        suelta.wait(3.0)
        return True

    ajustes = EdgeSettings(dev_mode=True, cloud_spool_dir=str(tmp_path / "spool"))
    ledger = ActuationLedger(ajustes, sink=sink_lento)

    def anotar(event_id: str) -> None:
        ledger.record(
            cause=ActuationCause.SASMEX,
            actor="wr-1",
            channel=ActuatorChannel.GAS_VALVE,
            action=ActuatorAction.ACTIVATE,
            event_id=event_id,
        )

    anotar("evt-antes")
    drenando = threading.Thread(target=ledger.drain)
    drenando.start()
    try:
        assert entro.wait(2.0), "premisa: la subida está esperando a la nube"
        t0 = time.monotonic()
        anotar("evt-durante")
        tardo = time.monotonic() - t0
    finally:
        suelta.set()
        drenando.join(5.0)

    assert tardo < 0.5, f"anotar una actuación esperó {tardo:.1f} s a la nube"
    # Y la marca sólo cubre lo confirmado: lo anotado durante la subida sigue pendiente.
    assert ledger.state()["pending"] == 1


# ---------------------------------------------------------------------------
# El gabinete: un sismo con el enlace medio abierto
# ---------------------------------------------------------------------------


def test_un_sismo_con_el_enlace_medio_abierto_no_ciega_la_deteccion(settings) -> None:  # noqa: ANN001
    """La cadena exacta del hilo de SeedLink, con un EVACUATE que publica eventos,
    ACK y telemetría de 1 Hz. Ninguna de esas publicaciones puede esperar al
    broker desde el hilo que alimenta la detección."""
    transporte = _MedioAbierto(espera_s=2.0)
    sup = EdgeSupervisor(settings, seedlink_source=None, mqtt_transport=transporte)
    sup.start()
    try:
        assert _hasta(lambda: transporte.connected), "premisa: el gabinete conectó"
        sim = RS4DSimulator(station=sup.settings.station)
        t0 = time.monotonic()
        for paquete in quake_packets(sim, datetime.now(UTC)):
            sup.seedlink.feed(paquete)
        tardo = time.monotonic() - t0

        assert sup.rules.last_decision.tier is Tier.EVACUATE_OR_HOLD, "premisa: el sismo"
        assert transporte.entro.wait(2.0), "premisa: el gabinete intentó avisar a la nube"
        aqui = threading.current_thread().name
        assert aqui not in transporte.hilos, "el hilo de la detección esperó al broker"
        assert tardo < transporte.espera_s, (
            f"la ingesta del sismo tardó {tardo:.1f} s con el broker callado"
        )
    finally:
        transporte.suelta.set()
        sup.stop()
