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
from dataclasses import replace
from typing import TYPE_CHECKING

from takab_api.narrative.base import Narrative, NarrativeFacts, NarrativeProvider, NarrativeRequest
from takab_api.narrative.deterministic import DeterministicProvider
from takab_api.narrative.quota import MOTIVO_AGOTADA, acumular, leer_estado
from takab_api.narrative.redact import facts_from
from takab_api.settings import Settings

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.ext.asyncio import AsyncConnection

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
    conn: AsyncConnection | None = None,
    tenant_id: str | None = None,
    actor: str | None = None,
) -> Narrative:
    """Prosa del dictamen. Nunca lanza: un fallo aquí degrada, no rompe la evidencia.

    [T-5.18] Con `conn` y `tenant_id`, ADEMÁS cobra contra la cuota mensual del
    cliente. Agotada, se cae al determinista **y se declara** — jamás se falla la
    exportación: el PDF es una superficie de vida y un tope de gasto no puede
    convertirse en una negación de evidencia.

    Sin los dos argumentos no hay cuota que cobrar y el comportamiento es
    exactamente el de antes. Es lo que mantiene fuera del camino a los tests y a
    cualquier llamador que no tenga transacción.
    """
    s = settings or Settings()
    chosen, slug = (provider, s.openrouter_model) if provider else select_provider(s)
    req = NarrativeRequest(facts=facts_from(model, damage_counts=damage_counts), model=slug)

    cobrable = conn is not None and tenant_id is not None and _sale_a_la_red(chosen)
    if cobrable:
        estado = await leer_estado(
            conn,  # type: ignore[arg-type]
            tenant_id,  # type: ignore[arg-type]
            cap_usd=s.ai_monthly_cap_usd,
            actor=actor,
        )
        if estado.exhausted:
            log.warning(
                "narrative: cuota de IA agotada (%s: %.4f/%.2f USD) → determinista",
                estado.period,
                estado.spent_usd,
                estado.cap_usd,
            )
            degradada = await DeterministicProvider().generate(req)
            return replace(degradada, degraded_reason=MOTIVO_AGOTADA)

    try:
        narrativa = await chosen.generate(req)
    except Exception as exc:  # noqa: BLE001 - último cinturón: la exportación sale igual
        log.warning("narrative: el proveedor %r lanzó (%s); se degrada", chosen, exc)
        return await DeterministicProvider().generate(req)

    if cobrable:
        # Se cobra DESPUÉS: el coste solo se conoce al volver del proveedor. El
        # desbordamiento máximo del tope es una llamada, y está declarado en
        # `narrative/quota.py`.
        await acumular(
            conn,  # type: ignore[arg-type]
            tenant_id,  # type: ignore[arg-type]
            cost_usd=narrativa.cost_usd,
            cap_usd=s.ai_monthly_cap_usd,
            warn_at=s.ai_warn_at,
            actor=actor,
        )
    return narrativa


def _sale_a_la_red(provider: NarrativeProvider) -> bool:
    """¿Este proveedor cuesta dinero? El determinista no, y cobrarle una llamada
    llenaría el contador de ceros y el `calls` de mentiras."""
    return not isinstance(provider, DeterministicProvider)


def apply_narrative(model: ReportModel, narrative: Narrative) -> None:
    """Cuelga la prosa del modelo. El veredicto del modelo NO se toca."""
    model.narrative = list(narrative.sections)
    model.narrative_provider = narrative.provider
    model.narrative_degraded = narrative.degraded_reason
