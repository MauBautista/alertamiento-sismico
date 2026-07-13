"""dispatch — consumidor de comandos y config firmados nube→edge (T-1.23).

Cierra el lazo de T-1.12: la nube publica en ``takab/cmd|cfg/<thing>``; aquí se
verifica TODO con `SecurityManager` (firma HMAC + nonce un-solo-uso + ventana)
antes de tocar nada, y se responde con `CommandAck` por ``takab/acks``.

Política de rechazo (regla de oro 8):
- **Firma inválida / replay / fuera de ventana / malformado** ⇒ NO se ejecuta y
  NO se emite ack (a un emisor no autenticado no se le responde; la nube expira
  el comando pendiente por TTL — el ack obligatorio se garantiza por expiración).
- **Verificado pero `command_enabled=false`** (default de fábrica por gateway)
  ⇒ ack `rejected` con detalle: el operador ve POR QUÉ no actuó.
- La config firmada la aplica `ConfigStore` (versión monótona, reversible);
  una config rechazada solo se loguea — el estado visible viaja en el health.

El payload se re-canonicaliza (json sort_keys sin espacios) EXACTAMENTE como
firma la nube; los vectores compartidos (`shared/schemas/tests/hmac_vectors
.json`) fijan el framing en ambos lados.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from typing import TYPE_CHECKING

from takab_edge.contracts import (
    ActuatorAction,
    ActuatorChannel,
    ActuatorCommand,
    CommandAck,
    utcnow,
)
from takab_edge.module import EdgeModule

if TYPE_CHECKING:
    from takab_edge.actuators import ActuatorManager
    from takab_edge.cloud import CloudConnector
    from takab_edge.config import ConfigStore, EdgeSettings
    from takab_edge.security import SecurityManager

log = logging.getLogger("takab_edge.dispatch")


def canonical_payload(payload: dict) -> bytes:
    """JSON canónico (claves ordenadas, sin espacios) — base de la firma HMAC."""
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


class CommandDispatcher(EdgeModule):
    """Verifica y despacha comandos/config firmados; publica los ACKs."""

    name = "dispatch"
    depends_on = ("security", "config", "actuators", "cloud")

    def __init__(
        self,
        settings: EdgeSettings,
        security: SecurityManager,
        config_store: ConfigStore,
        actuators: ActuatorManager,
        cloud: CloudConnector,
        acks_topic: str = "takab/acks",
        health=None,
        drill=None,
    ) -> None:
        super().__init__()
        self._settings = settings
        self._security = security
        self._config_store = config_store
        self._actuators = actuators
        self._cloud = cloud
        self._acks_topic = acks_topic
        # [T-1.59] Solo para adjuntar la salud CACHEADA al ack del self_test —
        # jamás se ejecutan sondas desde aquí (lección del panel local).
        self._health = health
        # [T-1.60] Controlador de simulacros (observador; cero relés).
        self._drill = drill

    # ------------------------------------------------------------- comandos

    def on_command(self, _topic: str, raw: bytes) -> None:
        """Callback del topic ``takab/cmd/<thing>``. JAMÁS lanza (hilo del broker)."""
        try:
            self._handle_command(raw)
        except Exception:  # noqa: BLE001 — un mensaje hostil nunca tira el enlace
            log.exception("comando: error inesperado procesando el mensaje")

    def _handle_command(self, raw: bytes) -> None:
        envelope = self._parse(raw)
        if envelope is None:
            return
        command_id = envelope.get("command_id")
        nonce = envelope.get("nonce")
        ts_raw = envelope.get("ts")
        signature = envelope.get("sig")
        payload = envelope.get("payload")
        if not (
            isinstance(command_id, str)
            and isinstance(nonce, str)
            and isinstance(ts_raw, str)
            and isinstance(signature, str)
            and isinstance(payload, dict)
        ):
            log.warning("comando descartado: envelope incompleto")
            return
        try:
            ts = datetime.fromisoformat(ts_raw)
            channel = ActuatorChannel(payload["channel"])
            action = ActuatorAction(payload["action"])
        except (KeyError, ValueError):
            log.warning("comando descartado: payload/ts inválidos")
            return

        body = canonical_payload(payload)
        if not self._security.verify_command(body, nonce, signature, ts):
            return  # no autenticado: sin ack (la nube lo expira por TTL)

        if not self._config_store.current().command_enabled:
            log.warning("comando %s rechazado: command_enabled=false (default)", command_id)
            self._ack(command_id, nonce, channel, action, False, "command_enabled=false")
            return

        # [T-1.59] self_test: recorrido de relés NO audibles en un hilo corto
        # (~1.6 s; el hilo del broker jamás se bloquea) + ack con `results`.
        if action is ActuatorAction.SELF_TEST:
            if channel is not ActuatorChannel.SYSTEM:
                self._ack(command_id, nonce, channel, action, False, "self_test exige canal system")
                return
            worker = threading.Thread(
                target=self._run_self_test,
                args=(command_id, nonce),
                name="cabinet-self-test",
                daemon=True,
            )
            worker.start()
            return
        # [T-1.60] Simulacro institucional: banner NO-real + voceo; cero relés.
        if action in (ActuatorAction.DRILL_START, ActuatorAction.DRILL_STOP):
            if channel is not ActuatorChannel.SYSTEM:
                self._ack(command_id, nonce, channel, action, False, "drill exige canal system")
                return
            if self._drill is None:
                self._ack(command_id, nonce, channel, action, False, "sin controlador de drill")
                return
            drill_id = str(payload.get("event_id") or f"CMD-{command_id}")
            if action is ActuatorAction.DRILL_START:
                duration = payload.get("duration_s") or 300
                try:
                    ok, reason = self._drill.start_drill(drill_id, float(duration))
                except (TypeError, ValueError):
                    ok, reason = False, f"duration_s inválido: {duration!r}"
                self._ack(command_id, nonce, channel, action, ok, reason)
            else:
                ended = self._drill.end_drill(drill_id, reason="drill_stop firmado")
                # Idempotente: parar un drill ya terminado es un no-op acked.
                detail = "simulacro terminado" if ended else "sin simulacro activo (no-op)"
                self._ack(command_id, nonce, channel, action, True, detail)
            return
        if channel is ActuatorChannel.SYSTEM:
            self._ack(
                command_id, nonce, channel, action, False, "canal system solo admite self_test"
            )
            return

        started = utcnow()
        command = ActuatorCommand(
            channel=channel,
            action=action,
            event_id=payload.get("event_id") or f"CMD-{command_id}",
        )
        result = self._actuators.execute(command)
        latency = (utcnow() - started).total_seconds()
        self._ack(
            command_id,
            nonce,
            channel,
            action,
            result.success,
            result.detail,
            latency_s=max(result.latency_s, latency),
        )

    def _run_self_test(self, command_id: str, nonce: str) -> None:
        """Corre el autodiagnóstico y ACKea con resultados. JAMÁS lanza (hilo propio)."""
        started = utcnow()
        try:
            outcome = self._actuators.cabinet_self_test()
        except Exception as exc:  # noqa: BLE001 — un test roto no tira el dispatcher
            log.exception("self-test lanzó excepción")
            outcome = {"ok": False, "reason": f"excepción: {exc}", "relays": {}}
        results: dict = {"relays": outcome.get("relays", {})}
        snapshot = getattr(self._health, "last_snapshot", None)
        if snapshot is not None:
            # Salud DEL CACHE (el heartbeat ya la midió): sin subprocesos aquí.
            results["health"] = {
                "ups_status": snapshot.ups_status.value,
                "ntp_offset_s": snapshot.ntp_offset_s,
                "cert_days_remaining": snapshot.cert_days_remaining,
                "disk_used_pct": snapshot.disk_used_pct,
                "captured_at": snapshot.captured_at.isoformat(),
            }
        latency = (utcnow() - started).total_seconds()
        self._ack(
            command_id,
            nonce,
            ActuatorChannel.SYSTEM,
            ActuatorAction.SELF_TEST,
            bool(outcome.get("ok")),
            outcome.get("reason") or "self-test completado",
            latency_s=latency,
            results=results,
        )

    def _ack(
        self,
        command_id: str,
        nonce: str,
        channel: ActuatorChannel,
        action: ActuatorAction,
        success: bool,
        detail: str,
        latency_s: float = 0.0,
        results: dict | None = None,
    ) -> None:
        ack = CommandAck(
            command_id=command_id,
            nonce=nonce,
            channel=channel,
            action=action,
            success=success,
            latency_s=latency_s,
            detail=detail,
            results=results,
        )
        self._cloud.publish(self._acks_topic, ack)
        log.info(
            "comando %s → %s (%s %s): %s",
            command_id,
            "ejecutado" if success else "rechazado/fallido",
            channel.value,
            action.value,
            detail or "ok",
        )

    # --------------------------------------------------------------- config

    def on_config(self, _topic: str, raw: bytes) -> None:
        """Callback del topic ``takab/cfg/<thing>``. JAMÁS lanza (hilo del broker)."""
        try:
            self._handle_config(raw)
        except Exception:  # noqa: BLE001 — una config hostil nunca tira el enlace
            log.exception("config: error inesperado procesando el mensaje")

    def _handle_config(self, raw: bytes) -> None:
        envelope = self._parse(raw)
        if envelope is None:
            return
        version = envelope.get("version")
        signature = envelope.get("sig")
        payload = envelope.get("payload")
        valid_shape = (
            isinstance(version, int) and isinstance(signature, str) and isinstance(payload, dict)
        )
        if not valid_shape:
            log.warning("config descartada: envelope incompleto")
            return
        from takab_edge.config import ConfigError

        try:
            applied = self._config_store.apply_signed_update(
                canonical_payload(payload), signature, version
            )
        except ConfigError as exc:
            # Firma mala / versión no monótona / payload inválido: NO se aplica.
            log.warning("config v%s rechazada: %s", version, exc)
            return
        log.info("config sync aplicada: v%d", applied)

    # -------------------------------------------------------------- helpers

    @staticmethod
    def _parse(raw: bytes) -> dict | None:
        try:
            envelope = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            log.warning("mensaje descartado: JSON inválido")
            return None
        if not isinstance(envelope, dict):
            log.warning("mensaje descartado: no es un objeto")
            return None
        return envelope

    def _on_start(self) -> None:
        log.info(
            "dispatcher activo (command_enabled=%s)",
            self._config_store.current().command_enabled,
        )
