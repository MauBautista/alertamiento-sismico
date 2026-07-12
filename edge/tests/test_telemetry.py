"""telemetry — batcheo escalonado por tier (T-1.56).

El criterio ancla del costo: 40 features de tier normal (10 s × 4 canales) salen
en UN solo publish (~97% menos requests SQS/IoT). Al escalar a watch+ el lote
acumulado sale ANTES del primer feature 1 Hz; el kill-switch restaura el camino
1 Hz exacto. Nada de esto toca la detección/actuación (wiring aparte).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from simulators.mqtt import FakeMqttTransport
from takab_edge.cloud import CloudConnector
from takab_edge.contracts import Feature1s, Tier
from takab_edge.telemetry import FEATURES_BATCH_TOPIC, FEATURES_TOPIC, FeatureBatcher

T0 = datetime(2026, 7, 12, 12, 0, 0, tzinfo=UTC)

CHANNELS = ("EHZ", "ENZ", "ENN", "ENE")


def _feature(i: int = 0, channel: str = "EHZ") -> Feature1s:
    return Feature1s(
        station="R4F74",
        channel=channel,
        window_start=T0 + timedelta(seconds=i),
        pga=0.001,
        pgv=0.01,
        rms=0.5,
        sta_lta=1.0,
    )


def _rig(settings, tmp_path, online: bool = True, **overrides):
    cfg = settings.model_copy(update=overrides) if overrides else settings
    transport = FakeMqttTransport(online=online)
    cloud = CloudConnector(cfg, transport=transport, spool_dir=str(tmp_path))
    if online:
        cloud.set_online(True)
    return FeatureBatcher(cfg, cloud=cloud), cloud, transport


def _published(transport: FakeMqttTransport, topic: str) -> list[dict]:
    return [payload for t, payload in transport.published if t == topic]


def test_tier_normal_40_features_un_solo_publish(settings, tmp_path):
    """ANCLA del costo: 10 s × 4 canales = 40 submits ⇒ 1 publish (vs 40)."""
    batcher, _cloud, transport = _rig(settings, tmp_path)
    for i in range(10):
        for channel in CHANNELS:
            batcher.submit(_feature(i, channel), Tier.NORMAL)
    assert transport.published == []  # nada sale hasta el timer/flush
    assert batcher.flush_pending() == 1
    batches = _published(transport, FEATURES_BATCH_TOPIC)
    assert len(batches) == 1
    assert len(batches[0]["features"]) == 40
    assert _published(transport, FEATURES_TOPIC) == []


def test_batch_max_dispara_flush_inmediato(settings, tmp_path):
    batcher, _cloud, transport = _rig(settings, tmp_path, cloud_features_batch_max=5)
    for i in range(5):
        batcher.submit(_feature(i), Tier.NORMAL)
    batches = _published(transport, FEATURES_BATCH_TOPIC)
    assert len(batches) == 1 and len(batches[0]["features"]) == 5
    assert batcher.pending == 0


def test_escalacion_por_features_drena_el_lote_antes_del_1hz(settings, tmp_path):
    """El contexto pre-evento (lote) sale ANTES del primer feature 1 Hz (FIFO)."""
    batcher, _cloud, transport = _rig(settings, tmp_path)
    for i in range(3):
        batcher.submit(_feature(i), Tier.NORMAL)
    batcher.submit(_feature(3), Tier.WATCH)
    topics = [t for t, _p in transport.published]
    assert topics == [FEATURES_BATCH_TOPIC, FEATURES_TOPIC]
    assert len(_published(transport, FEATURES_BATCH_TOPIC)[0]["features"]) == 3


def test_escalacion_sasmex_sin_feature_drena_el_lote(settings, tmp_path):
    """La ruta SASMEX (gpio) no trae feature: notify_tier drena el acumulado."""
    batcher, _cloud, transport = _rig(settings, tmp_path)
    for i in range(3):
        batcher.submit(_feature(i), Tier.NORMAL)
    batcher.notify_tier(Tier.EVACUATE_OR_HOLD)
    batches = _published(transport, FEATURES_BATCH_TOPIC)
    assert len(batches) == 1 and len(batches[0]["features"]) == 3


def test_desescalacion_vuelve_a_acumular(settings, tmp_path):
    batcher, _cloud, transport = _rig(settings, tmp_path)
    batcher.submit(_feature(0), Tier.WATCH)  # 1 Hz individual
    batcher.submit(_feature(1), Tier.NORMAL)
    batcher.submit(_feature(2), Tier.NORMAL)
    assert len(_published(transport, FEATURES_TOPIC)) == 1
    assert _published(transport, FEATURES_BATCH_TOPIC) == []
    assert batcher.pending == 2


def test_stop_offline_deja_el_lote_en_el_spool_durable(settings, tmp_path):
    """Shutdown limpio sin enlace: el acumulado cae al spool (cero pérdida)."""
    batcher, cloud, _transport = _rig(settings, tmp_path, online=False)
    batcher.start()
    for i in range(4):
        batcher.submit(_feature(i), Tier.NORMAL)
    batcher.stop()
    assert cloud.queued_by_topic(FEATURES_BATCH_TOPIC) == 1
    assert len(list(tmp_path.glob("*.json"))) == 1  # persistido en disco


def test_kill_switch_restaura_el_camino_1hz_exacto(settings, tmp_path):
    batcher, _cloud, transport = _rig(settings, tmp_path, cloud_features_batch_enabled=False)
    batcher.start()  # con kill-switch ni siquiera arranca el timer
    for i in range(5):
        batcher.submit(_feature(i), Tier.NORMAL)
    assert len(_published(transport, FEATURES_TOPIC)) == 5
    assert _published(transport, FEATURES_BATCH_TOPIC) == []
    batcher.stop()


def test_el_timer_publica_solo(settings, tmp_path):
    batcher, _cloud, transport = _rig(settings, tmp_path, cloud_features_batch_s=0.05)
    batcher.start()
    try:
        batcher.submit(_feature(0), Tier.NORMAL)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if _published(transport, FEATURES_BATCH_TOPIC):
                break
            time.sleep(0.01)
        assert len(_published(transport, FEATURES_BATCH_TOPIC)) == 1
    finally:
        batcher.stop()


def test_flush_trocea_en_lotes_del_contrato(settings, tmp_path):
    """Una carrera submit/timer puede pasar el buffer de batch_max: se trocea."""
    batcher, _cloud, transport = _rig(settings, tmp_path, cloud_features_batch_max=3)
    with batcher._lock:
        batcher._pending.extend(_feature(i) for i in range(7))
    assert batcher.flush_pending() == 3  # 3 + 3 + 1
    sizes = [len(b["features"]) for b in _published(transport, FEATURES_BATCH_TOPIC)]
    assert sizes == [3, 3, 1]


def test_un_cloud_roto_jamas_propaga_al_hilo_seedlink(settings, tmp_path):
    """La telemetría es reponible: un publish que lanza no rompe la detección."""

    class _BrokenCloud:
        def publish(self, topic, payload):
            raise RuntimeError("spool roto")

    batcher = FeatureBatcher(settings, cloud=_BrokenCloud())
    batcher.submit(_feature(0), Tier.NORMAL)  # acumula, sin tocar cloud
    batcher.submit(_feature(1), Tier.WATCH)  # flush + individual: ambos fallan
    batcher.notify_tier(Tier.WATCH)  # no lanza


def test_orden_de_submit_preservado_en_el_lote(settings, tmp_path):
    batcher, _cloud, transport = _rig(settings, tmp_path)
    for i in range(6):
        batcher.submit(_feature(i, CHANNELS[i % 4]), Tier.NORMAL)
    batcher.flush_pending()
    feats = _published(transport, FEATURES_BATCH_TOPIC)[0]["features"]
    starts = [f["window_start"] for f in feats]
    assert starts == sorted(starts)
    assert [f["channel"] for f in feats[:4]] == list(CHANNELS)
