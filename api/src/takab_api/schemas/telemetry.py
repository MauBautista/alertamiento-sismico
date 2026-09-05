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

#: [T-2.46] Cuarto estado de enlace, exclusivo del MAPA (no existe en la flota).
#:
#: ``schemas.fleet`` deriva el estado de un GABINETE, así que sus tres valores
#: presuponen que hay uno. El mapa habla de ESTACIONES, y una estación puede no
#: tener hardware instalado todavía. Colapsarlo en ``SIN ENLACE`` mandaría a un
#: técnico a revisar la antena de un edificio donde no hay nada que revisar; y
#: pintarlo como OPERATIVO sería peor. Es un hecho distinto y se dice distinto.
SIN_GABINETE = "SIN GABINETE"


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
    #: Estaciones que corroboraron el evento por quórum (T-1.71). Solo lo llevan los
    #: eventos ``local_quorum`` (``meta.node_count``); ``None`` en los demás.
    node_count: int | None = None


class MapSiteState(BaseModel):
    """Estado de un sitio en el mapa SOC: última métrica 1m + incidente abierto."""

    site_id: UUID
    tenant_id: UUID
    name: str
    #: [T-5.05] El código del sitio, que es un HECHO del dato y no una política.
    #: La consola lo necesita para distinguir un sitio de demostración de uno real
    #: —hoy se ven idénticos en el mapa— y decidir cómo se rotula es cosa de la
    #: presentación, no del contrato: aquí sale el código y allí se interpreta.
    code: str
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

    # --- [T-2.46] Enlace con el gabinete de la estación -----------------------
    # El mapa decía qué SINTIÓ cada edificio y nada sobre si su gabinete sigue
    # vivo: un punto verde podía ser "todo bien" o "llevo seis horas sin datos y
    # este color es un recuerdo". Exactamente lo que prohíbe la regla de oro 7.
    #
    # Lo deriva ``derive_fleet_state`` — la MISMA función que pinta /fleet — más
    # ``SIN GABINETE`` cuando la estación no tiene hardware. Aditivo y opcional:
    # ningún consumidor previo del contrato se rompe.
    #: ``OPERATIVO`` | ``DEGRADADO`` | ``SIN ENLACE`` | ``SIN GABINETE``.
    #: El default NO afirma un enlace vivo: sin dato, no hay gabinete que valga.
    link_state: str = SIN_GABINETE
    #: QUÉ degrada, en el idioma de la UI. Vacía salvo en ``DEGRADADO``: en
    #: ``SIN ENLACE`` el problema es el silencio, no una métrica.
    link_reasons: list[str] = []
    #: Último latido conocido. Es lo que permite a la UI decir la EDAD ("hace
    #: 1 h") en vez de dejar el color como si fuera una lectura viva.
    last_heartbeat_ts: datetime | None = None
    mqtt_rtt_ms: float | None = None
    seedlink_lag_s: float | None = None

    # --- [T-5.26] Identidad del hardware de la estación -----------------------
    # El mapa decía qué sintió el edificio y cómo estaba su enlace, y NADA sobre
    # qué aparato lo dice. Para saber el serial, el firmware o el modelo del
    # sismógrafo había que abandonar la consola e irse a Flota — un salto de
    # pantalla que en una demostración cae en el peor momento, y que en un
    # incidente real obliga a cambiar de contexto justo cuando no se debe.
    #
    # Todos opcionales y con `None` = **no se sabe**, jamás un valor de relleno:
    # una estación puede no tener gabinete (`SIN GABINETE`), o tenerlo sin
    # sensores dados de alta. La UI lo declara igual que el resto de sus huecos.
    #: Serial del gabinete que responde por la estación (el del latido más fresco).
    serial: str | None = None
    #: Versión de firmware que ese gabinete DECLARA (`gateways.fw_version`).
    fw_version: str | None = None
    #: Modelo(s) de los sismógrafos activos del sitio. Con varios distintos van
    #: los dos separados por «·»: inventar uno solo sería peor que enseñarlos.
    sensor_models: str | None = None
    #: Respaldo eléctrico: `line` · `battery` · `unknown` (o `None` si no hay dato).
    #: Ya viajaba en la consulta del mapa y se tiraba al construir la respuesta.
    power_status: str | None = None
    battery_pct: float | None = None


class MapState(BaseModel):
    """Snapshot de todos los sitios visibles (RLS) que alimenta el mapa del SOC."""

    sites: list[MapSiteState]
    #: Epicentros de los eventos con incidente abierto. Vacío = no se conoce
    #: ninguno; el mapa lo dice, no lo supone.
    epicenters: list[MapEpicenter]
