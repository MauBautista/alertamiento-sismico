"""[T-2.144] Ningún `kind` de la TABLA se pinta «SIN CLASIFICAR» en la consola.

El censo de `web/src/test-utils/incidentActionKinds.ts` es estático: resuelve la
expresión de cada `INSERT` y **se pone rojo con lo que no entiende**, que es su
virtud. Pero no ve un kind calculado en ejecución
(`_ACTION_KIND.get(new_state, new_state)`) ni un productor que viva fuera del
repositorio.

Éste sí, y por una **propiedad del esquema**, no por suerte: `incident_actions`
es append-only y **exenta de poda por retención** (regla de oro 11), así que
`SELECT DISTINCT kind` es la lista completa de todo lo que se ha escrito nunca.
El productor número nueve se caza la **primera vez que dispara** —en esta suite,
en la base de desarrollo o en el simulacro de restauración— en vez de estrenarse
en la pantalla de un SOC pintado de verde.

Por qué esto y no un `action_kinds.py` con todas las constantes: eso sería más
cómodo, pero su completitud descansaría en **una convención** —que nadie escriba
un literal suelto— y una convención no es una garantía. Aquí la garantía es que
la fila existe.

El registro se LEE de `bms.ts` en tiempo de test: es el espejo exacto de lo que
`bmsChannels.test.ts` ya hace al revés (leer `ACK_KIND` de `handlers.py`), y no
añade dependencia de build de `api/` sobre `web/`.

VALOR MÁXIMO CONTRA LA BASE DE PRODUCCIÓN. El simulacro de restauración ya monta
una: ahí es donde aparecen los kinds que ninguna suite genera.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import text

from takab_api.db.engine import get_engine

pytestmark = pytest.mark.asyncio

_BMS = Path(__file__).resolve().parents[3] / "shared" / "sdk-ts" / "src" / "bms.ts"


def _bloque(fuente: str, marca: str) -> str:
    try:
        return fuente.split(marca)[1].split("\n};")[0]
    except IndexError:  # pragma: no cover - el contrato se movió
        pytest.fail(f"{marca!r} no está en bms.ts: esto no está verde, está ciego")


def _kinds_con_rotulo() -> set[str]:
    fuente = _BMS.read_text(encoding="utf-8")
    kinds = set(
        re.findall(r"^  (\w+): \{", _bloque(fuente, "export const INCIDENT_ACTION_KINDS"), re.M)
    )
    # Los de actuador viven en la otra familia y se declaran como `siren_on: true`.
    kinds |= set(
        re.findall(r"\b(\w+): (?:true|false),", _bloque(fuente, "export const ACTUATOR_CHANNELS"))
    )
    assert len(kinds) >= 20, "el registro de bms.ts se movió; sin él este test no mide nada"
    return kinds


def huerfanos_de(kinds_escritos: set[str]) -> list[str]:
    """Los kinds escritos que ninguna familia de `bms.ts` sabe rotular."""
    return sorted(kinds_escritos - _kinds_con_rotulo())


def test_el_detector_CAZA_un_kind_sin_rotulo() -> None:
    """Que el mecanismo funcione se prueba aquí, no en la corrida contra la base.

    Esto existe porque la comprobación de abajo **puede no medir nada**: si en
    ese instante `incident_actions` está vacía, `set() - registro` es `set()` y
    pasa en verde sin haber mirado nada. Ese es exactamente el defecto que cierra
    `T-2.144` —un verde que no significa «bien» sino «no sé»—, y sería ridículo
    reintroducirlo en su propio test.

    Así que el mecanismo se acredita con datos fabricados, y la corrida contra la
    base **declara en voz alta** cuando no tuvo nada que mirar.
    """
    assert huerfanos_de({"kind_del_futuro"}) == ["kind_del_futuro"]
    # Y no acusa a los que sí están, uno de cada familia.
    assert huerfanos_de({"ack", "close", "siren_on", "damage_people_at_risk"}) == []


async def test_ningun_kind_escrito_se_pinta_sin_clasificar() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        filas = (await conn.execute(text("SELECT DISTINCT kind FROM incident_actions"))).all()
    escritos = {f[0] for f in filas}

    if not escritos:
        # NO se pasa en silencio. Un SKIP no es un PASS —lección de la Fase 2.6—
        # y aquí la diferencia es literal: sin filas, esta comprobación no ha
        # mirado nada. Su sitio natural es la base de desarrollo o el simulacro
        # de restauración, donde sí hay histórico.
        pytest.skip(
            "`incident_actions` está vacía: esta comprobación NO ha medido nada. "
            "Córrela contra una base con histórico (dev, o el simulacro de restore)."
        )

    huerfanos = huerfanos_de(escritos)
    assert huerfanos == [], (
        "kinds presentes en `incident_actions` que la consola pinta «SIN CLASIFICAR» y la "
        f"bitácora en bruto: {huerfanos}. Añádelos a `INCIDENT_ACTION_KINDS` en `bms.ts` con "
        "su rótulo y su severidad — el fallback avisa, pero no explica."
    )
