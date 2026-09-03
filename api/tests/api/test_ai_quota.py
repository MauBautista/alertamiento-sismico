"""El tope de gasto de la IA (T-5.18).

Lo que fija, y en este orden:

* **Agotada la cuota, la exportación SALE IGUAL** con texto determinista, y lo
  declara. El PDF del dictamen es una superficie de vida: alguien lo usa para
  decidir si un edificio se ocupa. Un 429 ahí convertiría un tope de gasto en una
  negación de evidencia.
* **El corte y el aviso dejan UNA fila por periodo, no una por petición** (regla
  de oro 10). Se comprueba llamando muchas veces y contando filas.
* **El tope se puede rebasar por UNA llamada, y está declarado**: el coste solo
  se conoce después de llamar. Reservar un estimado antes habría sido cobrar por
  lo que no se sabe.
* **Con la perilla apagada nada de esto cambia el comportamiento actual.**
"""

# ruff: noqa: F811
from __future__ import annotations

import dataclasses
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.narrative import quota

AHORA = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


async def _sql(sql: str, **p):
    engine = get_engine()
    async with engine.begin() as conn:
        r = await conn.execute(text(sql), p)
        return r.fetchall() if r.returns_rows else []


@pytest.fixture(autouse=True)
async def _limpio():
    yield
    await _sql("DELETE FROM ai_spend")
    await _sql("DELETE FROM audit_log WHERE verb LIKE 'ai_quota%'")


async def _conn():
    return get_engine().begin()


def test_el_periodo_es_el_MES_en_UTC():
    assert quota.periodo_de(AHORA) == "2026-09"
    # Un instante que en México es del mes anterior sigue siendo del periodo UTC.
    assert quota.periodo_de(datetime(2026, 10, 1, 2, 0, tzinfo=UTC)) == "2026-10"


async def test_sin_gasto_previo_la_llamada_SALE(base_data):
    async with get_engine().begin() as conn:
        est = await quota.leer_estado(conn, au.DB_TENANT_PRIV, cap_usd=5.0, now=AHORA)
    assert est.exhausted is False and est.spent_usd == 0.0


async def test_cap_CERO_significa_sin_tope_no_tope_cero(base_data):
    """La lectura conservadora del ajuste ausente. Cortar del todo es apagar la perilla."""
    async with get_engine().begin() as conn:
        await quota.acumular(
            conn, au.DB_TENANT_PRIV, cost_usd=999.0, cap_usd=0.0, warn_at=0.8, now=AHORA
        )
        est = await quota.leer_estado(conn, au.DB_TENANT_PRIV, cap_usd=0.0, now=AHORA)
    assert est.exhausted is False


async def test_alcanzado_el_tope_la_llamada_NO_sale(base_data):
    async with get_engine().begin() as conn:
        await quota.acumular(
            conn, au.DB_TENANT_PRIV, cost_usd=5.0, cap_usd=5.0, warn_at=0.8, now=AHORA
        )
        est = await quota.leer_estado(conn, au.DB_TENANT_PRIV, cap_usd=5.0, now=AHORA)
    assert est.exhausted is True and est.just_blocked is True


async def test_el_corte_se_declara_UNA_vez_por_periodo(base_data):
    """`just_blocked` solo en la primera. Es lo que evita una fila por petición."""
    async with get_engine().begin() as conn:
        await quota.acumular(
            conn, au.DB_TENANT_PRIV, cost_usd=9.0, cap_usd=5.0, warn_at=0.8, now=AHORA
        )
        primera = await quota.leer_estado(conn, au.DB_TENANT_PRIV, cap_usd=5.0, now=AHORA)
        siguientes = [
            await quota.leer_estado(conn, au.DB_TENANT_PRIV, cap_usd=5.0, now=AHORA)
            for _ in range(5)
        ]
    assert primera.just_blocked is True
    assert [e.just_blocked for e in siguientes] == [False] * 5
    assert all(e.exhausted for e in siguientes), "dejar de avisar no es dejar de cortar"


