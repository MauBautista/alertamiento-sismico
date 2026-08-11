"""[T-2.116] El acuse del comando declara el ESTADO DEL CANAL, no la intención.

La spec móvil §2.2 (`takab-docs/design/app/ESPECIFICACION-APP-MOVIL.md:536`) lo
pide con estas palabras:

    «Silenciar sirena» es una **retirada de la demanda del canal manual** en el
    arbitraje del edge — si otra demanda activa (alerta vigente) mantiene la
    sirena, la UI lo explica («La sirena permanece activa por alerta vigente»)
    en lugar de fingir éxito: el resultado real llega en el `command_ack` con el
    estado recalculado del relé.

Ese campo no existía. El gabinete mandaba `{channel, action, success,
latency_s, executed_at, detail, results}` con `detail="relay"`, así que un
`deactivate` ARBITRADO (la alerta sigue enclavada y sostiene la sirena) viajaba
a la nube con `success=true` y sin una sola palabra sobre el relé: la nube —y
con ella el teléfono— leía «silenciada» un edificio que seguía sonando.

**El arbitraje vive en `GpioController._desired_energized`** (`edge/takab_edge/
gpio/__init__.py`): suma `_sasmex_latched`, `_rules_demand`, `_audible_silenced`,
las pruebas y `_safed` para decidir el nivel eléctrico de cada canal. Lo que el
acuse transporta ahora es el resultado de ESA cuenta, leído de `GpioLink.
snapshot()` —una sola toma del lock, coherente— y jamás la orden que se pidió.

ESTE FICHERO ES LA PATA 1 DEL E2E de la ficha (las tres comparten el MISMO
payload, `tests/vectors/command_ack_siren_arbitrado.json`):

  1. aquí — el gabinete REAL (GpioController con pines mock + RelayActuator +
     ActuatorManager + CommandDispatcher) produce el acuse ante un `deactivate`
     FIRMADO con la alerta vigente, y se valida contra el JSON Schema
     comprometido;
  2. `api/tests/commands/test_e2e_estado_del_rele.py` — el MISMO payload entra
     por `handle_command_ack` a una DB real y queda en `commands.ack`;
  3. `mobile/src/features/control/estadoDelRele.test.tsx` — el MISMO payload
     llega a la hoja de control y la persona lee «LA SIRENA SIGUE ACTIVA».

Las tres patas no caben en un proceso: los venv de `api/` y `edge/` no se ven
(medido: `import takab_api` desde edge y `import takab_edge` desde api fallan).
El vector comprometido es la costura, y el schema —anti-drift en
`test_schemas.py`— es lo que impide que una pata se mueva sin las otras.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from takab_edge.actuators import ActuatorManager, RelayActuator
from takab_edge.config import ConfigStore, EdgeSettings
from takab_edge.contracts import (
    ActuatorAction,
    ActuatorChannel,
    ActuatorCommand,
    SirenReason,
)
from takab_edge.dispatch import CommandDispatcher, canonical_payload
from takab_edge.gpio import GpioController
from takab_edge.gpio_link import LocalGpioLink, channel_state_from
from takab_edge.security import SecurityManager

KEY = b"clave-de-test-estado-del-rele"
NOW = datetime(2026, 8, 10, 12, 0, 0, tzinfo=UTC)

#: El payload que las tres patas del E2E comparten. Se genera aquí y se lee
#: allí: si el gabinete deja de emitirlo así, esta pata cae ANTES que las otras.
VECTOR = Path(__file__).resolve().parent / "vectors" / "command_ack_siren_arbitrado.json"

SCHEMA = Path(__file__).resolve().parents[2] / "shared" / "schemas" / "command_ack.schema.json"


class _FakeCloud:
    """Registra lo publicado (sustituye a CloudConnector, como en test_dispatch)."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    def publish(self, topic: str, payload) -> bool:
        self.published.append((topic, payload.model_dump(mode="json")))
        return True


@pytest.fixture
def gabinete(settings: EdgeSettings):
    """Gabinete REAL de extremo a extremo: pines mock, arbitraje de verdad."""
    gpio = GpioController(settings.model_copy(update={"command_enabled": True}))
    gpio.start()
    try:
        yield gpio
    finally:
        gpio.stop()


