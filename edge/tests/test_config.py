"""Configuración: identidad, perfil fail-safe por canal (SPOF-07) y umbrales."""

from __future__ import annotations

import pytest
from takab_edge.config import ConfigError, ConfigStore, EdgeSettings, load_settings
from takab_edge.contracts import ActuatorChannel, FailSafeMode
from takab_edge.security import SecurityManager


def test_defaults_are_dev_mode():
    s = load_settings()
    assert s.dev_mode is True
    assert s.sample_rate == 100.0
    assert s.seedlink_port == 18000


def test_failsafe_profile_matches_spof_07():
    s = load_settings()
    # Sirena NO (una falla NO la deja sonando); puerta NC (una falla LIBERA);
    # gas fail-close (una falla la CIERRA). Blueprint §4.7 SPOF-07.
    assert s.failsafe[ActuatorChannel.SIREN] is FailSafeMode.NORMALLY_OPEN
    assert s.failsafe[ActuatorChannel.DOOR_RETAINER] is FailSafeMode.NORMALLY_CLOSED
    assert s.failsafe[ActuatorChannel.GAS_VALVE] is FailSafeMode.FAIL_CLOSE


def test_env_prefix_overrides(monkeypatch):
    monkeypatch.setenv("TAKAB_EDGE_TENANT_ID", "tenant-42")
    monkeypatch.setenv("TAKAB_EDGE_DEV_MODE", "false")
    s = EdgeSettings()
    assert s.tenant_id == "tenant-42"
    assert s.dev_mode is False


def test_threshold_band_hospital_default():
    s = load_settings()
    assert s.thresholds.pga_watch_g == 0.040
    assert s.thresholds.pga_trip_g == 0.060


# --- Sync firmada, versionada y reversible (T-1.12) ---


def _store():
    security = SecurityManager(b"clave-de-config-inyectada")
    return ConfigStore(load_settings(), security=security), security


def _signed(security, tenant_id, version):
    raw = load_settings().model_copy(update={"tenant_id": tenant_id}).model_dump_json().encode()
    return raw, security.sign_config(raw, version)


def test_apply_signed_config_update_bumps_version():
    store, security = _store()
    raw, sig = _signed(security, "tenant-new", 1)
    assert store.apply_signed_update(raw, sig, 1) == 1
    assert store.current().tenant_id == "tenant-new"
    assert store.version == 1


def test_unsigned_config_update_is_rejected():
    store, security = _store()
    raw, _ = _signed(security, "attacker", 1)
    with pytest.raises(ConfigError):
        store.apply_signed_update(raw, "firma-invalida", 1)
    assert store.version == 0  # no se aplicó


def test_fail_closed_without_security_verifier():
    store = ConfigStore(load_settings())  # sin security → NO se puede verificar
    with pytest.raises(ConfigError):
        store.apply_signed_update(b'{"tenant_id":"x"}', "cualquier-firma", 1)


def test_replay_with_relabeled_version_is_rejected():
    # La firma cubre la versión: no se puede re-aplicar una config vieja como una versión mayor.
    store, security = _store()
    raw1, sig1 = _signed(security, "v1", 1)
    store.apply_signed_update(raw1, sig1, 1)
    with pytest.raises(ConfigError):
        store.apply_signed_update(raw1, sig1, 999)  # firmada para v1, re-etiquetada v999


def test_non_monotonic_version_is_rejected():
    store, security = _store()
    raw, sig = _signed(security, "v5", 5)
    store.apply_signed_update(raw, sig, 5)
    raw2, sig2 = _signed(security, "v5b", 5)
    with pytest.raises(ConfigError):
        store.apply_signed_update(raw2, sig2, 5)  # versión ya vista


def test_rollback_does_not_reopen_replay_window():
    store, security = _store()
    good_raw, good_sig = _signed(security, "buena", 1)
    store.apply_signed_update(good_raw, good_sig, 1)
    bad_raw, bad_sig = _signed(security, "mala", 2)
    store.apply_signed_update(bad_raw, bad_sig, 2)
    store.rollback()  # revierte el CONTENIDO a "buena"
    assert store.current().tenant_id == "buena"
    # El frame malo v2 re-entregado (at-least-once) NO se re-aplica (high_water sigue en 2).
    with pytest.raises(ConfigError):
        store.apply_signed_update(bad_raw, bad_sig, 2)
    assert store.current().tenant_id == "buena"


