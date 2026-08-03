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


# --- T-2.34: la config firmada SOBREVIVE reinicios (caché en disco) ---


def _cached_store(tmp_path, *, key: bytes = b"clave-de-config-inyectada"):
    from takab_edge.security import SecurityManager as _SM

    security = _SM(key)
    path = str(tmp_path / "config-cache.json")
    return ConfigStore(load_settings(), security=security, cache_path=path), security, path


def test_applied_config_survives_restart(tmp_path):
    """El corte de energía del 2026-08-03 lo demostró en vivo: al reiniciar, el
    edge arrancaba en v0 y la nube no re-publica si nada cambió — umbrales,
    equipamiento y command_enabled REGRESABAN a defaults. La caché lo cierra."""
    store, security, path = _cached_store(tmp_path)
    store.start()
    raw = (
        load_settings()
        .model_copy(update={"tenant_id": "tenant-persistido", "command_enabled": True})
        .model_dump_json()
        .encode()
    )
    store.apply_signed_update(raw, security.sign_config(raw, 14), 14)
    store.stop()

    reborn = ConfigStore(load_settings(), security=security, cache_path=path)
    assert reborn.version == 0  # antes de arrancar: nada aplicado
    reborn.start()
    assert reborn.version == 14
    assert reborn.current().tenant_id == "tenant-persistido"
    assert reborn.current().command_enabled is True


def test_boot_restore_notifies_listeners(tmp_path):
    """La restauración notifica a los listeners (umbrales→rules, location):
    los módulos vivos adoptan la config restaurada igual que una sync."""
    store, security, path = _cached_store(tmp_path)
    store.start()
    raw = load_settings().model_copy(update={"tenant_id": "avisado"}).model_dump_json().encode()
    store.apply_signed_update(raw, security.sign_config(raw, 3), 3)

    reborn = ConfigStore(load_settings(), security=security, cache_path=path)
    seen: list[str] = []
    reborn.add_apply_listener(lambda cfg: seen.append(cfg.tenant_id))
    reborn.start()
    assert seen == ["avisado"]


def test_tampered_cache_boots_with_defaults(tmp_path):
    store, security, path = _cached_store(tmp_path)
    store.start()
    raw = load_settings().model_copy(update={"tenant_id": "legitimo"}).model_dump_json().encode()
    store.apply_signed_update(raw, security.sign_config(raw, 5), 5)

    import json as _json
    from pathlib import Path as _Path

    doc = _json.loads(_Path(path).read_text())
    doc["payload"] = doc["payload"].replace("legitimo", "atacante")  # sin re-firmar
    _Path(path).write_text(_json.dumps(doc))

    reborn = ConfigStore(load_settings(), security=security, cache_path=path)
    reborn.start()
    assert reborn.version == 0  # fail-closed: defaults de arranque
    assert reborn.current().tenant_id != "atacante"


def test_cache_with_rotated_key_boots_with_defaults(tmp_path):
    store, security, path = _cached_store(tmp_path)
    store.start()
    raw = load_settings().model_dump_json().encode()
    store.apply_signed_update(raw, security.sign_config(raw, 5), 5)

    from takab_edge.security import SecurityManager as _SM

    reborn = ConfigStore(load_settings(), security=_SM(b"clave-rotada-distinta"), cache_path=path)
    reborn.start()
    assert reborn.version == 0


def test_corrupt_or_missing_cache_boots_with_defaults(tmp_path):
    from pathlib import Path as _Path

    path = str(tmp_path / "config-cache.json")
    security = SecurityManager(b"clave-de-config-inyectada")
    missing = ConfigStore(load_settings(), security=security, cache_path=path)
    missing.start()
    assert missing.version == 0

    _Path(path).write_text("esto{no-es-json")
    corrupt = ConfigStore(load_settings(), security=security, cache_path=path)
    corrupt.start()
    assert corrupt.version == 0


def test_replay_rejected_across_restart(tmp_path):
    """[SEGURIDAD] Antes de T-2.34 el high_water moría con el proceso: un
    reinicio reabría la ventana de replay de CUALQUIER config vieja firmada."""
    store, security, path = _cached_store(tmp_path)
    store.start()
    raw = load_settings().model_dump_json().encode()
    sig = security.sign_config(raw, 7)
    store.apply_signed_update(raw, sig, 7)

    reborn = ConfigStore(load_settings(), security=security, cache_path=path)
    reborn.start()
    with pytest.raises(ConfigError):
        reborn.apply_signed_update(raw, sig, 7)  # replay del mismo frame tras reboot


def test_rollback_persists_reverted_config_without_lowering_high_water(tmp_path):
    store, security, path = _cached_store(tmp_path)
    store.start()
    raw1 = load_settings().model_copy(update={"tenant_id": "buena"}).model_dump_json().encode()
    store.apply_signed_update(raw1, security.sign_config(raw1, 1), 1)
    raw2 = load_settings().model_copy(update={"tenant_id": "mala"}).model_dump_json().encode()
    sig2 = security.sign_config(raw2, 2)
    store.apply_signed_update(raw2, sig2, 2)
    store.rollback()
    assert store.current().tenant_id == "buena"

    reborn = ConfigStore(load_settings(), security=security, cache_path=path)
    reborn.start()
    assert reborn.current().tenant_id == "buena"  # el reboot NO resucita la mala
    assert reborn.version == 1
    with pytest.raises(ConfigError):
        reborn.apply_signed_update(raw2, sig2, 2)  # high_water sobrevivió al reboot


def test_store_without_cache_path_behaves_as_before(tmp_path):
    """Sin cache_path (unit tests, dev suelto) nada se escribe ni se lee."""
    store, security = _store()
    store.start()
    raw = load_settings().model_dump_json().encode()
    store.apply_signed_update(raw, security.sign_config(raw, 1), 1)
    assert list(tmp_path.iterdir()) == []


# --- T-2.31: perfil de equipamiento por sitio ---


def test_equipment_defaults_to_all_installed():
    """Sin declarar nada, TODO instalado: la flota existente no cambia de conducta."""
    s = load_settings()
    assert s.equipment.model_dump() == {
        "siren": True,
        "strobe": True,
        "gas_valve": True,
        "elevator": True,
        "door_retainer": True,
    }
    assert ActuatorChannel.GAS_VALVE in s.equipment.installed()


def test_partial_config_doc_fills_equipment_with_true():
    """Un doc firmado parcial completa con true (compat con nubes viejas sin la clave)."""
    s = EdgeSettings.model_validate_json('{"equipment": {"gas_valve": false}}')
    assert s.equipment.gas_valve is False
    assert s.equipment.siren is True
    assert ActuatorChannel.GAS_VALVE not in s.equipment.installed()
    assert ActuatorChannel.SIREN in s.equipment.installed()


def test_signed_update_applies_equipment_hot():
    """El equipamiento llega FUSIONADO en el doc firmado y aplica en caliente."""
    from takab_edge.config import EquipmentProfile

    store, security = _store()
    raw = (
        load_settings()
        .model_copy(update={"equipment": EquipmentProfile(gas_valve=False, elevator=False)})
        .model_dump_json()
        .encode()
    )
    store.apply_signed_update(raw, security.sign_config(raw, 1), 1)
    equip = store.current().equipment
    assert equip.gas_valve is False and equip.elevator is False
    assert equip.siren is True


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
