"""T-2.42 · OpenRouter: listo y APAGADO.

Dos familias de pruebas. La primera es la que se despliega: con la configuración por
defecto nadie abre un socket. La segunda simula el día que se encienda, y ahí lo que se
prueba es el guardrail — porque un proveedor que se inventa una medición en un documento
que acabará ante Protección Civil es exactamente el fallo que hay que impedir.

El transporte se inyecta con `httpx.MockTransport`: se ejerce el cliente real
(cabeceras, cuerpo, parseo) sin salir a la red.
"""

from __future__ import annotations

import json

import httpx

from takab_api.narrative import build_narrative, select_provider
from takab_api.narrative.base import NarrativeRequest
from takab_api.narrative.deterministic import DeterministicProvider, sections_for
from takab_api.narrative.openrouter import (
    MAX_TOTAL_CHARS,
    OpenRouterProvider,
    guard,
    resolve_api_key,
)
from takab_api.narrative.prompts import SECTION_TITLES
from takab_api.narrative.redact import facts_from
from takab_api.settings import Settings
from tests.dictamen.test_pdf import model
from tests.narrative.test_redact import BASIS

FACTS = facts_from(model(verdict_basis=BASIS))
BUENAS = {t: c for t, c in sections_for(FACTS)}


def _settings(**over) -> Settings:
    base = {
        "openrouter_enabled": True,
        "openrouter_model": "algun/modelo",
        "openrouter_api_key": "sk-test",
    }
    return Settings(**{**base, **over})


def _respuesta(sections: dict[str, str], **extra) -> dict:
    return {
        "model": "algun/modelo",
        "choices": [{"message": {"content": json.dumps({"sections": sections})}}],
        "usage": {"prompt_tokens": 900, "completion_tokens": 300, "cost": 0.0042},
        **extra,
    }


def _provider(handler, **over) -> OpenRouterProvider:
    return OpenRouterProvider(
        _settings(**over), api_key="sk-test", transport=httpx.MockTransport(handler)
    )


# ---- apagado por defecto (esto es lo que se despliega) -----------------------


def test_por_defecto_el_proveedor_elegido_es_el_determinista() -> None:
    provider, slug = select_provider(Settings())
    assert isinstance(provider, DeterministicProvider)
    assert slug == ""


def test_sin_slug_de_modelo_no_se_enciende_aunque_el_flag_este_puesto() -> None:
    """No hay default de modelo a propósito: un slug hardcodeado caduca en silencio."""
    provider, _ = select_provider(_settings(openrouter_model=""))
    assert isinstance(provider, DeterministicProvider)


def test_sin_clave_resoluble_no_se_enciende() -> None:
    provider, _ = select_provider(_settings(openrouter_api_key=""))
    assert isinstance(provider, DeterministicProvider)


def test_estar_apagado_NO_es_una_degradacion() -> None:
    """El PDF solo debe declarar "narrativa degradada" cuando algo falló de verdad."""
    provider, _ = select_provider(Settings())
    assert isinstance(provider, DeterministicProvider)


