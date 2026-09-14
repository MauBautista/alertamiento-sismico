"""Contrato de la capa narrativa (T-2.42).

La prosa RODEA al dictamen; jamás lo produce. Eso no se promete en la documentación:
se impone por tipos. ``NarrativeRequest`` recibe el veredicto **ya calculado** por
``dictamen/rules.py``, y ``Narrative`` —lo único que un proveedor puede devolver— no
tiene ningún campo de veredicto, estado, prioridad ni severidad. Un proveedor no puede
emitir un veredicto porque no hay dónde ponerlo (regla de oro 1).

Los hechos que viajan al proveedor pasan antes por ``redact.py``, que es una
**allowlist**: lo que no está enumerado allí no sale de la nube.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class NarrativeFacts:
    """Hechos redactados del incidente. Los produce ``redact.facts_from``.

    Contiene el veredicto porque es una **entrada**: la prosa tiene que poder explicar
    por qué se dictaminó lo que se dictaminó. Lo que ningún proveedor puede hacer es
    devolver uno distinto — ver ``Narrative``.
    """

    folio: str
    opened_at: str
    severity: str
    trigger: str
    #: [T-7.36] Con qué se ABRIÓ. `trigger` es la última escalada: la ingesta lo
    #: sobrescribe, así que decir «se abrió a partir de» con él es falso en cuanto
    #: un incidente escala.
    opened_trigger: str
    state: str
    event_source: str | None

    verdict_label: str
    verdict_status: str | None
    verdict_signed: bool
    verdict_actions: tuple[str, ...]
    rule_set_version: str | None
    basis: dict = field(default_factory=dict)
    #: [T-7.38·E] ¿Consta una razón ESCRITA POR UNA PERSONA al firmar? Booleano, no
    #: el texto: la nota del inspector es prosa libre sin validar y la allowlist de
    #: `redact` existe para que no salga de la nube. Y es la CONJUNCIÓN «firmada Y
    #: con nota»: `rules.py` mete `notes` enlatado en todo dictamen automático, así
    #: que la clave sola no distingue una razón de una cadena de fábrica.
    reason_recorded: bool = False

    site_criticality: str | None = None
    felt_band: str = "unknown"
    felt_label: str = ""
    calibrated: bool = False
    peak_pga_g: float | None = None
    peak_pgv_cms: float | None = None
    lead_time: str = ""
    station_count: int = 0
    catalog_line: str | None = None

    channel_count: int = 0
    clipped_channels: tuple[str, ...] = ()
    action_counts: tuple[tuple[str, int], ...] = ()
    #: Reportes de daño, SOLO como conteo por categoría. Nunca el texto del ocupante.
    damage_counts: tuple[tuple[str, int], ...] = ()
    dictamen_count: int = 0
    has_epicenter: bool = False
    has_raw_waveform: bool = False
    #: [T-7.38·L] ¿CONSTA un objeto miniSEED en la cadena de custodia? `has_raw_waveform`
    #: responde a otra pregunta —«¿se decodificó?»— y la prosa decía «no hay forma de
    #: onda cruda archivada» sobre un incidente cuyo §10 lista el miniSEED con su hash.
    has_archived_miniseed: bool = False
    #: Cada dato que falta, con su razón. Es la materia prima de "Limitaciones".
    absences: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NarrativeRequest:
    """Lo que se le pide a un proveedor: hechos redactados y nada más."""

    facts: NarrativeFacts
    #: Slug del modelo. Vacío ⇒ ningún proveedor remoto puede correr (ver settings).
    model: str = ""


@dataclass(frozen=True, slots=True)
class Narrative:
    """Lo único que un proveedor puede devolver.

    **No tiene campo de veredicto, estado, prioridad ni severidad**, y un contract-test
    lo verifica sobre los nombres de los campos (``test_contract.py``). Añadir uno
    rompería el build antes de que pudiera llegar a un dictamen.
    """

    sections: tuple[tuple[str, str], ...]
    provider: str
    model: str | None = None
    #: Por qué se cayó al proveedor determinista, si se cayó. Se imprime en el PDF.
    degraded_reason: str | None = None
    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None

    def provenance(self) -> dict:
        """Procedencia para ``audit_log`` (verbo ``narrative_generated``).

        No hay tabla nueva: la narrativa queda congelada en el PDF, que ya es evidencia
        inmutable con sha256; la procedencia va al log append-only y sin poda.
        """
        return {
            "provider": self.provider,
            "model": self.model,
            "degraded_reason": self.degraded_reason,
            "latency_ms": self.latency_ms,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost_usd": self.cost_usd,
            "sections": [title for title, _ in self.sections],
        }


class NarrativeProvider(Protocol):
    """Contrato mínimo de un proveedor de prosa."""

    name: str

    async def generate(self, req: NarrativeRequest) -> Narrative: ...
