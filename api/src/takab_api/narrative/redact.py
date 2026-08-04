"""Qué sale de la nube hacia un proveedor de prosa (T-2.42).

**Allowlist, no denylist.** Se enumera campo por campo lo que viaja; cualquier cosa
que se añada al ``ReportModel`` mañana queda fuera por omisión. Una denylist tendría la
polaridad contraria: un campo nuevo saldría solo, y el día que ese campo fuera el nombre
del inmueble o la nota de un ocupante ya sería tarde.

**Nunca salen**: ``site_name``, dirección, coordenadas del sitio o del epicentro,
``user_sub``, ``signed_by``, notas de ocupantes, ``tenant_id``, ``incident_id``,
``s3_key`` ni hashes de evidencia. Los reportes de daño entrarían solo como conteo por
categoría.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from takab_api.dictamen.model import (
    FELT_LABELS,
    NO_CALIBRATION,
    NO_SPECTRUM,
    STATUS_ACTIONS,
    lead_time_text,
)
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
    return tuple(gaps)


def facts_from(m: ReportModel, *, damage_counts: dict[str, int] | None = None) -> NarrativeFacts:
    """Hechos redactados del dictamen. Solo lo enumerado aquí sale de la nube."""
    counts = tuple(sorted(Counter(a.kind for a in m.actions).items()))
    return NarrativeFacts(
        folio=m.folio,
        opened_at=m.opened_at.isoformat(),
        severity=m.severity,
        trigger=m.trigger,
        state=m.state,
        event_source=m.event_source,
        verdict_label=m.verdict_label,
        verdict_status=m.verdict_status,
        verdict_signed=m.verdict_signed,
        verdict_actions=STATUS_ACTIONS.get(m.verdict_status or "", ()),
        rule_set_version=m.rule_set_version,
        basis=redact_basis(m.verdict_basis),
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
        absences=absences_of(m),
    )