def test_local_panel_settings_defaults():
    """T-1.53: settings nuevos de la mini-consola LAN con defaults sensatos."""
    from takab_edge.config import load_settings

    s = load_settings()
    assert s.site_name == ""  # vacío ⇒ el panel muestra el gateway_id
    assert s.local_api_refresh_ms == 1000
    assert s.health_disk_path == "/"


# --- T-1.71: umbral por sitio aplicado EN VIVO al motor de reglas ---


def _signed_with_thresholds(security, version, **band):
    """EdgeSettings firmada con overrides de `thresholds` (config por sitio)."""
    base = load_settings()
    new = base.model_copy(update={"thresholds": base.thresholds.model_copy(update=band)})
    raw = new.model_dump_json().encode()
    return raw, security.sign_config(raw, version)


def _feat(pga):
    from datetime import UTC, datetime

    from takab_edge.contracts import Feature1s

    return Feature1s(
        station="R4F74",
        channel="ENZ",
        window_start=datetime(2026, 7, 6, 12, 0, tzinfo=UTC),
        pga=pga,
        pgv=0.0,
        rms=0.0,
        sta_lta=1.0,
        clipping=False,
        health_score=1.0,
    )


def test_config_listener_applies_thresholds_live_to_rule_engine():
    """Una config firmada por sitio baja el umbral y el motor lo adopta EN VIVO:
    una feature sub-umbral bajo la banda vieja SÍ dispara con la nueva."""
    from takab_edge.contracts import Tier
    from takab_edge.rules import RuleEngine, decide

    store, security = _store()
    rules = RuleEngine(store.current().thresholds)
    store.add_apply_listener(lambda cfg: rules.apply_thresholds(cfg.thresholds))

    # banda hospital por defecto: disparo 0.060g ⇒ 0.050g es sólo WATCH.
    assert decide({"ENZ": _feat(0.050)}, rules.thresholds)[0] is Tier.WATCH

    raw, sig = _signed_with_thresholds(security, 1, pga_watch_g=0.020, pga_trip_g=0.040)
    store.apply_signed_update(raw, sig, 1)

    # el motor adoptó la banda nueva sin reconstruirse ⇒ ahora 0.050g dispara.
    assert rules.thresholds.pga_trip_g == 0.040
    assert decide({"ENZ": _feat(0.050)}, rules.thresholds)[0] is Tier.RESTRICTED


def test_threshold_config_never_affects_sasmex_path():
    """Subir los umbrales por config JAMÁS silencia SASMEX (los ignora)."""
    from takab_edge.contracts import SasmexSignal, Tier
    from takab_edge.rules import RuleEngine

    store, security = _store()
    rules = RuleEngine(store.current().thresholds)
    store.add_apply_listener(lambda cfg: rules.apply_thresholds(cfg.thresholds))

    # umbrales absurdamente altos: nada instrumental dispararía.
    raw, sig = _signed_with_thresholds(security, 1, pga_trip_g=99.0, pgv_trip_cms=99.0)
    store.apply_signed_update(raw, sig, 1)
    assert rules.thresholds.pga_trip_g == 99.0

    decision = rules.evaluate_sasmex(SasmexSignal(active=True))
    assert decision is not None
    assert decision.tier is Tier.EVACUATE_OR_HOLD


def test_rollback_restores_previous_thresholds_to_rule_engine():
    """El rollback de config revierte también los umbrales del motor (listener)."""
    from takab_edge.rules import RuleEngine

    store, security = _store()
    rules = RuleEngine(store.current().thresholds)
    store.add_apply_listener(lambda cfg: rules.apply_thresholds(cfg.thresholds))
    default_trip = rules.thresholds.pga_trip_g

    raw, sig = _signed_with_thresholds(security, 1, pga_trip_g=0.030)
    store.apply_signed_update(raw, sig, 1)
    assert rules.thresholds.pga_trip_g == 0.030

    store.rollback()
    assert rules.thresholds.pga_trip_g == default_trip
