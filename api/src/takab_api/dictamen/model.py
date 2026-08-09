"""Modelo del dictamen (T-2.41): PURO, sin fpdf ni DB.

Separar el modelo del render permite probar el CONTENIDO —que es donde puede haber una
mentira— sin abrir un PDF. La regla que gobierna todo el módulo: **un dato ausente
produce un literal de ausencia con su razón, nunca 0, nunca cadena vacía, nunca un
guion suelto.** Un "0.000 g" en un dictamen que acabará ante Protección Civil no es un
detalle de formato.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime

from takab_api.compliance import ComplianceDocument

STATUS_LABELS: dict[str, str] = {
    "no_inhabit_inspect": "NO HABITAR · INSPECCIÓN",
    "inhabit_monitor": "HABITAR · MONITOREO",
    "normal_operation": "OPERACIÓN NORMAL",
    "restricted": "ACCESO RESTRINGIDO",
}

#: Qué hacer con cada veredicto. Tabla FIJA, no generada: son instrucciones de
#: seguridad y no pueden depender de nada que varíe entre dos ejecuciones.
STATUS_ACTIONS: dict[str, tuple[str, ...]] = {
    "no_inhabit_inspect": (
        "No reingresar al inmueble hasta contar con inspección estructural.",
        "Mantener el perímetro y las rutas de evacuación despejadas.",
        "Solicitar evaluación de un ingeniero estructural con responsiva.",
    ),
    "restricted": (
        "Restringir el acceso a las zonas señaladas por el responsable del inmueble.",
        "Documentar daños visibles antes de mover nada.",
        "Programar inspección estructural.",
    ),
    "inhabit_monitor": (
        "Se puede ocupar el inmueble; mantener vigilancia de daños visibles.",
        "Reportar grietas nuevas, puertas que dejan de cerrar o ruidos estructurales.",
        "Conservar la evidencia de este evento para la próxima revisión.",
    ),
    "normal_operation": (
        "Operación normal.",
        "Sin acciones adicionales derivadas de este evento.",
    ),
}

DISCLAIMER = (
    "Dictamen operativo PRELIMINAR generado por TAKAB Ailert a partir de evidencia "
    "instrumental. No sustituye la evaluación estructural formal ni certifica reingreso "
    "seguro sin firma de ingeniería."
)

TS_FMT = "%Y-%m-%d %H:%M:%S UTC"

#: Rótulos de ausencia. Existen como constantes para que un test pueda exigirlos y
#: para que no se cuele un "—" suelto que no explica nada.
ABSENT = "SIN DATO"
NO_CALIBRATION = (
    "SIN FUENTE DE CALIBRACIÓN DECLARADA · las aceleraciones y velocidades de este "
    "documento son valores RELATIVOS del sensor, no unidades físicas."
)
NO_SPECTRUM = (
    "ANÁLISIS ESPECTRAL NO DISPONIBLE. Requiere la forma de onda cruda a 100 sps; el "
    "sistema no la transmite en continuo (solo sube a evidencia en eventos "
    "confirmados). Este incidente no tiene miniSEED archivado."
)
NO_GEOMETRY = "SIN GEOMETRÍA REGISTRADA · no se puede dibujar el croquis del evento."
CENTROID_NOTE = (
    "EPICENTRO = CENTROIDE DE LAS ESTACIONES QUE DETECTARON EL SISMO. No es una "
    "localización sísmica: está entre las estaciones, no en la falla."
)
SKETCH_NOTE = "SIN CARTOGRAFÍA BASE · PROYECCIÓN EQUIRECTANGULAR LOCAL"
ENVELOPE_NOTE = (
    "ENVOLVENTE DE PICO POR SEGUNDO (1 Hz). NO es la forma de onda cruda: el sistema "
    "muestrea a 100 sps y no transmite el crudo en continuo."
)
NO_MMI = (
    "No se reporta intensidad macrosísmica (MMI) ni isosistas: TAKAB no las calcula. "
    "La banda que sigue es la sacudida MEDIDA por el sensor del propio inmueble."
)


def num(value: object, digits: int = 3, unit: str = "") -> str:
    """Número con unidad, o el literal de ausencia. Nunca 0 por defecto."""
    if value is None:
        return ABSENT
    text = f"{float(value):.{digits}f}"
    return f"{text} {unit}".strip()


@dataclass(frozen=True, slots=True)
class ChannelRow:
    channel: str
    peak_pga_g: float | None
    peak_pgv_cms: float | None
    peak_rms: float | None
    peak_stalta: float | None
    energy_sum: float | None
    clipped: bool
    samples: int
    peak_ts: datetime | None


@dataclass(frozen=True, slots=True)
class DictamenRow:
    dictamen_id: str
    status: str
    created_at: datetime
    signed_by: str | None
    rule_set_version: str
    supersedes: str | None


@dataclass(frozen=True, slots=True)
class VoteRow:
    label: str
    delta_s: float | None
    pga_g: float | None
    counted: bool


@dataclass(frozen=True, slots=True)
class ActionRow:
    ts: datetime
    kind: str
    actor: str


@dataclass(frozen=True, slots=True)
class EvidenceRow:
    kind: str
    sha256: str | None
    created_at: datetime | None


@dataclass
class ReportModel:
    """Todo lo que el dictamen puede afirmar. Nada se calcula durante el render."""

    folio: str
    incident_id: str
    site_name: str
    site_code: str
    site_criticality: str | None
    site_lat: float | None
    site_lon: float | None
    opened_at: datetime
    closed_at: datetime | None
    severity: str
    trigger: str
    state: str
    event_id: str | None
    event_source: str | None
    epicenter_lat: float | None
    epicenter_lon: float | None

    verdict_status: str | None
    verdict_label: str
    verdict_signed: bool
    rule_set_version: str | None

    peak_pga_g: float | None
    peak_pgv_cms: float | None
    peak_ts: datetime | None
    felt_band: str
    calibrated: bool
    lead_time_s: float | None
    lead_time_reason: str | None
    station_count: int
    catalog_line: str | None
    generated_at: datetime

    channels: list[ChannelRow] = field(default_factory=list)
    dictamens: list[DictamenRow] = field(default_factory=list)
    votes: list[VoteRow] = field(default_factory=list)
    actions: list[ActionRow] = field(default_factory=list)
    evidence: list[EvidenceRow] = field(default_factory=list)
    sensors: list[dict] = field(default_factory=list)
    peers: list[dict] = field(default_factory=list)
    #: Serie 1 Hz por canal: `{canal: [(ts, pga_g, clipping), …]}`.
    series: dict[str, list[tuple[datetime, float | None, bool]]] = field(default_factory=dict)
    #: Forma de onda cruda decodificada del miniSEED, si lo hubo.
    raw_waveform: dict[str, list[int]] = field(default_factory=dict)
    raw_sample_rate: float | None = None
    #: Espectro de amplitud del canal dominante: `(frecuencias_hz, amplitudes)`.
    spectrum: tuple[list[float], list[float]] | None = None
    spectrum_peak_hz: float | None = None
    #: Por qué no hay onda cruda ni espectro, si es el caso.
    raw_unavailable_reason: str | None = None
    #: `basis` del dictamen vigente (T-2.42): qué umbral, con qué valor, de qué versión
    #: de reglas. Es lo que hace auditable el "por qué este veredicto" de la prosa.
    verdict_basis: dict = field(default_factory=dict)
    #: Prosa opcional (T-2.42). El veredicto NO sale de aquí.
    narrative: list[tuple[str, str]] = field(default_factory=list)
    narrative_provider: str | None = None
    narrative_degraded: str | None = None
    #: [T-2.82] Marco normativo DECLARADO por el cliente (``compliance_labels``). Es
    #: la única parte del documento que TAKAB no midió ni verificó, y por eso viaja
    #: como documento con su propio estado de legibilidad en vez de como lista suelta.
    #: Entra en ``content_sha256``: cambiar lo que el dictamen afirma tiene que mover
    #: la huella, o la huella no sirve para comparar dos exportaciones.
    compliance: ComplianceDocument = field(default_factory=ComplianceDocument)

    def content_sha256(self) -> str:
        """Huella del CONTENIDO (no del archivo): identifica qué se afirmó.

        El sha256 del PDF no puede imprimirse dentro de sí mismo; este sí, y permite
        comparar dos exportaciones del mismo incidente sin abrirlas.
        """
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode()).hexdigest()


FELT_LABELS: dict[str, str] = {
    "trip": "SACUDIDA FUERTE (supera el umbral de actuación del inmueble)",
    "watch": "SACUDIDA MODERADA (supera el umbral de vigilancia)",
    "normal": "SACUDIDA LEVE (por debajo de los umbrales del inmueble)",
    "unknown": "SIN MEDICIÓN DE SACUDIDA",
}

LEAD_REASONS: dict[str, str] = {
    "not_sasmex": "no aplica: el incidente no se disparó por SASMEX",
    "no_peak": "no hubo pico medido en la ventana del incidente",
    "peak_before_alert": "el pico precedió a la alerta",
}


def lead_time_text(seconds: float | None, reason: str | None) -> str:
    """Tiempo de aviso ganado, o su ausencia explicada. Jamás '0 s' por defecto."""
    if seconds is not None:
        return f"{seconds:.1f} s"
    return f"NO CALCULABLE · {LEAD_REASONS.get(reason or '', reason or 'razón no registrada')}"
