"""El ejecutor del conteo en la nube (T-3.12.b).

Lo que se prueba aquí es la **disciplina de fallo**, no la aritmética —esa ya tiene sus
tests—: que cuando falta algo, el handler LANZA en vez de escribir un análisis a medias.
Un incidente con métricas incompletas es indistinguible de uno con métricas buenas, y el
reporte ya sabe decir `CLIP DISPONIBLE · ANÁLISIS PENDIENTE`, que es la verdad mientras
esto no termine.
"""

from __future__ import annotations

import json

import pytest
from takab_cctv.lambda_handler import AnalisisImposible, _clip_y_goteo, handler


class _Cursor:
    def __init__(self, fila):
        self._fila = fila

    def fetchone(self):
        return self._fila


class _Conn:
    """Conexión de mentira. Solo sabe devolver una fila."""

    def __init__(self, fila=None):
        self.fila = fila
        self.consultas: list[str] = []

    def execute(self, sql, _params=None):
        self.consultas.append(" ".join(sql.split()))
        return _Cursor(self.fila)


def test_sin_fila_del_clip_LANZA_en_vez_de_analizar_a_medias() -> None:
    """Es la mitad que importa: analizar un clip cuyo incidente no conocemos produciría
    métricas huérfanas, y una métrica huérfana en un dictamen no se distingue de una
    buena."""
    with pytest.raises(AnalisisImposible, match="no hay clip"):
        _clip_y_goteo(_Conn(fila=None), "no-existe")


def test_la_consulta_del_clip_trae_el_incidente_y_la_camara_en_UNA_pasada() -> None:
    """Dos consultas serían dos oportunidades de que el clip exista y su incidente no."""
    conn = _Conn(fila=(1, 2, 3, "evidence/t/e/cctv-x.mp4", "t1", "t0", "substream"))
    datos = _clip_y_goteo(conn, "clip-1")

    assert datos["s3_key"] == "evidence/t/e/cctv-x.mp4"
    assert datos["opened_at"] == "t0"
    assert len(conn.consultas) == 1
    assert "JOIN incidents" in conn.consultas[0]


def test_el_handler_procesa_un_registro_por_clip(monkeypatch) -> None:
    vistos: list[str] = []
    monkeypatch.setattr(
        "takab_cctv.lambda_handler.analizar_clip",
        lambda clip_id: vistos.append(clip_id) or {"clip_id": clip_id},
    )
    evento = {
        "Records": [{"body": json.dumps({"clip_id": "a"})}, {"body": json.dumps({"clip_id": "b"})}]
    }

    assert handler(evento)["analizados"] == [{"clip_id": "a"}, {"clip_id": "b"}]
    assert vistos == ["a", "b"]


def test_un_fallo_NO_se_traga_y_el_mensaje_vuelve_a_la_cola(monkeypatch) -> None:
    """Tragárselo dejaría el incidente en ANÁLISIS PENDIENTE para siempre y sin nadie a
    quien preguntarle por qué. Lanzar lo manda a la DLQ, que es donde se ve."""

    def revienta(_clip_id):
        raise AnalisisImposible("el clip no está en S3")

    monkeypatch.setattr("takab_cctv.lambda_handler.analizar_clip", revienta)

    with pytest.raises(AnalisisImposible):
        handler({"Records": [{"body": json.dumps({"clip_id": "a"})}]})


def test_un_evento_sin_registros_no_es_un_error() -> None:
    """SQS puede entregar un lote vacío; eso no es nada que reportar."""
    assert handler({})["analizados"] == []
