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
import os
import pathlib
import re
import subprocess
import threading
from datetime import datetime
from typing import TYPE_CHECKING

from takab_edge.audit import cause_for_command_origin
from takab_edge.contracts import (
    ActuatorAction,
    ActuatorChannel,
    ActuatorCommand,
    ChannelState,
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


#: [T-2.70] Forma de un id de release: `<ts>-<sha>` o `heredada-<ts>`, que es lo
#: que `deploy.sh` sabe crear. Se valida ANTES de invocar nada aunque el comando
#: venga firmado y aunque los argumentos vayan por `execve` sin shell: esta es la
#: única superficie que ejecuta un proceso en el gabinete por orden de la nube, y
#: una ruta con `..` sería un directorio fuera de `releases/`.
_RELEASE_VALIDA = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


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
        catalog=None,
        lora=None,
    ) -> None:
        super().__init__()
        self._settings = settings
        self._security = security
        self._config_store = config_store
        self._actuators = actuators
        self._cloud = cloud
        self._acks_topic = acks_topic
        # [T-2.24] Store del catálogo SSN (feed firmado nube→edge, opcional).
        self._catalog = catalog
        # [T-1.59] Solo para adjuntar la salud CACHEADA al ack del self_test —
        # jamás se ejecutan sondas desde aquí (lección del panel local).
        self._health = health
        # [T-1.60] Controlador de simulacros (observador; cero relés).
        self._drill = drill
        # [T-2.32] Última actuación comandada por el quórum de red (dict swap
        # atómico; el panel la lee vía status().network_alert y CERRAR ALERTA
        # la limpia). None = sin alerta de red viva.
        self._network_alert: dict | None = None
        # [T-2.33] Enlace a gabinetes secundarios (espejo de sirena/estrobo).
        self._lora = lora

    def network_alert(self) -> dict | None:
        """[T-2.32] Alerta de red viva (quórum) o ``None``."""
        return self._network_alert

    def clear_network_alert(self) -> None:
        """[T-2.32] CERRAR ALERTA también cierra la fuente «QUÓRUM RED»."""
        if self._network_alert is not None:
            log.warning("alerta de red (quórum) cerrada por operador (LAN)")
        self._network_alert = None

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
                except Exception as exc:  # noqa: BLE001 — un comando FIRMADO siempre se ACKea
                    # [T-2.70.a·D2/P1] El `except` de arriba nombraba dos tipos, y
                    # cualquier otro escapaba al `except` genérico de `on_command`,
                    # que registra y CALLA: la nube se quedaba sin ack esperando el
                    # TTL, sin poder distinguir «rechazado» de «el gabinete no
                    # contestó». `start_drill` ya falla cerrado por su cuenta; esto
                    # es el cinturón para todo lo demás que pueda romperse ahí.
                    log.exception("drill_start %s reventó; se ACKea el fallo", command_id)
                    ok, reason = False, f"el simulacro no pudo arrancar: {exc}"
                self._ack(command_id, nonce, channel, action, ok, reason)
            else:
                ended = self._drill.end_drill(drill_id, reason="drill_stop firmado")
                # Idempotente: parar un drill ya terminado es un no-op acked.
                detail = "simulacro terminado" if ended else "sin simulacro activo (no-op)"
                self._ack(command_id, nonce, channel, action, True, detail)
            return
        # [T-2.70] Actualización remota: ACTIVAR una release ya desplegada y
        # verificada, o VOLVER a la anterior.
        #
        # EL ORDEN DE ESTAS DOS LÍNEAS ES EL DISEÑO, no una preferencia. Activar
        # reinicia `takab-edge`, o sea EL PROCESO QUE ESTÁ EJECUTANDO ESTO: un
        # ack posterior al lanzamiento no se publicaría jamás y la nube se
        # quedaría esperando el TTL, sin poder distinguir «rechazado» de «el
        # gabinete no contestó». Así que se ACUSA PRIMERO y se lanza después.
        #
        # Y por eso el ack dice lo que de verdad sabe: «orden aceptada y en
        # marcha». NO dice que la actualización funcionara — eso no se puede
        # saber desde aquí ni en un segundo ni en dos. El resultado viaja por el
        # LATIDO (`fw_running`, T-2.69), que es la única señal que no miente
        # sobre qué código cargó el proceso, y es la que el canary de la nube
        # espera antes de soltar la siguiente cohorte.
        if action in (ActuatorAction.UPDATE_ACTIVATE, ActuatorAction.UPDATE_ROLLBACK):
            if channel is not ActuatorChannel.SYSTEM:
                self._ack(command_id, nonce, channel, action, False, "update exige canal system")
                return
            guion = pathlib.Path(self._settings.canary_script)
            if not os.access(guion, os.X_OK):
                # Un gabinete todavía sin layout A/B (o con el agente sin
                # instalar) no puede activar nada, y decirlo AQUÍ es barato: lo
                # contrario sería lanzar al vacío y dejar que el operador lo
                # dedujera del latido media hora después.
                self._ack(
                    command_id,
                    nonce,
                    channel,
                    action,
                    False,
                    f"sin agente de activación en {guion}",
                )
                return
            argumentos = [str(guion)]
            if action is ActuatorAction.UPDATE_ACTIVATE:
                release = str(payload.get("release_id") or "")
                if not _RELEASE_VALIDA.fullmatch(release):
                    self._ack(
                        command_id,
                        nonce,
                        channel,
                        action,
                        False,
                        f"release_id inválido: {release!r}",
                    )
                    return
                argumentos += ["activar", release]
                if payload.get("ventana_de_mantenimiento"):
                    argumentos.append("--ventana-de-mantenimiento")
            else:
                motivo = str(payload.get("motivo") or "orden de la nube")
                argumentos += ["revertir", "--motivo", motivo]
            self._ack(
                command_id,
                nonce,
                channel,
                action,
                True,
                "orden aceptada; el resultado viaja en el latido (fw_running)",
            )
            self._lanzar_canary(argumentos, command_id)
            return
        if channel is ActuatorChannel.SYSTEM:
            self._ack(
                command_id, nonce, channel, action, False, "canal system solo admite self_test"
            )
            return
        # [T-2.31] Canal no instalado en el sitio: rechazo HONESTO con ack (la
        # nube marca rejected en vez de esperar el TTL). El perfil se lee del
        # store vivo — la nube pudo publicarlo después del arranque.
        if not self._config_store.current().equipment.has(channel):
            self._ack(command_id, nonce, channel, action, False, "canal no instalado en este sitio")
            return

        started = utcnow()
        # [T-2.86.a · RO-4.e] La causa sale del `origin` que viaja DENTRO de la
        # firma —nadie lo inyecta sin la clave—, así que «quórum de red» y «alguien
        # en la consola» quedan como causas distintas en la bitácora, que es la
        # distinción que un perito necesita. El actor es el `command_id`: el edge
        # NO puede saber qué persona lo pulsó y no lo finge; es la nube quien une
        # ese id con su operador en `commands`.
        command = ActuatorCommand(
            channel=channel,
            action=action,
            event_id=payload.get("event_id") or f"CMD-{command_id}",
            cause=cause_for_command_origin(payload.get("origin")),
            actor=f"cloud:{command_id}",
        )
        result = self._actuators.execute(command)
        latency = (utcnow() - started).total_seconds()
        # [T-2.32] Comando de ACTUACIÓN del quórum de red ejecutado: el panel
        # rotula la fuente («QUÓRUM RED»). `origin` viene DENTRO de la firma —
        # nadie lo inyecta sin la clave. Swap atómico del dict (lector = panel).
        if (
            result.success
            and action is ActuatorAction.ACTIVATE
            and payload.get("origin") == "quorum"
        ):
            current = self._network_alert
            channels = sorted(
                {channel.value}
                | (
                    set(current["channels"])
                    if current and current["event_id"] == command.event_id
                    else set()
                )
            )
            if current is None or current["event_id"] != command.event_id:
                # Transición (regla de oro 10): UNA línea por evento de red, no por canal.
                log.warning(
                    "ALERTA DE RED (quórum ≥3): actuación comandada por la nube (%s)",
                    command.event_id,
                )
            self._network_alert = {
                "event_id": command.event_id,
                "at": utcnow().isoformat(),
                "channels": channels,
            }
            # [T-2.33] Espejo a secundarios: la alerta de red también destella
            # y suena a distancia (fire-and-forget; los flags se ACUMULAN si la
            # sirena y el estrobo llegan como comandos separados).
            if self._lora is not None and channel in (
                ActuatorChannel.SIREN,
                ActuatorChannel.STROBE,
            ):
                try:
                    self._lora.propagate(
                        "activate",
                        siren=channel is ActuatorChannel.SIREN,
                        strobe=channel is ActuatorChannel.STROBE,
                    )
                except Exception:  # noqa: BLE001 — el espejo jamás bloquea el ack
                    log.exception("lora.propagate desde comando de red falló (aislado)")
        # [T-2.116 · spec móvil §2.2] El acuse declara EL ESTADO DEL CANAL tras
        # el arbitraje de demandas, no la intención del comando. `result.success`
        # dice «la orden se ejecutó» —la demanda manual se retiró— y eso NO es lo
        # mismo que «el relé cambió»: con una alerta vigente, el enclave de
        # SASMEX sostiene la sirena y el `deactivate` sale con éxito sin apagar
        # nada. Lo trae el propio ack del actuador, que lo leyó del dueño de los
        # pines en la misma pasada que aplicó la demanda.
        self._ack(
            command_id,
            nonce,
            channel,
            action,
            result.success,
            result.detail,
            latency_s=max(result.latency_s, latency),
            channel_state=result.channel_state,
        )

    def _lanzar_canary(self, argumentos: list[str], command_id: str) -> None:
        """Lanza el agente DESLIGADO de este proceso, y no espera nada.

        `start_new_session=True` lo saca del grupo de procesos de `takab-edge`:
        sin eso, el `systemctl restart` que el propio agente ejecuta se llevaría
        por delante a su lanzador —el agente moriría a mitad del remojo y el
        gabinete se quedaría con la release nueva SIN NADIE que pudiera
        revertirla—. Es la misma razón por la que el agente vive fuera de las
        releases: el reversor no puede depender de lo que se está sustituyendo.

        La lista de argumentos va tal cual a `execve` (sin `shell=True`), así que
        el `release_id` no puede convertirse en comando por mucho que venga de
        fuera — y aun así se valida antes contra `_RELEASE_VALIDA`. Defensa en
        profundidad: esto lo dispara un comando FIRMADO, pero es la superficie
        que ejecuta algo en el gabinete.
        """
        try:
            subprocess.Popen(  # noqa: S603 — lista de argv, sin shell
                argumentos,
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            # El ack ya salió (tenía que salir antes: ver la nota de arriba), así
            # que aquí sólo queda el journal. La nube lo verá igual: `fw_running`
            # no cambiará, y para el canary de cohortes eso ES el fallo.
            log.exception("comando %s: no se pudo lanzar el agente de activación", command_id)

    def _run_self_test(self, command_id: str, nonce: str) -> None:
        """Corre el autodiagnóstico y ACKea con resultados. JAMÁS lanza (hilo propio)."""
        started = utcnow()
        try:
            outcome = self._actuators.cabinet_self_test(actor=f"cloud:{command_id}")
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
        channel_state: ChannelState | None = None,
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
            # [T-2.116] `None` en los acks de RECHAZO a propósito: sin ejecución
            # no hubo arbitraje, y declarar un estado ahí sería opinar sobre un
            # relé que este acuse no midió (regla de oro 7).
            channel_state=channel_state,
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

    # -------------------------------------------------------------- catálogo

    def on_catalog(self, _topic: str, raw: bytes) -> None:
        """[T-2.24] Callback de ``takab/catalog/<thing>``. JAMÁS lanza (hilo del broker)."""
        try:
            self._handle_catalog(raw)
        except Exception:  # noqa: BLE001 — un catálogo hostil nunca tira el enlace
            log.exception("catálogo: error inesperado procesando el mensaje")

    def _handle_catalog(self, raw: bytes) -> None:
        if self._catalog is None:
            log.warning("catálogo descartado: sin store cableado")
            return
        envelope = self._parse(raw)
        if envelope is None:
            return
        version = envelope.get("version")
        signature = envelope.get("sig")
        payload = envelope.get("payload")
        if not (
            isinstance(version, int) and isinstance(signature, str) and isinstance(payload, dict)
        ):
            log.warning("catálogo descartado: envelope incompleto")
            return
        from takab_edge.catalog import CatalogError

        try:
            applied = self._catalog.apply_signed_update(
                canonical_payload(payload), signature, version
            )
        except CatalogError as exc:
            # Firma mala / versión no fresca / payload inválido: NO se aplica.
            log.warning("catálogo v%s rechazado: %s", version, exc)
            return
        log.info("catálogo SSN sincronizado: v%d", applied)

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
