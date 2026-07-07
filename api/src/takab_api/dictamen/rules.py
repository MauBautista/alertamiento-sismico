"""Reglas PURAS del dictamen automático preliminar (blueprint §5: severidad/PGA
+ regla de nodos). Sin DB; espejo del patrón ``incident.quorum``.

La regla de nodos solo ELEVA la prudencia (§4.5: el quórum "eleva la confianza
del incidente y alimenta el dictamen"): una corroboración de red convierte
``normal_operation`` en ``inhabit_monitor``; jamás degrada un estado más
restrictivo. Los umbrales de PGA son placeholders calibrables por ingeniería
(override por ``rule_sets.config.dictamen``).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)

# Versión del conjunto de reglas: queda grabada en el basis de CADA dictamen
# automático (requisito de trazabilidad §9: ruleSetVersion).
RULE_SET_VERSION = "dictamen-v1"


class _DictamenDefaults(Protocol):
    """Proveedor de defaults del dictamen (``Settings`` u otro stand-in)."""

    dictamen_pga_no_inhabit_g: float
    dictamen_pga_monitor_g: float


@dataclass(frozen=True)
class DictamenParams:
    """Umbrales resueltos (rule_set → defaults)."""

    pga_no_inhabit_g: float
    pga_monitor_g: float


@dataclass(frozen=True)
class EvalInput:
    """Evidencia instrumental mínima de un incidente para dictaminar."""

    severity: str
    pga_g: float | None
    node_count: int
    quorum_min_nodes: int
    trigger: str
    event_id: str | None


@dataclass(frozen=True)
class Decision:
    """Status calculado + basis completo (versión, evidencia, params, notas)."""

    status: str
    basis: dict


def resolve_params(config: dict | None, settings: _DictamenDefaults) -> DictamenParams:
    """Resuelve los umbrales: ``config['dictamen']`` si viene, si no defaults.
    Cada campo se valida por separado; un par invertido (monitor ≥ no_inhabit)
    rompería la escala completa → se descarta el par y se cae a defaults."""
    defaults = DictamenParams(
        pga_no_inhabit_g=settings.dictamen_pga_no_inhabit_g,
        pga_monitor_g=settings.dictamen_pga_monitor_g,
    )
    raw = config.get("dictamen") if isinstance(config, dict) else None
    if not isinstance(raw, dict):
        return defaults
    no_inhabit = _field_num(
        raw, "pga_no_inhabit_g", defaults.pga_no_inhabit_g, valid=lambda v: v > 0
    )
    monitor = _field_num(raw, "pga_monitor_g", defaults.pga_monitor_g, valid=lambda v: v > 0)
    if monitor >= no_inhabit:
        logger.warning(
            "dictamen config: pga_monitor_g %r ≥ pga_no_inhabit_g %r invierte la escala → defaults",
            monitor,
            no_inhabit,
        )
        return defaults
    return DictamenParams(pga_no_inhabit_g=no_inhabit, pga_monitor_g=monitor)


def evaluate(inp: EvalInput, params: DictamenParams) -> Decision:
    """Dictamen automático preliminar por severidad/PGA + regla de nodos."""
    pga = inp.pga_g if inp.pga_g is not None else 0.0
    corroborated = inp.node_count >= inp.quorum_min_nodes
    if inp.severity == "critical" or pga >= params.pga_no_inhabit_g:
        status = "no_inhabit_inspect"
    elif inp.severity == "warning" or pga >= params.pga_monitor_g or corroborated:
        status = "inhabit_monitor"
    else:
        status = "normal_operation"
    basis = {
        "rule_set_version": RULE_SET_VERSION,
        "evidence": {
            "severity": inp.severity,
            "pga_g": pga,
            "node_count": inp.node_count,
            "corroborated": corroborated,
            "event_id": inp.event_id,
            "trigger": inp.trigger,
        },
        "params": {
            "pga_no_inhabit_g": params.pga_no_inhabit_g,
            "pga_monitor_g": params.pga_monitor_g,
        },
        "notes": "dictamen automático preliminar",
    }
    return Decision(status=status, basis=basis)


def _field_num(raw: dict, key: str, default: float, *, valid: Callable[[float], bool]) -> float:
    """Float validado del config; inválido/ausente → default del campo (+ log)."""
    value = raw.get(key, default)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and valid(float(value)):
        return float(value)
    if key in raw:
        logger.warning("dictamen config: %s=%r inválido → default %r", key, value, default)
    return default
