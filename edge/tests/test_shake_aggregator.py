"""ShakeAggregator (T-2.19) — agregado rodante de sacudida EN RAM, solo para el panel.

NO es logging por intervalo (regla de oro 10): nada se publica ni persiste; se
pierde al reiniciar A PROPÓSITO y el panel lo rotula DESDE EL ARRANQUE.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from takab_edge.contracts import AlertSource, Feature1s, Tier, TierDecision
from takab_edge.signal.aggregate import ShakeAggregator

T0 = datetime(2026, 7, 30, 0, 0, 0, tzinfo=UTC)
SENS = 2.6007802e-6  # m/s² por count (AM.R4F74, T-1.41)


def _feature(
    channel: str = "ENZ",
    hours: float = 0.0,
    minutes: float = 0.0,
    pga: float = 0.001,
    pgv: float = 0.1,
    rms: float = 400.0,
) -> Feature1s:
    return Feature1s(
        station="R4F74",
        channel=channel,
        window_start=T0 + timedelta(hours=hours, minutes=minutes),
        pga=pga,
        pgv=pgv,
        rms=rms,
        sta_lta=1.0,
    )


def _decision(tier: Tier) -> TierDecision:
    return TierDecision(
        event_id="evt-test", tier=tier, source=AlertSource.THRESHOLD, severity=0.1, reasons=[]
    )


def _rms_for_mg(mg: float) -> float:
    return mg * 9.80665 / 1000.0 / SENS


def test_hour_buckets_rotate_by_time_and_never_exceed_24():
    agg = ShakeAggregator()
    agg.observe_feature(_feature(hours=0, pga=0.9, pgv=9.0), SENS)  # el máximo VIEJO
    for h in range(1, 27):
        agg.observe_feature(_feature(hours=h), SENS)
    section = agg.snapshot()["by_channel"]["ENZ"]
    assert len(section["hourly"]) <= 24  # rotan por tiempo, no crecen sin límite
    # El máximo de 24 h ya NO incluye el bucket podado de la hora 0.
    assert section["pga_g_max_24h"] == 0.001
    oldest = datetime.fromisoformat(section["hourly"][0]["hour_start"])
    assert oldest > T0  # la hora 0 se cayó
    # Orden: del más viejo al más nuevo.
    starts = [b["hour_start"] for b in section["hourly"]]
    assert starts == sorted(starts)


def test_hourly_starts_short_after_boot():
    """Recién arrancado hay UN bucket, no 24 vacíos fingiendo continuidad."""
    agg = ShakeAggregator()
    agg.observe_feature(_feature(hours=0), SENS)
    assert len(agg.snapshot()["by_channel"]["ENZ"]["hourly"]) == 1
    agg.observe_feature(_feature(hours=1), SENS)
    assert len(agg.snapshot()["by_channel"]["ENZ"]["hourly"]) == 2


def test_hour_bucket_keeps_the_maximum():
    agg = ShakeAggregator()
    agg.observe_feature(_feature(hours=0, minutes=1, pga=0.010, pgv=1.0), SENS)
    agg.observe_feature(_feature(hours=0, minutes=2, pga=0.030, pgv=3.0), SENS)
    agg.observe_feature(_feature(hours=0, minutes=3, pga=0.020, pgv=2.0), SENS)
    bucket = agg.snapshot()["by_channel"]["ENZ"]["hourly"][0]
    assert bucket["pga_g_max"] == 0.030
    assert bucket["pgv_cms_max"] == 3.0


def test_events_by_tier_counts_transitions_not_ticks():
    agg = ShakeAggregator()
    for _ in range(5):
        agg.observe_decision(_decision(Tier.NORMAL))  # ticks en normal: NO son eventos
    assert sum(agg.snapshot()["events_by_tier"].values()) == 0
    agg.observe_decision(_decision(Tier.WATCH))
    agg.observe_decision(_decision(Tier.WATCH))  # tick sostenido: sigue siendo UNO
    agg.observe_decision(_decision(Tier.NORMAL))  # el re-arme sí es una transición
    events = agg.snapshot()["events_by_tier"]
    assert events["watch"] == 1
    assert events["normal"] == 1
    assert sum(events.values()) == 2


def test_events_by_tier_always_has_five_keys():
    events = ShakeAggregator().snapshot()["events_by_tier"]
    assert set(events) == {"normal", "watch", "restricted", "evacuate_or_hold", "manual_only"}
    assert all(v == 0 for v in events.values())


def test_noise_floor_minute_min_and_trend_rising_falling_stable():
    # <2 minutos de datos ⇒ stable (sin inventar tendencia).
    agg = ShakeAggregator()
    agg.observe_feature(_feature(minutes=0, rms=_rms_for_mg(0.8)), SENS)
    noise = agg.snapshot()["noise_floor"]
    assert noise["trend"] == "stable"
    assert noise["baseline_low_mg"] == 0.6
    assert noise["baseline_high_mg"] == 1.1
    # El MIN por minuto ignora los picos dentro del minuto (es piso, no promedio).
    agg.observe_feature(_feature(minutes=0, rms=_rms_for_mg(2.0)), SENS)
    assert agg.snapshot()["noise_floor"]["current_mg"] < 1.0

    # Sube el piso en la segunda mitad ⇒ rising.
    rising = ShakeAggregator()
    for m in range(45):
        mg = 0.7 if m < 30 else 1.4
        rising.observe_feature(_feature(minutes=m, rms=_rms_for_mg(mg)), SENS)
    assert rising.snapshot()["noise_floor"]["trend"] == "rising"

    # Baja ⇒ falling.
    falling = ShakeAggregator()
    for m in range(45):
        mg = 1.4 if m < 30 else 0.7
        falling.observe_feature(_feature(minutes=m, rms=_rms_for_mg(mg)), SENS)
    assert falling.snapshot()["noise_floor"]["trend"] == "falling"

    # Piso plano ⇒ stable.
    flat = ShakeAggregator()
    for m in range(45):
        flat.observe_feature(_feature(minutes=m, rms=_rms_for_mg(0.8)), SENS)
    assert flat.snapshot()["noise_floor"]["trend"] == "stable"


def test_noise_floor_ignores_geophone_channels():
    """El piso en mg viene del MEMS (EN*); el geófono (EH*) no es aceleración."""
    agg = ShakeAggregator()
    agg.observe_feature(_feature(channel="EHZ", rms=_rms_for_mg(50.0)), SENS)
    assert agg.snapshot()["noise_floor"]["current_mg"] is None


def test_snapshot_does_not_mutate_state():
    agg = ShakeAggregator()
    agg.observe_feature(_feature(hours=0, pga=0.02), SENS)
    agg.observe_decision(_decision(Tier.WATCH))
    assert agg.snapshot() == agg.snapshot()


# --- Cableado en el supervisor y el panel (secciones defensivas) ---------------


def _feed_packet(supervisor, channel: str = "ENZ", amplitude: int = 7) -> None:
    from takab_edge.contracts import WaveformPacket, utcnow

    supervisor.seedlink.feed(
        WaveformPacket(
            station="R4F74", channel=channel, starttime=utcnow(), samples=[0, amplitude] * 50
        )
    )


def test_status_includes_shake_history(supervisor):
    _feed_packet(supervisor)
    section = supervisor.local_api.status()["shake_history"]
    assert "ENZ" in section["by_channel"]
    assert len(section["by_channel"]["ENZ"]["hourly"]) >= 1
    assert set(section["events_by_tier"]) == {
        "normal",
        "watch",
        "restricted",
        "evacuate_or_hold",
        "manual_only",
    }
    assert section["noise_floor"]["baseline_low_mg"] == 0.6
    assert "since" in section


def test_sasmex_transition_counts_once_in_events_by_tier(supervisor):
    """La ruta SASMEX (no pasa por _on_packet) también cuenta — y UNA sola vez."""
    supervisor.gpio.simulate_sasmex(active=True)
    events = supervisor.local_api.status()["shake_history"]["events_by_tier"]
    assert events["evacuate_or_hold"] == 1


def test_shake_history_null_when_signal_broken(supervisor, monkeypatch):
    monkeypatch.setattr(supervisor.local_api, "_signal", None)
    import json as _json

    code, body = _get(supervisor.local_api, "/api/status")
    assert code == 200
    assert _json.loads(body)["shake_history"] is None


def test_shake_aggregation_publishes_nothing_to_cloud(supervisor, monkeypatch):
    """Regla de oro 10: agregado EN MEMORIA para el panel — cero publicaciones."""
    leaked = []
    monkeypatch.setattr(supervisor.cloud, "publish", lambda *a, **k: leaked.append(a))
    agg = supervisor.signal.aggregate
    agg.observe_feature(_feature(), SENS)
    agg.observe_decision(_decision(Tier.WATCH))
    for _ in range(5):
        supervisor.local_api.status()
        agg.snapshot()
    assert leaked == []


def _get(dashboard, path: str):
    import urllib.request

    _host, port = dashboard.address
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as response:
        return response.status, response.read()
