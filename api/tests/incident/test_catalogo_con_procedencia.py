"""[T-7.12] El catálogo cita a la fuente, y la cita se puede comprobar.

`consulted_at`, `review_status` y `provider_event_id` nacen NULL desde `T-5.10`:
NULL significa «no consta» y la UI **no pinta la cifra**. Llenarlos a mano sería
exactamente la mentira que esas tres columnas existen para impedir — un
`confirmado` tecleado es indistinguible de uno consultado, salvo por esto.

Esta prueba ata el seed a la respuesta ARCHIVADA del FDSN de USGS: para cada
fila que declara procedencia, el id tiene que estar en la consulta, y magnitud,
epicentro y profundidad tienen que coincidir con lo que contestó la fuente. Una
fila editada a mano —o un id copiado de otro evento— sale roja.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_RAIZ = Path(__file__).resolve().parents[3]
_SEED = _RAIZ / "db/seeds/reference_earthquakes.sql"
_CONSULTA = Path(__file__).resolve().parent / "fixtures" / "usgs-consulta-2026-09-14.json"

#: `('CLAVE', 'id')` de la tabla de procedencia del seed.
_ESTAMPADAS = re.compile(r"\('(?P<clave>[A-Z0-9-]+)',\s*'(?P<id>[a-z0-9]+)'\)")
#: Una fila del INSERT, con sus cifras.
_FILA = re.compile(
    r"\('(?P<clave>[A-Z0-9-]+)',\s*'(?P<t>[0-9T:-]+Z)',\s*(?P<mag>[\d.]+),.*?"
    r"ST_MakePoint\((?P<lon>-?[\d.]+),\s*(?P<lat>-?[\d.]+)\).*?geography,\s*(?P<prof>[\d.]+),",
    re.S,
)


@pytest.fixture(scope="module")
def consulta() -> dict:
    return json.loads(_CONSULTA.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def seed() -> str:
    return _SEED.read_text(encoding="utf-8")


def _por_id(consulta: dict) -> dict[str, dict]:
    return {f["id"]: f for c in consulta["consultas"] for f in c["features"]}


def test_la_consulta_archivada_declara_CUANDO_se_preguntó(consulta: dict) -> None:
    """Sin fecha, «confirmado» no dice nada: una cifra ajena envejece."""
    assert consulta["consultado_en"].startswith("2026-09-14")
    assert "earthquake.usgs.gov" in consulta["servicio"]
    assert consulta["consultas"], "la consulta archivada está vacía"


def test_cada_fila_ESTAMPADA_está_en_la_consulta(seed: str, consulta: dict) -> None:
    """El id no se teclea: o está en lo que contestó la fuente, o no se estampa."""
    disponibles = _por_id(consulta)
    estampadas = dict(m.group("clave", "id") for m in _ESTAMPADAS.finditer(seed))
    assert estampadas, "el seed no estampa procedencia a ninguna fila"
    for clave, event_id in estampadas.items():
        assert event_id in disponibles, (
            f"{clave} declara `{event_id}` y ese id no aparece en la consulta archivada"
        )


def test_las_cifras_del_seed_COINCIDEN_con_lo_que_contestó_la_fuente(
    seed: str, consulta: dict
) -> None:
    """Lo que hace citable a una cifra es que se pueda contrastar. Si el seed y la
    respuesta difieren, una de las dos está mal y el papel imprimiría la otra."""
    disponibles = _por_id(consulta)
    estampadas = dict(m.group("clave", "id") for m in _ESTAMPADAS.finditer(seed))
    filas = {m.group("clave"): m for m in _FILA.finditer(seed)}

    for clave, event_id in estampadas.items():
        assert clave in filas, f"{clave} se estampa pero no está en el INSERT"
        f, fuente = filas[clave], disponibles[event_id]
        assert float(f.group("mag")) == pytest.approx(fuente["mag"], abs=0.05), clave
        assert float(f.group("lat")) == pytest.approx(fuente["lat"], abs=0.001), clave
        assert float(f.group("lon")) == pytest.approx(fuente["lon"], abs=0.001), clave
        assert float(f.group("prof")) == pytest.approx(fuente["depth_km"], abs=0.05), clave


def test_solo_se_marca_CONFIRMADO_lo_que_la_fuente_tiene_revisado(consulta: dict) -> None:
    """`review_status` se COPIA del `status` del FDSN, no se asciende.

    Un `automatic` de la fuente es `preliminar`, y esa distinción es justo lo que
    separa una cifra citable de una que puede moverse mañana.
    """
    ids_del_seed = set(
        dict(
            m.group("clave", "id") for m in _ESTAMPADAS.finditer(_SEED.read_text(encoding="utf-8"))
        ).values()
    )
    for event_id, f in _por_id(consulta).items():
        if event_id in ids_del_seed:
            assert f["status"] == "reviewed", (
                f"{event_id} está `{f['status']}` en la fuente y el seed lo da por confirmado"
            )


def test_lo_que_NO_se_consultó_se_queda_en_blanco(seed: str) -> None:
    """Las filas del SSN no llevan procedencia porque **no se consultó al SSN**.

    NULL es «no consta» y la UI no pinta la cifra. Rellenarlas con la consulta de
    USGS sería atribuirle al SSN una confirmación que no dio, y el catálogo
    conserva los dos a propósito: sus soluciones difieren hasta 62 km.
    """
    estampadas = {m.group("clave") for m in _ESTAMPADAS.finditer(seed)}
    assert not [c for c in estampadas if c.startswith("SSN-")], (
        "una fila del SSN lleva la procedencia de una consulta a USGS"
    )
    assert "SSN-2022-09-19-MICH" in seed and "USGS-2022-09-19-MICH" in seed, (
        "el gemelo USGS de Michoacán 2022 y su fila SSN tienen que convivir"
    )