async def test_apagado_no_abre_ningun_socket(monkeypatch) -> None:
    """Se sabotea el cliente HTTP entero: si el camino apagado lo tocara, reventaría."""

    def explota(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        raise AssertionError("el camino apagado no debe construir un cliente HTTP")

    monkeypatch.setattr(httpx, "AsyncClient", explota)
    out = await build_narrative(model(), Settings())
    assert out.provider == "deterministic"
    assert out.degraded_reason is None


def test_la_clave_sale_del_secreto_cuando_no_esta_inline() -> None:
    class SM:
        def get_secret_value(self, SecretId: str) -> dict:  # noqa: N803
            assert SecretId == "takab/dev/openrouter"
            return {"SecretString": json.dumps({"api_key": "sk-del-secreto"})}

    s = _settings(openrouter_api_key="", openrouter_secret_id="takab/dev/openrouter")
    assert resolve_api_key(s, client=SM()) == "sk-del-secreto"


def test_un_secreto_irresoluble_degrada_a_clave_vacia() -> None:
    class SM:
        def get_secret_value(self, SecretId: str) -> dict:  # noqa: N803, ARG002
            raise RuntimeError("sin permisos")

    s = _settings(openrouter_api_key="", openrouter_secret_id="takab/dev/openrouter")
    assert resolve_api_key(s, client=SM()) == ""


# ---- guardrail ---------------------------------------------------------------


def test_una_respuesta_correcta_pasa() -> None:
    assert guard(BUENAS, FACTS) is None


def test_le_falta_una_seccion() -> None:
    parcial = {t: c for t, c in BUENAS.items() if t != "Por qué este veredicto"}
    assert "Por qué este veredicto" in (guard(parcial, FACTS) or "")


def test_una_seccion_vacia_cuenta_como_ausente() -> None:
    assert "Qué pasó" in (guard({**BUENAS, "Qué pasó": "   "}, FACTS) or "")


def test_una_seccion_inventada_se_rechaza() -> None:
    assert "no previstas" in (guard({**BUENAS, "Recomendación final": "x"}, FACTS) or "")


def test_una_respuesta_desbordada_se_rechaza() -> None:
    largo = {**BUENAS, "Qué pasó": "a" * (MAX_TOTAL_CHARS + 1)}
    assert "demasiado larga" in (guard(largo, FACTS) or "")


def test_no_puede_proponer_OTRO_veredicto() -> None:
    """El caso que motiva todo el módulo: la prosa no revisa el dictamen."""
    intruso = {
        **BUENAS,
        "Resumen ejecutivo": "En realidad corresponde NO HABITAR · INSPECCIÓN del inmueble.",
    }
    razon = guard(intruso, FACTS) or ""
    assert "veredicto distinto" in razon


def test_tampoco_por_la_clave_interna_del_estado() -> None:
    intruso = {**BUENAS, "Qué hacer ahora": "Debería marcarse como no_inhabit_inspect."}
    assert "veredicto distinto" in (guard(intruso, FACTS) or "")


def test_puede_citar_SU_PROPIO_veredicto() -> None:
    propio = {**BUENAS, "Resumen ejecutivo": f"El dictamen es «{FACTS.verdict_label}»."}
    assert guard(propio, FACTS) is None


def test_no_puede_inventarse_una_medicion() -> None:
    intruso = {**BUENAS, "Qué se midió": "La aceleración alcanzó 0.42 g en el eje vertical."}
    razon = guard(intruso, FACTS) or ""
    assert "mediciones que no están" in razon and "0.42" in razon


def test_puede_citar_las_mediciones_que_SI_estan() -> None:
    citando = {**BUENAS, "Qué se midió": "El pico fue de 0.081 g y 3.2 cm/s; umbral 0.25 g."}
    assert guard(citando, FACTS) is None


def test_una_palabra_que_empieza_por_g_no_es_una_medicion() -> None:
    """`\\b` evita que "9 grados" se lea como "9 g" y dispare un falso positivo."""
    texto = {**BUENAS, "Qué pasó": "El sensor giró 9 grados durante 12 gestiones."}
    assert guard(texto, FACTS) is None


# ---- el camino remoto, simulado ---------------------------------------------


async def test_una_respuesta_valida_se_acepta_con_su_procedencia() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "algun/modelo"
        assert request.headers["Authorization"] == "Bearer sk-test"
        assert len(body["messages"]) == 2
        # Los hechos redactados viajan; el nombre del inmueble no.
        assert "Planta Cholula" not in request.content.decode()
        return httpx.Response(200, json=_respuesta(BUENAS))

    out = await _provider(handler).generate(NarrativeRequest(facts=FACTS, model="algun/modelo"))
    assert out.provider == "openrouter"
    assert out.degraded_reason is None
    assert [t for t, _ in out.sections] == list(SECTION_TITLES)
    assert out.prompt_tokens == 900
    assert out.cost_usd == 0.0042
    assert out.latency_ms is not None


async def test_un_timeout_degrada_al_determinista_con_su_razon() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("tardó demasiado", request=request)

    out = await _provider(handler).generate(NarrativeRequest(facts=FACTS, model="m"))
    assert out.provider == "deterministic"
    assert "no respondió" in (out.degraded_reason or "")
    assert len(out.sections) == 6


async def test_un_500_degrada_en_vez_de_tumbar_la_exportacion() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    out = await _provider(handler).generate(NarrativeRequest(facts=FACTS, model="m"))
    assert out.provider == "deterministic"
    assert out.degraded_reason


async def test_un_json_roto_degrada() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "esto no es JSON"}}]})

    out = await _provider(handler).generate(NarrativeRequest(facts=FACTS, model="m"))
    assert out.provider == "deterministic"
    assert "no se pudo interpretar" in (out.degraded_reason or "")


async def test_el_guardrail_descarta_la_respuesta_ENTERA_no_la_arregla() -> None:
    """Media respuesta "corregida" sería justo el dato a medias que la regla 7 prohíbe."""
    intruso = {**BUENAS, "Qué se midió": "El pico fue de 0.99 g."}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_respuesta(intruso))

    out = await _provider(handler).generate(NarrativeRequest(facts=FACTS, model="m"))
    assert out.provider == "deterministic"
    assert "guardrail" in (out.degraded_reason or "")
    assert dict(out.sections)["Qué se midió"] == BUENAS["Qué se midió"]


async def test_tolera_el_bloque_de_markdown_que_ponen_algunos_modelos() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        envuelto = "```json\n" + json.dumps({"sections": BUENAS}) + "\n```"
        return httpx.Response(200, json={"choices": [{"message": {"content": envuelto}}]})

    out = await _provider(handler).generate(NarrativeRequest(facts=FACTS, model="m"))
    assert out.provider == "openrouter"


async def test_no_reintenta() -> None:
    """8 s ya es mucho dentro de un request que genera evidencia."""
    llamadas: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        llamadas.append(1)
        return httpx.Response(503, text="no disponible")

    await _provider(handler).generate(NarrativeRequest(facts=FACTS, model="m"))
    assert len(llamadas) == 1
