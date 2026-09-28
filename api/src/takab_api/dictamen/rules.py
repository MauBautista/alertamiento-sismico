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
# automático (requisito de trazabilidad §9: ruleSetVersion). [T-9.30 · D-43] Las
# filas NUEVAS son `dictamen-v2` (tres bandas); la regla v1 se CONSERVA —con su
# versión propia— porque las filas viejas la citan y el papel la rotula.
RULE_SET_VERSION_V1 = "dictamen-v1"
RULE_SET_VERSION = "dictamen-v2"


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
    """Evidencia instrumental mínima de un incidente para dictaminar.

    ``pga_source`` (basis v2): de dónde salió el pico — ``features`` (ventana
    de features del sensor), ``incident`` (max_pga_g preexistente) o ``none``
    (sin medición). La UI/PDF lo usan para rotular la honestidad del dictamen.
    """

    severity: str
    pga_g: float | None
    node_count: int
    quorum_min_nodes: int
    trigger: str
    event_id: str | None
    pga_source: str = "none"


@dataclass(frozen=True)
class Decision:
    """Status calculado + basis completo (versión, evidencia, params, notas).

    ``band`` (v2): ``verde``/``amarillo``/``rojo``; ``None`` en la regla v1."""

    status: str
    basis: dict
    band: str | None = None


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
    # El 0.0 es para COMPARAR —sin medición no se puede superar un umbral—, no para
    # guardar: [T-7.38·C] congelarlo en el `basis` hacía que la prosa imprimiera «El
    # valor evaluado fue 0.000 g» en un documento cuyo §5 dice «PGA PICO · SIN DATO».
    # Un cero fabricado presentado como medición es peor que decir que no consta.
    pga = inp.pga_g if inp.pga_g is not None else 0.0
    corroborated = inp.node_count >= inp.quorum_min_nodes
    if inp.severity == "critical" or pga >= params.pga_no_inhabit_g:
        status = "no_inhabit_inspect"
    elif inp.severity == "warning" or pga >= params.pga_monitor_g or corroborated:
        status = "inhabit_monitor"
    else:
        status = "normal_operation"
    basis = {
        "rule_set_version": RULE_SET_VERSION_V1,
        "evidence": {
            "severity": inp.severity,
            "pga_g": inp.pga_g,
            "node_count": inp.node_count,
            "corroborated": corroborated,
            "event_id": inp.event_id,
            "trigger": inp.trigger,
            # basis v2 (T-1.48, ADITIVO): sin medición NI corroboración, el
            # veredicto se sostiene solo en la severidad de la alerta — la UI
            # y el PDF lo rotulan en vez de fingir evidencia instrumental.
            "pga_source": inp.pga_source,
            "insufficient_data": inp.pga_g is None and inp.node_count == 0,
        },
        "params": {
            "pga_no_inhabit_g": params.pga_no_inhabit_g,
            "pga_monitor_g": params.pga_monitor_g,
        },
        "notes": "dictamen automático preliminar",
    }
    return Decision(status=status, basis=basis)


# ---------------------------------------------------------------------------
# [T-9.30 · D-43] dictamen-v2 · tres bandas por la aceleración del EDIFICIO
# ---------------------------------------------------------------------------

#: Banda → status de ``dictamens`` (el CHECK de status no cambia).
BANDA_STATUS: dict[str, str] = {
    "verde": "normal_operation",
    "amarillo": "inhabit_monitor",
    "rojo": "no_inhabit_inspect",
}
#: Orden de PRUDENCIA: la prudencia sube sola y sólo baja con firma.
ORDEN_BANDA: dict[str, int] = {"verde": 0, "amarillo": 1, "rojo": 2}
#: Status → banda, para cabezas sin ``band`` (filas v1 e históricas). ``restricted``
#: no es habitable ⇒ rojo; un status desconocido cae a rojo (default-deny).
STATUS_BANDA: dict[str, str] = {
    "normal_operation": "verde",
    "inhabit_monitor": "amarillo",
    "restricted": "rojo",
    "no_inhabit_inspect": "rojo",
}
#: Daños que exigen al inspector (D-43).
DANOS_ROJO = frozenset({"structural", "people_trapped", "gas_leak"})
#: Daños que piden confirmación. Una categoría DESCONOCIDA también cae aquí: un
#: reporte de daño nunca puede dejar el VERDE en pie.
DANOS_AMARILLO = frozenset({"non_structural", "water_leak", "electrical"})


def banda_por_danos(damage_keys: tuple[str, ...] | list[str]) -> str:
    """[F3·r3 · D-43] La banda que exigen SÓLO unos reportes de daño (≥ 1 reporte).

    La usa el worker sobre una cabeza firmada por una PERSONA: lo que esa persona ya
    vio (la PGA, los daños anteriores) no vuelve a subir; sólo los daños nuevos. Un
    reporte sin categoría o con una desconocida cuenta como amarillo, igual que en
    ``evaluate_v2`` (un reporte de daño nunca deja el VERDE en pie)."""
    return "rojo" if set(damage_keys) & DANOS_ROJO else "amarillo"


