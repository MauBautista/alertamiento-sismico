"""Tests del simulador de flota (T-1.17 B6) — sin AWS, reloj inyectado."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from simulators.fleet import (
    CHANNELS,
    EVENTS_TOPIC,
    FEATURES_TOPIC,
    HEALTH_TOPIC,
    SCHEMAS_DIR,
    ContractDriftError,
    FleetSimulator,
    enrich,
    gateway_for,
    run_plan,
    site_for,
    validate_payload,
)

T0 = datetime(2026, 7, 6, 12, 0, 0, tzinfo=UTC)


class FakeClock:
    """Reloj monotónico simulado: sleep avanza el tiempo, sin dormir de verdad."""

    def __init__(self) -> None:
        self.t = 0.0

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        assert seconds >= 0
        self.t += seconds


def _collector():
    sent: list = []

    def send(batch):
        sent.extend(batch)
        return len(batch), 0

    return sent, send


def _independent_validate(schema_name: str, payload: dict) -> None:
    # Validación independiente del módulo (detecta que validate_payload se rompa)
    from jsonschema import Draft202012Validator

    schema = json.loads((SCHEMAS_DIR / f"{schema_name}.schema.json").read_text())
    Draft202012Validator(schema).validate(payload)


def test_payloads_validan_contra_schema():
    sim = FleetSimulator(sites=20, with_health=True, quake="SIM003", seed=7, t0=T0)
    batch = sim.window_batch(0)
    features = [m for m in batch if m.topic == FEATURES_TOPIC]
    health = [m for m in batch if m.topic == HEALTH_TOPIC]
    assert len(features) == 20 * len(CHANNELS)  # 80 features por ventana (G1)
    assert len(health) == 4  # heartbeat de los 4 gateways en la ventana 0
    for msg in features[:8]:
        _independent_validate("feature_1s", msg.payload)
        assert 1e-4 <= msg.payload["pga"] <= 1e-3  # ruido realista
        assert msg.payload["sta_lta"] < 1.5
        assert msg.payload["clipping"] is False
    for msg in health:
        _independent_validate("health_snapshot", msg.payload)


def test_contrato_derivado_falla_ruidosamente():
    with pytest.raises(ContractDriftError):
        validate_payload(FEATURES_TOPIC, {"station": "SIM001"})  # faltan campos requeridos


def test_enriquecimiento_exactamente_tres_meta():
    original = {"station": "SIM001", "pga": 0.0005}
    enriched = enrich(original, FEATURES_TOPIC, "gw-sim-0001", ts_ms=1234567890123)
    assert set(enriched) - set(original) == {"meta_principal", "meta_topic", "meta_ts_iot"}
    assert enriched["meta_principal"] == "gw-sim-0001"
    assert enriched["meta_topic"] == FEATURES_TOPIC
    assert enriched["meta_ts_iot"] == 1234567890123
    assert "meta_principal" not in original  # no muta la entrada


def test_reparto_estacion_gateway_convencion_fija():
    assert gateway_for("SIM001") == "gw-sim-0001"
    assert gateway_for("SIM005") == "gw-sim-0001"
    assert gateway_for("SIM006") == "gw-sim-0002"
    assert gateway_for("SIM007") == "gw-sim-0002"
    assert gateway_for("SIM011") == "gw-sim-0003"
    assert gateway_for("SIM016") == "gw-sim-0004"
    assert gateway_for("SIM020") == "gw-sim-0004"
    assert site_for("SIM007") == "site-sim-007"
    with pytest.raises(ValueError):
        gateway_for("SIM021")  # fuera de la flota fija
    with pytest.raises(ValueError):
        gateway_for("R4F74")  # el sitio real no es parte de la flota sim


def test_plan_de_tasa_sin_drift():
    clock = FakeClock()
    sim = FleetSimulator(sites=2, rate=2.0, seed=1, t0=T0)  # ventana cada 0.5 s
    sent, send = _collector()
    summary = run_plan(sim, duration_s=5.0, send=send, clock=clock.monotonic, sleep=clock.sleep)
    # 10 ventanas × 2 sitios × 4 canales = 80 mensajes; agenda anclada (última en t=4.5)
    assert summary.sent == 80
    assert summary.errors == 0
    assert clock.t == pytest.approx(4.5)
    assert all(m.topic == FEATURES_TOPIC for m in sent)


def test_health_cada_30s_por_gateway():
    clock = FakeClock()
    sim = FleetSimulator(sites=20, rate=1.0, with_health=True, seed=2, t0=T0)
    sent, send = _collector()
    run_plan(sim, duration_s=61.0, send=send, clock=clock.monotonic, sleep=clock.sleep)
    health = [m for m in sent if m.topic == HEALTH_TOPIC]
    assert len(health) == 3 * 4  # ventanas 0/30/60 × 4 gateways
    assert {m.thing for m in health} == {f"gw-sim-{n:04d}" for n in range(1, 5)}


def test_quake_escala_con_mismo_event_id():
    clock = FakeClock()
    sim = FleetSimulator(sites=20, rate=1.0, quake="SIM007", seed=3, t0=T0)
    sent, send = _collector()
    run_plan(sim, duration_s=10.0, send=send, clock=clock.monotonic, sleep=clock.sleep)
    events = [m for m in sent if m.topic == EVENTS_TOPIC]
    assert [m.payload["tier"] for m in events] == ["watch", "evacuate_or_hold"]
    assert len({m.payload["event_id"] for m in events}) == 1  # MISMO event_id: escalada E2E
    for msg in events:
        _independent_validate("local_event", msg.payload)
        assert msg.thing == "gw-sim-0002"  # SIM007 pertenece a gw-sim-0002
        assert msg.payload["tenant_id"] == "tenant-dev"
        assert msg.payload["site_id"] == "site-sim-007"
        assert msg.payload["source"] == "local_threshold"


# ---- [T-7.11] la red de demostración: flota de fichero y CERO eventos --------
#
# La invariante del bloque VIII, que no es una preferencia de estilo: un
# `LocalEvent` simulado ABRE UN INCIDENTE DE VERDAD en la nube, el motor de
# cuórum forma con estaciones que no midieron nada y la cascada de notificación
# manda una alerta real a los teléfonos del sitio. Un simulador que puede hacer
# eso no se deja corriendo como unidad de systemd.


def _demo() -> list:
    from simulators.fleet import Estacion

    return [
        Estacion("SIM101", "gw-sim-0101", "site-sim-101"),
        Estacion("SIM102", "gw-sim-0102", "site-sim-102"),
        Estacion("SIM103", "gw-sim-0103", "site-sim-103"),
    ]


def test_con_no_events_NINGUNA_ventana_publica_en_takab_events() -> None:
    """Se barre una corrida larga, no la primera ventana: el sismo simulado del
    modo normal aparece a los 2 y 5 segundos, no en el arranque."""
    sim = FleetSimulator(estaciones=_demo(), tenant="tenant-dev", no_events=True, with_health=True)
    topics = {m.topic for w in range(120) for m in sim.window_batch(w)}
    assert "takab/events" not in topics
    assert topics == {"takab/features", "takab/health"}, sorted(topics)


def test_la_prohibicion_LANZA_en_vez_de_tragarse_el_mensaje() -> None:
    """Un simulador que descarta en silencio esconde el fallo en vez de enseñarlo.

    Se ataca el punto por el que pasa TODO mensaje, que es donde vive la guarda.
    """
    sim = FleetSimulator(estaciones=_demo(), no_events=True)
    with pytest.raises(RuntimeError, match="takab/events"):
        sim._msg("takab/events", "gw-sim-0101", {"lo que sea": 1})


def test_no_events_y_quake_son_INCOMPATIBLES() -> None:
    """Pedir los dos es pedir cosas opuestas: el sismo ES un LocalEvent."""
    with pytest.raises(ValueError, match="incompatibles"):
        FleetSimulator(estaciones=_demo(), no_events=True, quake="SIM101")


def test_sin_la_bandera_el_simulador_SIGUE_pudiendo_emitir() -> None:
    """Control de ceguera: si `no_events` no cambiara nada, los tres de arriba
    pasarían igual sobre un simulador que nunca emite eventos."""
    sim = FleetSimulator(estaciones=_demo(), quake="SIM101")
    topics = {m.topic for w in range(120) for m in sim.window_batch(w)}
    assert "takab/events" in topics


def test_la_flota_de_FICHERO_no_inventa_el_gateway_ni_el_sitio() -> None:
    """La convención fija deriva gateway y sitio del índice; la red de
    demostración no cabe en ella y sus tres sitios son de tres tipos."""
    import json
    import tempfile
    from pathlib import Path

    from simulators.fleet import flota_de_fichero

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(
            {
                "tenant": "tenant-demo",
                "stations": [{"station": "SIM101", "gateway": "gw-x", "site": "sitio-x"}],
            },
            fh,
        )
        ruta = Path(fh.name)
    try:
        tenant, estaciones = flota_de_fichero(ruta)
    finally:
        ruta.unlink()
    assert tenant == "tenant-demo"
    assert (estaciones[0].gateway, estaciones[0].site) == ("gw-x", "sitio-x")


def test_una_estacion_SIN_gateway_se_rechaza_al_leer_el_fichero() -> None:
    """Publicaría con un `thing` vacío y la nube la rechazaría por principal
    desconocido — un error mucho más caro de leer que éste."""
    import json
    import tempfile
    from pathlib import Path

    from simulators.fleet import flota_de_fichero

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump({"stations": [{"station": "SIM101", "site": "sitio-x"}]}, fh)
        ruta = Path(fh.name)
    try:
        with pytest.raises(ValueError, match="gateway"):
            flota_de_fichero(ruta)
    finally:
        ruta.unlink()