def _cadena(gpio: GpioController, settings: EdgeSettings):
    """gpio → RelayActuator → ActuatorManager → CommandDispatcher → nube."""
    s = settings.model_copy(update={"command_enabled": True})
    link = LocalGpioLink(gpio)
    actuators = ActuatorManager(RelayActuator(link))
    security = SecurityManager(KEY, command_ttl_s=60.0)
    cloud = _FakeCloud()
    dispatcher = CommandDispatcher(
        s,
        security,
        ConfigStore(s, security=security, cache_path=None),
        actuators,
        cloud,
    )
    return dispatcher, cloud, security, actuators


def _sobre_firmado(security: SecurityManager, payload: dict, nonce: str, ts: datetime) -> bytes:
    return json.dumps(
        {
            "kind": "command",
            "command_id": f"cid-{nonce[:8]}",
            "nonce": nonce,
            "ts": ts.isoformat(),
            "payload": payload,
            "sig": security.sign(canonical_payload(payload), nonce, ts),
        }
    ).encode()


def _silenciar(dispatcher, security, *, nonce: str = "nonce-silencio-01") -> None:
    payload = {"channel": "siren", "action": "deactivate", "event_id": "EVT-1"}
    dispatcher.on_command(
        "takab/cmd/gw-test",
        _sobre_firmado(security, payload, nonce, datetime.now(UTC)),
    )


# --------------------------------------------------------------------- unidad


def test_el_arbitraje_se_lee_del_snapshot_y_no_de_la_orden(gabinete):
    """`channel_state_from` traduce la instantánea del dueño de los pines."""
    gabinete.simulate_sasmex(True)
    estado = channel_state_from(gabinete.snapshot(), ActuatorChannel.SIREN)
    assert estado is not None
    assert estado.activated is True
    assert estado.reason is SirenReason.ALERT
    assert estado.alert_latched is True


def test_un_canal_que_no_gobierna_reles_no_inventa_estado(gabinete):
    """`system` es un canal LÓGICO: no tiene relé, así que no declara estado."""
    assert channel_state_from(gabinete.snapshot(), ActuatorChannel.SYSTEM) is None


def test_el_ack_del_actuador_tambien_lo_lleva(gabinete, settings):
    """El MISMO estado viaja en el `ActuatorAck` → `incident_actions.payload`.

    Es la otra mitad del defecto: la spec §2.1 pide que el checklist BMS pinte
    «el estado del relé recalculado por el arbitraje de demandas, **no la última
    orden enviada**», y la traza sólo llevaba el verbo (`siren_on`/`siren_off`).
    """
    gabinete.simulate_sasmex(True)
    actuators = ActuatorManager(RelayActuator(LocalGpioLink(gabinete)))
    ack = actuators.execute(
        ActuatorCommand(
            channel=ActuatorChannel.SIREN,
            action=ActuatorAction.DEACTIVATE,
            event_id="EVT-1",
        )
    )
    assert ack.success is True  # la orden se ejecutó…
    assert ack.channel_state is not None
    assert ack.channel_state.activated is True  # …y el relé NO se apagó
    assert ack.channel_state.reason is SirenReason.ALERT


def test_sin_alerta_el_retiro_apaga_de_verdad_y_el_estado_lo_dice(gabinete, settings):
    """Contraejemplo: sin la frase a fuego, el acuse sabe decir que SÍ apagó."""
    dispatcher, cloud, security, _ = _cadena(gabinete, settings)
    gabinete.activate(ActuatorChannel.SIREN)  # demanda de `rules`, sin SASMEX
    assert gabinete.siren_sounding is True
    _silenciar(dispatcher, security)
    _, ack = cloud.published[-1]
    assert ack["success"] is True
    assert ack["channel_state"]["activated"] is False
    assert ack["channel_state"]["reason"] is None
    assert ack["channel_state"]["alert_latched"] is False


# ------------------------------------------------------------------ E2E · pata 1


