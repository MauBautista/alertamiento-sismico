"""Emulador de los writers de T-1.17 para de-riesgar el plano API→WS→cliente.

Inserta como ``takab_ingest`` (BYPASSRLS) las mismas filas que producirá la
ingesta real, disparando los triggers de la migración 0004 (LISTEN/NOTIFY) sin
necesidad del pipeline SQS/IoT. Sirve para (a) probar el WS y medir el
presupuesto <2 s antes de que exista la ingesta, y (b) alimentar demos.

Uso CLI (dev)::

    uv run python scripts/fake_ingest.py \
        --tenant <uuid> --site <uuid> --sensor <uuid> --gateway <uuid> --quake

Sin flags, emite features 1 Hz (+ una transición de salud) hasta Ctrl-C.
Los helpers (``insert_feature``/``insert_health_transition``/``insert_quake``)
son importables desde los tests, operando sobre una conexión psycopg autocommit.
"""

from __future__ import annotations

import argparse
import os
import time
import uuid
from typing import Any

import psycopg

_DEFAULT_DSN = "postgresql://takab:takab_dev@127.0.0.1:5433/takab"


def raw_dsn(url: str) -> str:
    """Normaliza un ``postgresql+psycopg://`` (SQLAlchemy) a DSN psycopg crudo."""
    return url.replace("postgresql+psycopg://", "postgresql://")


def connect(dsn: str) -> psycopg.Connection:
    """Conexión autocommit con ``SET ROLE takab_ingest`` (BYPASSRLS en dev).

    ``takab_ingest`` es NOLOGIN: en dev se conecta con el super del DSN y se
    escala con ``SET ROLE`` (mismo patrón que ``conftest.use``). Autocommit →
    cada INSERT commitea y dispara su NOTIFY de inmediato.
    """
    conn = psycopg.connect(dsn, autocommit=True)
    conn.execute("SET ROLE takab_ingest")
    return conn


def insert_feature(
    conn: psycopg.Connection,
    *,
    tenant: str,
    site: str,
    sensor: str,
    channel: str = "EHZ",
    pga_g: float = 0.01,
    pgv_cms: float = 0.1,
    rms: float = 0.02,
    stalta: float = 1.2,
    energy: float = 0.5,
    clipping: bool = False,
) -> None:
    """Una fila de ``waveform_features_1s`` en ``now()`` (feed del poller live)."""
    conn.execute(
        "INSERT INTO waveform_features_1s "
        "(ts, tenant_id, site_id, sensor_id, channel, pga_g, pgv_cms, rms, stalta, "
        "energy, clipping) VALUES (now(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT DO NOTHING",
        (tenant, site, sensor, channel, pga_g, pgv_cms, rms, stalta, energy, clipping),
    )


def insert_health_transition(
    conn: psycopg.Connection,
    *,
    tenant: str,
    gateway: str,
    reason: str = "transition",
    mqtt_rtt_ms: float = 40.0,
    seedlink_lag_s: float = 0.4,
    ntp_offset_ms: float = 5.0,
    power_status: str = "mains",
    battery_pct: float = 100.0,
    cert_days_remaining: int = 120,
) -> None:
    """Una fila de ``device_health``; sólo ``reason='transition'`` emite NOTIFY."""
    conn.execute(
        "INSERT INTO device_health "
        "(ts, tenant_id, gateway_id, reason, mqtt_rtt_ms, seedlink_lag_s, "
        "ntp_offset_ms, power_status, battery_pct, cert_days_remaining) "
        "VALUES (now(), %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
        (
            tenant,
            gateway,
            reason,
            mqtt_rtt_ms,
            seedlink_lag_s,
            ntp_offset_ms,
            power_status,
            battery_pct,
            cert_days_remaining,
        ),
    )


def insert_quake(
    conn: psycopg.Connection,
    *,
    tenant: str,
    site: str,
    sensor: str,
    gateway: str,
    severity: str = "critical",
) -> dict[str, str]:
    """Un sismo simulado: ``seismic_events`` + ``incidents`` open + ``incident_actions``.

    Cada INSERT dispara su trigger de 0004 (incidente → NOTIFY 'incident';
    acciones → NOTIFY 'incident_action'). Devuelve los ids generados.
    """
    event_id = f"EVT-{uuid.uuid4().hex[:12]}"
    incident_id = str(uuid.uuid4())
    event_uuid = str(uuid.uuid4())

    conn.execute(
        "INSERT INTO seismic_events (event_id, source, magnitude, detected_at) "
        "VALUES (%s, 'local_quorum', 5.0, now())",
        (event_id,),
    )
    conn.execute(
        "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, event_id, "
        "opened_at, severity, trigger, max_pga_g) "
        "VALUES (%s, %s, %s, %s, %s, now(), %s, 'quorum', 0.18)",
        (incident_id, event_uuid, tenant, site, event_id, severity),
    )
    for kind, actor in (("siren_on", f"edge:{gateway}"), ("gas_closed", f"edge:{gateway}")):
        conn.execute(
            "INSERT INTO incident_actions (incident_id, tenant_id, kind, actor) "
            "VALUES (%s, %s, %s, %s)",
            (incident_id, tenant, kind, actor),
        )
    return {"event_id": event_id, "incident_id": incident_id, "event_uuid": event_uuid}


def _run(args: argparse.Namespace) -> None:
    dsn = raw_dsn(args.dsn)
    conn = connect(dsn)
    ids: dict[str, Any] = {"tenant": args.tenant, "site": args.site}
    if args.quake:
        ids = insert_quake(
            conn,
            tenant=args.tenant,
            site=args.site,
            sensor=args.sensor,
            gateway=args.gateway,
        )
        print(f"quake: {ids}")
    interval = 1.0 / max(args.rate, 0.1)
    deadline = time.monotonic() + args.duration if args.duration > 0 else None
    tick = 0
    try:
        while deadline is None or time.monotonic() < deadline:
            insert_feature(conn, tenant=args.tenant, site=args.site, sensor=args.sensor)
            if tick % 30 == 0:
                insert_health_transition(conn, tenant=args.tenant, gateway=args.gateway)
            tick += 1
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Emulador de writers de ingesta (dev).")
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL", _DEFAULT_DSN))
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--site", required=True)
    parser.add_argument("--sensor", required=True)
    parser.add_argument("--gateway", required=True)
    parser.add_argument("--rate", type=float, default=1.0, help="features por segundo")
    parser.add_argument("--duration", type=float, default=0.0, help="segundos (0 = infinito)")
    parser.add_argument("--quake", action="store_true", help="emite un sismo al inicio")
    _run(parser.parse_args())


if __name__ == "__main__":
    main()