def banda_de(status: str | None, band: str | None = None) -> str:
    """Banda de una fila de la cadena: la columna si existe; si no, del status."""
    if band in ORDEN_BANDA:
        return band
    return STATUS_BANDA.get(status or "", "rojo")


class _DictamenV2Defaults(Protocol):
    dictamen_verde_max_g: float
    dictamen_rojo_min_g: float


@dataclass(frozen=True)
class DictamenParamsV2:
    """Umbrales v2 resueltos (``rule_sets.config.dictamen_v2`` → defaults)."""

    verde_max_g: float
    rojo_min_g: float


@dataclass(frozen=True)
class EvalInputV2:
    """Evidencia de la regla v2. ``severity``/``trigger`` NO deciden: constan.

    ``active_sensors``/``uncalibrated_sensors`` cuentan SOLO sensores con
    ``status = 'active'``: un retirado ni aporta PGA ni impide el VERDE."""

    pga_g: float | None
    pga_source: str
    active_sensors: int
    uncalibrated_sensors: int
    damage_reports: int
    damage_keys: tuple[str, ...]
    severity: str
    trigger: str
    event_id: str | None


def resolve_params_v2(config: dict | None, settings: _DictamenV2Defaults) -> DictamenParamsV2:
    """``config['dictamen_v2']`` (sitio sobre tenant, lo elige quien llama) o
    defaults. Campo inválido ⇒ su default; par invertido o banda amarilla vacía
    (verde ≥ rojo) ⇒ el par entero a defaults. ``verde_max_g = 0`` es válido y
    apaga el automático (nada es VERDE)."""
    defaults = DictamenParamsV2(
        verde_max_g=settings.dictamen_verde_max_g,
        rojo_min_g=settings.dictamen_rojo_min_g,
    )
    raw = config.get("dictamen_v2") if isinstance(config, dict) else None
    if not isinstance(raw, dict):
        return defaults
    verde = _field_num(raw, "verde_max_g", defaults.verde_max_g, valid=lambda v: v >= 0)
    rojo = _field_num(raw, "rojo_min_g", defaults.rojo_min_g, valid=lambda v: v > 0)
    if verde >= rojo:
        logger.warning(
            "dictamen_v2 config: verde_max_g %r ≥ rojo_min_g %r invierte la escala → defaults",
            verde,
            rojo,
        )
        return defaults
    return DictamenParamsV2(verde_max_g=verde, rojo_min_g=rojo)


def evaluate_v2(inp: EvalInputV2, params: DictamenParamsV2) -> Decision:
    """Banda por PGA máxima del edificio, daños reportados y calibración.

    Determinista (regla de oro 1). Cada motivo que sostiene la banda queda en
    ``basis.motivos``: el papel puede decir POR QUÉ, no sólo QUÉ."""
    motivos: list[str] = []
    rojo = False
    amarillo = False

    pga = inp.pga_g
    if pga is None:
        motivos.append("sin_pga")
        amarillo = True
    elif pga >= params.rojo_min_g:
        motivos.append("pga_banda_roja")
        rojo = True
    elif pga >= params.verde_max_g:
        motivos.append("pga_banda_amarilla")
        amarillo = True

    calibrated = inp.active_sensors > 0 and inp.uncalibrated_sensors == 0
    if not calibrated:
        motivos.append("sin_calibracion")
        amarillo = True

    keys = sorted(set(inp.damage_keys))
    for key in keys:
        motivos.append(f"dano:{key}")
        if key in DANOS_ROJO:
            rojo = True
        else:
            amarillo = True  # no estructural o desconocida
    if inp.damage_reports > 0 and not keys:
        motivos.append("dano_sin_categoria")
        amarillo = True

    band = "rojo" if rojo else "amarillo" if amarillo else "verde"
    if band == "verde":
        motivos.append("pga_bajo_verde")
    basis = {
        "rule_set_version": RULE_SET_VERSION,
        "band": band,
        "evidence": {
            "pga_g": pga,
            "pga_source": inp.pga_source,
            "calibrated": calibrated,
            "active_sensors": inp.active_sensors,
            "uncalibrated_sensors": inp.uncalibrated_sensors,
            "damage_reports": inp.damage_reports,
            "damage_categories": keys,
            # Constan, NO deciden (D-43: SASMEX deja de forzar NO HABITAR).
            "severity": inp.severity,
            "trigger": inp.trigger,
            "event_id": inp.event_id,
            "insufficient_data": pga is None,
        },
        "params": {
            "verde_max_g": params.verde_max_g,
            "rojo_min_g": params.rojo_min_g,
        },
        "motivos": motivos,
        "notes": "dictamen automático preliminar",
    }
    return Decision(status=BANDA_STATUS[band], basis=basis, band=band)


def _field_num(raw: dict, key: str, default: float, *, valid: Callable[[float], bool]) -> float:
    """Float validado del config; inválido/ausente → default del campo (+ log)."""
    value = raw.get(key, default)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and valid(float(value)):
        return float(value)
    if key in raw:
        logger.warning("dictamen config: %s=%r inválido → default %r", key, value, default)
    return default
