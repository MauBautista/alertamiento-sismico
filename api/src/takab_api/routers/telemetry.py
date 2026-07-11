"""Router de telemetría del SOC (T-1.22 · B3): features, métricas y estado del mapa.

Solo lectura (``read_session`` → rol ``takab_app`` + GUCs RLS del request). El acceso
se restringe a los roles con Consola C4I de RBAC §2 (todos los de superficie web); los
roles móvil-only (brigadista/security_guard/occupant) quedan fuera. La tenancy la
resuelve la DB: features por la vista segura, métricas por ``JOIN sites`` (RLS).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.auth.claims import Claims
from takab_api.auth.deps import require_roles
from takab_api.auth.matrix import CONSOLE, ROLE_ROUTE_MATRIX
from takab_api.felt import felt_band, thresholds_from_row
from takab_api.queries.telemetry import (
    select_features,
    select_features_by_channel,
    select_map_epicenters,
    select_map_state,
    select_metrics,
    select_site_calibrated,
)
from takab_api.routers._common import http_error, read_session
from takab_api.schemas.telemetry import (
    ChannelSeries,
    FeatureSeries,
    MapEpicenter,
    MapIncident,
    MapSiteState,
    MapState,
    MetricSeries,
    MultiChannelFeatures,
)

# Roles con acceso a Consola C4I (RBAC §2) = fuente única desde la matriz de rutas.
CONSOLE_ROLES: tuple[str, ...] = tuple(
    sorted(role for role, routes in ROLE_ROUTE_MATRIX.items() if CONSOLE in routes)
)
_require_console = require_roles(*CONSOLE_ROLES)

# Límites de rango (segundos).
_MAX_FEATURES_SPAN_S = 2 * 3600  # crudo 1 s: máx 2 h por request
_DEFAULT_FEATURES_SPAN_S = 10 * 60  # default: últimos 10 min
_DEFAULT_METRICS_SPAN_S = 24 * 3600  # default: últimas 24 h
_BUCKET_1H_SPAN_S = 7 * 24 * 3600  # spans > 7 días → bucket 1h por defecto

_BUCKETS = ("1m", "1h")

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


async def _site_calibrated(conn: AsyncConnection, site_id: UUID) -> bool:
    """¿Puede el SOC pintar 'g' y 'cm/s' para este sitio, o solo unidades relativas?

    Default-deny: un sitio sin sensores visibles (RLS) o con alguno sin
    ``calibration_source`` cuenta como NO calibrado. ``bool_and`` sobre cero filas
    devuelve NULL, que aquí colapsa a ``False``.
    """
    stmt, params = select_site_calibrated(site_id=str(site_id))
    return bool((await conn.execute(stmt, params)).scalar())


def _parse_ts(value: str) -> datetime:
    """RFC3339 → datetime aware (UTC si viene naïve). 422 si no parsea."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise http_error(422, f"timestamp inválido (usa RFC3339): {value!r}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _resolve_range(
    from_: str | None, to: str | None, *, default_span_s: int
) -> tuple[datetime, datetime]:
    """Normaliza ``from``/``to`` a un rango aware; default = últimos ``default_span_s``."""
    to_ts = _parse_ts(to) if to else datetime.now(UTC)
    from_ts = _parse_ts(from_) if from_ else to_ts - timedelta(seconds=default_span_s)
    if to_ts <= from_ts:
        raise http_error(422, "rango inválido: 'to' debe ser posterior a 'from'")
    return from_ts, to_ts


def _resolve_bucket(bucket: str | None, from_ts: datetime, to_ts: datetime) -> str:
    """Bucket explícito (validado) o derivado del span: > 7 días → 1h, si no 1m."""
    if bucket is not None:
        if bucket not in _BUCKETS:
            raise http_error(422, "bucket inválido: usa '1m' o '1h'")
        return bucket
    return "1h" if (to_ts - from_ts).total_seconds() > _BUCKET_1H_SPAN_S else "1m"


def _map_site(r: Any) -> MapSiteState:
    """Fila del mapa → estado del sitio, con la sacudida MEDIDA ya clasificada.

    CON incidente abierto, `felt` es el PICO de su ventana (lo que el edificio
    llegó a sentir). SIN incidente, es el último minuto (lo que siente ahora).

    Y con incidente abierto NO se cae al último minuto: la sacudida ya pasó y ese
    bucket está en ruido de fondo, así que caer ahí pintaría de VERDE —"no se
    movió"— un inmueble que acaba de sacudirse. Visto en la nube con datos reales:
    Sitio Dev Puebla, incidente por `local_threshold`, pico medido 0.567 g (9× su
    umbral de disparo) y el minuto vivo en 0.0014 g. Sin pico ⇒ `unknown` (gris):
    no sabemos qué sintió, y eso no es lo mismo que decir que no sintió nada.
    """
    thresholds = thresholds_from_row(r.pga_watch_g, r.pga_trip_g, r.pgv_watch_cms, r.pgv_trip_cms)
    if r.incident_id is not None:
        pga, pgv = r.inc_pga_g, r.inc_pgv_cms
    else:
        pga, pgv = r.max_pga_g, r.max_pgv_cms
    return MapSiteState(
        site_id=r.site_id,
        tenant_id=r.tenant_id,
        name=r.name,
        criticality=r.criticality,
        lon=r.lon,
        lat=r.lat,
        last_bucket=r.last_bucket,
        max_pga_g=r.max_pga_g,
        max_pgv_cms=r.max_pgv_cms,
        open_incident=(
            MapIncident(
                incident_id=r.incident_id,
                severity=r.severity,
                state=r.state,
                opened_at=r.opened_at,
            )
            if r.incident_id is not None
            else None
        ),
        felt=felt_band(pga, pgv, thresholds),
        felt_pga_g=pga,
        felt_pgv_cms=pgv,
        # bool_and sobre cero sensores da NULL ⇒ NO calibrado (default-deny).
        calibrated=bool(r.calibrated),
    )


