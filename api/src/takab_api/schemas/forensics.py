"""Contrato forense de un incidente (T-2.40).

Todo lo que puede faltar es opcional Y trae su razón. La regla que gobierna este
módulo: **un valor ausente nunca se rellena con 0**. "No se midió" y "se midió 0" son
hechos distintos, y confundirlos en un dictamen que puede acabar ante Protección Civil
no es un detalle de presentación.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from takab_api.schemas.compliance import ComplianceDocOut


class ChannelPeak(BaseModel):
    """Pico de un canal SEED en la ventana del incidente."""

    channel: str
    peak_pga_g: float | None = None
    peak_pgv_cms: float | None = None
    peak_rms: float | None = None
    peak_stalta: float | None = None
    energy_sum: float | None = None
    clipped: bool = False
    samples: int = 0
    peak_ts: datetime | None = None


class SensorInfo(BaseModel):
    """Sensor del sitio. ``calibration_source`` decide la honestidad de las unidades.

    Sin procedencia declarada, el PGA/PGV NO está en g ni cm/s: son valores
    RELATIVOS. Un dictamen que los presentara como gravedades estaría afirmando una
    medición física que nadie hizo.
    """

    sensor_id: UUID
    kind: str
    model: str
    serial: str | None = None
    channels: list[str] = []
    sample_rate: int | None = None
    mount: str | None = None
    calibration_source: str | None = None


class CatalogMatch(BaseModel):
    """Sismo del catálogo de referencia más cercano en tiempo.

    Es el único contraste externo disponible. Sirve para declarar "la red estimó
    esto, el catálogo dice aquello", no para corregir el dato propio.
    """

    catalog_key: str
    origin_time: datetime
    magnitude: float | None = None
    place: str | None = None
    depth_km: float | None = None
    source: str
    lat: float | None = None
    lon: float | None = None
    dt_s: float


class CatalogDelta(BaseModel):
    """Diferencia entre lo que estimó la red y lo que dice el catálogo."""

    km: float | None = None
    bearing: str | None = None
    dt_s: float
    magnitude: float | None = None


class QuorumPeer(BaseModel):
    """Estación que votó. Coordenadas nulas = la RLS oculta esa estación (otra red)."""

    sensor_id: UUID
    site_code: str | None = None
    delta_s: float | None = None
    pga_g: float | None = None
    counted: bool
    lat: float | None = None
    lon: float | None = None


class SiteGeo(BaseModel):
    """Ficha del sitio para el croquis y la portada del dictamen."""

    code: str
    name: str
    criticality: str | None = None
    building_type: str | None = None
    address: str | None = None
    lat: float | None = None
    lon: float | None = None


class ForensicsOut(BaseModel):
    """Hechos medidos de un incidente. Una sola fuente para pantalla y PDF.

    ``lead_time_s`` es el tiempo de aviso GANADO: cuánto pasó entre la alerta y el
    pico de la sacudida. Solo tiene sentido con ``trigger='sasmex'`` — en un
    incidente disparado por umbral local la "alerta" ES la sacudida, y el número sería
    cero por construcción, no un logro. Cuando no se puede calcular vale ``None`` y
    ``lead_time_reason`` dice por qué; nunca 0.
    """

    incident_id: UUID
    site: SiteGeo | None = None
    window_from: datetime
    window_to: datetime

    channels: list[ChannelPeak] = []
    peak_pga_g: float | None = None
    peak_pgv_cms: float | None = None
    peak_ts: datetime | None = None
    felt_band: str = "unknown"

    lead_time_s: float | None = None
    lead_time_reason: str | None = None

    station_count: int = 0
    peers: list[QuorumPeer] = []

    catalog: CatalogMatch | None = None
    catalog_delta: CatalogDelta | None = None

    sensors: list[SensorInfo] = []
    #: ``False`` si ALGÚN sensor activo carece de procedencia de calibración.
    #: Default-deny: sin sensores no se afirma que esté calibrado.
    calibrated: bool = False

    #: [T-2.82] Marco normativo DECLARADO por el cliente dueño del incidente. Es la
    #: única parte de esta respuesta que TAKAB no midió, y por eso viaja con su
    #: procedencia y su deslinde pegados: la pantalla que la pinta es la misma en la
    #: que el inspector FIRMA el dictamen.
    compliance: ComplianceDocOut = Field(default_factory=ComplianceDocOut)
