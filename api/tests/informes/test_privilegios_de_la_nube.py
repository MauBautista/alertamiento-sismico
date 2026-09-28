"""[T-9.42] Lo que el worker `informes` LEE tiene su GRANT a `takab_ingest` escrito.

Medido el 2026-09-28 corriendo el worker contra una base migrada paso a paso (la
local de `soc-local`, que se parece a la nube): «permission denied for table
compliance_labels», y el informe quedó `fallido`. La suite estaba verde porque en
una base NUEVA la `0001` concede `SELECT … ON ALL TABLES` a `takab_ingest` DESPUÉS de
aplicar `db/schema.sql`: en CI el rol lo puede leer todo, y ningún test de
privilegios puede ver lo que la nube no tiene.

Aquí no se enumera nada a mano. Se corre el generador DE VERDAD, se capturan las
sentencias que ejecuta y se sacan de ellas las tablas que lee. La regla es la que
cumple una base que nació antes de que existieran esas tablas: **toda tabla que
nació en una migración posterior a la 0001 necesita un GRANT a `takab_ingest` en
alguna migración**. Es conservadora a propósito: en una base cuya `0001` ya traía la
tabla, el GRANT sobra y no estorba; al revés, falta y el informe no sale.

⚠️ Un `CREATE OR REPLACE VIEW` no cuenta como nacimiento (conserva los GRANT de la
vista que reemplaza); una vista que NACIERA así en una migración tardía escaparía.

⚠️ Cubre lo que el escenario ejerce. Una rama del builder que sólo corre con datos
que este escenario no siembra (cámaras, fotos) no deja sentencia, y su tabla no se
mira aquí.
"""

# ruff: noqa: F811  (fixtures de pytest importadas por nombre)
from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import event

from takab_api.db import pool
from takab_api.informes import pasada as P
from tests.informes.test_generador_real import _con_bucket, bucket  # noqa: F401
from tests.informes.test_pasada import BASE, Escena, escena  # noqa: F401

MIGRACIONES = Path(__file__).resolve().parents[2] / "migrations" / "versions"

#: Un NACIMIENTO: `CREATE TABLE`/`CREATE VIEW` sin `OR REPLACE`. Reemplazar una vista
#: conserva sus GRANT (la 0017 reescribe `waveform_features_1s_secure`, que ya existía),
#: así que un `CREATE OR REPLACE` no dice cuándo nació el objeto.
_CREA = re.compile(
    r"CREATE\s+(?:TABLE|VIEW|MATERIALIZED\s+VIEW)\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?([a-z_][a-z0-9_]*)",
    re.IGNORECASE,
)
_CONCEDE = re.compile(
    r"GRANT\s+([A-Z ,]+?)\s+ON\s+(?:TABLE\s+)?([a-z0-9_,\s]+?)\s+TO\s+([^;]+);",
    re.IGNORECASE,
)
_LEE = re.compile(r"\b(?:FROM|JOIN)\s+(?:public\.)?([a-z_][a-z0-9_]*)", re.IGNORECASE)


def _posteriores_a_la_0001() -> list[str]:
    return [
        p.read_text()
        for p in sorted(MIGRACIONES.glob("*.py"))
        if re.match(r"\d{4}_", p.name) and not p.name.startswith("0001_")
    ]


def _nacidas_despues_de_la_0001() -> set[str]:
    return {m.lower() for texto in _posteriores_a_la_0001() for m in _CREA.findall(texto)}


def _concedidas_a_ingest() -> set[str]:
    tablas: set[str] = set()
    for texto in _posteriores_a_la_0001():
        for privilegios, objetos, roles in _CONCEDE.findall(texto):
            if "takab_ingest" not in roles:
                continue
            if not re.search(r"\b(SELECT|ALL)\b", privilegios, re.IGNORECASE):
                continue
            tablas |= {o.strip().lower() for o in objetos.split(",") if o.strip()}
    return tablas


def test_el_censo_no_esta_ciego() -> None:
    """Si las expresiones dejaran de casar, la regla pasaría en vacío."""
    assert "post_event_reports" in _nacidas_despues_de_la_0001()
    assert "post_event_reports" in _concedidas_a_ingest()


def test_lo_que_lee_el_informe_tiene_su_GRANT_escrito(
    escena: Escena, bucket, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentencias: list[str] = []
    crear = P.create_async_engine

    def _motor_que_escucha(*a, **k):  # noqa: ANN002, ANN003
        motor = crear(*a, **k)
        event.listen(
            motor.sync_engine,
            "before_cursor_execute",
            lambda _c, _cur, sql, *_r: sentencias.append(sql),
        )
        return motor

    monkeypatch.setattr(P, "create_async_engine", _motor_que_escucha)
    inc = escena.incidente()
    escena.firma(inc, cuando=BASE + timedelta(minutes=2))
    r = P.run_informes_pass(
        lambda: pool.connect(_con_bucket().database_url),
        _con_bucket(),
        now=BASE + timedelta(minutes=5),
    )
    assert r.generados == (inc,), r
    assert sentencias, "el generador no ejecutó nada: la captura está ciega"

    leidas = {m.lower() for sql in sentencias for m in _LEE.findall(sql)}
    faltan = sorted((leidas & _nacidas_despues_de_la_0001()) - _concedidas_a_ingest())
    assert not faltan, (
        "el worker `informes` lee tablas que nacieron después de la 0001 sin un GRANT a "
        f"takab_ingest en ninguna migración (en la nube: permission denied): {faltan}"
    )
