"""Tests HTTP del router de telemetría (T-1.22 · B3).

Ejercitan features (vista segura, columnar, span máx 2 h), métricas (caggs 1m/1h)
y estado del mapa, más la autorización por rol (Consola C4I de RBAC §2). La
tenancy fina (A no ve B, gov solo gov_shared) vive en los contract-tests.
"""

# Los fixtures se importan por nombre y se reciben como parámetros de test: ruff lo
# lee como redefinición del import (F811). Es el patrón estándar de pytest → se
# silencia a nivel de archivo (este dir es de B2 y no podemos añadir un conftest).
# ruff: noqa: F811
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

import auth_utils as au
from _telemetry_fixtures import (  # noqa: F401  (fixtures cargadas por nombre)
    S_A,
    S_B,
    S_SHOOK,
    T_PRIV_A,
    T_PRIV_B,
    seed,
    telemetry_app,
    telemetry_client,
    ts_engine,
)


def _auth(role: str, tenant: str) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*", surface="web"))


async def test_features_columnar_default_window(telemetry_client, seed) -> None:
    r = await telemetry_client.get(
        f"/telemetry/sites/{S_A}/features", headers=_auth("soc_operator", T_PRIV_A)
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"ts", "pga", "pgv", "stalta", "clipping", "calibrated"}
    # 3 puntos sembrados (now-30/60/90 s), dentro de los últimos 10 min por defecto.
    assert len(body["ts"]) == 3
    assert all(abs(v - 0.10) < 0.01 for v in body["pga"])
    assert body["ts"] == sorted(body["ts"])  # orden temporal ascendente
    assert True in body["clipping"]


async def test_features_channel_filter(telemetry_client, seed) -> None:
    r_ehz = await telemetry_client.get(
        f"/telemetry/sites/{S_A}/features?channel=EHZ",
        headers=_auth("soc_operator", T_PRIV_A),
    )
    r_enz = await telemetry_client.get(
        f"/telemetry/sites/{S_A}/features?channel=ENZ",
        headers=_auth("soc_operator", T_PRIV_A),
    )
    assert len(r_ehz.json()["ts"]) == 3
    assert r_enz.json()["ts"] == []  # solo se sembró EHZ


async def test_features_span_over_2h_rejected(telemetry_client, seed) -> None:
    now = datetime.now(UTC)
    # params= deja que httpx percent-encode el '+' del offset (como un cliente real).
    r = await telemetry_client.get(
        f"/telemetry/sites/{S_A}/features",
        params={"from": (now - timedelta(hours=3)).isoformat(), "to": now.isoformat()},
        headers=_auth("soc_operator", T_PRIV_A),
    )
    assert r.status_code == 422
    assert "2 h" in r.json()["detail"]


async def test_features_bad_timestamp_rejected(telemetry_client, seed) -> None:
    r = await telemetry_client.get(
        f"/telemetry/sites/{S_A}/features?from=not-a-date",
        headers=_auth("soc_operator", T_PRIV_A),
    )
    assert r.status_code == 422


async def test_features_cross_tenant_is_empty(telemetry_client, seed) -> None:
    # Tenant A pide el sitio de B: RLS (vía la vista) devuelve cero filas, no fuga.
    r = await telemetry_client.get(
        f"/telemetry/sites/{S_B}/features", headers=_auth("soc_operator", T_PRIV_A)
    )
    assert r.status_code == 200
    assert r.json()["ts"] == []


