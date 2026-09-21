"""T-7.26 · La promesa ABSOLUTA de `build_narrative`, con guarda.

`build_narrative` promete **«Nunca lanza»** en negrita, y la promesa no tenía guarda:
se probaba algún tramo suelto y nadie comprobaba el enunciado entero. Propagaba por dos
vías:

* `select_provider(s)` vivía **fuera de todo `try`** — y lee ajustes y sale a Secrets
  Manager, que es exactamente donde falla la nube el primer día.
* `_degradar` —por donde pasan **todas** las degradaciones— llamaba a
  `DeterministicProvider().generate(req)` sin cinturón. Si el respaldo fallaba, la
  excepción se llevaba por delante la exportación: el mismo modo de fallo que la ficha
  vino a cerrar, recreado un nivel más abajo.

Cuánto cinturón había, re-medido sobre el último commit (`git show
3a72ac1:api/src/takab_api/narrative/__init__.py`): **un solo `try`**, alrededor de
`chosen.generate` — o sea **uno de los seis tramos**. Por eso el censo dejó de ser un
número escrito en una frase y pasó a ser `narrative.TRAMOS`, **sobre el que se
parametriza este fichero**: dar de alta un tramo sin escribir su sabotaje deja la suite
en rojo.

⚠️ Aquí decía «el docstring decía *cuatro tramos pueden fallar y los cuatro están
cubiertos* y eran cuatro de seis». Esa frase **no está en ningún commit** (`git grep
"cuatro tramos" 3a72ac1` no devuelve nada) y el «cuatro» no lo respaldaba el dato. Se
va: un censo que nace citando una medición que no se puede repetir no se distingue de
uno inventado.

Y lo que se afirma en cada caso no es que la función devuelva algo, sino que **el
dictamen se exporta**: `render` hasta los bytes del PDF. Pararse en `build_narrative`
fue justamente lo que dejó pasar una guarda que no medía lo que su nombre decía.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest

from takab_api.dictamen.pdf import render
from takab_api.narrative import TRAMOS, Narrative, apply_narrative, build_narrative
from takab_api.narrative.base import (
    MOTIVO_CUOTA_ILEGIBLE,
    MOTIVO_ELECCION,
    MOTIVO_PROVEEDOR,
    MOTIVO_RESPALDO_CAIDO,
    MOTIVO_SIN_HECHOS,
    SUFIJO_DETERMINISTA,
)
from takab_api.settings import Settings
from tests.dictamen.test_pdf import model


def _revienta(*a, **k):  # noqa: ANN002, ANN003, ANN202, ARG001
    raise RuntimeError("sabotaje del tramo")


async def _revienta_async(*a, **k):  # noqa: ANN002, ANN003, ANN202, ARG001
    raise RuntimeError("sabotaje del tramo")


class _Explota:
    """Proveedor de red que revienta. No es el determinista a propósito: así pasa el
    filtro de `_sale_a_la_red` y ejerce también el camino cobrable."""

    name = "explota"

    async def generate(self, req):  # noqa: ANN001, ANN202, ARG002
        raise RuntimeError("sabotaje del tramo")


class _Redacta:
    """Proveedor remoto que SÍ redacta: es el único que llega al tramo del cobro."""

    name = "openrouter"

    async def generate(self, req):  # noqa: ANN001, ANN202
        from takab_api.narrative.deterministic import sections_for  # noqa: PLC0415

        return Narrative(sections=sections_for(req.facts), provider="openrouter", cost_usd=0.004)


# Un sabotaje por tramo de `TRAMOS`. Cada entrada devuelve el `build_narrative` ya
# armado; `motivo` es el fragmento que el papel tiene que llevar, o `None` cuando la
# degradación NO corresponde (el cobro falla DESPUÉS de que la prosa salió buena: la
# contabilidad rota no es una degradación de la narrativa, y marcarla mentiría).
_SABOTAJES: dict[str, tuple[Callable[[pytest.MonkeyPatch], Awaitable[Narrative]], str | None]] = {}


def _alta(tramo: str, motivo: str | None):  # noqa: ANN202
    def deco(fn):  # noqa: ANN001, ANN202
        _SABOTAJES[tramo] = (fn, motivo)
        return fn

    return deco


@_alta("elegir proveedor", MOTIVO_ELECCION)
async def _sabotea_eleccion(monkeypatch: pytest.MonkeyPatch) -> Narrative:
    monkeypatch.setattr("takab_api.narrative.select_provider", _revienta)
    return await build_narrative(model(), Settings())


@_alta("redactar los hechos", MOTIVO_SIN_HECHOS)
async def _sabotea_hechos(monkeypatch: pytest.MonkeyPatch) -> Narrative:  # noqa: ARG001
    # Un dato raro del incidente de verdad, no un parche: `redact.facts_from` recorre
    # `m.channels` y con `None` revienta con `TypeError`.
    return await build_narrative(model(channels=None), Settings())


@_alta("leer la cuota", MOTIVO_CUOTA_ILEGIBLE)
async def _sabotea_cuota(monkeypatch: pytest.MonkeyPatch) -> Narrative:
    monkeypatch.setattr("takab_api.narrative.leer_estado", _revienta_async)
    return await build_narrative(
        model(), Settings(), provider=_Explota(), conn=object(), tenant_id="t-1"
    )


@_alta("llamar al proveedor", MOTIVO_PROVEEDOR)
async def _sabotea_proveedor(monkeypatch: pytest.MonkeyPatch) -> Narrative:  # noqa: ARG001
    return await build_narrative(model(), Settings(), provider=_Explota())


@_alta("cobrar", None)
async def _sabotea_cobro(monkeypatch: pytest.MonkeyPatch) -> Narrative:
    from takab_api.narrative.quota import EstadoCuota  # noqa: PLC0415

    async def leer(*a, **k):  # noqa: ANN002, ANN003, ANN202, ARG001
        return EstadoCuota("2026-09", 0.0, 0, 5.0, exhausted=False)

    monkeypatch.setattr("takab_api.narrative.leer_estado", leer)
    monkeypatch.setattr("takab_api.narrative.acumular", _revienta_async)
    return await build_narrative(
        model(), Settings(), provider=_Redacta(), conn=object(), tenant_id="t-1"
    )


@_alta("el respaldo determinista", MOTIVO_RESPALDO_CAIDO)
async def _sabotea_respaldo(monkeypatch: pytest.MonkeyPatch) -> Narrative:
    # Por `_degradar` pasan TODAS las degradaciones: se entra por el proveedor caído y
    # se encuentra el respaldo caído también.
    monkeypatch.setattr("takab_api.narrative.deterministic.sections_for", _revienta)
    return await build_narrative(model(), Settings(), provider=_Explota())


def test_el_censo_de_sabotajes_SE_DERIVA_de_TRAMOS() -> None:
    """La guarda de la guarda. Un tramo nuevo en `TRAMOS` sin sabotaje aquí es un
    tramo cuya cobertura nadie midió, y es como se llegó a «cuatro de seis»."""
    assert set(_SABOTAJES) == set(TRAMOS), (
        f"tramos sin sabotaje: {set(TRAMOS) - set(_SABOTAJES)} · "
        f"sabotajes sin tramo: {set(_SABOTAJES) - set(TRAMOS)}"
    )


@pytest.mark.parametrize("tramo", TRAMOS)
async def test_build_narrative_NUNCA_lanza_y_el_dictamen_SE_EXPORTA(
    tramo: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Con cada tramo reventado: vuelve una `Narrative` y el PDF sale con sus bytes."""
    sabotaje, motivo = _SABOTAJES[tramo]
    out = await sabotaje(monkeypatch)
    assert isinstance(out, Narrative), f"el tramo «{tramo}» no devolvió narrativa"
    assert out.sections, f"el tramo «{tramo}» dejó el §16 vacío y mudo (regla de oro 7)"

    # La prueba de verdad: el papel.
    m = model(channels=None) if tramo == "redactar los hechos" else model()
    apply_narrative(m, out)
    pdf = render(m, "technical")
    assert pdf[:4] == b"%PDF" and len(pdf) > 10_000, f"el tramo «{tramo}» tumbó la exportación"

    if motivo is None:
        # El cobro roto NO es una degradación de la prosa: la prosa salió buena y del
        # proveedor remoto. Marcarla diría que el documento se redactó peor de lo que
        # se redactó, y el gasto sin registrar se grita en el log, no en el dictamen.
        assert out.degraded_reason is None, f"el tramo «{tramo}» marcó una prosa que sí salió"
        assert out.provider == "openrouter"
    else:
        assert motivo in (out.degraded_reason or ""), (
            f"el tramo «{tramo}» degradó sin decir por qué"
        )


@pytest.mark.parametrize("tramo", TRAMOS)
async def test_el_motivo_PROMETE_respaldo_solo_si_lo_hay(
    tramo: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El sufijo «; texto determinista» es una AFIRMACIÓN, y tiene que ser verdad.

    Es la misma doctrina que la ficha aplicó al motivo de «sin hechos»: prometer en el
    pie del §16 seis secciones deterministas donde solo hay una es el documento
    desmintiéndose tres líneas más abajo. Aquí se comprueba en los dos sentidos —lo
    tuvo una vuelta al revés— y sobre todos los tramos a la vez.
    """
    sabotaje, _ = _SABOTAJES[tramo]
    out = await sabotaje(monkeypatch)
    razon = out.degraded_reason or ""
    promete = SUFIJO_DETERMINISTA in razon
    hay = len(out.sections) == 6
    assert promete == (hay and bool(razon)), (
        f"el tramo «{tramo}» {'promete' if promete else 'no promete'} texto determinista "
        f"y salieron {len(out.sections)} secciones · motivo: {razon!r}"
    )
