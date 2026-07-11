"""Modelos de respuesta de telemetría (T-1.22 · B3).

Respuestas COLUMNARES (listas paralelas) para las series de tiempo del SOC: el
payload es pequeño y el frontend las pinta directo sin re-pivotar. Las features
salen SIEMPRE de la vista ``waveform_features_1s_secure`` y las métricas de los
caggs con JOIN a ``sites`` (regla dura de tenancy; ver ``queries.telemetry``).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class FeatureSeries(BaseModel):
    """Strip de features 1 s (crudo procesado en el edge, no waveform 100 sps).

    ``calibrated`` es falso mientras algún sensor activo del sitio no declare su
    ``calibration_source``. Con él en falso, ``pga``/``pgv`` NO son ``g`` ni ``cm/s``:
    son cuentas escaladas por las sensibilidades placeholder del edge. La consola
    pinta unidades relativas — un número físico inventado es peor que ninguno.
    """

    ts: list[datetime]
    pga: list[float | None]
    pgv: list[float | None]
    stalta: list[float | None]
    clipping: list[bool]
    calibrated: bool


class ChannelSeries(BaseModel):
    """Una traza por canal SEED del RS4D: ``EHZ`` (geófono) o ``EN[ZNE]`` (acelerómetro)."""

    channel: str
    ts: list[datetime]
    pga: list[float | None]
    pgv: list[float | None]
    stalta: list[float | None]
    clipping: list[bool]


class MultiChannelFeatures(BaseModel):
    """Strip multicanal (T-1.34). Sigue siendo features 1 s, NO waveform 100 sps.

    Los canales llegan ordenados alfabéticamente y solo aparecen los que tienen datos
    en el rango: un canal muerto se ve por su ausencia, no por una línea plana falsa.
    """

    channels: list[ChannelSeries]
    calibrated: bool


class MetricSeries(BaseModel):
    """Máximos por bucket (1m o 1h) de un sitio, para rangos medios y largos.

    Los nombres ``max_pga_g``/``max_pgv_cms`` vienen del cagg y se conservan por
    compatibilidad; su unidad real depende de ``calibrated`` (ver ``FeatureSeries``).
    """

    bucket: str
    ts: list[datetime]
    max_pga_g: list[float | None]
    max_pgv_cms: list[float | None]
    calibrated: bool


class MapIncident(BaseModel):
    """Incidente abierto (no cerrado) más reciente de un sitio, para el mapa."""

    incident_id: UUID
    severity: str
    state: str
    opened_at: datetime


class MapEpicenter(BaseModel):
    """Dónde se ORIGINÓ el sismo. No es ningún edificio.

    Sale de ``seismic_events.epicenter``: catálogo SSN/USGS, motor de quórum o
    reubicación manual del operador. Un incidente puede no tener evento asociado
    (una alerta SASMEX sola no dice dónde fue), y un evento puede no tener
    epicentro conocido: en ambos casos NO aparece aquí y el mapa lo DECLARA en
    vez de inventar un punto.
    """

    event_id: str
    source: str
    lon: float
    lat: float
    magnitude: float | None
    depth_km: float | None
    detected_at: datetime


class MapSiteState(BaseModel):
    """Estado de un sitio en el mapa SOC: última métrica 1m + incidente abierto."""

    site_id: UUID
    tenant_id: UUID
    name: str
    criticality: str
    lon: float
    lat: float
    last_bucket: datetime | None
    max_pga_g: float | None
    max_pgv_cms: float | None
    open_incident: MapIncident | None

    # Lo que este EDIFICIO sintió, medido por su propio sensor y clasificado con
    # los umbrales de su rule_set (`felt.py`). NO es la severidad del incidente:
    # una alerta SASMEX abre `critical` aunque el inmueble no se haya movido.
    # `unknown` = el sitio no reportó nada; jamás significa "no se movió".
    felt: str
    felt_pga_g: float | None
    felt_pgv_cms: float | None
    #: False ⇒ PGA/PGV son RELATIVOS, no unidades físicas: la UI no puede
    #: presentarlos como una intensidad real (db/schema.sql §sensors).
    calibrated: bool


class MapState(BaseModel):
    """Snapshot de todos los sitios visibles (RLS) que alimenta el mapa del SOC."""

    sites: list[MapSiteState]
    #: Epicentros de los eventos con incidente abierto. Vacío = no se conoce
    #: ninguno; el mapa lo dice, no lo supone.
    epicenters: list[MapEpicenter]
