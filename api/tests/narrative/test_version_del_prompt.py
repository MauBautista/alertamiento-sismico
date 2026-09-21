"""T-7.26 · Los dos campos de procedencia que faltaban: versión del prompt y hash de la salida.

La ficha los pide por su nombre y **no existían en todo `api/`** (medido con grep antes
de escribir esto). Son los dos que contestan la única pregunta que importa el día que
alguien audite un dictamen redactado con asistencia: *¿con qué instrucciones y qué
devolvió exactamente el modelo?*

**La versión se DERIVA del texto del prompt, no se teclea.** Un número de versión a mano
se queda viejo al primer retoque de redacción —y entonces el campo no significa nada,
que es peor que no tenerlo—. Derivándola de un hash de las plantillas, nadie puede
cambiar el prompt sin que la versión cambie. Estos tests son justamente eso: se cambia
cada pieza del prompt y se exige que la versión se mueva.

**El hash de la salida es de lo que devolvió el modelo, ANTES de aplicar nada**: antes
de parsear, antes del guardrail y antes de recortar. Si la respuesta se descarta, el
hash sigue estando — es cuando más falta hace saber qué dijo.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from takab_api.narrative import build_narrative, prompts
from takab_api.narrative.base import NarrativeRequest
from takab_api.narrative.deterministic import sections_for
from takab_api.narrative.openrouter import OpenRouterProvider
from takab_api.narrative.prompts import piezas_del_prompt, prompt_version
from takab_api.narrative.redact import facts_from
from takab_api.settings import Settings
from tests.dictamen.test_pdf import model
from tests.narrative.test_redact import BASIS

FACTS = facts_from(model(verdict_basis=BASIS))
BUENAS = dict(sections_for(FACTS))
_PROMPTS = Path(__file__).resolve().parents[2] / "src/takab_api/narrative/prompts.py"


def _provider(handler) -> OpenRouterProvider:
    ajustes = Settings(
        openrouter_enabled=True, openrouter_model="algun/modelo", openrouter_api_key="sk-test"
    )
    return OpenRouterProvider(ajustes, api_key="sk-test", transport=httpx.MockTransport(handler))


def _respuesta(sections: dict[str, str]) -> str:
    return json.dumps({"sections": sections})


# ── la versión se DERIVA ──────────────────────────────────────────────────────


def test_la_version_es_estable_mientras_el_prompt_no_cambie() -> None:
    assert prompt_version() == prompt_version()
    assert prompt_version(), "una versión vacía no identifica nada"


@pytest.mark.parametrize("pieza", [n for n, _ in piezas_del_prompt()])
def test_cambiar_CUALQUIER_pieza_del_prompt_mueve_la_version(monkeypatch, pieza: str) -> None:
    """⚠️ [T-7.27·A] **Este censo se DERIVA; antes se enumeraba a mano y divergió.**

    Había un test por pieza —el prompt de sistema, los títulos, el encabezado del
    usuario— y `T-7.27` añadió `INSTRUCCION_FOTOS` en otro fichero y **se saltó
    `ROTULO_FOTO`**: medido, se podía sacar el rótulo del material y las 201 pruebas
    seguían verdes, aunque el docstring de `prompt_version` promete que entra y aunque
    cambiar ese texto dejaría dictámenes registrados con una versión que no es la que se
    usó — el defecto exacto que este campo existe para impedir.

    Hoy la lista sale de `prompts.piezas_del_prompt()`, que es la MISMA función de la que
    sale el material que se hashea: una plantilla nueva entra en las dos a la vez o en
    ninguna. Un censo enumerado a mano acaba divergiendo; es la cuarta vez.
    """
    antes = prompt_version()
    valor = getattr(prompts, pieza)
    otro = ("otra cosa", *valor) if isinstance(valor, tuple) else f"{valor} · otra cosa"
    monkeypatch.setattr(f"takab_api.narrative.prompts.{pieza}", otro)
    assert prompt_version() != antes, f"cambiar {pieza} no movió la versión del prompt"


def test_el_censo_de_piezas_NO_esta_vacio_ni_se_encoge_en_silencio() -> None:
    """El control de no-vacuidad del parametrizado de arriba: con la lista vacía, cero
    tests correrían y el fichero seguiría en verde."""
    nombres = {n for n, _ in piezas_del_prompt()}
    assert {"SYSTEM", "SECTION_TITLES", "USER_PREFIX", "INSTRUCCION_FOTOS", "ROTULO_FOTO"} <= (
        nombres
    ), f"el censo de plantillas perdió piezas: {sorted(nombres)}"
    assert all(texto for _, texto in piezas_del_prompt()), "una plantilla vacía no instruye nada"


def test_la_version_NO_esta_tecleada_en_el_modulo() -> None:
    """Que la versión de hoy no esté ESCRITA en `prompts.py`. Nada más, y se dice.

    ⚠️ Esta guarda prometía cazar «cualquier constante que sustituya a la derivación» y
    solo mira este fichero y esta cadena: una constante escrita en otro módulo, o una
    que no aparezca literalmente (`material = "…"`), la dejan verde. Medido. Quien caza
    esos casos son los TRES tests de derivación de arriba —se toca cada pieza del prompt
    y se exige que la versión se mueva—, y el conjunto sí aguanta. Esta sola, no: su
    valor es que un `return "p1"` tecleado aquí se vea al primer vistazo.
    """
    assert prompt_version() not in _PROMPTS.read_text(encoding="utf-8")


# ── el hash de la salida ──────────────────────────────────────────────────────


async def test_una_respuesta_aceptada_va_con_su_version_y_su_HASH() -> None:
    contenido = _respuesta(BUENAS)

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(
            200,
            json={
                "model": "algun/modelo",
                "choices": [{"message": {"content": contenido}}],
                "usage": {"prompt_tokens": 900, "completion_tokens": 300, "cost": 0.0042},
            },
        )

    out = await _provider(handler).generate(NarrativeRequest(facts=FACTS, model="algun/modelo"))
    assert out.provider == "openrouter"
    assert out.prompt_version == prompt_version()
    assert out.output_sha256 == hashlib.sha256(contenido.encode("utf-8")).hexdigest()


async def test_una_respuesta_DESCARTADA_conserva_el_hash_de_lo_que_dijo() -> None:
    """Es cuando más falta hace: el guardrail tiró la respuesta y el único rastro de
    qué se propuso el modelo es este hash contra el log del proveedor."""
    intruso = {**BUENAS, "Qué se midió": "El pico fue de 0.99 g."}
    contenido = _respuesta(intruso)

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(200, json={"choices": [{"message": {"content": contenido}}]})

    out = await _provider(handler).generate(NarrativeRequest(facts=FACTS, model="m"))
    assert out.provider == "deterministic"
    assert "guardrail" in (out.degraded_reason or "")
    assert out.output_sha256 == hashlib.sha256(contenido.encode("utf-8")).hexdigest()
    assert out.prompt_version == prompt_version()


async def test_sin_respuesta_no_hay_hash_pero_SI_version() -> None:
    """El prompt se mandó: eso es un hecho aunque no volviera nada. Fingir un hash
    de una salida que no existe sería inventarse evidencia."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("tardó demasiado", request=request)

    out = await _provider(handler).generate(NarrativeRequest(facts=FACTS, model="m"))
    assert out.output_sha256 is None
    assert out.prompt_version == prompt_version()


async def test_el_determinista_puro_no_finge_haber_mandado_un_prompt() -> None:
    """Con la perilla apagada no hubo prompt ni salida: los dos campos van vacíos.
    Rellenarlos con la versión «actual» diría que se consultó a un modelo."""
    out = await build_narrative(model(), Settings())
    assert out.prompt_version is None
    assert out.output_sha256 is None
