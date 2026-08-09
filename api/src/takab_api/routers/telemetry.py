"""Router de telemetría del SOC (T-1.22 · B3): features, métricas y estado del mapa.

Solo lectura (``read_session`` → rol ``takab_app`` + GUCs RLS del request). El acceso
se restringe a los roles con MONITOREO de RBAC §2 (todos los de superficie web); los
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
from takab_api.auth.deps import get_console_scope, require_roles
from takab_api.auth.matrix import CONSOLE, ROLE_ROUTE_MATRIX
from takab_api.auth.scope import ConsoleScope
from takab_api.felt import felt_band, thresholds_from_row
from takab_api.queries.telemetry import (
    select_features,
    select_features_by_channel,
    select_map_epicenters,
    select_map_state,
    select_metrics,
    select_site_calibrated,
)
from takab_api.routers._common import http_error, parse_ts, read_session
from takab_api.schemas.fleet import DEGRADADO, derive_fleet_state, fleet_degrade_reasons
from takab_api.schemas.telemetry import (
    SIN_GABINETE,
    ChannelSeries,
    FeatureSeries,
    MapEpicenter,
    MapIncident,
    MapSiteState,
    MapState,
    MetricSeries,
    MultiChannelFeatures,
)
from takab_api.settings import Settings

# Roles con acceso a MONITOREO (RBAC §2) = fuente única desde la matriz de rutas.
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


# [T-1.57] El parser vive en routers._common (lo comparten incidents/audit);
# alias local para no tocar llamadores ni tests de este router.
_parse_ts = parse_ts


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


def _map_link(r: Any, s: Settings) -> tuple[str, list[str]]:
    """[T-2.46] Estado del enlace de la ESTACIÓN, con la verdad única de la flota.

    Sin gabinete (o con el único retirado) el resultado es ``SIN GABINETE``: no hay
    hardware del que predicar un enlace, y decir ``SIN ENLACE`` mandaría a alguien a
    revisar una antena inexistente.

    Con gabinete se delega ENTERO en ``derive_fleet_state`` — la misma función que
    pinta /fleet, con los mismos umbrales de ``Settings``. Reimplementarla aquí
    crearía una segunda opinión sobre el mismo gabinete, y tarde o temprano las dos
    pantallas dirían cosas distintas del mismo hecho.

    Las razones solo aplican a ``DEGRADADO``: en ``SIN ENLACE`` el problema es el
    silencio, no una métrica, y en ``OPERATIVO`` son vacías por definición.
    """
    if r.link_gateway_id is None:
        return SIN_GABINETE, []
    metrics = {
        "power_status": r.link_power_status,
        "battery_pct": r.link_battery_pct,
        "cert_days_remaining": r.link_cert_days_remaining,
        "mqtt_rtt_ms": r.link_mqtt_rtt_ms,
        "seedlink_lag_s": r.link_seedlink_lag_s,
        "ntp_offset_ms": r.link_ntp_offset_ms,
        # [T-2.70.a·B1] Un gabinete sin dueño de pines late perfectamente: sin
        # esta clave el mapa lo pintaría OPERATIVO mientras la Flota lo marca
        # DEGRADADO, y serían dos opiniones del mismo hecho.
        "relays_state": r.link_relays_state,
    }
    limits = {
        "battery_min_pct": s.fleet_battery_min_pct,
        "cert_min_days": s.fleet_cert_min_days,
        "mqtt_rtt_max_ms": s.fleet_mqtt_rtt_max_ms,
        "seedlink_lag_max_s": s.fleet_seedlink_lag_max_s,
        "ntp_offset_max_ms": s.fleet_ntp_offset_max_ms,
    }
    state = derive_fleet_state(
        age_s=r.link_age_s, sin_enlace_s=s.sin_enlace_min * 60.0, **metrics, **limits
    )
    reasons = fleet_degrade_reasons(**metrics, **limits) if state == DEGRADADO else []
    return state, reasons


def _map_site(r: Any, s: Settings) -> MapSiteState:
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
    link_state, link_reasons = _map_link(r, s)
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
        # [T-2.46] El enlace va en su PROPIO canal: jamás toca `felt`. Uno mide el
        # suelo y otro la red; si el enlace pudiera alterar el color, el mapa
        # mentiría sobre lo que el edificio sintió cada vez que cae una antena.
        link_state=link_state,
        link_reasons=link_reasons,
        last_heartbeat_ts=r.link_health_ts,
        mqtt_rtt_ms=r.link_mqtt_rtt_ms,
        seedlink_lag_s=r.link_seedlink_lag_s,
    )


def _scope_or_404(scope: ConsoleScope, site_id: UUID) -> None:
    """[T-2.45] Fuera de alcance ⇒ 404, nunca 403: un 403 confirma que el sitio existe."""
    if not scope.allows(str(site_id)):
        raise http_error(404, "sitio no encontrado")


@router.get("/map/state", response_model=MapState)
async def map_state(
    _claims: Claims = Depends(_require_console),
    scope: ConsoleScope = Depends(get_console_scope),
    conn: AsyncConnection = Depends(read_session),
) -> MapState:
    """Estado de los sitios visibles Y dentro del alcance: sacudida + enlace + epicentros."""
    settings = Settings()
    stmt, params = select_map_state(scope)
    sites = [_map_site(r, settings) for r in (await conn.execute(stmt, params)).all()]

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
            node_count=r.node_count,
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
    scope: ConsoleScope = Depends(get_console_scope),
    conn: AsyncConnection = Depends(read_session),
) -> FeatureSeries:
    """Strip de features 1 s de un sitio (vista segura). Span máx 2 h, default 10 min."""
    _scope_or_404(scope, site_id)
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
    scope: ConsoleScope = Depends(get_console_scope),
    conn: AsyncConnection = Depends(read_session),
) -> MultiChannelFeatures:
    """Features 1 s por canal SEED (EHZ + EN[ZNE]). Mismo límite de 2 h que el strip.

    Una sola query agrupada en memoria: los canales de un sitio son 4, y pedirlos por
    separado multiplicaría por cuatro los planes de consulta sobre la vista segura.
    """
    _scope_or_404(scope, site_id)
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
    scope: ConsoleScope = Depends(get_console_scope),
    conn: AsyncConnection = Depends(read_session),
) -> MetricSeries:
    """Máximos por bucket de un sitio (cagg 1m/1h con JOIN sites). Default 24 h."""
    _scope_or_404(scope, site_id)
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
