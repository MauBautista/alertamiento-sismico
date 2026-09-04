"""Contrato forense de un incidente (T-2.40).

Todo lo que puede faltar es opcional Y trae su razón. La regla que gobierna este
módulo: **un valor ausente nunca se rellena con 0**. "No se midió" y "se midió 0" son
hechos distintos, y confundirlos en un dictamen que puede acabar ante Protección Civil
no es un detalle de presentación.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

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
    """Sismo del catálogo de referencia que el criterio de `T-5.11` declara NUESTRO.

    Es el único contraste externo disponible. Sirve para declarar "la red estimó
    esto, el catálogo dice aquello", no para corregir el dato propio.

    **No es ya "el más cercano en el tiempo".** Hasta `T-5.11` lo era, y por eso
    un sismo de otro continente ocurrido dentro de ±120 s se imprimía como el
    nuestro en un dictamen firmado. Ahora es el que pasó los tres criterios de
    identidad, y los campos de abajo son las medidas que lo sostienen.
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

    #: [T-5.11] Distancia epicentro↔SITIO (km): la que decide la identidad, y la
    #: única disponible en la ruta del receptor, que no tiene epicentro propio.
    km_al_sitio: float | None = None
    #: Rumbo del sitio hacia el epicentro, en la rosa de 16.
    rumbo_al_sitio: str | None = None
    #: PGA que ATTEN-LAW v1 predice en el sitio. ``None`` si el catálogo no
    #: publicó magnitud — y entonces la coherencia no se pudo verificar.
    pga_esperada_g: float | None = None


class CatalogDelta(BaseModel):
    """Diferencia entre lo que estimó la red y lo que dice el catálogo."""

    km: float | None = None
    bearing: str | None = None
    dt_s: float
    magnitude: float | None = None


class CatalogCriterion(BaseModel):
    """[T-5.11] Los tres umbrales que se aplicaron, para poder leer el veredicto.

    Viajan con la respuesta y se imprimen: un criterio que no se puede citar no
    es defendible ante quien firma el dictamen.
    """

    #: Velocidad de la onda que produce la sacudida (km/s).
    v_s_km_s: float
    #: Tolerancia de reloj, y único margen hacia atrás.
    margen_s: float
    #: Radio máximo epicentro↔sitio (km).
    radio_km: float
    #: Piso de PGA estimada en el sitio (g).
    pga_minima_g: float


class CatalogDiscard(BaseModel):
    """[T-5.11] Un sismo que estaba en la ventana y NO es el nuestro.

    Existe para que el sistema pueda decir «hay un evento en el catálogo pero no
    es el nuestro», que es justo lo que no sabía decir: sin esto un descarte se
    convierte en una pantalla vacía que el operador lee como «no pasó nada».
    """

    catalog_key: str
    #: Vocabulario cerrado de `forensics.correlacion` (`fuera_de_radio`, …).
    motivo: str
    #: La misma razón en una línea legible, con el número que la motivó.
    detalle: str
    km_al_sitio: float | None = None
    retraso_s: float | None = None
    retraso_admisible_s: float | None = None
    pga_esperada_g: float | None = None


class CatalogCorrelation(BaseModel):
    """[T-5.11] Cómo se decidió la correlación con el catálogo, y con qué resultado."""

    #: Uno de los cinco estados de `shared/glossary/procedencia.json` (T-5.10).
    #: `sin_correlacion` cuando se consultó el catálogo y nada suyo es éste.
    estado: str
    #: `contrastado` si hay epicentro propio con el que contrastar;
    #: `no_verificable` si la identidad se estableció pero no hay nada nuestro
    #: que comparar — y llamarlo «contraste» prometería una verificación que no
    #: ocurrió. ``None`` cuando no hubo acierto.
    verificacion: str | None = None
    criterio: CatalogCriterion
    #: Los que estaban en la ventana y no casaron, con su motivo.
    descartes: list[CatalogDiscard] = []


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

    ``json_schema_serialization_defaults_required``: esta respuesta se serializa
    ENTERA —el router no usa ``exclude_none`` ni ``exclude_unset``—, así que todo
    campo con default viaja igual, con su ``null`` o su lista vacía. Sin esta línea
    el contrato los publicaba como **ausentes posibles** y el SDK los generaba
    ``?: T``, que es una ausencia que nunca ocurre: obliga a cada consumidor a
    escribir una rama muerta. Es lo que dejó inalcanzable —y a la vez formalmente
    justificada— la rama «NO DISPONIBLE» de ``ComplianceDeclared``.
    """

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

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
    #: [T-5.11] El criterio que se aplicó y lo que descartó. Va SIEMPRE, también
    #: —y sobre todo— cuando no hubo acierto: es donde vive la diferencia entre
    #: «el catálogo no tiene nada» y «lo que tiene no es esto».
    catalog_correlation: CatalogCorrelation | None = None

    sensors: list[SensorInfo] = []
    #: ``False`` si ALGÚN sensor activo carece de procedencia de calibración.
    #: Default-deny: sin sensores no se afirma que esté calibrado.
    calibrated: bool = False

    #: [T-2.82] Marco normativo DECLARADO por el cliente dueño del incidente. Es la
    #: única parte de esta respuesta que TAKAB no midió, y por eso viaja con su
    #: procedencia y su deslinde pegados: la pantalla que la pinta es la misma en la
    #: que el inspector FIRMA el dictamen.
    compliance: ComplianceDocOut = Field(default_factory=ComplianceDocOut)
