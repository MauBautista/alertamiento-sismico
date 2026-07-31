"""SiteLocationCache (T-2.20) — el gabinete por fin sabe dónde está.

Diseño CORREGIDO del backlog: la fuente de verdad es `edge.env`; el sync firmado
solo COMPLETA (overlay de solo-no-nulos — `apply_signed_update` es reemplazo
total y la nube publica documentos parciales por diseño); la caché estrecha en
disco sobrevive reinicios sin WAN. `null` ⇒ SIN UBICACIÓN PROVISIONADA: jamás
un punto inventado.
"""

from __future__ import annotations

import json

from takab_edge.config import NeighborStation, SiteLocationCache, load_settings

LAT, LON = 19.0433, -98.1980  # Puebla (donde vive el gabinete real)


def _settings(tmp_path, **over):
    cache = tmp_path / "site_location.json"
    settings = load_settings().model_copy(
        update={"site_location_cache": str(cache), "local_api_port": 0, **over}
    )
    return settings, cache


def test_env_settings_are_source_of_truth(tmp_path):
    settings, cache = _settings(tmp_path, site_lat=LAT, site_lon=LON)
    # Una caché vieja con OTRO punto no puede pisar lo que declara edge.env.
    cache.write_text(json.dumps({"site_lat": 0.0, "site_lon": 0.0, "neighbors": []}))
    current = SiteLocationCache(settings).current()
    assert current["site_lat"] == LAT
    assert current["site_lon"] == LON


def test_partial_signed_config_cannot_null_out_location(tmp_path):
    """El crux de T-2.20: un sync PARCIAL (lat/lon en None) jamás borra lo sabido."""
    settings, _ = _settings(tmp_path, site_lat=LAT, site_lon=LON)
    location = SiteLocationCache(settings)
    partial, _ = _settings(tmp_path)  # documento sin ubicación (None/None)
    location.on_config_applied(partial)
    current = location.current()
    assert current["site_lat"] == LAT and current["site_lon"] == LON


def test_cache_written_only_when_learning_non_null(tmp_path):
    settings, cache = _settings(tmp_path)
    location = SiteLocationCache(settings)
    nothing, _ = _settings(tmp_path)
    location.on_config_applied(nothing)
    assert not cache.exists()  # nada aprendido ⇒ nada escrito (por evento, no por tick)
    learned, _ = _settings(tmp_path, site_lat=LAT, site_lon=LON)
    location.on_config_applied(learned)
    data = json.loads(cache.read_text())
    assert data["site_lat"] == LAT and data["site_lon"] == LON
    assert cache.stat().st_mode & 0o777 == 0o644
    # Re-aplicar el MISMO par no re-escribe (no es «distinto»).
    cache.unlink()
    location.on_config_applied(learned)
    assert not cache.exists()


def test_cache_survives_reboot_without_wan(tmp_path):
    settings, cache = _settings(tmp_path)
    SiteLocationCache(settings).on_config_applied(
        _settings(tmp_path, site_lat=LAT, site_lon=LON)[0]
    )
    assert cache.exists()
    # Segunda vida del proceso: sin WAN, sin sync — la ubicación sigue viva.
    reborn, _ = _settings(tmp_path)
    current = SiteLocationCache(reborn).current()
    assert current["site_lat"] == LAT and current["site_lon"] == LON


def test_corrupt_cache_is_ignored(tmp_path):
    settings, cache = _settings(tmp_path)
    cache.write_text("esto{no-es-json")
    current = SiteLocationCache(settings).current()
    assert current == {"site_lat": None, "site_lon": None, "neighbors": []}


def test_neighbors_last_non_empty_overlay(tmp_path):
    settings, _ = _settings(
        tmp_path,
        site_lat=LAT,
        site_lon=LON,
        neighbors=[NeighborStation(code="AM.R0001", lat=19.1, lon=-98.3, distance_km=17.0)],
    )
    location = SiteLocationCache(settings)
    empty, _ = _settings(tmp_path)  # parcial sin vecinos: NO borra la lista
    location.on_config_applied(empty)
    assert len(location.current()["neighbors"]) == 1
    two, _ = _settings(
        tmp_path,
        neighbors=[
            NeighborStation(code="AM.R0001", lat=19.1, lon=-98.3),
            NeighborStation(code="AM.R0002", lat=18.9, lon=-98.0),
        ],
    )
    location.on_config_applied(two)
    assert [n["code"] for n in location.current()["neighbors"]] == ["AM.R0001", "AM.R0002"]


def test_site_location_parses_from_env(monkeypatch):
    """El formato documentado en el runbook de alta funciona tal cual."""
    monkeypatch.setenv("TAKAB_EDGE_SITE_LAT", "19.0433")
    monkeypatch.setenv("TAKAB_EDGE_SITE_LON", "-98.1980")
    monkeypatch.setenv(
        "TAKAB_EDGE_NEIGHBORS",
        '[{"code":"AM.R0001","lat":19.10,"lon":-98.30,"distance_km":17.0}]',
    )
    settings = load_settings()
    assert settings.site_lat == LAT and settings.site_lon == LON
    assert settings.neighbors[0].code == "AM.R0001"
    assert settings.neighbors[0].distance_km == 17.0


# --- Cableado: supervisor + panel ----------------------------------------------


def test_status_site_location_null_without_provisioning(supervisor):
    status = supervisor.local_api.status()
    assert status["site_lat"] is None  # SIN UBICACIÓN PROVISIONADA, sin invento
    assert status["site_lon"] is None
    assert status["neighbors"] == []


def test_signed_config_teaches_location_live(supervisor, tmp_path):
    """El sync firmado enseña la ubicación EN VIVO y el panel la refleja ya."""
    updated = supervisor.settings.model_copy(deep=True)
    updated.site_lat, updated.site_lon = LAT, LON
    updated.site_location_cache = str(tmp_path / "loc.json")  # escribible en test
    raw = updated.model_dump_json().encode()
    supervisor.config.apply_signed_update(raw, supervisor.security.sign_config(raw, 3), 3)
    status = supervisor.local_api.status()
    assert status["site_lat"] == LAT and status["site_lon"] == LON


def test_neighbors_do_not_affect_actuation(settings):
    """Criterio anti-quórum (SPOF-01): las vecinas JAMÁS tocan la actuación."""
    from takab_edge.supervisor import EdgeSupervisor

    with_neighbors = settings.model_copy(
        update={
            "neighbors": [
                NeighborStation(code="AM.R0001", lat=19.1, lon=-98.3),
                NeighborStation(code="AM.R0002", lat=18.9, lon=-98.0),
                NeighborStation(code="AM.R0003", lat=19.2, lon=-97.9),
            ]
        }
    )
    sup = EdgeSupervisor(with_neighbors, seedlink_source=None)
    sup.start()
    try:
        # El reflejo SASMEX dispara la sirena EXACTAMENTE igual con 3 vecinas
        # configuradas: no hay espera de corroboración, no hay veto.
        sup.gpio.simulate_sasmex(active=True)
        assert sup.gpio.siren_sounding is True
        assert sup.local_api.status()["last_tier"] == "evacuate_or_hold"
        # Y las vecinas solo existen como INFORMACIÓN del panel.
        assert len(sup.local_api.status()["neighbors"]) == 3
    finally:
        sup.stop()
