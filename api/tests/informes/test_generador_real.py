"""[T-9.42 · D-48] La pasada con el `generar_informe` DE VERDAD y un S3 falso.

`test_pasada.py` inyecta un generador de mentira; éste corre el builder, la prosa
determinista, el render de fpdf2, la evidencia y la bitácora reales, con el rol del
worker (`SET LOCAL ROLE takab_ingest`). Lo que fija:

* el PDF llega al «bucket» y su sha256 es el de la evidencia;
* `export_pdf` queda firmado por `system:informes`, con `origen='informe_automatico'`
  y el `site_id` que el freno del edificio cuenta;
* `preliminar` sale de la CABEZA de la cadena: sin firma, `True`; firmada, `False`,
  y `dictamen_vigente` es esa cabeza.
"""

# ruff: noqa: F811  (fixtures de pytest importadas por nombre)
from __future__ import annotations

import hashlib
from datetime import timedelta

import pytest

from takab_api.db import pool
from takab_api.informes import pasada as P
from takab_api.routers import reports as reports_mod
from tests.informes.test_pasada import BASE, Escena, _settings, escena  # noqa: F401


@pytest.fixture
def bucket(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    """Un S3 en un dict: `put_object` guarda, `get_object` no encuentra nada."""
    guardado: dict[str, bytes] = {}

    def _put(settings, key, body, *, content_type=None):  # noqa: ANN001, ARG001
        guardado[key] = body

    def _get(settings, key):  # noqa: ANN001, ARG001
        raise FileNotFoundError(key)

    monkeypatch.setattr(reports_mod, "put_object", _put)
    monkeypatch.setattr(reports_mod, "get_object", _get)
    return guardado


def _con_bucket():
    return _settings(evidence_bucket="bucket-de-prueba")


def test_el_informe_real_deja_PDF_evidencia_y_bitacora(escena: Escena, bucket) -> None:
    inc = escena.incidente()
    r = P.run_informes_pass(
        lambda: pool.connect(_con_bucket().database_url),
        _con_bucket(),
        now=BASE + timedelta(minutes=25),
    )
    assert r.generados == (inc,), r

    fila = escena.informe(inc)
    assert (fila["state"], fila["trigger"], fila["variant"]) == ("ok", "plazo", "executive")
    assert fila["preliminar"] is True, "sin dictamen firmado el informe es PRELIMINAR"
    assert fila["dictamen_vigente"] is None

    [(key, pdf)] = bucket.items()
    assert pdf.startswith(b"%PDF")
    assert "report-executive-" in key
    ev = escena.conn.execute(
        "SELECT sha256, s3_key, kind FROM evidence_objects WHERE evidence_id = %s",
        (fila["evidence_id"],),
    ).fetchone()
    assert ev["sha256"] == hashlib.sha256(pdf).hexdigest()
    assert (ev["s3_key"], ev["kind"]) == (key, "report_pdf")

    [auditoria] = escena.conn.execute(
        "SELECT actor, meta FROM audit_log WHERE verb = 'export_pdf' AND object = %s",
        (f"evidence:{fila['evidence_id']}",),
    ).fetchall()
    assert auditoria["actor"] == P.ACTOR
    assert auditoria["meta"]["origen"] == P.ORIGEN
    assert auditoria["meta"]["site_id"] == escena.site
    assert auditoria["meta"]["variant"] == "executive"


def test_con_la_cabeza_firmada_NO_es_preliminar(escena: Escena, bucket) -> None:
    inc = escena.incidente()
    escena.firma(inc, cuando=BASE + timedelta(minutes=2))
    cabeza = escena.conn.execute(
        "SELECT dictamen_id FROM dictamens WHERE incident_id = %s", (inc,)
    ).fetchone()["dictamen_id"]
    P.run_informes_pass(
        lambda: pool.connect(_con_bucket().database_url),
        _con_bucket(),
        now=BASE + timedelta(minutes=5),
    )
    fila = escena.informe(inc)
    assert (fila["state"], fila["trigger"], fila["preliminar"]) == ("ok", "firma", False)
    assert fila["dictamen_vigente"] == cabeza
    [accion] = escena.acciones(inc)
    assert accion["payload"]["preliminar"] is False
