"""Simulador del enlace LoRa (T-2.33) — módem + gabinetes secundarios ESP32 falsos.

``SimulatedLoraTransport`` implementa el Protocol ``LoraTransport`` en proceso
(patrón ``FakeMqttTransport``/``WR1Simulator``): lo que el ``LoraLink`` envía se
entrega a los ``FakeSecondaryCabinet`` registrados, que responden ACK y emiten
heartbeats BAJO DEMANDA (los tests controlan el tiempo; cero hilos, cero
aleatoriedad — la pérdida de paquetes es determinista con ``drop_next``).
"""

from __future__ import annotations

from collections.abc import Callable

from takab_edge.lora import frame as fr


class FakeSecondaryCabinet:
    """ESP32 simulado: verifica con SU clave derivada, ACKea y late a demanda."""

    def __init__(self, site_key: bytes, cabinet_id: int, *, battery_mv: int = 3900) -> None:
        self.cabinet_id = cabinet_id
        self.key = fr.derive_key(site_key, cabinet_id)
        self.battery_mv = battery_mv
        self.session = 0xA0000000 + cabinet_id  # "boot" determinista
        self.seq = 0
        self.alarm_active = False
        self.flags_seen = 0
        # [T-5.25] El ESTADO ELÉCTRICO de sus dos relés, que es lo único que se
        # puede medir de pie delante del nodo. `flags_seen` guarda la ÚLTIMA
        # ORDEN, que no es lo mismo: un test posterior la pisa, y una orden que
        # llegó no dice qué quedó encendido. La distinción importa porque el
        # fallo que arregla T-5.25 —el edificio sigue sonando— solo se ve aquí.
        #
        # Esto es además la especificación EJECUTABLE del firmware ESP32 futuro:
        # las cuatro reglas de abajo son las que tendrá que cumplir en C.
        self.siren_on = False
        self.strobe_on = False
        #: Destellos de verificación (TEST): no tocan los relés enclavados.
        self.test_pulses = 0
        self.received: list[fr.LoraFrame] = []
        self.guard = fr.ReplayGuard()

    def handle(self, raw: bytes) -> bytes | None:
        """Procesa una trama downlink; devuelve el ACK uplink (o None)."""
        try:
            frame = fr.decode(raw, self.key)
        except fr.FrameError:
            return None  # no era para mí (clave de otro) o forja
        if frame.cabinet_id != self.cabinet_id or not self.guard.accept(frame):
            return None
        self.received.append(frame)
        if frame.msg_type == fr.ALARM_ACT:
            # «ALARM_ACT ENCIENDE» (LORA-SECUNDARIOS §2): suma, no pisa. Por eso
            # un silencio NO puede viajar como un ALARM_ACT sin el bit de sirena.
            self.alarm_active = True
            self.flags_seen = frame.flags
            self.siren_on = self.siren_on or bool(frame.flags & fr.FLAG_SIREN)
            self.strobe_on = self.strobe_on or bool(frame.flags & fr.FLAG_STROBE)
        elif frame.msg_type == fr.ALARM_CLEAR:
            self.alarm_active = False
            self.siren_on = False
            self.strobe_on = False
        elif frame.msg_type == fr.SILENCE:
            # [T-5.25] Cae lo AUDIBLE y solo lo audible: el estrobo sigue y la
            # alerta sigue viva. Es el espejo de `gpio.silence_audibles()`.
            self.siren_on = False
            self.strobe_on = self.strobe_on or bool(frame.flags & fr.FLAG_STROBE)
            self.flags_seen = frame.flags
        elif frame.msg_type == fr.TEST:
            # Destella el estrobo SIN sirena y no cambia `alarm_active` — ni los
            # relés enclavados: un test durante una alarma no puede apagar nada.
            self.flags_seen = frame.flags
            self.test_pulses += 1
        self.seq += 1
        return fr.LoraFrame(
            msg_type=fr.ACK,
            cabinet_id=self.cabinet_id,
            session=self.session,
            seq=self.seq,
            battery_mv=self.battery_mv,
            arg=frame.seq,
        ).encode(self.key)

    def heartbeat(self) -> bytes:
        """Uplink de vida (los tests lo inyectan cuando su guion lo pide)."""
        self.seq += 1
        flags = fr.FLAG_ALARM_ACTIVE if self.alarm_active else 0
        return fr.LoraFrame(
            msg_type=fr.HEARTBEAT,
            cabinet_id=self.cabinet_id,
            session=self.session,
            seq=self.seq,
            flags=flags,
            battery_mv=self.battery_mv,
        ).encode(self.key)


class SimulatedLoraTransport:
    """Radio en proceso: entrega síncrona, pérdida determinista y RSSI fijo."""

    def __init__(self, *, rssi_dbm: float = -92.0, snr_db: float = 7.5) -> None:
        self.cabinets: list[FakeSecondaryCabinet] = []
        self.sent: list[bytes] = []
        self.rssi_dbm = rssi_dbm
        self.snr_db = snr_db
        self.opened = False
        self._drop_next = 0
        # [T-5.25] Nodos que NO oyen nada (fuera de alcance, antena rota,
        # jamming local). `drop_next` pierde las próximas N tramas de todos; esto
        # pierde TODAS las de unos pocos, que es el caso que hace falta para
        # medir «silenciar cuatro de cinco no es silenciar».
        self.deaf: set[int] = set()
        self._on_receive: Callable[[bytes, float | None, float | None], None] | None = None

    # --- Protocol LoraTransport ---
    def open(self) -> None:
        self.opened = True

    def close(self) -> None:
        self.opened = False

    def set_on_receive(self, callback) -> None:
        self._on_receive = callback

    def send(self, raw: bytes) -> None:
        self.sent.append(raw)
        if self._drop_next > 0:
            self._drop_next -= 1  # el aire se comió la trama (determinista)
            return
        destino = int.from_bytes(raw[2:4], "big")  # el downlink es unicast
        if destino in self.deaf:
            return
        for cabinet in self.cabinets:
            ack = cabinet.handle(raw)
            if ack is not None:
                self.deliver(ack)

    # --- helpers de test ---
    def attach(self, cabinet: FakeSecondaryCabinet) -> FakeSecondaryCabinet:
        self.cabinets.append(cabinet)
        return cabinet

    def drop_next(self, n: int) -> None:
        """Las próximas ``n`` tramas downlink se pierden en el aire."""
        self._drop_next = n

    def deliver(self, raw: bytes) -> None:
        """Entrega un uplink al LoraLink (ACK o heartbeat)."""
        if self._on_receive is not None:
            self._on_receive(raw, self.rssi_dbm, self.snr_db)
