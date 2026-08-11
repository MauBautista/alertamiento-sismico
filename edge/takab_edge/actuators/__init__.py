"""actuators — interfaz `Actuator` única + driver de relés + adaptador BACnet/IP.

[RATIFICADO 2026-07-09 · T-1.45 · gate #4] Driver primario = **relés fail-safe** del
módulo `gpio`; el adaptador **BACnet/IP** (gas, ascensores, puertas) vive detrás de la
MISMA interfaz `Actuator`, **activable por contrato** (`bacnet_channels`). La decisión
está cerrada, pero la interfaz la sigue aislando: reabrirla cambiaría qué driver es el
primario, nunca el motor de reglas.

La **sirena y el estrobo** (alerta audible/visual de vida) van SIEMPRE por relé local
directo — nunca por BACnet, para no depender de una pasarela de terceros en el camino
de vida. Cada acción devuelve un `ActuatorAck` con timestamp relativo al comando
(`T+0.42s`). En dev/tests el adaptador BACnet usa el simulador (mock, sin hardware);
el driver real (`bacpypes3`/`BAC0`) es el extra ``[bacnet]`` (gate hardware).
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Iterable, Sequence
from typing import Protocol, runtime_checkable

from takab_edge.contracts import (
    ActuatorAck,
    ActuatorAction,
    ActuatorChannel,
    ActuatorCommand,
    ChannelState,
    utcnow,
)
from takab_edge.gpio_link import GpioLink, as_link, channel_state_from
from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.actuators")

#: Canales que NUNCA se enrutan a BACnet (vida audible/visual = relé local directo).
RELAY_ONLY: tuple[ActuatorChannel, ...] = (ActuatorChannel.SIREN, ActuatorChannel.STROBE)


def _ack(
    command: ActuatorCommand,
    *,
    success: bool,
    detail: str,
    channel_state: ChannelState | None = None,
) -> ActuatorAck:
    # Latencia = tiempo desde que `rules` emitió el comando hasta su ejecución (T+X.XXs).
    latency_s = max(0.0, (utcnow() - command.issued_at).total_seconds())
    return ActuatorAck(
        channel=command.channel,
        action=command.action,
        event_id=command.event_id,
        success=success,
        latency_s=latency_s,
        detail=detail,
        channel_state=channel_state,
    )


@runtime_checkable
class Actuator(Protocol):
    """Contrato único que `rules`/`ActuatorManager` consumen para accionar un canal."""

    channels: tuple[ActuatorChannel, ...]

    def execute(self, command: ActuatorCommand) -> ActuatorAck:
        """Ejecuta el comando y devuelve un ACK con latencia medida."""
        ...


class RelayActuator:
    """Driver primario: acciona los relés locales fail-safe por la COSTURA `gpio`.

    [T-2.70.a·D2/P1] Recibe un :class:`~takab_edge.gpio_link.GpioLink`, no el
    `GpioController`. `as_link` sigue aceptando el controlador crudo (tests,
    `demo/gabinete.py`), pero el supervisor construye la costura UNA vez y se la
    reparte a los cinco consumidores.
    """

    channels = (
        ActuatorChannel.SIREN,
        ActuatorChannel.STROBE,
        ActuatorChannel.GAS_VALVE,
        ActuatorChannel.ELEVATOR,
        ActuatorChannel.DOOR_RETAINER,
    )

    def __init__(self, gpio: GpioLink) -> None:
        self._link: GpioLink = as_link(gpio)

    def execute(self, command: ActuatorCommand) -> ActuatorAck:
        return self.execute_batch([command])[0]

    def execute_batch(self, commands: Sequence[ActuatorCommand]) -> list[ActuatorAck]:
        """[T-2.70.a·D2/P1] La secuencia entera como UNA petición a la costura.

        Cinco cruces se vuelven uno y el resultado físico se decide en un solo
        sitio, bajo una sola toma del lock del dueño de los pines, en vez de en
        cinco round-trips que pueden intercalarse entre sí.

        El aislamiento por canal se conserva: la costura devuelve un resultado por
        canal y aquí se traduce a un ACK por canal, en el MISMO orden. Si la
        costura entera no contesta, cada canal recibe su ACK fallido — nunca una
        excepción al hilo de detección.
        """
        if not commands:
            return []
        demands = [(c.channel, c.action == c.action.ACTIVATE) for c in commands]
        try:
            outcomes = self._link.apply(demands)
        except Exception as exc:  # noqa: BLE001 — vida: el lote caído se ACKea, no se lanza
            log.exception("la costura del gabinete no aceptó el lote de %d canales", len(commands))
            return [
                _ack(command, success=False, detail=f"costura no disponible: {exc}")
                for command in commands
            ]
        if len(outcomes) != len(commands):
            # Contrato roto por el otro lado: se ACKea fallo antes que emparejar
            # a ciegas un resultado con un canal que no le corresponde.
            log.error(
                "la costura devolvió %d resultados para %d canales", len(outcomes), len(commands)
            )
            return [
                _ack(command, success=False, detail="costura incoherente") for command in commands
            ]
        estados = self._estados_tras_el_arbitraje()
        return [
            _ack(
                command,
                success=outcome.ok,
                detail=outcome.detail,
                channel_state=estados.get(command.channel),
            )
            for command, outcome in zip(commands, outcomes, strict=True)
        ]

    def _estados_tras_el_arbitraje(self) -> dict[ActuatorChannel, ChannelState]:
        """[T-2.116] El censo de relés RECALCULADO, en UNA sola lectura.

        Va después de `apply` y no dentro: lo que hay que declarar es el estado
        que quedó, y el arbitraje de `GpioController._desired_energized` no se
        conoce hasta que la demanda entró. Una sola instantánea para todo el
        lote —no una por canal— porque con el dueño de los pines en otro proceso
        cada lectura es un round-trip, y T-2.70.a redujo la secuencia entera del
        tier a UN cruce justo para eso.

        Falla CERRADO y en silencio para el acuse: si la costura no contesta, el
        ack sale sin `channel_state` (`None` = «no pude preguntar») en vez de
        romper la actuación. El relé ya se movió; perder el censo no puede
        impedir que la sirena suene ni que el ack viaje (regla de oro 4).
        """
        try:
            snapshot = self._link.snapshot()
        except Exception:  # noqa: BLE001 — vida: el censo jamás bloquea el acuse
            log.warning(
                "no se pudo leer el estado arbitrado de los canales; el acuse "
                "viaja sin censo del relé (None = «no pude preguntar»)",
                exc_info=True,
            )
            return {}
        estados: dict[ActuatorChannel, ChannelState] = {}
        for relay in snapshot.relays:
            estado = channel_state_from(snapshot, relay.channel)
            if estado is not None:
                estados[relay.channel] = estado
        return estados

    def cabinet_self_test(self) -> dict:
        """Recorrido de relés NO audibles (T-1.59) — delega en gpio, el dueño
        del modelo de demandas."""
        return self._link.action("cabinet_self_test")


@runtime_checkable
class BacnetClient(Protocol):
    """Cliente BACnet/IP mínimo (implementado por el simulador y, en prod, por BAC0)."""

    def write_present_value(self, channel: ActuatorChannel, active: bool) -> bool: ...


class BacnetActuator:
    """Adaptador BACnet/IP (gas/ascensores/puertas), detrás de la misma interfaz.

    En dev usa el simulador BACnet (mock). El driver real con `bacpypes3`/`BAC0` es el
    extra ``[bacnet]`` (gate hardware).
    """

    channels = (
        ActuatorChannel.GAS_VALVE,
        ActuatorChannel.ELEVATOR,
        ActuatorChannel.DOOR_RETAINER,
    )

    def __init__(self, client: BacnetClient) -> None:
        self._client = client

    def execute(self, command: ActuatorCommand) -> ActuatorAck:
        on = command.action == command.action.ACTIVATE
        ok = self._client.write_present_value(command.channel, on)
        return _ack(command, success=ok, detail="bacnet")


class ActuatorManager(EdgeModule):
    """Enruta cada comando a su driver (relé por defecto; BACnet por contrato) y colecciona ACKs."""

    name = "actuators"
    depends_on = ("gpio",)
    critical = True  # driver de relés/BACnet que toca sirena/gas/puertas; fail-fast

    def __init__(
        self,
        relay: Actuator,
        bacnet: Actuator | None = None,
        bacnet_channels: Iterable[ActuatorChannel] = (),
        *,
        ledger=None,
    ) -> None:
        super().__init__()
        self._relay = relay
        self._bacnet = bacnet
        # [T-2.86.a · RO-4.e] Bitácora local de actuación. Va aquí y no en cada
        # llamador porque `_record` es el EMBUDO ÚNICO: `execute` y
        # `execute_sequence` pasan los dos por él, así que no hay forma de mover un
        # relé por esta clase sin dejar fila. `None` = sin bitácora (tests viejos y
        # `demo/gabinete.py`), y entonces esto es un no-op silencioso.
        self._ledger = ledger
        # La sirena/estrobo nunca van por BACnet (vida audible = relé local directo).
        self._bacnet_channels = {c for c in bacnet_channels if c not in RELAY_ONLY}
        # Ventana rodante de ACKs (evita crecimiento sin límite en un EVACUATE sostenido).
        self._acks: deque[ActuatorAck] = deque(maxlen=256)

    def _driver_for(self, channel: ActuatorChannel) -> Actuator:
        if self._bacnet is not None and channel in self._bacnet_channels:
            return self._bacnet
        return self._relay

    def execute(self, command: ActuatorCommand) -> ActuatorAck:
        # Aislamiento de fallo: un actuador que LANZA (p.ej. BACnet real por timeout) NO
        # debe abortar la secuencia; devolvemos un ACK fallido y seguimos (best-effort).
        try:
            ack = self._driver_for(command.channel).execute(command)
        except Exception as exc:  # noqa: BLE001 — vida: nunca abortar el resto de la secuencia
            ack = _ack(command, success=False, detail=f"excepción: {exc}")
            log.exception("actuador %s lanzó excepción", command.channel.value)
        return self._record(command, ack)

    def _record(self, command: ActuatorCommand, ack: ActuatorAck) -> ActuatorAck:
        """Anota el ACK en la ventana rodante y lo registra (éxito/fallo).

        [T-2.86.a] Y deja **constancia local con actor y causa**, sobreviva o no el
        enlace: hasta aquí el ACK sólo decía QUÉ pasó, y la pregunta que hace un
        perito es QUIÉN lo ordenó. La bitácora es informativa a propósito (misma
        doctrina que el registro del cerrojo) y `record()` no lanza jamás, así que
        un disco lleno no puede impedir que la sirena suene — pero el fallo se
        declara en `ActuationLedger.state()`, que es lo que pinta el panel.
        """
        self._acks.append(ack)
        if self._ledger is not None:
            self._ledger.record_ack(command, ack)
        if ack.success:
            log.info(
                "actuador %s %s vía %s (%s)",
                command.channel.value,
                command.action.value,
                ack.detail,
                ack.relative_label,
            )
        else:
            log.warning(
                "actuador %s %s FALLÓ (%s, %s)",
                command.channel.value,
                command.action.value,
                ack.detail,
                ack.relative_label,
            )
        return ack

    def execute_sequence(self, commands: Sequence[ActuatorCommand]) -> list[ActuatorAck]:
        """Ejecuta la secuencia del tier best-effort (cada canal se intenta y se ACKea).

        [T-2.70.a·D2/P1] Los tramos CONTIGUOS que van por relé cruzan la costura
        como UNA sola petición: sin BACnet por contrato —el caso normal— toda la
        secuencia del tier es un cruce en vez de cinco.

        Contiguos y no «todos los de relé juntos» a propósito: agrupar salteando
        reordenaría la actuación física respecto del orden que emite `rules`, y
        «conducta idéntica a hoy» incluye ese orden. Sin BACnet la agrupación es
        la secuencia entera igualmente.
        """
        acks: list[ActuatorAck] = []
        for driver, tramo in self._tramos(commands):
            lote = getattr(driver, "execute_batch", None)
            if lote is None or len(tramo) == 1:
                acks.extend(self.execute(command) for command in tramo)
                continue
            try:
                resultados = lote(tramo)
            except Exception as exc:  # noqa: BLE001 — vida: nunca abortar el resto
                log.exception("el lote de %d canales lanzó excepción", len(tramo))
                resultados = [_ack(c, success=False, detail=f"excepción: {exc}") for c in tramo]
            acks.extend(
                self._record(command, ack) for command, ack in zip(tramo, resultados, strict=True)
            )
        return acks

    def _tramos(
        self, commands: Sequence[ActuatorCommand]
    ) -> list[tuple[Actuator, list[ActuatorCommand]]]:
        """Corta la secuencia en tramos CONSECUTIVOS que comparten driver."""
        tramos: list[tuple[Actuator, list[ActuatorCommand]]] = []
        for command in commands:
            driver = self._driver_for(command.channel)
            if tramos and tramos[-1][0] is driver:
                tramos[-1][1].append(command)
            else:
                tramos.append((driver, [command]))
        return tramos

    def cabinet_self_test(self, actor: str = "") -> dict:
        """Autodiagnóstico del gabinete (T-1.59): SOLO relés locales — BACnet no
        participa (un self-test jamás toca una pasarela de terceros).

        [T-2.86.a] Pulsa relés reales, así que deja fila igual que cualquier otra
        actuación: no pasa por `_record` (no produce `ActuatorAck`) y por eso el
        registro va explícito aquí, que es el otro embudo de esta clase.
        """
        runner = getattr(self._relay, "cabinet_self_test", None)
        if runner is None:
            outcome = {"ok": False, "reason": "driver de relés sin autodiagnóstico", "relays": {}}
        else:
            outcome = runner()
        if self._ledger is not None:
            from takab_edge.contracts import ActuationCause

            self._ledger.record(
                cause=ActuationCause.CABINET_SELF_TEST,
                actor=actor or "cloud",
                channel=ActuatorChannel.SYSTEM,
                action=ActuatorAction.SELF_TEST,
                success=bool(outcome.get("ok")),
                detail=str(outcome.get("reason") or "self-test de relés no audibles"),
            )
        return outcome

    @property
    def last_acks(self) -> list[ActuatorAck]:
        return list(self._acks)

    def _on_start(self) -> None:
        bacnet = sorted(c.value for c in self._bacnet_channels) if self._bacnet else []
        log.info("actuadores listos (BACnet por contrato: %s; resto por relé local)", bacnet or "—")