async def test_el_aviso_tambien_es_UNA_vez_por_periodo(base_data):
    async with get_engine().begin() as conn:
        avisos = []
        for _ in range(6):
            _, avisar = await quota.acumular(
                conn, au.DB_TENANT_PRIV, cost_usd=1.0, cap_usd=5.0, warn_at=0.8, now=AHORA
            )
            avisos.append(avisar)
    # 1,2,3 por debajo de 4.0; el cuarto cruza el 80 % y avisa; los demás, no.
    assert avisos == [False, False, False, True, False, False]


async def test_el_periodo_siguiente_ARRANCA_LIMPIO(base_data):
    async with get_engine().begin() as conn:
        await quota.acumular(
            conn, au.DB_TENANT_PRIV, cost_usd=9.0, cap_usd=5.0, warn_at=0.8, now=AHORA
        )
        octubre = datetime(2026, 10, 1, 0, 0, tzinfo=UTC)
        est = await quota.leer_estado(conn, au.DB_TENANT_PRIV, cap_usd=5.0, now=octubre)
    assert est.exhausted is False and est.spent_usd == 0.0


async def test_una_llamada_SIN_coste_reportado_cuenta_igual(base_data):
    """El proveedor puede no devolver el coste; el contador de llamadas no miente."""
    async with get_engine().begin() as conn:
        await quota.acumular(
            conn, au.DB_TENANT_PRIV, cost_usd=None, cap_usd=5.0, warn_at=0.8, now=AHORA
        )
        est = await quota.leer_estado(conn, au.DB_TENANT_PRIV, cap_usd=5.0, now=AHORA)
    assert est.calls == 1 and est.spent_usd == 0.0


async def test_el_gasto_de_un_tenant_NO_lo_ve_el_otro(base_data):
    """Aislamiento: la cuota es por cliente, y el vecino no la agota."""
    async with get_engine().begin() as conn:
        await quota.acumular(
            conn, au.DB_TENANT_PRIV, cost_usd=9.0, cap_usd=5.0, warn_at=0.8, now=AHORA
        )
        otro = await quota.leer_estado(conn, au.DB_TENANT_PRIV2, cap_usd=5.0, now=AHORA)
    assert otro.exhausted is False and otro.spent_usd == 0.0


async def test_el_tope_se_rebasa_por_UNA_llamada_como_mucho(base_data):
    """Declarado a propósito: el coste solo se sabe DESPUÉS de llamar.

    Reservar un estimado antes habría sido cobrar por lo que no se sabe. Lo que
    esto fija es que el desbordamiento se detiene en la siguiente lectura.
    """
    async with get_engine().begin() as conn:
        est = await quota.leer_estado(conn, au.DB_TENANT_PRIV, cap_usd=5.0, now=AHORA)
        assert est.exhausted is False, "con el contador a cero la llamada sale"
        await quota.acumular(
            conn, au.DB_TENANT_PRIV, cost_usd=50.0, cap_usd=5.0, warn_at=0.8, now=AHORA
        )
        despues = await quota.leer_estado(conn, au.DB_TENANT_PRIV, cap_usd=5.0, now=AHORA)
    assert despues.exhausted is True
    assert despues.spent_usd == 50.0, "el gasto real queda escrito, no recortado al tope"


# ── el CRUCE deja UNA fila de auditoría, y la deja quien lo sella ──────────
#
# La primera versión auditaba desde el router releyendo el estado, y no escribía
# NUNCA: `leer_estado` consume la transición al sellar `blocked_at`, así que la
# segunda lectura ya la veía consumida. Lo cazó escribir este test.


async def _filas(verb: str) -> list:
    return await _sql("SELECT meta FROM audit_log WHERE verb = :v ORDER BY ts", v=verb)


