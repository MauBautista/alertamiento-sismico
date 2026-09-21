"""T-7.26 · `cap_usd = 0` significa CERO, y «sin tope» hay que pedirlo aparte.

**El defecto, medido:** `leer_estado` trataba `cap_usd <= 0` como *sin tope*. Es la
lectura conservadora del ajuste ausente… y convierte el error de dedo más probable de
todos en el peor resultado posible: quien pone el tope a cero creyendo que apaga el
gasto lo deja **ilimitado**. Un despliegue con `TAKAB_API_AI_MONTHLY_CAP_USD=0` no
apagaba la IA, la desataba.

**La decisión, y su razón:** de los dos modos de equivocarse, uno deja el sistema SIN
IA —el dictamen sale igual, con prosa determinista declarada— y el otro deja la tarjeta
abierta. El defecto tiene que caer del primer lado. Así que **cero es cero**, y el modo
«sin tope» es EXPLÍCITO y distinto: un tope negativo, que nadie teclea por accidente.

Esto contradice a propósito lo que decía `narrative/quota.py` y `settings.py` hasta hoy.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.narrative import build_narrative, quota
from takab_api.settings import Settings
from tests.dictamen.test_pdf import model


@pytest.fixture(autouse=True)
async def _limpio(base_data):
    """Solo `ai_spend`, que es la única tabla de aquí que el teardown común no toca.

    ⚠️ Aquí había también un `DELETE FROM audit_log WHERE verb LIKE 'ai_quota%'`, y
    `audit_log` es **append-only por trigger**: `tabla append-only: audit_log no permite
    DELETE`. Sobrevivía por casualidad —ningún test de este fichero pasaba `actor=`, así
    que el `DELETE` casaba cero filas y el trigger no disparaba—, y era una mina con
    nombre y apellido: **la primera guarda que midiera la auditoría del corte hacía
    estallar el fichero entero en teardown**. Esa guarda es la de abajo, y es justo la
    que faltaba. Quien limpia `audit_log` es el `TRUNCATE` de `db_engine`
    (`tests/api/conftest.py`), que sí puede.
    """
    yield
    async with get_engine().begin() as conn:
        await conn.execute(text("DELETE FROM ai_spend"))


async def test_cap_CERO_es_tope_CERO_y_la_llamada_NO_sale() -> None:
    """Sin un peso gastado y con el tope en cero, la IA no sale a la red."""
    async with get_engine().begin() as conn:
        est = await quota.leer_estado(conn, au.DB_TENANT_PRIV, cap_usd=0.0)
    assert est.exhausted is True
    assert est.spent_usd == 0.0, "no hizo falta gastar nada para estar cortado"


async def test_SIN_TOPE_se_pide_explicitamente_con_un_negativo() -> None:
    """El modo ilimitado sigue existiendo —hay clientes que lo querrán— pero deja de
    ser el que sale de un dedo torcido."""
    async with get_engine().begin() as conn:
        await quota.acumular(
            conn, au.DB_TENANT_PRIV, cost_usd=999.0, cap_usd=quota.SIN_TOPE, warn_at=0.8
        )
        est = await quota.leer_estado(conn, au.DB_TENANT_PRIV, cap_usd=quota.SIN_TOPE)
    assert est.exhausted is False
    assert quota.SIN_TOPE < 0, "sin tope es un valor que hay que escribir a conciencia"


async def test_el_tope_en_cero_lo_DECLARA_el_papel_y_no_dice_agotada() -> None:
    """Decir «cuota agotada» de un mes en el que no se gastó un centavo sería falso:
    no se agotó, es que no había. Son dos hechos distintos y llevan dos frases."""
    async with get_engine().begin() as conn:
        est = await quota.leer_estado(conn, au.DB_TENANT_PRIV, cap_usd=0.0)
    assert est.motivo == quota.MOTIVO_TOPE_CERO
    assert est.motivo != quota.MOTIVO_AGOTADA


async def test_un_tope_normal_agotado_sigue_diciendo_AGOTADA() -> None:
    async with get_engine().begin() as conn:
        await quota.acumular(conn, au.DB_TENANT_PRIV, cost_usd=9.0, cap_usd=5.0, warn_at=0.8)
        est = await quota.leer_estado(conn, au.DB_TENANT_PRIV, cap_usd=5.0)
    assert est.exhausted is True
    assert est.motivo == quota.MOTIVO_AGOTADA


async def _filas_de_corte() -> list[dict]:
    async with get_engine().begin() as conn:
        filas = (
            await conn.execute(
                text("SELECT meta FROM audit_log WHERE verb = :v ORDER BY ts"),
                {"v": quota.VERB_BLOCKED},
            )
        ).fetchall()
    return [f[0] for f in filas]


async def test_el_corte_por_tope_CERO_DEJA_CONSTANCIA_en_la_bitacora() -> None:
    """Un corte que no deja rastro es un corte que nadie puede explicar después.

    **El defecto, medido:** la marca de transición era un `UPDATE` sobre `ai_spend` y
    con el tope en cero no se gastó un centavo, así que no había fila que actualizar:
    casaba cero filas, `just_blocked` salía `False` y `_auditar` no llegaba a correr.
    O sea que un despliegue con `TAKAB_API_AI_MONTHLY_CAP_USD=0` —el error de dedo
    contra el que esta misma ficha protege— apagaba la IA en TODOS los dictámenes sin
    una línea en la bitácora. El contraste que lo destapó: con tope 5 y 9 gastados la
    fila salía; con tope 0 y nada gastado, cero filas.

    Y `audit_log` no se poda nunca (regla de oro 11), así que esta fila es la única que
    contesta meses después por qué un mes entero de dictámenes salió sin IA.
    """
    async with get_engine().begin() as conn:
        est = await quota.leer_estado(conn, au.DB_TENANT_PRIV, cap_usd=0.0, actor="user:u-1")
    assert est.exhausted is True
    assert est.just_blocked is True, "el corte tiene que reconocerse como transición"

    filas = await _filas_de_corte()
    assert len(filas) == 1, f"el corte por tope cero no dejó constancia: {len(filas)} filas"
    meta = filas[0]
    assert meta["cap_usd"] == 0.0 and meta["spent_usd"] == 0.0, (
        "y la fila dice la verdad exacta: no se agotó nada, es que no había"
    )
    assert meta["calls"] == 0


async def test_la_constancia_del_tope_CERO_es_UNA_por_periodo() -> None:
    """La decisión 2 del módulo (regla de oro 10) vale también para el camino nuevo:
    una fila por transición, no una por dictamen exportado."""
    async with get_engine().begin() as conn:
        for _ in range(4):
            await quota.leer_estado(conn, au.DB_TENANT_PRIV, cap_usd=0.0, actor="user:u-1")
    assert len(await _filas_de_corte()) == 1


async def test_un_tope_NORMAL_agotado_sigue_dejando_su_fila() -> None:
    """El control positivo: sin él, «no auditar nunca» pasaría igual que antes."""
    async with get_engine().begin() as conn:
        await quota.acumular(conn, au.DB_TENANT_PRIV, cost_usd=9.0, cap_usd=5.0, warn_at=0.8)
        await quota.leer_estado(conn, au.DB_TENANT_PRIV, cap_usd=5.0, actor="user:u-1")
    filas = await _filas_de_corte()
    assert len(filas) == 1
    assert filas[0]["cap_usd"] == 5.0 and filas[0]["spent_usd"] == 9.0


class _Redacta:
    """Proveedor de red que SÍ funciona: lo que se mide es que no llega a correr."""

    name = "openrouter"

    def __init__(self) -> None:
        self.llamadas = 0

    async def generate(self, req):  # noqa: ANN001, ANN202, ARG002
        self.llamadas += 1
        raise AssertionError("con el tope en cero no se sale a la red")


async def test_con_el_tope_en_CERO_la_exportacion_sale_con_prosa_determinista() -> None:
    """El tope no puede convertirse en una negación de evidencia (T-5.18), ni siquiera
    en cero: el PDF sale, con texto determinista y diciéndolo."""
    async with get_engine().begin() as conn:
        out = await build_narrative(
            model(),
            Settings(ai_monthly_cap_usd=0.0),
            provider=_Redacta(),
            conn=conn,
            tenant_id=au.DB_TENANT_PRIV,
        )
    assert out.provider == "deterministic"
    assert out.degraded_reason == quota.MOTIVO_TOPE_CERO
    assert len(out.sections) == 6