@router.get("/map/state", response_model=MapState)
async def map_state(
    _claims: Claims = Depends(_require_console),
    conn: AsyncConnection = Depends(read_session),
) -> MapState:
    """Estado de todos los sitios visibles: sacudida medida + incidente + epicentros."""
    stmt, params = select_map_state()
    sites = [_map_site(r) for r in (await conn.execute(stmt, params)).all()]

    ep_stmt, ep_params = select_map_epicenters()
    epicenters = [
        MapEpicenter(
            event_id=r.event_id,
            source=r.source,
            lon=r.lon,
            lat=r.lat,
            magnitude=r.magnitude,
            depth_km=r.depth_km,
            detected_at=r.detected_at,
        )
        for r in (await conn.execute(ep_stmt, ep_params)).all()
    ]
    return MapState(sites=sites, epicenters=epicenters)


@router.get("/sites/{site_id}/features", response_model=FeatureSeries)
async def site_features(
    site_id: UUID,
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    channel: str | None = Query(None),
    _claims: Claims = Depends(_require_console),
    conn: AsyncConnection = Depends(read_session),
) -> FeatureSeries:
    """Strip de features 1 s de un sitio (vista segura). Span máx 2 h, default 10 min."""
    from_ts, to_ts = _resolve_range(from_, to, default_span_s=_DEFAULT_FEATURES_SPAN_S)
    if (to_ts - from_ts).total_seconds() > _MAX_FEATURES_SPAN_S:
        raise http_error(422, "rango de features excede el máximo de 2 h")
    stmt, params = select_features(
        site_id=str(site_id),
        from_ts=from_ts.isoformat(),
        to_ts=to_ts.isoformat(),
        channel=channel,
    )
    rows = (await conn.execute(stmt, params)).all()
    return FeatureSeries(
        ts=[r.ts for r in rows],
        pga=[r.pga_g for r in rows],
        pgv=[r.pgv_cms for r in rows],
        stalta=[r.stalta for r in rows],
        clipping=[r.clipping for r in rows],
        calibrated=await _site_calibrated(conn, site_id),
    )


@router.get("/sites/{site_id}/features/by-channel", response_model=MultiChannelFeatures)
async def site_features_by_channel(
    site_id: UUID,
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    _claims: Claims = Depends(_require_console),
    conn: AsyncConnection = Depends(read_session),
) -> MultiChannelFeatures:
    """Features 1 s por canal SEED (EHZ + EN[ZNE]). Mismo límite de 2 h que el strip.

    Una sola query agrupada en memoria: los canales de un sitio son 4, y pedirlos por
    separado multiplicaría por cuatro los planes de consulta sobre la vista segura.
    """
    from_ts, to_ts = _resolve_range(from_, to, default_span_s=_DEFAULT_FEATURES_SPAN_S)
    if (to_ts - from_ts).total_seconds() > _MAX_FEATURES_SPAN_S:
        raise http_error(422, "rango de features excede el máximo de 2 h")

    stmt, params = select_features_by_channel(
        site_id=str(site_id), from_ts=from_ts.isoformat(), to_ts=to_ts.isoformat()
    )
    rows = (await conn.execute(stmt, params)).all()

    grouped: dict[str, ChannelSeries] = {}
    for r in rows:
        series = grouped.get(r.channel)
        if series is None:
            series = ChannelSeries(channel=r.channel, ts=[], pga=[], pgv=[], stalta=[], clipping=[])
            grouped[r.channel] = series
        series.ts.append(r.ts)
        series.pga.append(r.pga_g)
        series.pgv.append(r.pgv_cms)
        series.stalta.append(r.stalta)
        series.clipping.append(r.clipping)

    return MultiChannelFeatures(
        channels=[grouped[c] for c in sorted(grouped)],
        calibrated=await _site_calibrated(conn, site_id),
    )


@router.get("/sites/{site_id}/metrics", response_model=MetricSeries)
async def site_metrics(
    site_id: UUID,
    bucket: str | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    _claims: Claims = Depends(_require_console),
    conn: AsyncConnection = Depends(read_session),
) -> MetricSeries:
    """Máximos por bucket de un sitio (cagg 1m/1h con JOIN sites). Default 24 h."""
    from_ts, to_ts = _resolve_range(from_, to, default_span_s=_DEFAULT_METRICS_SPAN_S)
    resolved = _resolve_bucket(bucket, from_ts, to_ts)
    stmt, params = select_metrics(
        bucket=resolved,
        site_id=str(site_id),
        from_ts=from_ts.isoformat(),
        to_ts=to_ts.isoformat(),
    )
    rows = (await conn.execute(stmt, params)).all()
    return MetricSeries(
        bucket=resolved,
        ts=[r.bucket for r in rows],
        max_pga_g=[r.max_pga_g for r in rows],
        max_pgv_cms=[r.max_pgv_cms for r in rows],
        calibrated=await _site_calibrated(conn, site_id),
    )