async def test_el_corte_deja_UNA_fila_de_auditoria_no_una_por_peticion(base_data):
    async with get_engine().begin() as conn:
        await quota.acumular(
            conn, au.DB_TENANT_PRIV, cost_usd=9.0, cap_usd=5.0, warn_at=0.8, now=AHORA
        )
        for _ in range(4):
            await quota.leer_estado(
                conn, au.DB_TENANT_PRIV, cap_usd=5.0, now=AHORA, actor="user:u-1"
            )

    filas = await _filas(quota.VERB_BLOCKED)
    assert len(filas) == 1, f"una fila por petición en vez de una por periodo: {len(filas)}"
    assert filas[0][0]["cap_usd"] == 5.0 and filas[0][0]["spent_usd"] == 9.0


async def test_el_aviso_deja_UNA_fila_de_auditoria(base_data):
    async with get_engine().begin() as conn:
        for _ in range(6):
            await quota.acumular(
                conn,
                au.DB_TENANT_PRIV,
                cost_usd=1.0,
                cap_usd=5.0,
                warn_at=0.8,
                now=AHORA,
                actor="user:u-1",
            )
    assert len(await _filas(quota.VERB_WARNED)) == 1


async def test_sin_actor_la_transicion_se_SELLA_igual(base_data):
    """No auditar no puede significar auditar dos veces más tarde."""
    async with get_engine().begin() as conn:
        await quota.acumular(
            conn, au.DB_TENANT_PRIV, cost_usd=9.0, cap_usd=5.0, warn_at=0.8, now=AHORA
        )
        sin_actor = await quota.leer_estado(conn, au.DB_TENANT_PRIV, cap_usd=5.0, now=AHORA)
        con_actor = await quota.leer_estado(
            conn, au.DB_TENANT_PRIV, cap_usd=5.0, now=AHORA, actor="user:u-1"
        )
    assert sin_actor.just_blocked is True
    assert con_actor.just_blocked is False, "la transición se volvió a ofrecer"
    assert await _filas(quota.VERB_BLOCKED) == []


# ── con la perilla APAGADA nada de esto cambia el comportamiento ───────────


async def test_con_la_IA_apagada_no_se_cobra_ni_una_llamada(base_data):
    """El criterio que protege el estado actual: hoy la perilla está apagada.

    `build_narrative` sin proveedor de red no toca la cuota, ni siquiera con
    conexión y tenant: cobrarle al determinista llenaría el contador de ceros y
    el `calls` de mentiras sobre cuántas veces se salió a la red.
    """
    from takab_api.dictamen.model import ReportModel
    from takab_api.narrative import build_narrative
    from takab_api.settings import Settings

    # El modelo se rellena por INTROSPECCIÓN y no a mano: son 28 campos
    # obligatorios y ninguno importa aquí — lo que se prueba es que la cuota no
    # se toca. Teclearlos habría sido una segunda copia del dictamen que se
    # quedaría vieja al primer campo nuevo.
    campos = {
        f.name: None
        for f in dataclasses.fields(ReportModel)
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
    }
    modelo = ReportModel(
        **{
            **campos,
            "folio": "TKB-X",
            "incident_id": str(uuid.uuid4()),
            # Los dos que `redact.facts_from` sí lee: son fechas y las formatea.
            "opened_at": AHORA,
            "generated_at": AHORA,
        }
    )
    ajustes = Settings(openrouter_enabled=False, ai_monthly_cap_usd=5.0)

    async with get_engine().begin() as conn:
        n = await build_narrative(
            modelo, ajustes, conn=conn, tenant_id=au.DB_TENANT_PRIV, actor="user:u-1"
        )
        estado = await quota.leer_estado(conn, au.DB_TENANT_PRIV, cap_usd=5.0)

    assert n.provider == "deterministic"
    assert n.degraded_reason is None, "apagar la perilla NO es una degradación"
    assert estado.calls == 0 and estado.spent_usd == 0.0
    assert await _filas(quota.VERB_BLOCKED) == [] and await _filas(quota.VERB_WARNED) == []
