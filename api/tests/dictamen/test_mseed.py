"""T-2.41 · El lector miniSEED propio decodifica lo que el edge escribe.

Los vectores dorados los generó **el propio ObsPy del edge** con el mismo camino de
código que produce la evidencia real (`edge/takab_edge/buffer`: int32 ⇒ STEIM2,
big-endian). Regenerarlos:

    cd edge && uv run python - <<'PY'   # ver el script en el commit de T-2.41

Si este test falla tras tocar `mseed.py`, la traza del dictamen técnico estaría
mintiendo sobre la forma de onda que registró el sensor. No hay degradación aceptable
aquí: o decodifica exacto, o declara que no puede.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from takab_api.dictamen.mseed import MseedError, read_traces

_VECTORS = json.loads((Path(__file__).parent / "mseed_vectors.json").read_text())


@pytest.mark.parametrize("name", sorted(_VECTORS))
def test_decodifica_exactamente_lo_que_escribio_el_edge(name: str) -> None:
    case = _VECTORS[name]
    traces = read_traces(bytes.fromhex(case["mseed_hex"]))
    assert len(traces) == 1
    assert traces[0].samples == case["samples"], f"vector {name}: muestras distintas"


def test_conserva_la_identidad_seed_del_canal() -> None:
    tr = read_traces(bytes.fromhex(_VECTORS["steim2_transient"]["mseed_hex"]))[0]
    assert (tr.network, tr.station, tr.location, tr.channel) == ("AM", "R4F74", "00", "ENZ")
    assert tr.sample_rate == pytest.approx(100.0)


def test_una_señal_plana_no_se_convierte_en_ruido() -> None:
    """Todas las diferencias son 0: el caso donde un bug de nibbles se nota enseguida."""
    tr = read_traces(bytes.fromhex(_VECTORS["steim2_flat"]["mseed_hex"]))[0]
    assert set(tr.samples) == {12345}


def test_un_blob_que_no_es_miniseed_falla_explicitamente() -> None:
    """Fallar es correcto; adivinar produciría una traza plausible y falsa."""
    with pytest.raises(MseedError):
        read_traces(b"esto no es un registro SEED" * 4)


def test_un_blob_demasiado_corto_falla() -> None:
    with pytest.raises(MseedError):
        read_traces(b"corto")


def test_hay_un_techo_de_tamaño() -> None:
    """Un request no puede masticar cientos de MB para imprimir un PDF."""
    from takab_api.dictamen.mseed import MAX_BYTES  # noqa: PLC0415

    with pytest.raises(MseedError, match="demasiado grande"):
        read_traces(b"\x00" * (MAX_BYTES + 1))
