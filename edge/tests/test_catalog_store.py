"""CatalogStore (T-2.24) — instantánea SSN con feed firmado nube→edge.

Fail-closed en todo: sin verificador se rechaza, firma mala se rechaza, versión
ya vista se rechaza (anti-replay que SOBREVIVE reinicios: el high-water viaja en
el propio archivo como `feed_version`). El contrato de `GET /api/catalog` no
cambia: la actualización solo refresca la instantánea.
"""

from __future__ import annotations

import json

import pytest
from takab_edge.catalog import CatalogError, CatalogStore
from takab_edge.dispatch import canonical_payload
from takab_edge.security import SecurityManager

KEY = b"clave-de-pruebas-catalogo-0001"

SNAPSHOT = {
    "fuente": "Servicio Sismológico Nacional (SSN) · Instituto de Geofísica, UNAM",
    "capturado": "2026-07-31T06:00:00-06:00",
    "replicas_nota": "sin réplicas en curso",
    "eventos": [
        {
            "m": 4.2,
            "fecha": "2026-07-30",
            "hora": "22:11:02",
            "lat": 16.7,
            "lon": -98.1,
            "prof": 12.0,
            "loc": "costa de Guerrero",
        }
    ],
    "referencias": [{"n": "CDMX", "lat": 19.4326, "lon": -99.1332}],
}


def _store(tmp_path, with_security: bool = True) -> CatalogStore:
    security = SecurityManager(KEY) if with_security else None
    return CatalogStore(str(tmp_path / "ssn-catalog.json"), security=security)


def _signed(payload: dict, version: int) -> tuple[bytes, str]:
    raw = canonical_payload(payload)
    return raw, SecurityManager(KEY).sign_catalog(raw, version)


def test_apply_signed_update_swaps_and_persists(tmp_path):
    store = _store(tmp_path)
    assert store.current()["available"] is False  # sin archivo: degradado honesto
    raw, sig = _signed(SNAPSHOT, 3)
    assert store.apply_signed_update(raw, sig, 3) == 3
    served = store.current()
    assert served["available"] is True
    assert served["captured_at"] == "2026-07-31T06:00:00-06:00"
    assert served["events"][0]["place"] == "costa de Guerrero"
    # Persistió ATÓMICO con el high-water dentro; una vida nueva lo hereda.
    reborn = _store(tmp_path)
    assert reborn.current()["available"] is True
    assert reborn.version == 3


def test_replay_and_stale_versions_rejected_even_across_restarts(tmp_path):
    store = _store(tmp_path)
    raw, sig = _signed(SNAPSHOT, 5)
    store.apply_signed_update(raw, sig, 5)
    with pytest.raises(CatalogError):
        store.apply_signed_update(raw, sig, 5)  # replay exacto
    older = dict(SNAPSHOT, capturado="2026-01-01T00:00:00-06:00")
    raw2, sig2 = _signed(older, 4)
    with pytest.raises(CatalogError):
        store.apply_signed_update(raw2, sig2, 4)  # versión vieja re-firmada
    # El piso anti-replay SOBREVIVE el reinicio (viaja en el archivo).
    reborn = _store(tmp_path)
    with pytest.raises(CatalogError):
        reborn.apply_signed_update(raw, sig, 5)


def test_bad_signature_rejected_and_nothing_written(tmp_path):
    store = _store(tmp_path)
    raw, _ = _signed(SNAPSHOT, 1)
    with pytest.raises(CatalogError):
        store.apply_signed_update(raw, "firma-falsa", 1)
    assert store.current()["available"] is False
    assert not (tmp_path / "ssn-catalog.json").exists()  # fail-closed: ni un byte


def test_without_verifier_is_fail_closed(tmp_path):
    store = _store(tmp_path, with_security=False)
    raw, sig = _signed(SNAPSHOT, 1)
    with pytest.raises(CatalogError):
        store.apply_signed_update(raw, sig, 1)


def test_garbage_payload_with_valid_signature_rejected(tmp_path):
    store = _store(tmp_path)
    raw = b"esto-no-es-json"
    sig = SecurityManager(KEY).sign_catalog(raw, 1)
    with pytest.raises(CatalogError):
        store.apply_signed_update(raw, sig, 1)
    assert store.current()["available"] is False


def test_signed_feed_reaches_panel_over_http(supervisor, tmp_path, monkeypatch):
    """E2E del feed: sobre firmado → dispatch → store → GET /api/catalog nuevo.

    El contrato del endpoint NO cambia: el panel solo ve la instantánea fresca.
    """
    import urllib.request

    monkeypatch.setattr(supervisor.catalog, "_path", tmp_path / "ssn-catalog.json")
    raw = canonical_payload(SNAPSHOT)
    envelope = json.dumps(
        {
            "kind": "catalog_update",
            "version": 1,
            "payload": SNAPSHOT,
            "sig": supervisor.security.sign_catalog(raw, 1),
        }
    ).encode()
    supervisor.dispatch.on_catalog(supervisor.settings.catalog_topic, envelope)
    _host, port = supervisor.local_api.address
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/catalog", timeout=5) as r:
        served = json.loads(r.read())
    assert served["available"] is True
    assert served["captured_at"] == SNAPSHOT["capturado"]
    # Un sobre hostil (firma mala) se descarta EN SILENCIO y no toca lo servido.
    bad = json.dumps(
        {"kind": "catalog_update", "version": 2, "payload": SNAPSHOT, "sig": "mala"}
    ).encode()
    supervisor.dispatch.on_catalog(supervisor.settings.catalog_topic, bad)
    assert supervisor.catalog.version == 1


def test_supervisor_subscribes_catalog_topic(supervisor):
    """El cableado existe: el conector conoce la suscripción del catálogo."""
    assert supervisor.settings.catalog_topic == f"takab/catalog/{supervisor.settings.thing_name}"


def test_legacy_provisioned_file_reads_as_version_zero(tmp_path):
    """El archivo instalado a mano (formato del entregable, sin feed_version)."""
    path = tmp_path / "ssn-catalog.json"
    path.write_text(json.dumps(SNAPSHOT), "utf-8")
    store = CatalogStore(str(path), security=SecurityManager(KEY))
    assert store.current()["available"] is True
    assert store.version == 0  # el feed puede actualizarlo desde la v1
    raw, sig = _signed(dict(SNAPSHOT, capturado="2026-08-01T00:00:00-06:00"), 1)
    store.apply_signed_update(raw, sig, 1)
    assert store.current()["captured_at"] == "2026-08-01T00:00:00-06:00"
