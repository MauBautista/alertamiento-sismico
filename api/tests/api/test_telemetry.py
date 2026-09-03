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


async def test_map_state_publica_el_codigo_del_sitio(telemetry_client, seed) -> None:
    """[T-5.05] El mapa necesita el CÓDIGO para poder distinguir demo de real.

    Hasta esta ficha el payload traía el `name` y nada más, así que la consola no
    tenía con qué separar los sitios simulados de los reales: en el mapa se veían
    idénticos, y en una demostración eso son veinte edificios que no existen
    pintados como si existieran.

    Sale el código —un HECHO— y no un `demo: bool`: decidir qué se rotula es de la
    presentación, y meter la política del seed en el contrato la duplicaría.
    """
    r = await telemetry_client.get("/telemetry/map/state", headers=_auth("soc_operator", T_PRIV_A))
    assert r.status_code == 200, r.text
    sites = {s["site_id"]: s for s in r.json()["sites"]}
    assert sites, "el mapa salió vacío: el test no comprueba nada"
    for site in sites.values():
        assert site["code"], f"sitio sin código en el mapa: {site['site_id']}"


# ── [T-5.26] La identidad del hardware, sin salir de la consola ──────────────
#
# El mapa decía qué sintió el edificio y cómo estaba su enlace, y NADA sobre qué
# aparato lo dice: para el serial, el firmware o el modelo del sismógrafo había
# que abandonar la consola e irse a Flota. En una demostración eso es un salto de
# pantalla en el peor momento; en un incidente real, un cambio de contexto justo
# cuando no se debe.

_GW_T526 = "8e000000-0000-0000-0000-0000000005a6"


@pytest.fixture
def gabinete_del_sitio_a():
    """Un gabinete real para `S_A`, con su latido. Se retira SIEMPRE al terminar.

    No se añade al fixture compartido a propósito: hoy los sitios del mapa salen
    `SIN GABINETE` y varios tests miden justo eso. Darles hardware a todos
    cambiaría el estado del enlace bajo los pies de esos tests.

    El `finally` no es ceremonia: `gateways` referencia `sites`, así que un
    gabinete huérfano rompería el `DELETE FROM sites` del cleanup y envenenaría
    el archivo entero con un fallo de clave foránea que no menciona esta línea.
    """
    import psycopg

    from conftest import _dsn

    with psycopg.connect(_dsn(), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, fw_version) "
            "VALUES (%s, %s, %s, 'SER-T526', '62f3f1e')",
            (_GW_T526, T_PRIV_A, S_A),
        )
        cur.execute(
            "INSERT INTO device_health (ts, tenant_id, gateway_id, reason, power_status,"
            " battery_pct) VALUES (now(), %s, %s, 'heartbeat', 'battery', 61.5)",
            (T_PRIV_A, _GW_T526),
        )
    try:
        yield _GW_T526
    finally:
        with psycopg.connect(_dsn(), autocommit=True) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM device_health WHERE gateway_id = %s", (_GW_T526,))
            cur.execute("DELETE FROM gateways WHERE gateway_id = %s", (_GW_T526,))


async def test_map_state_trae_la_IDENTIDAD_del_hardware(
    telemetry_client, seed, gabinete_del_sitio_a
) -> None:
    """Serial, firmware, modelo del sismógrafo y respaldo eléctrico, en el mapa."""
    r = await telemetry_client.get("/telemetry/map/state", headers=_auth("soc_operator", T_PRIV_A))
    assert r.status_code == 200, r.text
    sitio = next(s for s in r.json()["sites"] if s["site_id"] == S_A)

    assert sitio["serial"] == "SER-T526", (
        f"el serial del gabinete no llega al mapa ({sitio['serial']!r}): el dato "
        "sigue viviendo solo en Flota"
    )
    assert sitio["fw_version"] == "62f3f1e"
    assert sitio["sensor_models"] == "RS4D", (
        f"el modelo del sismógrafo no llega al mapa: {sitio['sensor_models']!r}"
    )
    # El respaldo eléctrico YA viajaba en la consulta —lo usa `derive_fleet_state`—
    # y se tiraba al construir la respuesta: el dato estaba y no se veía.
    assert sitio["power_status"] == "battery"
    assert sitio["battery_pct"] == pytest.approx(61.5)


async def test_el_mapa_dice_SIN_DATO_en_vez_de_inventar_identidad(telemetry_client, seed) -> None:
    """El criterio honesto que ya usa el medidor de respaldo: sin dato, lo dice.

    Sin este test, un `""` o un `0` de relleno pasarían: son valores que la UI
    pinta como una versión de firmware y una batería que nadie ha medido. Aquí los
    sitios NO tienen gabinete, así que la respuesta correcta es `None` en los
    cuatro campos de hardware — y el modelo del sensor sí, porque ése sí consta.
    """
    r = await telemetry_client.get("/telemetry/map/state", headers=_auth("soc_operator", T_PRIV_A))
    sitio = next(s for s in r.json()["sites"] if s["site_id"] == S_A)

    for campo in ("serial", "fw_version", "power_status", "battery_pct"):
        assert sitio[campo] is None, (
            f"{campo} = {sitio[campo]!r} para una estación SIN GABINETE: eso es "
            "afirmar un hardware que no existe"
        )
    assert sitio["sensor_models"] == "RS4D", "el sensor sí está dado de alta y no aparece"


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


async def test_map_state_epicenter_reports_node_count(telemetry_client, seed) -> None:
    """El epicentro del mapa expone cuántas estaciones corroboraron (quórum, T-1.71).

    Un evento formado por quórum lleva ``meta.node_count``; el mapa lo surfacea en el
    propio epicentro para que el operador vea "N estaciones". Un evento sin esa marca
    (sasmex/externo) devuelve ``node_count`` nulo — la UI no inventa la cuenta.

    ``seismic_events`` NO lo limpia el teardown (es dato de RED), así que el evento y su
    incidente ligado se borran aquí en un ``finally``.
    """
    import json

    import psycopg

    from _telemetry_fixtures import _dsn

    evt = "EVT-QUORUM-MAP-1"
    with psycopg.connect(_dsn(), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO seismic_events (event_id, source, epicenter, detected_at, meta) "
            "VALUES (%s, 'local_quorum', "
            "ST_SetSRID(ST_MakePoint(-98.20, 19.00), 4326)::geography, now(), %s::jsonb)",
            (evt, json.dumps({"node_count": 3})),
        )
        cur.execute(
            "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, event_id, "
            "opened_at, severity, state, trigger) VALUES "
            "(gen_random_uuid(), gen_random_uuid(), %s, %s, %s, now(), 'critical', 'open', "
            "'quorum')",
            (T_PRIV_A, S_A, evt),
        )
    try:
        r = await telemetry_client.get(
            "/telemetry/map/state", headers=_auth("soc_operator", T_PRIV_A)
        )
        assert r.status_code == 200, r.text
        eps = {e["event_id"]: e for e in r.json()["epicenters"]}
        assert evt in eps, "el epicentro del evento con incidente abierto debe aparecer"
        assert eps[evt]["node_count"] == 3
    finally:
        with psycopg.connect(_dsn(), autocommit=True) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM incidents WHERE event_id = %s", (evt,))
            cur.execute("DELETE FROM seismic_events WHERE event_id = %s", (evt,))


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
