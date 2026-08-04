"""Proveedor OpenRouter — LISTO Y APAGADO (T-2.42).

Se entrega completo para que encenderlo sea una decisión de configuración y no un
proyecto, pero **no se enciende en esta tarea**: el gate #9 del plan maestro lo sitúa en
Fase 3 y en modo sombra. Con la configuración por defecto (``openrouter_enabled=False``,
sin slug de modelo) este módulo no abre un socket.

Tres propiedades que no son negociables aquí:

- **Fail-open total.** Cualquier fallo —red, timeout, 4xx, JSON roto, guardrail—
  degrada al proveedor determinista con su razón, que se imprime en el PDF. Una
  exportación de evidencia no puede caerse porque un tercero esté caído.
- **Sin reintentos.** Un timeout de 8 s ya es mucho dentro de un request HTTP que está
  generando evidencia; reintentar solo multiplica la espera del operador.
- **El guardrail descarta, no corrige.** Si la respuesta intenta imponer un estado, se
  inventa una medición o le falta una sección, se tira entera. Media respuesta
  "arreglada" sería justo el tipo de dato a medias que la regla de oro 7 prohíbe.

**Sin slug de modelo por defecto.** Vacío ⇒ determinista. El día que se encienda, el
slug se verifica contra ``GET /api/v1/models`` de OpenRouter antes de configurarlo: un
default hardcodeado aquí caducaría en silencio.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from takab_api.dictamen.model import STATUS_LABELS
from takab_api.narrative.base import Narrative, NarrativeFacts, NarrativeRequest
from takab_api.narrative.deterministic import sections_for
from takab_api.narrative.prompts import SECTION_TITLES, system_prompt, user_prompt
from takab_api.settings import Settings

log = logging.getLogger("takab_api.narrative")

NAME = "openrouter"

#: Techo de la respuesta completa. Seis secciones de prosa no pasan de aquí; más largo
#: es señal de que el proveedor se fue por otro lado.
MAX_TOTAL_CHARS = 9000
MAX_OUTPUT_TOKENS = 1600

#: Mediciones que la prosa puede citar. Cualquier otro número con unidad es inventado.
_MEASUREMENT = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(g|cm/s)\b")
_TOLERANCE = 1e-6


def _allowed_measurements(facts: NarrativeFacts) -> set[float]:
    """Valores con unidad que aparecen en los hechos, redondeados como se imprimen."""
    raw: list[float | None] = [facts.peak_pga_g, facts.peak_pgv_cms]
    basis = facts.basis if isinstance(facts.basis, dict) else {}
    for block in ("evidence", "params"):
        for value in (basis.get(block) or {}).values():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                raw.append(float(value))
    allowed: set[float] = set()
    for value in raw:
        if value is None:
            continue
        allowed.add(float(value))
        # La prosa cita con los decimales del documento: 0.0812 se imprime "0.081".
        allowed.update(round(float(value), digits) for digits in (0, 1, 2, 3))
    return allowed


def guard(sections: dict[str, str], facts: NarrativeFacts) -> str | None:
    """Razón por la que se descarta la respuesta, o ``None`` si es aceptable."""
    faltantes = [t for t in SECTION_TITLES if not (sections.get(t) or "").strip()]
    if faltantes:
        return f"secciones ausentes o vacías: {', '.join(faltantes)}"
    sobrantes = [t for t in sections if t not in SECTION_TITLES]
    if sobrantes:
        return f"secciones no previstas: {', '.join(sorted(sobrantes))}"

    texto = "\n".join(sections[t] for t in SECTION_TITLES)
    if len(texto) > MAX_TOTAL_CHARS:
        return f"respuesta demasiado larga ({len(texto)} caracteres)"

    propio = facts.verdict_label
    ajenos = sorted(
        {label for label in STATUS_LABELS.values() if label != propio and label in texto}
        | {
            status
            for status in STATUS_LABELS
            if status != facts.verdict_status and re.search(rf"\b{status}\b", texto)
        }
    )
    if ajenos:
        return f"menciona un veredicto distinto del dictaminado: {', '.join(ajenos)}"

    permitidas = _allowed_measurements(facts)
    inventadas = sorted(
        {
            f"{m.group(1)} {m.group(2)}"
            for m in _MEASUREMENT.finditer(texto)
            if not any(abs(float(m.group(1)) - a) <= _TOLERANCE for a in permitidas)
        }
    )
    if inventadas:
        return f"cita mediciones que no están en los hechos: {', '.join(inventadas)}"
    return None


def resolve_api_key(settings: Settings, *, client: Any | None = None) -> str:
    """Clave inline (dev) o de Secrets Manager (producción). Vacía ⇒ no se llama a nadie.

    Espejo del patrón de ``commands/keys.py``: el secreto nunca vive en el repo ni en la
    imagen, y su ausencia es fail-closed hacia el proveedor determinista.
    """
    if settings.openrouter_api_key:
        return settings.openrouter_api_key
    if not settings.openrouter_secret_id:
        return ""
    try:
        sm = client
        if sm is None:  # pragma: no cover - requiere AWS real
            import boto3  # noqa: PLC0415 - import perezoso: solo en producción

            sm = boto3.client("secretsmanager", region_name=settings.aws_region)
        raw = sm.get_secret_value(SecretId=settings.openrouter_secret_id)["SecretString"]
        payload = json.loads(raw)
        return str(payload.get("api_key") or "")
    except Exception as exc:  # noqa: BLE001 - un secreto irresoluble degrada, no rompe
        log.warning("narrative: no se pudo resolver la clave de OpenRouter: %s", exc)
        return ""


def _parse(content: str) -> dict[str, str]:
    """Secciones del JSON de respuesta. Tolera el ```json de algunos modelos."""
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    data = json.loads(text)
    sections = data.get("sections") if isinstance(data, dict) else None
    if not isinstance(sections, dict):
        raise ValueError("la respuesta no trae un objeto 'sections'")
    return {str(k): str(v) for k, v in sections.items()}


class OpenRouterProvider:
    """Cliente HTTP de OpenRouter con degradación total al determinista."""

    name = NAME

    def __init__(self, settings: Settings, *, api_key: str = "", transport: Any | None = None):
        self._settings = settings
        self._api_key = api_key
        self._transport = transport

    async def generate(self, req: NarrativeRequest) -> Narrative:
        started = time.monotonic()
        try:
            payload = await self._post(req)
        except Exception as exc:  # noqa: BLE001 - fail-open: la evidencia sale igual
            log.warning("narrative: OpenRouter falló (%s); se degrada a determinista", exc)
            return self._degraded(req, f"el proveedor no respondió ({type(exc).__name__})")

        elapsed_ms = int((time.monotonic() - started) * 1000)
        try:
            content = payload["choices"][0]["message"]["content"]
            sections = _parse(content)
        except Exception as exc:  # noqa: BLE001
            log.warning("narrative: respuesta de OpenRouter ilegible: %s", exc)
            return self._degraded(req, "la respuesta del proveedor no se pudo interpretar")

        rejected = guard(sections, req.facts)
        if rejected:
            log.warning("narrative: guardrail descartó la respuesta — %s", rejected)
            return self._degraded(req, f"guardrail: {rejected}")

        usage = payload.get("usage") or {}
        return Narrative(
            sections=tuple((t, sections[t].strip()) for t in SECTION_TITLES),
            provider=NAME,
            model=payload.get("model") or req.model,
            latency_ms=elapsed_ms,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            cost_usd=usage.get("cost"),
        )

    async def _post(self, req: NarrativeRequest) -> dict:
        import httpx  # noqa: PLC0415 - import perezoso: el camino apagado no lo paga

        s = self._settings
        kwargs: dict[str, Any] = {"timeout": s.openrouter_timeout_s}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        async with httpx.AsyncClient(**kwargs) as client:
            resp = await client.post(
                f"{s.openrouter_base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    # Cortesía de OpenRouter: identifica la app en su consola.
                    "X-Title": "TAKAB Ailert",
                },
                json={
                    "model": req.model,
                    "messages": [
                        {"role": "system", "content": system_prompt()},
                        {"role": "user", "content": user_prompt(req.facts)},
                    ],
                    "max_tokens": MAX_OUTPUT_TOKENS,
                    "response_format": {"type": "json_object"},
                    "usage": {"include": True},
                },
            )
            resp.raise_for_status()
            return resp.json()

    def _degraded(self, req: NarrativeRequest, reason: str) -> Narrative:
        return Narrative(
            sections=sections_for(req.facts),
            provider="deterministic",
            model=req.model or None,
            degraded_reason=reason,
        )
