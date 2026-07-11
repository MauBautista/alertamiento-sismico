"""Fixtures compartidas de los tests de telemetría (T-1.22 · B3).

Reutilizadas por ``tests/api/``, ``tests/contracts/`` y ``tests/perf/`` (cada
directorio las importa en su ``conftest.py``). Espejan el patrón de
``tests/auth/conftest.py`` (env de auth + engine async por test), y añaden un
sembrado de series de tiempo (features + caggs 1m/1h + incidentes) commiteado por
un ``takab_ingest``/superusuario para que la API async lo lea por HTTP.

UUIDs con prefijo ``8`` → disjuntos de los del conftest sync (1/2/3/9/a/b/c) y de
los async de auth (prefijo 7). Las filas se limpian en el teardown (truncate +
delete) para no contaminar los ``count(*)`` globales de las suites de T-1.16/17.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import psycopg
import pytest
from fastapi import FastAPI

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.telemetry import router as telemetry_router

# --- Catálogo dedicado (prefijo 8) --------------------------------------------
T_PRIV_A = "81111111-1111-1111-1111-111111111111"  # private
T_PRIV_B = "82222222-2222-2222-2222-222222222222"  # private (fuga cross-tenant)
T_GOV = "83333333-3333-3333-3333-333333333333"  # gov_shared
T_AGENCY = "89999999-9999-9999-9999-999999999999"  # agencia gov (no es tenant cliente)

S_A = "8a000000-0000-0000-0000-0000000000a1"
S_B = "8b000000-0000-0000-0000-0000000000b1"
S_G = "8c000000-0000-0000-0000-0000000000c1"
#: Sitio que SACUDIÓ fuerte y ya se calmó, con el pico del incidente aún sin
#: rellenar. Es el escenario que el mapa pintaba mal (ver test_map_state_*).
S_SHOOK = "8a100000-0000-0000-0000-0000000000a2"

SENSOR_A = "8d000000-0000-0000-0000-0000000000d1"
SENSOR_B = "8e000000-0000-0000-0000-0000000000e1"
SENSOR_G = "8f000000-0000-0000-0000-0000000000f1"
SENSOR_SHOOK = "8d100000-0000-0000-0000-0000000000d2"

_MINE = (T_PRIV_A, T_PRIV_B, T_GOV)
_SITES = (
    (S_A, T_PRIV_A, SENSOR_A),
    (S_B, T_PRIV_B, SENSOR_B),
    (S_G, T_GOV, SENSOR_G),
    (S_SHOOK, T_PRIV_A, SENSOR_SHOOK),
)

_GEOM = "ST_SetSRID(ST_MakePoint(-99.13, 19.43), 4326)::geography"


def _dsn() -> str:
    url = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab"
    )
    return url.replace("postgresql+psycopg://", "postgresql://")


@dataclass(frozen=True)
class SeedIds:
    """IDs y sitios sembrados, para que los tests referencien sin literales sueltos."""

    priv_a: str = T_PRIV_A
    priv_b: str = T_PRIV_B
    gov: str = T_GOV
    agency: str = T_AGENCY
    site_a: str = S_A
    site_b: str = S_B
    site_g: str = S_G


def _refresh(cur: psycopg.Cursor) -> None:
    """Materializa 1m/1h en la ventana de trabajo (autocommit; fuera de txn)."""
    cur.execute(
        "CALL refresh_continuous_aggregate('site_metrics_1m', now() - interval '2 hours', now())"
    )
    cur.execute(
        "CALL refresh_continuous_aggregate('site_metrics_1h', now() - interval '2 hours', now())"
    )


def _seed(conn: psycopg.Connection) -> SeedIds:
    """Siembra tenants/sitios/sensores + features recientes + incidentes abiertos."""
    with conn.cursor() as cur:
        for tid, code, vis in (
            (T_PRIV_A, "B3_A", "private"),
            (T_PRIV_B, "B3_B", "private"),
            (T_GOV, "B3_G", "gov_shared"),
        ):
            cur.execute(
                "INSERT INTO tenants (tenant_id, code, name, visibility) "
                "VALUES (%s, %s, 'B3 telemetry', %s) ON CONFLICT (tenant_id) DO NOTHING",
                (tid, code, vis),
            )
        for sid, tid, sensor in _SITES:
            cur.execute(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) "
                f"VALUES (%s, %s, %s, 'Sitio B3', {_GEOM}) "
                "ON CONFLICT (site_id) DO NOTHING",
                (sid, tid, sid[:6]),
            )
            cur.execute(
                "INSERT INTO sensors (sensor_id, tenant_id, site_id, kind, model) "
                "VALUES (%s, %s, %s, 'ground', 'RS4D') ON CONFLICT (sensor_id) DO NOTHING",
                (sensor, tid, sid),
            )
        # Features recientes: pga distinto por tenant para distinguir fugas.
        for sid, tid, sensor, pga in (
            (S_A, T_PRIV_A, SENSOR_A, 0.10),
            (S_B, T_PRIV_B, SENSOR_B, 0.90),
            (S_G, T_GOV, SENSOR_G, 0.50),
        ):
            for offset, clip in ((30, False), (60, False), (90, True)):
                cur.execute(
                    "INSERT INTO waveform_features_1s (ts, tenant_id, site_id, sensor_id, "
                    "channel, pga_g, pgv_cms, stalta, clipping) VALUES "
                    "(now() - (%s || ' seconds')::interval, %s, %s, %s, 'EHZ', "
                    "%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (str(offset), tid, sid, sensor, pga, pga * 10, pga * 20, clip),
                )
        # S_SHOOK: SACUDIÓ fuerte hace 20 min (0.50 g) y AHORA está en calma
        # (0.001 g). Es el escenario que el mapa pintaba de VERDE — "no se movió" —
        # porque miraba el último minuto en vez del pico de la ventana del incidente.
        for offset, pga in ((1200, 0.50), (30, 0.001)):
            cur.execute(
                "INSERT INTO waveform_features_1s (ts, tenant_id, site_id, sensor_id, "
                "channel, pga_g, pgv_cms, stalta, clipping) VALUES "
                "(now() - (%s || ' seconds')::interval, %s, %s, %s, 'EHZ', "
                "%s, %s, %s, false) ON CONFLICT DO NOTHING",
                (str(offset), T_PRIV_A, S_SHOOK, SENSOR_SHOOK, pga, pga * 10, pga * 20),
            )

        # Un incidente ABIERTO por sitio (alimenta el open_incident del mapa).
        for sid, tid in ((S_A, T_PRIV_A), (S_B, T_PRIV_B), (S_G, T_GOV)):
            cur.execute(
                "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, "
                "opened_at, severity, state, trigger) VALUES "
                "(gen_random_uuid(), gen_random_uuid(), %s, %s, now(), 'warning', "
                "'open', 'sasmex')",
                (tid, sid),
            )
        # El de S_SHOOK abrió CUANDO sacudió, y su `max_pga_g` sigue NULL: solo lo
        # rellena el pase de dictamen, que aún no ha corrido. Exactamente el estado
        # en que estaban los incidentes reales de la nube.
        cur.execute(
            "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, "
            "opened_at, severity, state, trigger) VALUES "
            "(gen_random_uuid(), gen_random_uuid(), %s, %s, now() - interval '20 minutes', "
            "'critical', 'open', 'local_threshold')",
            (T_PRIV_A, S_SHOOK),
        )
        _refresh(cur)
    return SeedIds()


def _cleanup() -> None:
    """Limpia todo lo commiteado (features, caggs, incidentes, catálogo prefijo 8)."""
    with psycopg.connect(_dsn(), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE waveform_features_1s")
        cur.execute("TRUNCATE incidents, incident_actions, audit_log CASCADE")
        cur.execute("DELETE FROM sensors WHERE tenant_id = ANY(%s)", (list(_MINE),))
        cur.execute("DELETE FROM sites   WHERE tenant_id = ANY(%s)", (list(_MINE),))
        cur.execute("DELETE FROM tenants WHERE tenant_id = ANY(%s)", (list(_MINE),))
        _refresh(cur)  # re-materializa la ventana con la base vacía → sin filas mías


@pytest.fixture(autouse=True)
def _ts_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Alinea el entorno con el keypair/JWKS de test y limpia caches (como auth)."""
    monkeypatch.setenv("TAKAB_API_AUTH_ISSUER", au.ISSUER)
    monkeypatch.setenv("TAKAB_API_AUTH_AUDIENCE", au.AUDIENCE)
    monkeypatch.setenv("TAKAB_API_AUTH_JWKS_JSON", au.jwks_json())
    monkeypatch.setenv("TAKAB_API_AUTH_DEV_PRIVATE_KEY", au.dev_private_key_pem())
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        monkeypatch.setenv("TAKAB_API_DATABASE_URL", dsn)
    deps._reset_caches()
    get_engine.cache_clear()
    yield
    deps._reset_caches()


@pytest.fixture
async def ts_engine():
    """Engine async por test; limpia lo commiteado y se dispone al terminar."""
    yield
    _cleanup()
    if get_engine.cache_info().currsize:
        await get_engine().dispose()
    get_engine.cache_clear()


@pytest.fixture
def seed(ts_engine) -> SeedIds:
    """Siembra series + incidentes (commit) y devuelve los IDs; limpia en ts_engine."""
    with psycopg.connect(_dsn(), autocommit=True) as conn:
        return _seed(conn)


@pytest.fixture
def telemetry_app() -> FastAPI:
    """App base + el router de telemetría montado (integración real la hace main)."""
    app = create_app()
    app.include_router(telemetry_router)
    return app


@pytest.fixture
async def client(ts_engine, telemetry_app: FastAPI):
    """Cliente HTTP ASGI; ``ts_engine`` garantiza limpieza + dispose del engine."""
    async with au.client_for(telemetry_app) as c:
        yield c