async def test_metrics_default_bucket_1m(telemetry_client, seed) -> None:
    r = await telemetry_client.get(
        f"/telemetry/sites/{S_A}/metrics", headers=_auth("soc_operator", T_PRIV_A)
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["bucket"] == "1m"  # span 24 h por defecto ⇒ 1m
    assert len(body["ts"]) >= 1
    assert body["max_pga_g"]


async def test_metrics_bucket_1h_explicit(telemetry_client, seed) -> None:
    r = await telemetry_client.get(
        f"/telemetry/sites/{S_A}/metrics?bucket=1h",
        headers=_auth("soc_operator", T_PRIV_A),
    )
    assert r.status_code == 200, r.text
    assert r.json()["bucket"] == "1h"


async def test_metrics_invalid_bucket_rejected(telemetry_client, seed) -> None:
    r = await telemetry_client.get(
        f"/telemetry/sites/{S_A}/metrics?bucket=5m",
        headers=_auth("soc_operator", T_PRIV_A),
    )
    assert r.status_code == 422


async def test_map_state_has_site_with_open_incident(telemetry_client, seed) -> None:
    r = await telemetry_client.get("/telemetry/map/state", headers=_auth("soc_operator", T_PRIV_A))
    assert r.status_code == 200, r.text
    sites = {s["site_id"]: s for s in r.json()["sites"]}
    assert S_A in sites
    site = sites[S_A]
    assert site["open_incident"] is not None
    assert site["open_incident"]["state"] == "open"
    assert site["last_bucket"] is not None  # última métrica 1m materializada
    assert site["max_pga_g"] is not None
    # Aislamiento: el sitio de B (private) no aparece para A.
    assert S_B not in sites


async def test_map_state_reports_shaking_MEASURED_not_alert_severity(
    telemetry_client, seed
) -> None:
    """El mapa pinta lo que el EDIFICIO sintió, no el nivel de la alerta.

    El seed abre el incidente con `trigger='sasmex'` y `severity='warning'`, pero el
    sensor del sitio midió 0.10 g — por encima del umbral de disparo (0.060 g). Son
    dos hechos distintos y el mapa debe exponer los dos por separado: la severidad
    viene del canal de alerta (SASMEX es un booleano, no mide nada de lo que pasa
    aquí) y `felt` viene del acelerógrafo del inmueble.
    """
    r = await telemetry_client.get("/telemetry/map/state", headers=_auth("soc_operator", T_PRIV_A))
    assert r.status_code == 200, r.text
    site = {s["site_id"]: s for s in r.json()["sites"]}[S_A]

    assert site["open_incident"]["severity"] == "warning"  # el canal de alerta dice esto…
    assert site["felt"] == "trip"  # …y el edificio dice esto otro
    assert site["felt_pga_g"] == pytest.approx(0.10, abs=0.01)


async def test_map_state_uses_the_INCIDENT_PEAK_not_the_calm_that_came_after(
    telemetry_client, seed
) -> None:
    """Un edificio que sacudió y ya se calmó NO puede pintarse de verde.

    Regresión de un fallo cazado contra la nube con datos reales: Sitio Dev Puebla
    tenía un incidente abierto por `local_threshold` —o sea, disparado por SU PROPIO
    sensor—, con un pico medido de 0.567 g (9× su umbral) y `incidents.max_pga_g`
    todavía en NULL, porque ese campo solo lo rellena el pase de dictamen. El mapa
    caía entonces al último bucket de 1 minuto, que para cuando el operador mira ya
    está en ruido de fondo (0.0014 g), y pintaba el inmueble de VERDE: "no se movió".

    Con incidente abierto, `felt` tiene que ser el PICO de su ventana, no la calma
    posterior. S_SHOOK reproduce ese estado: 0.50 g hace 20 min, 0.001 g ahora.
    """
    r = await telemetry_client.get("/telemetry/map/state", headers=_auth("soc_operator", T_PRIV_A))
    assert r.status_code == 200, r.text
    site = {s["site_id"]: s for s in r.json()["sites"]}[S_SHOOK]

    assert site["felt"] == "trip", "la sacudida pasada manda sobre la calma de ahora"
    assert site["felt_pga_g"] == pytest.approx(0.50, abs=0.01)
    # El pico de la ventana nunca puede quedar POR DEBAJO de la lectura viva: si eso
    # pasara, el mapa estaría enseñando algo más suave de lo que el edificio sintió.
    # (No se asserta el valor exacto del bucket vivo: cuándo materializa TimescaleDB
    # el minuto en curso es asunto suyo, y atarlo aquí hace el test frágil.)
    assert site["felt_pga_g"] >= site["max_pga_g"]


async def test_map_state_declares_uncalibrated_sites(telemetry_client, seed) -> None:
    """Sin fuente de calibración el PGA es RELATIVO: la UI no puede llamarlo intensidad."""
    r = await telemetry_client.get("/telemetry/map/state", headers=_auth("soc_operator", T_PRIV_A))
    site = {s["site_id"]: s for s in r.json()["sites"]}[S_A]
    # El seed inserta sensores sin `calibration_source`.
    assert site["calibrated"] is False


async def test_map_state_has_no_epicenter_when_no_event_locates_one(telemetry_client, seed) -> None:
    """Sin evento localizado NO se inventa un epicentro (y NUNCA es el edificio).

    El seed abre incidentes sin `event_id`, así que no hay sismo localizado: la lista
    sale vacía y el mapa lo declara, en vez de plantar el epicentro sobre el inmueble.
    """
    r = await telemetry_client.get("/telemetry/map/state", headers=_auth("soc_operator", T_PRIV_A))
    assert r.json()["epicenters"] == []


async def test_mobile_only_role_forbidden(telemetry_client, seed) -> None:
    r = await telemetry_client.get(
        f"/telemetry/sites/{S_A}/features",
        headers=au.bearer(
            au.make_token("occupant", tenant=T_PRIV_A, site_scope="*", surface="mobile")
        ),
    )
    assert r.status_code == 403


async def test_missing_token_unauthorized(telemetry_client, seed) -> None:
    r = await telemetry_client.get(f"/telemetry/sites/{S_A}/features")
    assert r.status_code == 401
