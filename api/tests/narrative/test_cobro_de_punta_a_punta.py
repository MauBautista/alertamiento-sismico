"""T-7.26 · El criterio 3, de punta a punta: `usage.cost` → `ai_spend.spent_usd`.

**El agujero, medido:** `select_provider` construía `OpenRouterProvider(settings,
api_key=…)` **sin costura de transporte**, así que ninguna prueba podía ejercer
`build_narrative` → `select_provider` → proveedor remoto con `httpx.MockTransport`.
Todas las del camino feliz construían el proveedor a mano, y la cadena que el criterio
3 de la ficha pide —`usage.cost` → `Narrative.cost_usd` → `acumular` →
`ai_spend.spent_usd`— quedaba probada **por mitades y con dobles en los dos extremos**:
un test afirmaba `cost_usd == 0.0042` sobre un proveedor construido a mano, y otro
monkeypatcheaba `acumular` para mirarle el argumento. Nadie escribía nunca en
`ai_spend` un coste venido de un `usage` de OpenRouter.

Lo que no se puede ejercer, no está defendido. Con la costura puesta, aquí se recorre
el camino que el despliegue enciende de verdad y se mira la TABLA.

De paso cierra la otra mitad: `OpenRouterProvider._degraded` escribía
`provider="deterministic"` como literal mientras `_hubo_redaccion_cobrable` decidía SI
SE COBRA comparando contra `deterministic.NAME`. La decisión de dinero dependía de que
dos cadenas escritas en dos ficheros distintos siguieran coincidiendo; hoy es la misma
constante, y el control negativo de abajo lo mide donde importa: en la factura.
"""

from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.narrative import build_narrative
from takab_api.narrative.deterministic import NAME as DETERMINISTA
from takab_api.narrative.deterministic import sections_for
from takab_api.narrative.prompts import prompt_version
from takab_api.narrative.redact import facts_from
from takab_api.settings import Settings
from tests.dictamen.test_pdf import model
from tests.narrative.grabado import enrutar
from tests.narrative.test_redact import BASIS

#: El modelo tiene `verdict_basis` porque el guardrail compara las cifras de la prosa
#: contra las de los hechos: sin base, la respuesta canónica citaría mediciones que no
#: están y se descartaría entera — y este fichero mide el camino que SÍ cobra.
MODELO = dict(verdict_basis=BASIS)
FACTS = facts_from(model(**MODELO))
COSTE = 0.0042


@pytest.fixture(autouse=True)
async def _limpio(base_data):
    """`ai_spend` no entra en el `TRUNCATE` de `db_engine`; `audit_log` sí, y además es
    append-only: borrarlo desde aquí lo veta un trigger."""
    yield
    async with get_engine().begin() as conn:
        await conn.execute(text("DELETE FROM ai_spend"))


def _ajustes(**over) -> Settings:
    """La configuración que `deploy.sh` exporta en `dev`, con la clave inline."""
    base = {
        "openrouter_enabled": True,
        "openrouter_model": "anthropic/claude-sonnet-5",
        "openrouter_api_key": "sk-or-v1-de-prueba",
        "ai_monthly_cap_usd": 10.0,
    }
    return Settings(**{**base, **over})


def _redacta(request: httpx.Request) -> httpx.Response:
    """Respuesta válida de OpenRouter, con su bloque `usage` — que es de donde sale el
    dinero. El cuerpo se comprueba aquí: si `select_provider` dejara de pasar la clave
    o el slug, esto se pone rojo antes que la tabla."""
    cuerpo = json.loads(request.content)
    assert cuerpo["model"] == "anthropic/claude-sonnet-5"
    assert request.headers["Authorization"] == "Bearer sk-or-v1-de-prueba"
    prosa = json.dumps({"sections": dict(sections_for(FACTS))})
    return httpx.Response(
        200,
        json={
            "model": "anthropic/claude-sonnet-5",
            "choices": [{"message": {"content": prosa}}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 300, "cost": COSTE},
        },
    )


def _cae(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
    return httpx.Response(500, text="boom")


async def _fila() -> dict | None:
    async with get_engine().begin() as conn:
        fila = (
            (
                await conn.execute(
                    text(
                        "SELECT spent_usd, calls FROM ai_spend "
                        "WHERE tenant_id = CAST(:t AS uuid) ORDER BY period DESC LIMIT 1"
                    ),
                    {"t": au.DB_TENANT_PRIV},
                )
            )
            .mappings()
            .first()
        )
    return dict(fila) if fila else None


async def test_el_coste_del_usage_LLEGA_a_ai_spend_por_el_camino_real() -> None:
    """Criterio 3, recorrido entero: nadie construye el proveedor a mano aquí."""
    async with get_engine().begin() as conn:
        out = await build_narrative(
            model(**MODELO),
            _ajustes(),
            conn=conn,
            tenant_id=au.DB_TENANT_PRIV,
            actor="user:u-1",
            transport=httpx.MockTransport(enrutar(_redacta)),
        )

    assert out.provider == "openrouter", "el camino real no llegó al proveedor remoto"
    assert out.degraded_reason is None
    assert out.cost_usd == pytest.approx(COSTE)
    # Y la procedencia que la ficha pide por su nombre, producida por este mismo camino.
    assert out.prompt_version == prompt_version()
    assert out.output_sha256 and len(out.output_sha256) == 64

    fila = await _fila()
    assert fila is not None, "se redactó con IA y no se cobró nada"
    assert float(fila["spent_usd"]) == pytest.approx(COSTE)
    assert fila["calls"] == 1


async def test_una_llamada_que_el_PROVEEDOR_degrado_no_deja_factura() -> None:
    """El control negativo, sobre el `OpenRouterProvider` de verdad.

    Es el que ejerce `_degraded`: si su `provider` dejara de ser `deterministic.NAME`,
    `_hubo_redaccion_cobrable` contaría como redacción una llamada que devolvió prosa
    determinista, y `ai_spend.calls` acabaría diciendo «la IA redactó 40 veces» de un
    mes en el que el proveedor estuvo caído.
    """
    async with get_engine().begin() as conn:
        out = await build_narrative(
            model(**MODELO),
            _ajustes(),
            conn=conn,
            tenant_id=au.DB_TENANT_PRIV,
            actor="user:u-1",
            transport=httpx.MockTransport(enrutar(_cae)),
        )

    # La factura PRIMERO: es el daño, y el nombre del proveedor solo es el mecanismo.
    assert await _fila() is None, "se facturó una llamada que no redactó nada"
    assert out.provider == DETERMINISTA
    assert out.degraded_reason, "un fallback no puede ser `ok`"


async def test_con_el_TOPE_agotado_no_se_abre_el_socket_ni_por_el_camino_real() -> None:
    """La cuota corta ANTES del proveedor, también cuando el proveedor es el de verdad."""

    def nadie(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        raise AssertionError("con la cuota agotada no se sale a la red")

    async with get_engine().begin() as conn:
        out = await build_narrative(
            model(**MODELO),
            _ajustes(ai_monthly_cap_usd=0.0),
            conn=conn,
            tenant_id=au.DB_TENANT_PRIV,
            actor="user:u-1",
            transport=httpx.MockTransport(nadie),
        )
    assert out.provider == DETERMINISTA
    assert len(out.sections) == 6
