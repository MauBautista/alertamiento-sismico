"""Los directorios temporales de repuesto se borran con su dueño.

Sin ruta configurada, el anillo miniSEED, el spool de la nube y el backfill caían
a un `mkdtemp` que NADIE borraba. En el Pi no pasa (el aprovisionamiento fija las
rutas), pero en desarrollo y en la suite sí: el 2026-09-29 había ~2 900
directorios de cada uno en un `/tmp` tmpfs de 3,6 GB, y la suite del edge murió
con «Disk quota exceeded» en una prueba que no tenía nada que ver.

Borrar es peligroso, así que la mitad de estas pruebas comprueba lo contrario:
**una ruta CONFIGURADA no se toca jamás**, aunque su dueño muera.
"""

from __future__ import annotations

import gc
import re
import tempfile
from pathlib import Path

import pytest
from simulators.mqtt import FakeMqttTransport
from takab_edge.backfill import BackfillManager
from takab_edge.buffer import RingBuffer
from takab_edge.cloud import CloudConnector
from takab_edge.config import BufferConfig, EdgeSettings

PAQUETE = Path(__file__).resolve().parents[1] / "takab_edge"


@pytest.fixture
def tmp_propio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """El temporal del sistema apunta aquí: lo que se cree se puede contar."""
    base = tmp_path / "tmp-del-sistema"
    base.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(base))
    return base


def test_el_anillo_sin_ruta_borra_su_temporal_al_morir(tmp_propio: Path) -> None:
    anillo = RingBuffer()
    raiz = anillo.root
    assert raiz.parent == tmp_propio and raiz.is_dir()
    (raiz / "AM.R4F74.00.EHZ.20260929.mseed").write_bytes(b"x" * 1024)
    del anillo
    gc.collect()
    assert not raiz.exists(), "el temporal del anillo sobrevivió a su dueño"


def test_el_anillo_con_ruta_configurada_NO_se_borra(tmp_path: Path) -> None:
    raiz = tmp_path / "nvme" / "buffer"
    anillo = RingBuffer(BufferConfig(root=str(raiz)))
    (raiz / "dato.mseed").write_bytes(b"x")
    del anillo
    gc.collect()
    assert (raiz / "dato.mseed").exists(), "¡se borró un anillo CONFIGURADO!"


def _nube(settings: EdgeSettings, **kw: object) -> CloudConnector:
    return CloudConnector(settings, transport=FakeMqttTransport(), **kw)


def test_el_spool_sin_ruta_borra_su_temporal_al_morir(tmp_propio: Path) -> None:
    nube = _nube(EdgeSettings(dev_mode=True, cloud_spool_dir=""))
    creados = list(tmp_propio.glob("takab-cloud-spool-*"))
    assert len(creados) == 1
    del nube
    gc.collect()
    assert not creados[0].exists(), "el spool temporal sobrevivió a su dueño"


@pytest.mark.parametrize("por", ["settings", "argumento"])
def test_el_spool_con_ruta_configurada_NO_se_borra(tmp_path: Path, por: str) -> None:
    spool = tmp_path / "nvme" / "spool"
    if por == "settings":
        nube = _nube(EdgeSettings(dev_mode=True, cloud_spool_dir=str(spool)))
    else:
        nube = _nube(EdgeSettings(dev_mode=True, cloud_spool_dir=""), spool_dir=spool)
    (spool / "pendiente.json").write_text("{}")
    del nube
    gc.collect()
    assert (spool / "pendiente.json").exists(), "¡se borró un spool CONFIGURADO!"


def test_el_backfill_sin_ruta_no_deja_un_temporal_huerfano(
    tmp_propio: Path, tmp_path: Path
) -> None:
    """Hacía un `mkdtemp` sólo para quedarse con su PADRE: el directorio creado no
    se usaba nunca. La ruta resultante no cambia."""
    settings = EdgeSettings(dev_mode=True, cloud_spool_dir="")
    nube = _nube(settings, spool_dir=tmp_path / "spool")
    gestor = BackfillManager(settings, nube)
    assert gestor._pending_dir == tmp_propio / "backfill-pending"
    assert not list(tmp_propio.glob("takab-backfill-*"))


def test_ningun_mkdtemp_del_paquete_queda_suelto() -> None:
    """El censo lo pone el árbol: un `mkdtemp` nuevo en el paquete tiene que pasar
    por `directorio_efimero`, o vuelve a llenar `/tmp` sin que nadie lo vea."""
    sueltos = [
        f"{py.relative_to(PAQUETE)}:{n}"
        for py in sorted(PAQUETE.rglob("*.py"))
        if py.name != "efimero.py"
        for n, linea in enumerate(py.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r"\bmkdtemp\(", linea)
    ]
    assert not sueltos, f"mkdtemp sin dueño: {sueltos}"