def test_e2e_silenciar_con_alerta_vigente_el_acuse_dice_que_sigue_energizada(gabinete, settings):
    """SASMEX vigente + `deactivate` FIRMADO ⇒ el acuse declara la sirena viva.

    Es el criterio 3 de la ficha, medido sobre el gabinete real: nadie simula
    el arbitraje — lo resuelve `GpioController` con sus propias demandas.
    """
    dispatcher, cloud, security, _ = _cadena(gabinete, settings)

    # Alerta REAL enclavada por el contacto seco del WR-1: la sirena suena.
    gabinete.simulate_sasmex(True)
    assert gabinete.siren_sounding is True

    _silenciar(dispatcher, security)

    topic, ack = cloud.published[-1]
    assert topic == "takab/acks"
    assert ack["kind"] == "command_ack"
    assert ack["channel"] == "siren"
    assert ack["action"] == "deactivate"
    # La ORDEN se ejecutó (la demanda manual se retiró)…
    assert ack["success"] is True
    # …y el RELÉ sigue energizado, que es lo que la spec exige transportar.
    assert ack["channel_state"]["channel"] == "siren"
    assert ack["channel_state"]["activated"] is True
    assert ack["channel_state"]["energized"] is True
    assert ack["channel_state"]["reason"] == "alert"
    assert ack["channel_state"]["alert_latched"] is True
    # Y el gabinete, en efecto, sigue sonando.
    assert gabinete.siren_sounding is True


def test_e2e_el_acuse_valida_contra_el_schema_comprometido(gabinete, settings):
    """Lo que sale del gabinete es exactamente lo que la nube acepta.

    `api/src/takab_api/contracts/loader.py` valida cada mensaje de ``takab/acks``
    contra este mismo archivo antes de que ningún handler lo toque: un campo que
    no valide aquí acaba en la DLQ allí.
    """
    dispatcher, cloud, security, _ = _cadena(gabinete, settings)
    gabinete.simulate_sasmex(True)
    _silenciar(dispatcher, security)
    _, ack = cloud.published[-1]

    schema = json.loads(SCHEMA.read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(ack)


def test_e2e_el_vector_compartido_es_el_que_produce_el_gabinete(gabinete, settings):
    """El payload que leen las patas 2 y 3 sale de AQUÍ, no de una copia a mano.

    Se normalizan sólo los campos volátiles (identificadores del comando y
    tiempos): todo lo demás —incluido el `channel_state` entero— tiene que
    coincidir byte a byte con el vector comprometido.
    """
    dispatcher, cloud, security, _ = _cadena(gabinete, settings)
    gabinete.simulate_sasmex(True)
    _silenciar(dispatcher, security, nonce="nonce-silencio-01")
    _, ack = cloud.published[-1]

    producido = dict(ack)
    producido["command_id"] = "cid-nonce-si"
    producido["nonce"] = "nonce-silencio-01"
    producido["latency_s"] = 0.0
    producido["executed_at"] = NOW.isoformat().replace("+00:00", "Z")

    esperado = json.loads(VECTOR.read_text())
    assert producido == esperado, (
        "el gabinete dejó de producir el vector compartido del E2E; si el cambio "
        f"es deliberado, actualiza {VECTOR} y las patas 2 y 3 que lo leen"
    )


def test_el_comando_rechazado_no_finge_conocer_el_rele(gabinete, settings):
    """Sin ejecución no hay arbitraje que declarar: el campo se queda vacío.

    Un ack de rechazo con estado de relé sería el gabinete opinando sobre algo
    que no midió en ese instante (regla de oro 7).
    """
    s = settings.model_copy(update={"command_enabled": False})
    security = SecurityManager(KEY, command_ttl_s=60.0)
    cloud = _FakeCloud()
    dispatcher = CommandDispatcher(
        s,
        security,
        ConfigStore(s, security=security, cache_path=None),
        ActuatorManager(RelayActuator(LocalGpioLink(gabinete))),
        cloud,
    )
    gabinete.simulate_sasmex(True)
    _silenciar(dispatcher, security)

    _, ack = cloud.published[-1]
    assert ack["success"] is False
    assert ack["channel_state"] is None


def test_la_ventana_del_acuse_no_depende_del_reloj_de_pared(gabinete, settings):
    """Guardia del arnés: el sobre firmado se acepta dentro de su ventana."""
    dispatcher, cloud, security, _ = _cadena(gabinete, settings)
    payload = {"channel": "siren", "action": "deactivate", "event_id": "EVT-1"}
    viejo = datetime.now(UTC) - timedelta(hours=1)
    dispatcher.on_command("takab/cmd/gw-test", _sobre_firmado(security, payload, "n-viejo", viejo))
    # Fuera de ventana: ni ejecuta ni ACKea (regla de oro 8).
    assert cloud.published == []
