"""Proveedor determinista (T-2.42). Es el que está ACTIVO.

No es un relleno mientras llega la IA: es el suelo del que la IA nunca puede bajar. Sin
red, sin clave y sin coste, produce las seis secciones a partir de los mismos hechos
redactados, y el veredicto que cita es literalmente el que calculó ``dictamen/rules.py``.

Si el proveedor remoto falla, degrada aquí — por eso la prosa nunca falta.
"""

from __future__ import annotations

from takab_api.dictamen.model import ABSENT, num
from takab_api.narrative.base import Narrative, NarrativeFacts, NarrativeRequest
from takab_api.narrative.prompts import SECTION_TITLES

NAME = "deterministic"

_TRIGGER_TEXT = {
    "sasmex": "un acuse del receptor SASMEX (contacto seco en el gabinete)",
    "local_threshold": "el umbral instrumental del sensor del propio inmueble",
    "quorum": "la corroboración de varias estaciones de la red",
    "manual": "una activación manual de un operador",
    "drill": "un simulacro programado",
}

_SOURCE_TEXT = {
    "features": "la ventana de features del sensor",
    "incident": "el pico ya registrado en el incidente",
    "none": "ninguna medición instrumental",
}


def _resumen(f: NarrativeFacts) -> str:
    firmado = "firmado por un inspector" if f.verdict_signed else "sin firma de inspector todavía"
    pico = (
        f"con un pico medido de {num(f.peak_pga_g, 3, 'g')}"
        if f.peak_pga_g is not None
        else "sin pico instrumental medido"
    )
    return (
        f"Folio {f.folio}. El dictamen vigente es «{f.verdict_label}», {firmado}. "
        f"El incidente se abrió con severidad {f.severity} {pico}, "
        f"clasificado como {f.felt_label.lower()}. "
        f"Este documento es preliminar y no sustituye una evaluación estructural formal."
    )


def _que_paso(f: NarrativeFacts) -> str:
    disparo = _TRIGGER_TEXT.get(f.trigger, f"un disparo de tipo «{f.trigger}»")
    partes = [f"El incidente se abrió el {f.opened_at} a partir de {disparo}."]
    if f.station_count:
        partes.append(
            f"{f.station_count} estación(es) de la red registraron el evento en la ventana "
            "de asociación."
        )
    else:
        partes.append("Ninguna otra estación de la red corroboró el evento.")
    if f.has_epicenter:
        origen = f.event_source or "origen no declarado"
        partes.append(f"El evento tiene epicentro localizado (fuente: {origen}).")
    else:
        partes.append("El evento no tiene epicentro localizado.")
    partes.append(f"Tiempo de aviso ganado: {f.lead_time}.")
    if f.catalog_line:
        partes.append(f"Correlación con catálogo: {f.catalog_line}.")
    if f.action_counts:
        detalle = ", ".join(f"{kind} ×{n}" for kind, n in f.action_counts)
        partes.append(f"Acciones registradas en la bitácora del incidente: {detalle}.")
    return " ".join(partes)


def _que_se_midio(f: NarrativeFacts) -> str:
    partes = [
        f"Aceleración pico: {num(f.peak_pga_g, 3, 'g')}. "
        f"Velocidad pico: {num(f.peak_pgv_cms, 2, 'cm/s')}. "
        f"Banda de sacudida: {f.felt_label}."
    ]
    if f.channel_count:
        partes.append(f"Se archivaron features de {f.channel_count} canal(es).")
    if f.clipped_channels:
        partes.append(
            f"Los canales {', '.join(f.clipped_channels)} saturaron: en ellos el valor "
            "registrado es el techo del convertidor, no la sacudida real."
        )
    partes.append(
        "Los valores están calibrados a unidades físicas."
        if f.calibrated
        else "Los valores son RELATIVOS del sensor: no hay fuente de calibración declarada."
    )
    partes.append(
        "El incidente tiene forma de onda cruda archivada."
        if f.has_raw_waveform
        else "No hay forma de onda cruda archivada para este incidente."
    )
    return " ".join(partes)


