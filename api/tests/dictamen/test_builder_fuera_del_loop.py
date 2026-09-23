"""[T-8.12 · A-080] El builder lee S3 y decodifica FUERA del event loop.

`fetch_object` es boto3 SÍNCRONO, y el builder lo llamaba en línea para cada
foto del brigadista y para el miniSEED —y después redimensionaba cada foto con
Pillow y calculaba tres transformadas de la onda, también en el loop—. Con una
docena de fotos eso son segundos de loop parado en el único worker de la API.

Se demuestra igual que en `tests/api/test_reports_no_bloquea_el_loop.py`: se hace
lenta la lectura y una corrutina concurrente mide el hueco más largo del loop.
Sin base: `_danos` recibe una conexión mínima que devuelve una fila. Medido
contra el código de antes (2026-09-23): 0.50 s de loop parado por el miniSEED y
1.17 s por dos fotos —las dos lecturas de 0.5 s más su redimensionado—.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from takab_api.dictamen import builder
from tests.dictamen.test_fotos_en_el_papel import _jpeg

_SUENO_S = 0.5
_HUECO_MAX_S = 0.25


async def _hueco_mas_largo(corrutina):  # noqa: ANN001, ANN202
    parada = asyncio.Event()
    huecos: list[float] = []

    async def latido() -> None:
        ultimo = time.monotonic()
        while True:
            await asyncio.sleep(0.01)
            ahora = time.monotonic()
            huecos.append(ahora - ultimo)
            ultimo = ahora
            # Se mira DESPUÉS de anotar: la vuelta que despierta tras el bloqueo
            # es justo la que trae el hueco, y no se puede perder.
            if parada.is_set():
                return

    tarea = asyncio.create_task(latido())
    await asyncio.sleep(0)  # que el latido esté girando ANTES de empezar
    try:
        resultado = await corrutina
    finally:
        parada.set()
        await tarea
    # No-vacuidad: el latido tiene que haber dado al menos una vuelta COMPLETA. No
    # se le pide un número de vueltas: con el loop bloqueado da sólo dos o tres,
    # y es justo el caso que el hueco de abajo tiene que poder contar.
    assert huecos, "el latido no llegó a girar: la medida no dice nada"
    return resultado, max(huecos)


def _lectura_lenta(datos: bytes):  # noqa: ANN202
    def fetch(_key: str) -> bytes:
        time.sleep(_SUENO_S)
        return datos

    return fetch


@pytest.mark.asyncio
async def test_la_ONDA_se_lee_y_se_decodifica_fuera_del_loop() -> None:
    filas = [SimpleNamespace(kind="miniseed", s3_key="evidence/x/onda.mseed")]
    salida, hueco = await _hueco_mas_largo(
        builder._raw_waveform(filas, _lectura_lenta(b"no es miniseed"), "technical")
    )
    assert salida[-1], "el caso dejó de pasar por la lectura: no mediría nada"
    assert hueco < _HUECO_MAX_S, f"el loop se paró {hueco:.2f} s leyendo el miniSEED"


class _ConexionMinima:
    """Lo único que `_danos` le pide a la base: la fila del reporte."""

    def __init__(self, fila) -> None:  # noqa: ANN001
        self._fila = fila

    async def execute(self, *_a, **_k):  # noqa: ANN002, ANN003, ANN202
        return SimpleNamespace(all=lambda: [self._fila])


@pytest.mark.asyncio
async def test_las_FOTOS_se_leen_y_se_preparan_fuera_del_loop() -> None:
    evidencia = SimpleNamespace(evidence_id="e-1", s3_key="evidence/x/foto.jpg", sha256="a" * 64)
    fila = SimpleNamespace(
        report_id="d-1",
        evidence_ids=["e-1", "e-1"],
        categories=[],
        people_at_risk=False,
        notes=None,
        ts=datetime(2026, 8, 3, 10, 0, tzinfo=UTC),
        zona="Nivel 3",
        rol="brigadista",
    )
    danos, hueco = await _hueco_mas_largo(
        builder._danos(_ConexionMinima(fila), "i-1", [evidencia], _lectura_lenta(_jpeg(3)))
    )
    assert [f.jpeg is not None for f in danos[0].fotos] == [True, True]
    assert hueco < _HUECO_MAX_S, f"el loop se paró {hueco:.2f} s leyendo las fotos"
