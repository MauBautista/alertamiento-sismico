"""rules — tabla de verdad determinista de tiers y mapeo tier→comandos."""

from __future__ import annotations

from datetime import UTC, datetime

from takab_edge.config import ThresholdBand
from takab_edge.contracts import (
    ActuatorChannel,
    AlertSource,
    Feature1s,
    SasmexSignal,
    Tier,
)
from takab_edge.rules import (
    RuleEngine,
    commands_for,
    tier_from_features,
    tier_from_sasmex,
)

TH = ThresholdBand()  # hospital: watch 0.040g, trip 0.060g
START = datetime(2026, 1, 1, tzinfo=UTC)


def _feature(pga=0.0, pgv=0.0, clipping=False, health=1.0) -> Feature1s:
    return Feature1s(
        station="TAKAB",
        channel="ENZ",
        window_start=START,
        pga=pga,
        pgv=pgv,
        rms=0.0,
        sta_lta=1.0,
        clipping=clipping,
        health_score=health,
    )


def test_tier_normal_below_watch():
    assert tier_from_features(_feature(pga=0.010), TH).tier is Tier.NORMAL


def test_tier_watch_between_bands():
    assert tier_from_features(_feature(pga=0.050), TH).tier is Tier.WATCH


def test_tier_evacuate_above_trip():
    assert tier_from_features(_feature(pga=0.120), TH).tier is Tier.EVACUATE_OR_HOLD


def test_tier_manual_only_on_degraded_sensor():
    assert tier_from_features(_feature(pga=0.120, clipping=True), TH).tier is Tier.MANUAL_ONLY
    assert tier_from_features(_feature(pga=0.120, health=0.2), TH).tier is Tier.MANUAL_ONLY


def test_sasmex_decision_is_evacuate_from_sasmex_source():
    decision = tier_from_sasmex(SasmexSignal(active=True))
    assert decision.tier is Tier.EVACUATE_OR_HOLD
    assert decision.source is AlertSource.SASMEX


def test_commands_for_evacuate_covers_extended_sequence():
    # Ruta instrumental (umbral, sin SASMEX): debe incluir la sirena general
    # (blueprint §4.5) — sin ella un sismo local detectado por umbral no alertaría.
    decision = tier_from_features(_feature(pga=0.120), TH)
    assert decision.source is AlertSource.THRESHOLD
    channels = {c.channel for c in commands_for(decision)}
    assert channels == {
        ActuatorChannel.SIREN,
        ActuatorChannel.STROBE,
        ActuatorChannel.ELEVATOR,
        ActuatorChannel.DOOR_RETAINER,
        ActuatorChannel.GAS_VALVE,
    }


def test_commands_for_normal_is_empty():
    assert commands_for(tier_from_features(_feature(pga=0.0), TH)) == []


def test_engine_ignores_inactive_and_test_sasmex():
    engine = RuleEngine(TH)
    assert engine.evaluate_sasmex(SasmexSignal(active=False)) is None
    assert engine.evaluate_sasmex(SasmexSignal(active=True, is_test=True)) is None
    assert engine.evaluate_sasmex(SasmexSignal(active=True)).tier is Tier.EVACUATE_OR_HOLD
