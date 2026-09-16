"""Qué sale de la nube hacia un proveedor de prosa (T-2.42).

**Allowlist, no denylist.** Se enumera campo por campo lo que viaja; cualquier cosa
que se añada al ``ReportModel`` mañana queda fuera por omisión. Una denylist tendría la
polaridad contraria: un campo nuevo saldría solo, y el día que ese campo fuera el nombre
del inmueble o la nota de un ocupante ya sería tarde.

**Nunca salen**: ``site_name``, dirección, coordenadas del sitio o del epicentro,
``user_sub``, ``signed_by``, notas de ocupantes, ``tenant_id``, ``s3_key`` ni hashes de
evidencia. Los reportes de daño entrarían solo como conteo por categoría.

**El FOLIO sí sale, entero, y hay que decirlo** (T-5.27). Esta lista afirmaba que el
``incident_id`` nunca salía, y era falso a medias: el folio lo lleva dentro. Un folio es
``TKB-<código de sitio>-<fecha>-<8 hex del incident_id>-<E|T>``, o sea que por él viajan
**el código del sitio** y un **prefijo del identificador del incidente**.

Se decidió DEJARLO, no recortarlo, por dos razones. (1) El folio es el nombre público
del documento —``folio_of`` lo dice: «se imprime y se cita por teléfono»— y la prosa
tiene que poder nombrar el dictamen que describe; un folio recortado en el texto sería
un folio que no existe, y el que lo teclee no encontrará nada. (2) Lo que viaja no es un
dato personal: es un identificador de documento, estable y correlacionable entre
dictámenes del mismo incidente, que es justo para lo que se diseñó.

Lo que NO sale por ninguna vía es el ``incident_id`` **completo**, ni el ``event_id``
(ver ``_BASIS_EVIDENCE_KEYS``): con 8 hex se puede correlacionar dos documentos, no
reconstruir el identificador ni cruzarlo con otra tabla. La diferencia entre las dos
cosas la fija ``tests/narrative/test_redact.py``, que ya no borra el folio antes de
mirar.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from takab_api.dictamen.bitacora import ROTULOS
from takab_api.dictamen.model import (
    CCTV_PARCIALMENTE_PURGADO,
    CCTV_PENDIENTE,
    CCTV_PURGADO_SIN_ANALISIS,
    CCTV_SIN_CLIP,
    FELT_LABELS,
    NO_CALIBRATION,
    NO_CCTV,
    NO_SPECTRUM,
    STATUS_ACTIONS,
    lead_time_text,
)
from takab_api.felt import ORIGEN_INMUEBLE
from takab_api.narrative.base import NarrativeFacts

if TYPE_CHECKING:  # pragma: no cover - solo para el tipo; evita ciclo de imports
    from takab_api.dictamen.model import ReportModel

#: Claves del ``basis`` que pueden salir. `event_id` NO está: es un identificador
#: correlacionable, y la prosa no lo necesita para explicar un umbral.
_BASIS_EVIDENCE_KEYS = (
    "severity",
    "pga_g",
    "node_count",
    "corroborated",
    "trigger",
    "pga_source",
    "insufficient_data",
)
_BASIS_PARAM_KEYS = ("pga_no_inhabit_g", "pga_monitor_g")


def redact_basis(basis: dict | None) -> dict:
    """Umbrales y evidencia numérica del dictamen; nada identificable."""
    if not isinstance(basis, dict):
        return {}
    evidence = basis.get("evidence") if isinstance(basis.get("evidence"), dict) else {}
    params = basis.get("params") if isinstance(basis.get("params"), dict) else {}
    out: dict = {}
    version = basis.get("rule_set_version")
    if isinstance(version, str):
        out["rule_set_version"] = version
    ev = {k: evidence[k] for k in _BASIS_EVIDENCE_KEYS if k in evidence}
    pa = {k: params[k] for k in _BASIS_PARAM_KEYS if k in params}
    if ev:
        out["evidence"] = ev
    if pa:
        out["params"] = pa
    return out


#: [T-7.38·M] Estados de vídeo en los que NO hay conteo de evacuación. Se enumeran
#: por estado y no por `t90_s is None`: «análisis disponible» con `t90_s` nulo es un
#: camino real, y condicionar ahí produciría la ausencia «(1) análisis disponible».
_CCTV_SIN_ANALISIS = frozenset(
    {NO_CCTV, CCTV_SIN_CLIP, CCTV_PENDIENTE, CCTV_PURGADO_SIN_ANALISIS, CCTV_PARCIALMENTE_PURGADO}
)
SIN_CONTEO_CCTV = "No hay conteo de evacuación por vídeo para este incidente."
SIN_FUNDAMENTO_REGISTRADO = (
    "El dictamen vigente no registra evidencia instrumental en su fundamento."
)
SIN_UMBRALES_DEL_INMUEBLE = (
    "La sacudida se clasificó con la banda de referencia: no consta configuración de "
    "umbrales del inmueble anterior al incidente."
)


def absences_of(m: ReportModel) -> tuple[str, ...]:
    """Cada dato ausente, con su razón. Es lo que sostiene "Limitaciones".

    Enumerar los huecos es parte del contenido, no un descargo: un dictamen que calla
    lo que no midió afirma más de lo que sabe.
    """
    gaps: list[str] = []
    if m.peak_pga_g is None:
        gaps.append("No hubo aceleración pico medida en la ventana del incidente.")
    if m.peak_pgv_cms is None:
        gaps.append("No hubo velocidad pico medida en la ventana del incidente.")
    if not m.calibrated:
        gaps.append(NO_CALIBRATION)
    if m.felt_band == "unknown":
        gaps.append("La banda de sacudida no pudo determinarse: no hubo medición.")
    if m.lead_time_s is None:
        gaps.append(f"Tiempo de aviso: {lead_time_text(None, m.lead_time_reason)}.")
    if not m.channels:
        gaps.append("No hay features por canal archivadas para este incidente.")
    if m.station_count == 0:
        gaps.append("Ninguna otra estación de la red corroboró el evento.")
    if m.catalog_line is None:
        gaps.append("No hay sismo de catálogo (SSN) asociable a este incidente.")
    if not m.raw_waveform:
        gaps.append(m.raw_unavailable_reason or NO_SPECTRUM)
    if m.epicenter_lat is None or m.epicenter_lon is None:
        gaps.append("El evento no tiene epicentro localizado.")
    if not m.dictamens:
        gaps.append("El incidente aún no tiene dictamen registrado.")
    clipped = [c.channel for c in m.channels if c.clipped]
    if clipped:
        gaps.append(
            f"Canales saturados ({', '.join(clipped)}): en ellos el pico registrado es "
            "el techo del convertidor, no la sacudida real."
        )
    # [T-7.38·M] Tres huecos que el documento YA declara en sus secciones y que esta
    # lista no miraba, de modo que podía cerrar con «No se detectaron datos ausentes»
    # una página después de haber declarado dos.
    if m.cctv.estado in _CCTV_SIN_ANALISIS:
        gaps.append(SIN_CONTEO_CCTV)
    # Gateado en que HAYA dictamen: sin él, la línea de arriba ya lo dice y ésta
    # afirmaría un «dictamen vigente» que no existe.
    if m.dictamens and not (m.verdict_basis or {}).get("evidence"):
        gaps.append(SIN_FUNDAMENTO_REGISTRADO)
    if (m.felt_thresholds or {}).get("origen") != ORIGEN_INMUEBLE:
        gaps.append(SIN_UMBRALES_DEL_INMUEBLE)
    # [T-7.22] Y los cinco que trae el informe del evento. Misma razón que el
    # bloque de arriba: el documento CIERRA sobre esta lista, así que un hueco
    # declarado en su sección y ausente aquí deja al papel diciendo «no se
    # detectaron datos ausentes» unas páginas después de haberlo declarado. Ya
    # ocurrió una vez (`T-7.38·M`); esta lista se enumera a mano y es el precio.
    if m.estaciones and not any(e.lat is not None and e.lon is not None for e in m.estaciones):
        gaps.append(
            "Ninguna estación de la red tiene coordenadas registradas: no se pudo "
            "situar el mapa de la red."
        )
    if not m.actions:
        gaps.append("No hay acciones registradas en la bitácora de este incidente.")
    sin_rotulo = [a.kind for a in m.actions if a.kind not in ROTULOS]
    if sin_rotulo:
        gaps.append(
            f"{len(sin_rotulo)} acciones de la cronología se imprimen con su "
            "identificador técnico: no hay rótulo declarado para ellas."
        )
    if not m.danos:
        gaps.append(
            "No hay reportes de daños desde el táctico. Eso no dice que el inmueble "
            "esté sin daños: dice que nadie registró una inspección."
        )
    no_impresas = sum(1 for d in m.danos for f in d.fotos if f.jpeg is None)
    omitidas = sum(d.fotos_omitidas for d in m.danos)
    if no_impresas or omitidas:
        gaps.append(
            f"{no_impresas + omitidas} fotografías de los reportes de daños no se "
            "imprimen en este documento; quedan en el expediente de evidencia."
        )
    return tuple(gaps)


def _razon_de_persona(m: ReportModel) -> bool:
    """[T-7.38·E] ¿Firmó una persona Y escribió por qué?

    La conjunción no es adorno: `sign_dictamen` inserta `basis = {}` cuando no hay
    nota, y `dictamen/rules.py` mete `notes` ENLATADO («dictamen automático
    preliminar») en todos los automáticos. Con la clave sola, una cadena de fábrica
    pasaría por el fundamento de un veredicto; con `verdict_signed` solo, un firmado
    sin razón sería indistinguible de uno con razón.
    """
    if not m.verdict_signed:
        return False
    nota = (m.verdict_basis or {}).get("notes")
    return isinstance(nota, str) and bool(nota.strip())


def facts_from(m: ReportModel, *, damage_counts: dict[str, int] | None = None) -> NarrativeFacts:
    """Hechos redactados del dictamen. Solo lo enumerado aquí sale de la nube."""
    counts = tuple(sorted(Counter(a.kind for a in m.actions).items()))
    return NarrativeFacts(
        folio=m.folio,
        opened_at=m.opened_at.isoformat(),
        severity=m.severity,
        trigger=m.trigger,
        opened_trigger=m.opened_trigger,
        state=m.state,
        event_source=m.event_source,
        verdict_label=m.verdict_label,
        verdict_status=m.verdict_status,
        verdict_signed=m.verdict_signed,
        verdict_actions=STATUS_ACTIONS.get(m.verdict_status or "", ()),
        rule_set_version=m.rule_set_version,
        basis=redact_basis(m.verdict_basis),
        reason_recorded=_razon_de_persona(m),
        site_criticality=m.site_criticality,
        felt_band=m.felt_band,
        felt_label=FELT_LABELS.get(m.felt_band, FELT_LABELS["unknown"]),
        calibrated=m.calibrated,
        peak_pga_g=m.peak_pga_g,
        peak_pgv_cms=m.peak_pgv_cms,
        lead_time=lead_time_text(m.lead_time_s, m.lead_time_reason),
        station_count=m.station_count,
        catalog_line=m.catalog_line,
        channel_count=len(m.channels),
        clipped_channels=tuple(c.channel for c in m.channels if c.clipped),
        action_counts=counts,
        damage_counts=tuple(sorted((damage_counts or {}).items())),
        dictamen_count=len(m.dictamens),
        has_epicenter=m.epicenter_lat is not None and m.epicenter_lon is not None,
        has_raw_waveform=bool(m.raw_waveform),
        has_archived_miniseed=any(e.kind == "miniseed" for e in m.evidence),
        absences=absences_of(m),
    )
