"""rules — tabla multi-canal, dedup por episodio, dropout, latencia y transición."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from takab_edge.config import ThresholdBand
from takab_edge.contracts import (
    ActuatorChannel,
    AlertSource,
    Feature1s,
    SasmexSignal,
    Tier,
    TierDecision,
)
from takab_edge.rules import RuleEngine, commands_for, decide, tier_from_sasmex

TH = ThresholdBand()  # hospital: watch 0.040g, trip 0.060g
START = datetime(2026, 7, 6, 12, 0, 0, tzinfo=UTC)


def _feature(pga=0.0, pgv=0.0, channel="ENZ", clipping=False, health=1.0, when=START) -> Feature1s:
    return Feature1s(
        station="R4F74",
        channel=channel,
        window_start=when,
        pga=pga,
        pgv=pgv,
        rms=0.0,
        sta_lta=1.0,
        clipping=clipping,
        health_score=health,
    )


class _Clock:
    """Reloj controlable para el dedup de episodio (reloj de recepción del Pi)."""

    def __init__(self, t: datetime) -> None:
        self.t = t

    def __call__(self) -> datetime:
        return self.t


# --- Tabla de verdad multi-canal ---


def test_decide_normal_below_watch():
    assert decide({"ENZ": _feature(pga=0.010)}, TH)[0] is Tier.NORMAL


def test_decide_watch_single_channel():
    assert decide({"ENZ": _feature(pga=0.050)}, TH)[0] is Tier.WATCH


def test_decide_restricted_single_trip():
    assert decide({"ENZ": _feature(pga=0.120)}, TH)[0] is Tier.RESTRICTED


def test_decide_evacuate_needs_two_trips():
    features = {
        "ENZ": _feature(pga=0.120, channel="ENZ"),
        "ENN": _feature(pga=0.120, channel="ENN"),
    }
    assert decide(features, TH)[0] is Tier.EVACUATE_OR_HOLD


def test_decide_manual_only_when_all_channels_dead():
    # Canales muertos (health<0.5, p.ej. dropout rms=0), NO saturados: sin dato fiable → humano.
    features = {
        "ENZ": _feature(health=0.0, channel="ENZ"),
        "ENN": _feature(health=0.2, channel="ENN"),
    }
    assert decide(features, TH)[0] is Tier.MANUAL_ONLY


def test_clipping_counts_as_trip_and_escalates():
    # Saturación del ADC = sacudida ≥ fondo de escala → cuenta como DISPARO (fail-loud),
    # nunca de-escala (antes caía a restricted/manual_only = defecto crítico corregido).
    mixed = {
        "ENZ": _feature(pga=0.120, channel="ENZ"),
        "ENN": _feature(pga=0.0, clipping=True, health=0.5, channel="ENN"),
    }
    assert decide(mixed, TH)[0] is Tier.EVACUATE_OR_HOLD  # 1 limpio + 1 saturado = 2 disparos
    all_saturated = {
        "ENZ": _feature(clipping=True, health=0.5, channel="ENZ"),
        "ENN": _feature(clipping=True, health=0.5, channel="ENN"),
        "ENE": _feature(clipping=True, health=0.5, channel="ENE"),
    }
    assert decide(all_saturated, TH)[0] is Tier.EVACUATE_OR_HOLD  # NO manual_only


def test_all_five_tiers_reachable():
    tiers = {
        decide({"ENZ": _feature(pga=0.0)}, TH)[0],
        decide({"ENZ": _feature(pga=0.050)}, TH)[0],
        decide({"ENZ": _feature(pga=0.120)}, TH)[0],
        decide({"A": _feature(pga=0.12, channel="A"), "B": _feature(pga=0.12, channel="B")}, TH)[0],
        decide({"ENZ": _feature(health=0.0)}, TH)[0],  # canal muerto → manual_only
    }
    assert tiers == set(Tier)


def test_sasmex_decision_is_evacuate_from_sasmex_source():
    decision = tier_from_sasmex(SasmexSignal(active=True))
    assert decision.tier is Tier.EVACUATE_OR_HOLD
    assert decision.source is AlertSource.SASMEX


# --- Mapeo tier → comandos ---


def test_commands_for_evacuate_sounds_siren_and_extended_sequence():
    decision = TierDecision(tier=Tier.EVACUATE_OR_HOLD, source=AlertSource.THRESHOLD)
    channels = {c.channel for c in commands_for(decision)}
    assert channels == {
        ActuatorChannel.SIREN,
        ActuatorChannel.STROBE,
        ActuatorChannel.ELEVATOR,
        ActuatorChannel.DOOR_RETAINER,
        ActuatorChannel.GAS_VALVE,
    }


def test_commands_for_restricted_and_normal():
    restricted = commands_for(TierDecision(tier=Tier.RESTRICTED, source=AlertSource.THRESHOLD))
    assert {c.channel for c in restricted} == {
        ActuatorChannel.ELEVATOR,
        ActuatorChannel.DOOR_RETAINER,
    }
    assert commands_for(TierDecision(tier=Tier.NORMAL, source=AlertSource.THRESHOLD)) == []


# --- Motor: multi-canal, dedup, dropout, latencia, transición ---


def test_engine_corroborates_across_channels():
    engine = RuleEngine(TH)
    assert engine.evaluate_features(_feature(pga=0.12, channel="ENZ")).tier is Tier.RESTRICTED
    assert engine.evaluate_features(_feature(pga=0.12, channel="ENN")).tier is Tier.EVACUATE_OR_HOLD


def test_engine_drops_stale_channel_on_dropout():
    engine = RuleEngine(TH, staleness_s=3.0)
    engine.evaluate_features(_feature(pga=0.12, channel="ENZ", when=START))
    engine.evaluate_features(_feature(pga=0.12, channel="ENN", when=START))  # evacuate
    # 10 s después, un canal normal; ENZ/ENN quedaron obsoletos (>3 s) → caen.
    later = engine.evaluate_features(
        _feature(pga=0.0, channel="EHZ", when=START + timedelta(seconds=10))
    )
    assert later.tier is Tier.NORMAL


def test_engine_ignores_inactive_and_test_sasmex():
    engine = RuleEngine(TH)
    assert engine.evaluate_sasmex(SasmexSignal(active=False)) is None
    assert engine.evaluate_sasmex(SasmexSignal(active=True, is_test=True)) is None
    assert engine.evaluate_sasmex(SasmexSignal(active=True)).tier is Tier.EVACUATE_OR_HOLD


def test_sasmex_and_threshold_same_quake_share_event_id():
    # Doble disparo del MISMO sismo (SASMEX + umbral local) = UN evento, no dos.
    clock = _Clock(START)
    engine = RuleEngine(TH, dedup_window_s=30.0, clock=clock)
    sasmex = engine.evaluate_sasmex(SasmexSignal(active=True))
    clock.t = START + timedelta(seconds=2)  # 2 s después (mismo episodio)
    threshold = engine.evaluate_features(_feature(pga=0.12, channel="ENZ"))
    assert sasmex.event_id == threshold.event_id


def test_distinct_events_get_distinct_ids():
    clock = _Clock(START)
    engine = RuleEngine(TH, dedup_window_s=30.0, clock=clock)
    first = engine.evaluate_sasmex(SasmexSignal(active=True))
    clock.t = START + timedelta(seconds=60)  # 60 s después (nuevo evento)
    later = engine.evaluate_sasmex(SasmexSignal(active=True))
    assert first.event_id != later.event_id


def test_dedup_uses_reception_clock_not_payload_time():
    # Aunque los timestamps del payload estén desfasados (Pi sin NTP: received_at de pared
    # muy atrasado vs window_start del Shake), el episodio se correlaciona con el reloj de
    # RECEPCIÓN del Pi → el mismo sismo sigue siendo UN evento (hallazgo cross-reloj).
    clock = _Clock(START)
    engine = RuleEngine(TH, dedup_window_s=30.0, clock=clock)
    sasmex = engine.evaluate_sasmex(
        SasmexSignal(active=True, received_at=datetime(2000, 1, 1, tzinfo=UTC))
    )
    clock.t = START + timedelta(seconds=3)
    threshold = engine.evaluate_features(
        _feature(pga=0.12, channel="ENZ", when=START + timedelta(seconds=3))
    )
    assert sasmex.event_id == threshold.event_id


def test_decision_latency_under_budget():
    engine = RuleEngine(TH)
    engine.evaluate_features(_feature(pga=0.12))
    assert engine.last_latency_s is not None
    assert engine.last_latency_s < 0.2  # presupuesto §4.3 (con margen; relé real en hardware)


def test_tier_transition_logged_once_per_change(caplog):
    engine = RuleEngine(TH)
    with caplog.at_level(logging.WARNING, logger="takab_edge.rules"):
        engine.evaluate_features(_feature(pga=0.0, channel="ENZ", when=START))  # →normal
        engine.evaluate_features(
            _feature(pga=0.0, channel="ENZ", when=START + timedelta(seconds=1))
        )
        engine.evaluate_features(
            _feature(pga=0.12, channel="ENZ", when=START + timedelta(seconds=2))
        )
    transitions = [r for r in caplog.records if "transición de tier" in r.getMessage()]
    assert len(transitions) == 2  # None→normal y normal→restricted; el normal repetido NO re-loguea
