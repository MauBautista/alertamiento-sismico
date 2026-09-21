"""Proveedor OpenRouter (T-2.42) — apagado por defecto, encendido POR CONFIGURACIÓN.

Se entregó completo para que encenderlo fuera una decisión de configuración y no un
proyecto. **En T-7.26 se enciende en el entorno `dev` desde el despliegue**
(``TAKAB_API_OPENROUTER_ENABLED``, ``_MODEL``, ``_SECRET_ID``); el default del código
sigue siendo apagado y así se queda: con ``openrouter_enabled=False`` y sin slug de
modelo este módulo no abre un socket, y eso lo defiende un test.

⚠️ [T-7.26] **Apagado y «encendido pero no pude» dejaron de ser lo mismo.** Antes,
cualquier fallo al resolver la clave devolvía cadena vacía y el sistema se comportaba
igual que si nadie hubiera pedido IA — de modo que un ``AccessDenied`` sobre el secreto
(lo que pasa en la nube el primer día) salía como un dictamen normal. Ahora
``resolve_api_key`` devuelve el fallo con nombre y ``select_provider`` lo declara en el
papel. Ver ``narrative/__init__.py``.

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

⚠️ **Y ese día llegó sin la verificación.** T-7.26 enciende el slug desde el despliegue
y nadie lo ha contrastado contra ``/api/v1/models`` — hace falta la clave real y salida
a la red, así que queda pendiente de ``GATE-AWS``. Lo que SÍ está cubierto entretanto es
que un slug caducado no pase por un fallo de red: OpenRouter responde 400 y el papel
imprime «el proveedor de redacción respondió con error (HTTP 400)», no «no respondió».
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from takab_api.dictamen.model import STATUS_LABELS
from takab_api.narrative.base import (
    MOTIVO_PROVEEDOR_CREDENCIAL,
    MOTIVO_PROVEEDOR_ESTADO,
    MOTIVO_PROVEEDOR_MUDO,
    MOTIVO_RESPUESTA_ILEGIBLE,
    Narrative,
    NarrativeFacts,
    NarrativeRequest,
    motivo_con_causa,
    motivo_guardrail,
)
from takab_api.narrative.deterministic import NAME as DETERMINISTA
from takab_api.narrative.deterministic import sections_for
from takab_api.narrative.prompts import SECTION_TITLES, prompt_version, system_prompt, user_prompt
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


@dataclass(frozen=True, slots=True)
class ClaveOpenRouter:
    """Resultado de buscar la clave. **La ausencia y el fallo NO son lo mismo.**

    Antes de T-7.26 esto devolvía una cadena, y vacía significaba las dos cosas a la
    vez: «no hay nada configurado» y «lo hay pero no pude leerlo». Con esa confusión, un
    ``AccessDenied`` sobre el secreto —lo que pasa en la nube el primer día, mientras el
    rol de la instancia no tiene permiso— se veía exactamente igual que tener la IA
    apagada, y el PDF salía con prosa determinista **sin declarar nada**.
    """

    api_key: str
    #: Código del fallo (``AccessDeniedException``…), o ``None`` si no hubo fallo. Con
    #: ``api_key`` vacía y ``error`` a ``None``, lo que pasa es que no se configuró
    #: ningún origen de clave.
    error: str | None = None


#: El secreto existe y se leyó, pero no trae `api_key`. Es un CÓDIGO y no la frase que
#: había antes («el secreto no trae la clave 'api_key'»): `ClaveOpenRouter.error` viaja
#: a `motivo_con_causa`, cuya regla es que la causa es un nombre corto y jamás un
#: mensaje. La frase no filtraba nada —la escribíamos nosotros—, pero dejaba la regla
#: escrita sin cumplir por una rama, y una regla que se cumple «casi siempre» no se
#: puede vigilar. El papel lo imprime igual de legible: «… la clave no se pudo leer
#: (SecretoSinApiKey); texto determinista».
CODIGO_SECRETO_SIN_CLAVE = "SecretoSinApiKey"


def _codigo_de(exc: Exception) -> str:
    """Nombre corto de la causa, NUNCA el mensaje.

    El de botocore es del tipo «An error occurred (AccessDeniedException) … not
    authorized to perform secretsmanager:GetSecretValue on resource arn:aws:…:634…»: se
    lleva por delante el ARN y el número de cuenta, y esto acaba impreso en un dictamen
    que sale de la organización.
    """
    respuesta = getattr(exc, "response", None)
    if isinstance(respuesta, dict):
        codigo = (respuesta.get("Error") or {}).get("Code")
        if codigo:
            return str(codigo)
    return type(exc).__name__


def resolve_api_key(settings: Settings, *, client: Any | None = None) -> ClaveOpenRouter:
    """Clave inline (dev) o de Secrets Manager (producción). Sin clave ⇒ no se llama a nadie.

    Espejo del patrón de ``commands/keys.py``: el secreto nunca vive en el repo ni en la
    imagen, y su ausencia es fail-closed hacia el proveedor determinista. Lo que cambia
    en T-7.26 es que el fallo **vuelve con nombre**, para que quien decide (
    ``select_provider``) pueda declararlo en el papel.
    """
    if settings.openrouter_api_key:
        return ClaveOpenRouter(settings.openrouter_api_key)
    if not settings.openrouter_secret_id:
        return ClaveOpenRouter("")
    try:
        sm = client
        if sm is None:  # pragma: no cover - requiere AWS real
            import boto3  # noqa: PLC0415 - import perezoso: solo en producción

            sm = boto3.client("secretsmanager", region_name=settings.aws_region)
        raw = sm.get_secret_value(SecretId=settings.openrouter_secret_id)["SecretString"]
        payload = json.loads(raw)
        clave = str(payload.get("api_key") or "")
    except Exception as exc:  # noqa: BLE001 - un secreto irresoluble degrada, no rompe
        log.warning("narrative: no se pudo resolver la clave de OpenRouter: %s", _codigo_de(exc))
        return ClaveOpenRouter("", error=_codigo_de(exc))
    if not clave:
        # El secreto existe y se leyó, pero no trae `api_key`. Es un fallo de contenido
        # y no una ausencia de configuración: quien lo creó creyó que estaba puesto.
        return ClaveOpenRouter("", error=CODIGO_SECRETO_SIN_CLAVE)
    return ClaveOpenRouter(clave)


def _content_of(payload: dict) -> str | None:
    """El texto de la respuesta, o ``None`` si el sobre no tiene la forma esperada.

    No lanza a propósito: se llama ANTES del ``try`` que interpreta, porque el hash de
    la salida tiene que existir aunque el contenido resulte ilegible.
    """
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    return content if isinstance(content, str) else None


def _sha256_de(content: str | None) -> str | None:
    """Huella de la salida. ``None`` si no volvió nada: fingir el hash de una salida
    que no existe sería inventarse evidencia."""
    if content is None:
        return None
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _parse(content: str | None) -> dict[str, str]:
    """Secciones del JSON de respuesta. Tolera el ```json de algunos modelos."""
    if content is None:
        raise ValueError("la respuesta no trae contenido")
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    data = json.loads(text)
    sections = data.get("sections") if isinstance(data, dict) else None
    if not isinstance(sections, dict):
        raise ValueError("la respuesta no trae un objeto 'sections'")
    return {str(k): str(v) for k, v in sections.items()}


def _motivo_del_fallo(exc: Exception) -> str:
    """Por qué no hubo prosa del proveedor. **«No respondió» y «respondió que no» no
    son lo mismo, y confundirlos manda a depurar al sitio equivocado.**

    Medido con la clave revocada: OpenRouter devuelve un ``401`` —o sea que respondió,
    y rápido— y el papel imprimía «el proveedor no respondió (HTTPStatusError)». Quien
    leyera eso iría a mirar la red; el problema estaba en el secreto. Es el mismo tipo
    de frase conservadora-pero-falsa que esta ficha corrigió en la cuota («agotada»
    contra «no había»).

    El estado HTTP entra en la causa porque es el dato que decide a dónde ir: 401/403
    al secreto, 400 al slug del modelo, 5xx a esperar. Sale de ``response.status_code``,
    que solo tienen las excepciones que SÍ traen respuesta (``HTTPStatusError``); un
    timeout o un fallo de DNS no lo tienen y caen en «no respondió», que entonces es
    verdad.
    """
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if not isinstance(status, int):
        return motivo_con_causa(MOTIVO_PROVEEDOR_MUDO, type(exc).__name__)
    if status in (401, 403):
        return motivo_con_causa(MOTIVO_PROVEEDOR_CREDENCIAL, f"HTTP {status}")
    return motivo_con_causa(MOTIVO_PROVEEDOR_ESTADO, f"HTTP {status}")


class OpenRouterProvider:
    """Cliente HTTP de OpenRouter con degradación total al determinista."""

    name = NAME

    def __init__(self, settings: Settings, *, api_key: str = "", transport: Any | None = None):
        self._settings = settings
        self._api_key = api_key
        self._transport = transport

    async def generate(self, req: NarrativeRequest) -> Narrative:
        started = time.monotonic()
        # [T-7.26] La versión se calcula ANTES de salir y acompaña a la respuesta pase
        # lo que pase: que el prompt se mandó es un hecho aunque no vuelva nada.
        version = prompt_version()
        try:
            payload = await self._post(req)
        except Exception as exc:  # noqa: BLE001 - fail-open: la evidencia sale igual
            log.warning("narrative: OpenRouter falló (%s); se degrada a determinista", exc)
            return self._degraded(req, _motivo_del_fallo(exc), prompt_version=version)

        elapsed_ms = int((time.monotonic() - started) * 1000)
        # [T-7.26] El hash es de lo que devolvió el modelo, TAL CUAL: antes de parsear,
        # antes del guardrail y antes de recortar. Si la respuesta se descarta es cuando
        # más falta hace — es el único rastro de qué se propuso, contable contra el log
        # del proveedor.
        content = _content_of(payload)
        salida = _sha256_de(content)
        try:
            sections = _parse(content)
        except Exception as exc:  # noqa: BLE001
            log.warning("narrative: respuesta de OpenRouter ilegible: %s", exc)
            return self._degraded(
                req,
                MOTIVO_RESPUESTA_ILEGIBLE,
                prompt_version=version,
                output_sha256=salida,
            )

        rejected = guard(sections, req.facts)
        if rejected:
            log.warning("narrative: guardrail descartó la respuesta — %s", rejected)
            return self._degraded(
                req,
                motivo_guardrail(rejected),
                prompt_version=version,
                output_sha256=salida,
            )

        usage = payload.get("usage") or {}
        return Narrative(
            sections=tuple((t, sections[t].strip()) for t in SECTION_TITLES),
            provider=NAME,
            model=payload.get("model") or req.model,
            latency_ms=elapsed_ms,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            cost_usd=usage.get("cost"),
            prompt_version=version,
            output_sha256=salida,
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

    def _degraded(
        self,
        req: NarrativeRequest,
        reason: str,
        *,
        prompt_version: str | None = None,
        output_sha256: str | None = None,
    ) -> Narrative:
        # ⚠️ La constante, no la cadena. `narrative._hubo_redaccion_cobrable` decide SI
        # SE COBRA comparando `provider` contra `deterministic.NAME`: con el literal
        # tecleado aquí, la decisión de dinero dependía de que dos cadenas escritas en
        # dos ficheros distintos siguieran coincidiendo.
        return Narrative(
            sections=sections_for(req.facts),
            provider=DETERMINISTA,
            model=req.model or None,
            degraded_reason=reason,
            prompt_version=prompt_version,
            output_sha256=output_sha256,
        )
