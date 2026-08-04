"""Construcción del ``ReportModel`` desde la base (T-2.41).

Aísla el acceso a datos del render y del modelo: ``pdf.py`` no toca la DB y
``model.py`` no sabe que existe. Así el contenido del dictamen —donde puede haber una
mentira— se prueba sin abrir un PDF ni levantar Postgres.

La forma de onda cruda y el espectro son **best-effort**: llegan de un objeto de S3 que
puede no existir, estar a medias o venir en un encoding que el lector no soporta.
Cualquiera de esas cosas degrada la sección con su razón — jamás tumba la exportación
de una evidencia de compliance.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.dictamen.model import (
    STATUS_LABELS,
    ActionRow,
    ChannelRow,
    DictamenRow,
    EvidenceRow,
    ReportModel,
    VoteRow,
)
from takab_api.dictamen.mseed import MseedError, read_traces
from takab_api.forensics import build_forensics
from takab_api.queries import forensics as qf
from takab_api.schemas.forensics import ForensicsOut
from takab_api.settings import Settings

log = logging.getLogger(__name__)

#: Muestras máximas por canal para la FFT. 60 s a 100 sps es de sobra para ver el
#: contenido de una sacudida y acota el coste dentro de un request HTTP.
MAX_FFT_SAMPLES = 6000

_INCIDENT = text(
    """
    SELECT i.incident_id, i.site_id, i.event_id, i.opened_at, i.closed_at,
           i.severity, i.state, i.trigger,
           s.name AS site_name, s.code AS site_code, s.criticality,
           ST_Y(s.geom::geometry)::float8 AS site_lat,
           ST_X(s.geom::geometry)::float8 AS site_lon,
           e.source AS event_source,
           ST_Y(e.epicenter::geometry)::float8 AS epi_lat,
           ST_X(e.epicenter::geometry)::float8 AS epi_lon
    FROM incidents i
    JOIN sites s ON s.site_id = i.site_id
    LEFT JOIN seismic_events e ON e.event_id = i.event_id
    WHERE i.incident_id = CAST(:id AS uuid)
    """
)

_DICTAMENS = text(
    "SELECT dictamen_id, status, created_at, signed_by, basis, supersedes_dictamen_id "
    "FROM dictamens WHERE incident_id = CAST(:id AS uuid) ORDER BY created_at DESC"
)

_ACTIONS = text(
    "SELECT ts, kind, actor FROM incident_actions "
    "WHERE incident_id = CAST(:id AS uuid) ORDER BY ts ASC"
)

_EVIDENCE = text(
    "SELECT kind, sha256, created_at, s3_key FROM evidence_objects "
    "WHERE incident_id = CAST(:id AS uuid) ORDER BY created_at ASC"
)


def folio_of(site_code: str, opened_at: datetime, incident_id: str, variant: str) -> str:
    """Identificador legible del documento. Se imprime y se cita por teléfono."""
    suffix = "E" if variant == "executive" else "T"
    short = incident_id.replace("-", "")[:8].upper()
    return f"TKB-{site_code}-{opened_at:%Y%m%d}-{short}-{suffix}"


async def build_model(
    conn: AsyncConnection,
    incident_id: str,
    *,
    variant: str = "technical",
    generated_at: datetime,
    fetch_object=None,
    settings: Settings | None = None,
) -> ReportModel | None:
    """Modelo completo del dictamen, o ``None`` si la RLS no ve el incidente.

    ``fetch_object`` es la lectura del miniSEED de S3 (``s3_key -> bytes``). Se inyecta
    para que el modelo sea probable sin red; si es ``None``, la sección de onda cruda se
    declara no disponible.
    """
    s = settings or Settings()
    row = (await conn.execute(_INCIDENT, {"id": incident_id})).first()
    if row is None:
        return None
    inc = dict(row._mapping)

    forensics = await build_forensics(conn, incident_id, s)
    if forensics is None:  # pragma: no cover - el SELECT de arriba ya lo cubriría
        return None

    dictamens = [
        DictamenRow(
            dictamen_id=str(r.dictamen_id),
            status=r.status,
            created_at=r.created_at,
            signed_by=str(r.signed_by) if r.signed_by else None,
            rule_set_version=(r.basis or {}).get("rule_set_version", "sin versión"),
            supersedes=str(r.supersedes_dictamen_id) if r.supersedes_dictamen_id else None,
        )
        for r in (await conn.execute(_DICTAMENS, {"id": incident_id})).all()
    ]
    head = dictamens[0] if dictamens else None

    actions = [
        ActionRow(ts=r.ts, kind=r.kind, actor=r.actor)
        for r in (await conn.execute(_ACTIONS, {"id": incident_id})).all()
    ]
    evidence_rows = (await conn.execute(_EVIDENCE, {"id": incident_id})).all()
    evidence = [
        EvidenceRow(kind=r.kind, sha256=r.sha256, created_at=r.created_at) for r in evidence_rows
    ]

    series = await _series(conn, site_id=str(inc["site_id"]), f=forensics)
    raw, rate, spectrum, peak_hz, reason = await _raw_waveform(evidence_rows, fetch_object, variant)

    return ReportModel(
        folio=folio_of(inc["site_code"], inc["opened_at"], incident_id, variant),
        incident_id=incident_id,
        site_name=inc["site_name"],
        site_code=inc["site_code"],
        site_criticality=inc["criticality"],
        site_lat=inc["site_lat"],
        site_lon=inc["site_lon"],
        opened_at=inc["opened_at"],
        closed_at=inc["closed_at"],
        severity=inc["severity"],
        trigger=inc["trigger"],
        state=inc["state"],
        event_id=inc["event_id"],
        event_source=inc["event_source"],
        epicenter_lat=inc["epi_lat"],
        epicenter_lon=inc["epi_lon"],
        verdict_status=head.status if head else None,
        verdict_label=(
            STATUS_LABELS.get(head.status, head.status) if head else "SIN DICTAMEN REGISTRADO"
        ),
        verdict_signed=bool(head and head.signed_by),
        rule_set_version=head.rule_set_version if head else None,
        peak_pga_g=forensics.peak_pga_g,
        peak_pgv_cms=forensics.peak_pgv_cms,
        peak_ts=forensics.peak_ts,
        felt_band=forensics.felt_band,
        calibrated=forensics.calibrated,
        lead_time_s=forensics.lead_time_s,
        lead_time_reason=forensics.lead_time_reason,
        station_count=forensics.station_count,
        catalog_line=_catalog_line(forensics),
        generated_at=generated_at,
        channels=[
            ChannelRow(
                channel=c.channel,
                peak_pga_g=c.peak_pga_g,
                peak_pgv_cms=c.peak_pgv_cms,
                peak_rms=c.peak_rms,
                peak_stalta=c.peak_stalta,
                energy_sum=c.energy_sum,
                clipped=c.clipped,
                samples=c.samples,
                peak_ts=c.peak_ts,
            )
            for c in forensics.channels
        ],
        dictamens=dictamens,
        votes=[
            VoteRow(
                label=p.site_code or (str(p.sensor_id)[:8] + " · OTRA RED"),
                delta_s=p.delta_s,
                pga_g=p.pga_g,
                counted=p.counted,
            )
            for p in forensics.peers
        ],
        actions=actions,
        evidence=evidence,
        sensors=[sn.model_dump() for sn in forensics.sensors],
        peers=[p.model_dump() for p in forensics.peers],
        series=series,
        raw_waveform=raw,
        raw_sample_rate=rate,
        spectrum=spectrum,
        spectrum_peak_hz=peak_hz,
        raw_unavailable_reason=reason,
    )


def _catalog_line(f: ForensicsOut) -> str | None:
    if not f.catalog or not f.catalog_delta:
        return None
    d = f.catalog_delta
    dist = (
        f"{d.km:.0f} km {d.bearing or ''}".strip()
        if d.km is not None
        else "sin epicentro propio que comparar"
    )
    mag = f" · M {f.catalog.magnitude:.1f}" if f.catalog.magnitude is not None else ""
    return f"{f.catalog.source} {f.catalog.catalog_key}{mag} · Δt {d.dt_s:.0f} s · {dist}"


async def _series(
    conn: AsyncConnection, *, site_id: str, f: ForensicsOut
) -> dict[str, list[tuple[datetime, float | None, bool]]]:
    """Serie 1 Hz por canal para las trazas de envolvente."""
    out: dict[str, list[tuple[datetime, float | None, bool]]] = {}
    rows = await qf.series(conn, site_id=site_id, from_ts=f.window_from, to_ts=f.window_to)
    for r in rows:
        out.setdefault(r.channel, []).append((r.ts, r.pga_g, bool(r.clipping)))
    return out


async def _raw_waveform(evidence_rows, fetch_object, variant: str):
    """`(waveform, rate, spectrum, peak_hz, reason)` — best-effort y fail-soft."""
    if variant != "technical":
        return {}, None, None, None, "El resumen ejecutivo no incluye análisis de onda."
    if fetch_object is None:
        return {}, None, None, None, None

    mseed = next((r for r in evidence_rows if r.kind == "miniseed"), None)
    if mseed is None:
        return {}, None, None, None, None

    try:
        blob = fetch_object(mseed.s3_key)
        traces = read_traces(blob)
    except MseedError as exc:
        log.warning("dictamen: miniSEED ilegible (%s): %s", mseed.s3_key, exc)
        return {}, None, None, None, f"MINISEED ARCHIVADO ILEGIBLE · {exc}"
    except Exception as exc:  # noqa: BLE001 - un fallo de S3 no puede tumbar la evidencia
        log.warning("dictamen: no se pudo leer el miniSEED (%s): %s", mseed.s3_key, exc)
        return {}, None, None, None, "NO SE PUDO RECUPERAR EL MINISEED ARCHIVADO"

    if not traces:
        return {}, None, None, None, "EL MINISEED ARCHIVADO NO CONTIENE TRAZAS"

    waveform = {t.channel: t.samples for t in traces}
    rate = traces[0].sample_rate
    spectrum, peak_hz = _spectrum(max(traces, key=lambda t: len(t.samples)), rate)
    return waveform, rate, spectrum, peak_hz, None


def _spectrum(trace, rate: float):
    """Espectro de amplitud del canal con más muestras.

    Se le quita la media antes de transformar: el waveform crudo del RS4D trae una
    componente DC enorme (millones de cuentas) que, sin restarla, domina el espectro
    entero y esconde todo lo demás. Es el mismo hallazgo de T-2.25 sobre el panel.
    """
    import numpy as np  # noqa: PLC0415 - import perezoso: solo el técnico lo necesita

    samples = np.asarray(trace.samples[:MAX_FFT_SAMPLES], dtype=np.float64)
    if samples.size < 32 or rate <= 0:
        return None, None
    samples = samples - samples.mean()
    windowed = samples * np.hanning(samples.size)
    amps = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(samples.size, d=1.0 / rate)

    # Se descarta la primera muestra (DC residual) para el pico: no es una frecuencia.
    peak_hz = float(freqs[1:][int(np.argmax(amps[1:]))]) if amps.size > 1 else None
    # Se diezma a ~400 puntos: más no se distingue en 180 mm de papel.
    step = max(1, freqs.size // 400)
    return (freqs[::step].tolist(), amps[::step].tolist()), peak_hz