def _por_que(f: NarrativeFacts) -> str:
    """Trazabilidad literal del ``basis``: qué umbral, con qué valor, de qué versión."""
    if f.verdict_status is None:
        return (
            "El incidente todavía no tiene dictamen registrado, de modo que no hay un "
            "veredicto que explicar. Los hechos de las secciones anteriores son la "
            "evidencia disponible hasta ahora."
        )
    version = f.rule_set_version or ABSENT
    partes = [f"El veredicto «{f.verdict_label}» lo produjo el conjunto de reglas {version}."]

    evidencia = f.basis.get("evidence", {}) if isinstance(f.basis, dict) else {}
    params = f.basis.get("params", {}) if isinstance(f.basis, dict) else {}
    if not evidencia and not params:
        partes.append(
            "El registro de fundamento (basis) de este dictamen no quedó guardado, por lo "
            "que no puede reconstruirse qué umbral lo determinó."
        )
        return " ".join(partes)

    pga = evidencia.get("pga_g")
    no_hab = params.get("pga_no_inhabit_g")
    monitor = params.get("pga_monitor_g")
    if pga is not None and no_hab is not None and monitor is not None:
        comparacion = (
            f"El valor evaluado fue {num(pga, 3, 'g')} frente a un umbral de no habitar de "
            f"{num(no_hab, 3, 'g')} y uno de monitoreo de {num(monitor, 3, 'g')}: "
        )
        if pga >= no_hab:
            comparacion += "superó el umbral de no habitar."
        elif pga >= monitor:
            comparacion += "superó el umbral de monitoreo sin alcanzar el de no habitar."
        else:
            comparacion += "no alcanzó ninguno de los dos umbrales."
        partes.append(comparacion)

    severidad = evidencia.get("severity")
    if severidad:
        partes.append(f"La severidad del incidente en el momento de dictaminar era {severidad}.")
    nodos = evidencia.get("node_count")
    if nodos is not None:
        corroborado = evidencia.get("corroborated")
        partes.append(
            f"La regla de nodos contó {nodos} estación(es) y "
            f"{'sí' if corroborado else 'no'} alcanzó el quórum; esa regla solo puede elevar "
            "la prudencia del dictamen, nunca rebajarla."
        )
    fuente = evidencia.get("pga_source")
    if fuente:
        partes.append(f"El pico evaluado provino de {_SOURCE_TEXT.get(fuente, fuente)}.")
    if evidencia.get("insufficient_data"):
        partes.append(
            "Sin medición instrumental ni corroboración de red, el veredicto se sostiene "
            "únicamente en la severidad de la alerta recibida."
        )
    if f.dictamen_count > 1:
        partes.append(
            f"Hay {f.dictamen_count} dictámenes en la cadena de este incidente; el vigente "
            "es el más reciente y los anteriores se conservan como evidencia."
        )
    return " ".join(partes)


def _que_hacer(f: NarrativeFacts) -> str:
    if not f.verdict_actions:
        return (
            "No hay acciones asociadas a este estado en la tabla de instrucciones. "
            "Consulte al responsable del inmueble antes de tomar una decisión de ocupación."
        )
    pasos = " ".join(f"{i}. {a}" for i, a in enumerate(f.verdict_actions, start=1))
    critico = (
        " El inmueble está clasificado como crítico, por lo que la inspección tiene prioridad."
        if f.site_criticality == "critical"
        else ""
    )
    return f"{pasos}{critico}"


def _limitaciones(f: NarrativeFacts) -> str:
    base = (
        "Este dictamen es preliminar y automático. TAKAB no calcula intensidad "
        "macrosísmica ni isosistas, y no localiza sismos: lo que reporta es la sacudida "
        "medida en el propio inmueble."
    )
    if not f.absences:
        return f"{base} No se detectaron datos ausentes en este incidente."
    lista = " ".join(f"({i}) {a}" for i, a in enumerate(f.absences, start=1))
    return f"{base} Datos ausentes en este incidente: {lista}"


_RENDERERS = (_resumen, _que_paso, _que_se_midio, _por_que, _que_hacer, _limitaciones)


def sections_for(facts: NarrativeFacts) -> tuple[tuple[str, str], ...]:
    """Las seis secciones. Mismos hechos ⇒ mismo texto, byte a byte."""
    return tuple(zip(SECTION_TITLES, (r(facts) for r in _RENDERERS), strict=True))


class DeterministicProvider:
    """Proveedor por defecto. Sin red, sin clave, sin coste."""

    name = NAME

    async def generate(self, req: NarrativeRequest) -> Narrative:
        return Narrative(sections=sections_for(req.facts), provider=NAME)
