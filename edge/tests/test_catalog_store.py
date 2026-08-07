"""CatalogStore (T-2.24) — instantánea SSN con feed firmado nube→edge.

Fail-closed en todo: sin verificador se rechaza, firma mala se rechaza, versión
ya vista se rechaza (anti-replay que SOBREVIVE reinicios: el high-water viaja en
el propio archivo como `feed_version`). El contrato de `GET /api/catalog` no
cambia: la actualización solo refresca la instantánea.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

import pytest
from takab_edge.catalog import (
    CATALOG_STALE_AFTER_S,
    DEGRADED,
    CatalogError,
    CatalogStore,
)
from takab_edge.dispatch import canonical_payload
from takab_edge.security import SecurityManager

KEY = b"clave-de-pruebas-catalogo-0001"

#: [T-2.66] Reloj INYECTADO: la edad del catálogo se calcula en Python (el panel
#: no tiene reloj congelado) y sin esta costura el test envejecería con el
#: calendario. `SNAPSHOT` se capturó el 2026-07-31T06:00-06:00 = 12:00 UTC.
_AHORA = datetime(2026, 8, 6, 18, 0, 0, tzinfo=UTC)

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


# --- T-2.66 · edad y procedencia de la instantánea ---------------------------


def _provisioned(tmp_path, snapshot: dict, instalado: datetime) -> CatalogStore:
    """Archivo instalado a mano (`provision_gateway.sh --catalog`) con mtime fijo."""
    path = tmp_path / "ssn-catalog.json"
    path.write_text(json.dumps(snapshot), "utf-8")
    os.utime(path, (instalado.timestamp(), instalado.timestamp()))
    return CatalogStore(str(path), security=SecurityManager(KEY), clock=lambda: _AHORA)


def test_provenance_de_archivo_provisionado_declara_origen_edad_y_umbral(tmp_path):
    """Dos hechos DISTINTOS: cuándo se capturó y cuándo llegó al gabinete.

    En el gabinete real difieren 1h48m; con el entregable del repo, meses.
    """
    instalado = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)
    store = _provisioned(tmp_path, SNAPSHOT, instalado)
    prov = store.provenance()
    assert prov["origin"] == "provisioned_file"
    assert prov["version"] == 0
    assert prov["captured_at"] == "2026-07-31T06:00:00-06:00"
    assert prov["installed_at"] == instalado.isoformat()
    assert prov["captured_age_s"] == pytest.approx(6.25 * 86400)  # 31-jul 12:00Z → 6-ago 18:00Z
    assert prov["installed_age_s"] == pytest.approx(5.25 * 86400)
    # El umbral VIAJA en el payload (patrón `_SIGNAL_STALE_S`): el panel no lo esconde.
    assert prov["stale_after_s"] == CATALOG_STALE_AFTER_S == 48 * 3600.0


def test_provenance_tras_feed_firmado_usa_el_reloj_no_el_mtime(tmp_path):
    """`installed_at` sale del reloj, no del archivo: `_write_atomic` puede fallar
    (dev, disco lleno) y el swap en memoria SÍ ocurre — el mtime mentiría."""
    path = tmp_path / "ssn-catalog.json"
    store = CatalogStore(str(path), security=SecurityManager(KEY), clock=lambda: _AHORA)
    assert store.provenance()["origin"] == "absent"
    raw, sig = _signed(SNAPSHOT, 7)
    store.apply_signed_update(raw, sig, 7)
    prov = store.provenance()
    assert prov["origin"] == "signed_feed"
    assert prov["version"] == 7
    assert prov["installed_at"] == _AHORA.isoformat()
    assert prov["installed_age_s"] == pytest.approx(0.0)
    # Una vida nueva lo relee del archivo: `feed_version` es la huella del feed.
    reborn = CatalogStore(str(path), security=SecurityManager(KEY), clock=lambda: _AHORA)
    assert reborn.provenance()["origin"] == "signed_feed"
    assert reborn.provenance()["version"] == 7


def test_provenance_sin_catalogo_declara_ausencia_sin_inventar_edades(tmp_path):
    store = CatalogStore(str(tmp_path / "no-existe.json"), clock=lambda: _AHORA)
    prov = store.provenance()
    assert prov["origin"] == "absent"
    assert prov["installed_at"] is None and prov["captured_at"] is None
    assert prov["captured_age_s"] is None and prov["installed_age_s"] is None
    assert prov["stale_after_s"] == CATALOG_STALE_AFTER_S
    # La forma degradada que sirve el panel ya trae la procedencia (contrato aditivo).
    assert DEGRADED["provenance"]["origin"] == "absent"


@pytest.mark.parametrize("capturado", ["ayer por la tarde", "", "   ", None, 20260731])
def test_captured_at_ilegible_deja_la_edad_desconocida_y_jamas_lanza(tmp_path, capturado):
    """`capturado` es un STRING LIBRE (la nube solo valida que sea truthy).
    Ilegible ⇒ edad DESCONOCIDA (ámbar en el panel), jamás 0 y jamás una excepción."""
    store = _provisioned(
        tmp_path, dict(SNAPSHOT, capturado=capturado), datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    )
    prov = store.provenance()
    assert prov["captured_age_s"] is None
    assert prov["origin"] == "provisioned_file"  # el archivo SÍ está: eso no se pierde
    assert prov["installed_age_s"] == pytest.approx(5.25 * 86400)


def test_captura_sin_zona_se_lee_como_utc_y_una_captura_futura_no_rejuvenece(tmp_path):
    """Naive ⇒ UTC: en México eso da la instantánea 6 h MÁS VIEJA, nunca más joven.
    Y un reloj del Pi atrasado no puede producir una edad negativa."""
    instalado = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    naive = _provisioned(tmp_path, dict(SNAPSHOT, capturado="2026-08-06T12:00:00"), instalado)
    assert naive.provenance()["captured_age_s"] == pytest.approx(6 * 3600)
    futuro = _provisioned(
        tmp_path, dict(SNAPSHOT, capturado="2026-08-07T00:00:00+00:00"), instalado
    )
    assert futuro.provenance()["captured_age_s"] == 0.0


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
