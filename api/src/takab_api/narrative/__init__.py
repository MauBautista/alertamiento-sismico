"""Capa narrativa del dictamen (T-2.42): prosa que RODEA al veredicto.

El punto de entrada es ``build_narrative``. Elige proveedor por configuración y devuelve
siempre una ``Narrative`` — nunca lanza, nunca devuelve ``None``. Un dictamen sin prosa
sigue siendo un dictamen válido; un dictamen que no se puede exportar, no.

Por qué esta capa no puede tocar el veredicto (regla de oro 1):

1. ``Narrative`` no tiene campo de veredicto: no hay dónde ponerlo.
2. ``narrative/`` no importa ``dictamen.rules`` ni ``dictamen.service``: no puede
   siquiera invocar al motor que dictamina.
3. ``pdf.render`` produce el mismo veredicto con o sin prosa.

Las tres son contract-tests (``tests/narrative/test_contract.py``), no promesas escritas.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from takab_api.narrative.base import Narrative, NarrativeFacts, NarrativeProvider, NarrativeRequest
from takab_api.narrative.deterministic import DeterministicProvider
from takab_api.narrative.redact import facts_from
from takab_api.settings import Settings

if TYPE_CHECKING:  # pragma: no cover
    from takab_api.dictamen.model import ReportModel

log = logging.getLogger("takab_api.narrative")

__all__ = [
    "Narrative",
    "NarrativeFacts",
    "NarrativeProvider",
    "NarrativeRequest",
    "apply_narrative",
    "build_narrative",
    "facts_from",
    "select_provider",
]


def select_provider(settings: Settings) -> tuple[NarrativeProvider, str]:
    """Proveedor activo y slug de modelo. Por defecto, siempre el determinista.

    Tres condiciones para salir a la red, todas necesarias: el flag encendido, una clave
    resoluble y un slug de modelo. Que falte cualquiera **no es una degradación** — es la
    configuración pedida, y por eso no marca ``degraded_reason`` en el PDF.
    """
    if not settings.openrouter_enabled or not settings.openrouter_model:
        return DeterministicProvider(), ""

    from takab_api.narrative.openrouter import (  # noqa: PLC0415 - solo si está encendido
        OpenRouterProvider,
        resolve_api_key,
    )

    api_key = resolve_api_key(settings)
    if not api_key:
        log.warning("narrative: OpenRouter encendido sin clave resoluble → determinista")
        return DeterministicProvider(), ""
    return OpenRouterProvider(settings, api_key=api_key), settings.openrouter_model


async def build_narrative(
    model: ReportModel,
    settings: Settings | None = None,
    *,
    provider: NarrativeProvider | None = None,
    damage_counts: dict[str, int] | None = None,
) -> Narrative:
    """Prosa del dictamen. Nunca lanza: un fallo aquí degrada, no rompe la evidencia."""
    s = settings or Settings()
    chosen, slug = (provider, s.openrouter_model) if provider else select_provider(s)
    req = NarrativeRequest(facts=facts_from(model, damage_counts=damage_counts), model=slug)
    try:
        return await chosen.generate(req)
    except Exception as exc:  # noqa: BLE001 - último cinturón: la exportación sale igual
        log.warning("narrative: el proveedor %r lanzó (%s); se degrada", chosen, exc)
        return await DeterministicProvider().generate(req)


def apply_narrative(model: ReportModel, narrative: Narrative) -> None:
    """Cuelga la prosa del modelo. El veredicto del modelo NO se toca."""
    model.narrative = list(narrative.sections)
    model.narrative_provider = narrative.provider
    model.narrative_degraded = narrative.degraded_reason
