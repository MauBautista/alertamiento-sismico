"""lora — enlace a gabinetes secundarios (ESP32 + sirena/estrobo) vía LoRa (T-2.33).

Los secundarios son ESPEJOS de la protección local: reciben la orden de alarma
cuando el gabinete principal ACTÚA (SASMEX o comando firmado de quórum), y
reportan su salud por heartbeat. JAMÁS gatean nada: este módulo es no-crítico,
no depende de gpio y ``propagate()`` es fire-and-forget (regla de oro 4: el
camino GPIO ni se entera).

Transporte: el radio real es un módem ESP32+LoRa colgado del USB del Pi
hablando NDJSON a 115200 (``{"t":"tx","p":"<hex>"}`` / ``{"t":"rx","p":"<hex>",
"rssi":-97,"snr":7.5}``). La seguridad vive en la TRAMA (``lora.frame``: HMAC
truncado por gabinete + anti-replay por sesión), no en el bridge.

Disciplina de aire: una orden se repite hasta ACK con espaciado
``alarm_retry_s`` y tope ``alarm_retry_max``; los heartbeats los emiten los
secundarios (ALOHA con jitter, lado firmware). Un heartbeat ausente más de
``timeout_factor × heartbeat_s`` ⇒ ENLACE PERDIDO — transición logueada UNA vez
(regla de oro 10); el jamming se hace VISIBLE, no se disimula (regla 7).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import TYPE_CHECKING, Protocol

from takab_edge.contracts import SecondaryCabinetState, utcnow
from takab_edge.lora import frame as fr
from takab_edge.module import EdgeModule

if TYPE_CHECKING:
    from collections.abc import Callable

    from takab_edge.config import EdgeSettings

log = logging.getLogger("takab_edge.lora")


class LoraTransport(Protocol):
    """Contrato del módem (real por serial o simulado en tests)."""

    def open(self) -> None: ...

    def close(self) -> None: ...

    def send(self, raw: bytes) -> None: ...

    def set_on_receive(self, callback: Callable[[bytes, float | None, float | None], None]) -> None:
        """``callback(trama, rssi_dbm, snr_db)`` — RSSI/SNR los mide el módem."""
        ...


class SerialLoraTransport:
    """Módem ESP32 por USB-serial, NDJSON por líneas (import perezoso de pyserial).

    ``pyserial`` vive en el extra ``lora`` (como ``hardware``/``aws``): el core
    importa sin él; abrir el puerto sin la dependencia falla con mensaje claro.
    """

    def __init__(self, port: str, baud: int) -> None:
        self._port = port
        self._baud = baud
        self._serial = None
        self._on_receive: Callable[[bytes, float | None, float | None], None] | None = None
        self._reader: threading.Thread | None = None
        self._stop = threading.Event()

    def set_on_receive(self, callback) -> None:
        self._on_receive = callback

    def open(self) -> None:
        try:
            import serial  # noqa: PLC0415 — extra [lora], perezoso a propósito
        except ImportError as exc:  # pragma: no cover — entorno sin el extra
            raise RuntimeError("radio LoRa exige el extra 'lora' (pyserial)") from exc
        self._serial = serial.Serial(self._port, self._baud, timeout=1.0)
        self._stop.clear()
        self._reader = threading.Thread(target=self._read_loop, name="lora-serial", daemon=True)
        self._reader.start()

    def close(self) -> None:
        self._stop.set()
        if self._reader is not None:
            self._reader.join(timeout=3.0)
            self._reader = None
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    def send(self, raw: bytes) -> None:
        if self._serial is None:
            return
        line = json.dumps({"t": "tx", "p": raw.hex()}) + "\n"
        self._serial.write(line.encode())

    def _read_loop(self) -> None:  # pragma: no cover — requiere puerto real
        while not self._stop.is_set() and self._serial is not None:
            try:
                line = self._serial.readline()
            except Exception:  # noqa: BLE001 — el puerto puede desaparecer (USB)
                log.warning("lora: lectura serial falló; reintento", exc_info=True)
                self._stop.wait(1.0)
                continue
            if not line:
                continue
            try:
                msg = json.loads(line)
                if msg.get("t") == "rx" and self._on_receive is not None:
                    self._on_receive(bytes.fromhex(msg["p"]), msg.get("rssi"), msg.get("snr"))
            except (ValueError, KeyError, TypeError):
                log.debug("lora: línea NDJSON inválida del módem (ignorada)")


class LoraLink(EdgeModule):
    """Registro de secundarios + propagación de alarma con repeat-until-ack."""

    name = "lora"
    critical = False
    depends_on = ()

    def __init__(self, settings: EdgeSettings, transport: LoraTransport, site_key: bytes) -> None:
        super().__init__()
        self._cfg = settings.lora
        self._transport = transport
        self._session = int.from_bytes(os.urandom(4), "big")  # anti-replay por boot
        self._seq = 0
        self._guard = fr.ReplayGuard()
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop_evt = threading.Event()
        self._sender: threading.Thread | None = None
        self._keys = {c.id: fr.derive_key(site_key, c.id) for c in self._cfg.secondaries}
        self._reg: dict[int, dict] = {
            c.id: {
                "id": c.id,
                "name": c.name or f"SEC-{c.id}",
                "zone": c.zone,
                "last_seen": None,
                "battery_mv": None,
                "rssi_dbm": None,
                "snr_db": None,
                "alarm_active": False,
                "link": "never",  # never | online | offline
                # orden pendiente: {type, flags, attempts, next_at, acked, sent_seq}
                "pending": None,
            }
            for c in self._cfg.secondaries
        }

    # ------------------------------------------------------------ API pública

    def propagate(self, action: str, *, siren: bool = False, strobe: bool = False) -> None:
        """Encola la orden a TODOS los secundarios y regresa YA (jamás bloquea).

        ``action``: ``activate`` | ``clear`` | ``test`` | ``silence``. El hilo
        emisor repite cada orden hasta su ACK (tope ``alarm_retry_max``); el
        estado de ack por secundario queda visible en ``snapshot()``.
        """
        kind = {
            "activate": fr.ALARM_ACT,
            "clear": fr.ALARM_CLEAR,
            "test": fr.TEST,
            "silence": fr.SILENCE,
        }.get(action)
        if kind is None:
            raise ValueError(f"acción LoRa desconocida: {action}")
        flags = (fr.FLAG_SIREN if siren else 0) | (fr.FLAG_STROBE if strobe else 0)
        if kind is fr.ALARM_ACT:
            flags |= fr.FLAG_ALARM_ACTIVE
        if kind is fr.TEST:
            flags |= fr.FLAG_TEST
        if kind is fr.SILENCE:
            # [T-5.25] El silencio lleva su estado completo, no una diferencia:
            # la alerta SIGUE viva y el estrobo SIGUE encendido — lo único que
            # cae es lo audible. Los flags se fijan aquí y se ignora lo que pida
            # el llamante: un `silence(siren=True)` no es una orden rara, es un
            # error, y encenderla sería exactamente lo contrario de silenciar.
            flags = fr.FLAG_ALARM_ACTIVE | fr.FLAG_STROBE
        now = _mono()
        with self._lock:
            for entry in self._reg.values():
                pending = entry["pending"]
                merged = flags
                if kind is fr.ALARM_ACT and pending is not None and pending["type"] is fr.ALARM_ACT:
                    # Los comandos de red llegan POR CANAL (sirena y estrobo por
                    # separado): una nueva activación SUMA flags, no los pisa.
                    merged |= pending["flags"]
                entry["pending"] = {
                    "type": kind,
                    "flags": merged,
                    "attempts": 0,
                    "next_at": now,
                    "acked": False,
                    "sent_seq": None,
                }
        self._wake.set()

    def snapshot(self) -> dict:
        """Estado para el panel (vía ``/api/status``, sección ``lora``)."""
        timeout_s = self._cfg.heartbeat_s * self._cfg.heartbeat_timeout_factor
        now = utcnow()
        out = []
        with self._lock:
            for entry in self._reg.values():
                last_seen = entry["last_seen"]
                age_s = (now - last_seen).total_seconds() if last_seen else None
                pending = entry["pending"]
                state = SecondaryCabinetState(
                    id=entry["id"],
                    name=entry["name"],
                    zone=entry["zone"],
                    age_s=age_s,
                    battery_mv=entry["battery_mv"],
                    rssi_dbm=entry["rssi_dbm"],
                    snr_db=entry["snr_db"],
                    alarm_active=entry["alarm_active"],
                    link=entry["link"] if (age_s is None or age_s <= timeout_s) else "offline",
                    acked=None if pending is None else bool(pending["acked"]),
                    # [T-5.25] QUÉ orden es la que espera (o tiene) su ACK.
                    # «SIN ACK» a secas no distingue un silencio que no llegó
                    # —el nodo SIGUE SONANDO— de un test que se perdió, y
                    # silenciar cuatro de cinco no es silenciar.
                    pending=None if pending is None else _kind_name(pending["type"]),
                )
                out.append(state.model_dump(mode="json"))
        return {"enabled": True, "heartbeat_s": self._cfg.heartbeat_s, "secondaries": out}

    # ---------------------------------------------------------- ciclo de vida

    def _on_start(self) -> None:
        self._transport.set_on_receive(self._on_frame)
        self._transport.open()
        self._stop_evt.clear()
        self._sender = threading.Thread(target=self._sender_loop, name="lora-sender", daemon=True)
        self._sender.start()

    def _on_stop(self) -> None:
        self._stop_evt.set()
        self._wake.set()
        if self._sender is not None:
            self._sender.join(timeout=3.0)
            self._sender = None
        self._transport.close()

    # ------------------------------------------------------------- recepción

    def _on_frame(self, raw: bytes, rssi: float | None, snr: float | None) -> None:
        """Callback del módem. Verifica firma POR GABINETE + anti-replay."""
        try:
            if len(raw) != fr.FRAME_LEN:
                return
            cabinet_id = int.from_bytes(raw[2:4], "big")  # solo para elegir la clave
            key = self._keys.get(cabinet_id)
            if key is None:
                return  # gabinete no provisionado: ni se intenta verificar
            frame = fr.decode(raw, key)
            if not self._guard.accept(frame):
                return
        except fr.FrameError:
            return  # forja/alteración: silencio (la firma es la autoridad)
        with self._lock:
            entry = self._reg.get(frame.cabinet_id)
            if entry is None:
                return
            entry["last_seen"] = utcnow()
            entry["rssi_dbm"] = rssi
            entry["snr_db"] = snr
            if frame.msg_type is not fr.ACK and frame.battery_mv:
                entry["battery_mv"] = frame.battery_mv
            if frame.msg_type == fr.HEARTBEAT:
                entry["alarm_active"] = bool(frame.flags & fr.FLAG_ALARM_ACTIVE)
            if entry["link"] != "online":
                # Transición (regla 10): una línea al recuperar/ganar enlace.
                log.warning("lora: secundario %s EN LÍNEA", entry["name"])
                entry["link"] = "online"
            pending = entry["pending"]
            if (
                frame.msg_type == fr.ACK
                and pending is not None
                and pending["sent_seq"] is not None
                and frame.arg == pending["sent_seq"]
                and not pending["acked"]
            ):
                pending["acked"] = True
                if pending["type"] in (fr.ALARM_ACT, fr.ALARM_CLEAR):
                    entry["alarm_active"] = pending["type"] == fr.ALARM_ACT
                log.info("lora: %s ACK de %s", entry["name"], _kind_name(pending["type"]))

    # ---------------------------------------------------------------- emisor

    def _sender_loop(self) -> None:
        while not self._stop_evt.is_set():
            self._pump()
            self._check_timeouts()
            self._wake.wait(timeout=min(self._cfg.alarm_retry_s, 1.0) / 2)
            self._wake.clear()

    def _pump(self) -> None:
        now = _mono()
        to_send: list[tuple[int, bytes]] = []
        with self._lock:
            for cab_id, entry in self._reg.items():
                pending = entry["pending"]
                if pending is None or pending["acked"]:
                    continue
                if pending["attempts"] >= self._cfg.alarm_retry_max:
                    continue  # agotado: queda visible como SIN ACK en el panel
                if now < pending["next_at"]:
                    continue
                self._seq += 1
                frame = fr.LoraFrame(
                    msg_type=pending["type"],
                    cabinet_id=cab_id,
                    session=self._session,
                    seq=self._seq,
                    flags=pending["flags"],
                )
                pending["sent_seq"] = self._seq
                pending["attempts"] += 1
                pending["next_at"] = now + self._cfg.alarm_retry_s
                to_send.append((cab_id, frame.encode(self._keys[cab_id])))
                if pending["attempts"] == self._cfg.alarm_retry_max:
                    # Transición (regla 10): tope agotado se dice UNA vez.
                    log.warning(
                        "lora: %s SIN ACK tras %d intentos (%s)",
                        entry["name"],
                        pending["attempts"],
                        _kind_name(pending["type"]),
                    )
        for _cab_id, raw in to_send:
            try:
                self._transport.send(raw)
            except Exception:  # noqa: BLE001 — el radio jamás tumba el módulo
                log.warning("lora: send falló (módem)", exc_info=True)

    def _check_timeouts(self) -> None:
        timeout_s = self._cfg.heartbeat_s * self._cfg.heartbeat_timeout_factor
        now = utcnow()
        with self._lock:
            for entry in self._reg.values():
                last_seen = entry["last_seen"]
                if entry["link"] == "online" and last_seen is not None:
                    if (now - last_seen).total_seconds() > timeout_s:
                        entry["link"] = "offline"
                        # Transición (regla 10): el jamming/corte se hace VISIBLE.
                        log.warning("lora: secundario %s ENLACE PERDIDO", entry["name"])


def _kind_name(kind: int) -> str:
    return {
        fr.ALARM_ACT: "activate",
        fr.ALARM_CLEAR: "clear",
        fr.TEST: "test",
        fr.SILENCE: "silence",
    }.get(kind, str(kind))


def _mono() -> float:
    return time.monotonic()
