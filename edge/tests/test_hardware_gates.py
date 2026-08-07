"""Censo de los tests que un `skipif` de hardware puede apagar (T-2.63).

`test_signal_hardware.py` y `test_seedlink_hardware.py` llevan un `pytestmark =
skipif` que depende de **alcanzar por socket** al Raspberry Shake. En CI eso NUNCA
se cumple: los 5 tests se saltan, el job sigue verde y no acredita nada. Es la
misma familia de fallo que T-2.58 (67 tests del panel saltados en silencio por un
`skipif` de `node`), pero **el precedente no es replicable**: allí la solución fue
exigir la dependencia (`node --version` en `ci.yml`); aquí no se puede hacer ping
al Shake desde un runner de GitHub.

La guardia equivalente es **contabilizar el skip, no exigir el hardware**:

1. este censo declara, con nombre y gate, EXACTAMENTE qué tests puede apagar el
   hardware ausente — un `skipif` de socket nuevo y sin registrar rompe el build;
2. `conftest.py` imprime al final de cada corrida cuántos de ellos se saltaron,
   para que el log no pueda leerse como si el gate estuviera acreditado;
3. y como ningún censo por patrones lo ve todo, una SEGUNDA red (capa 2) exige
   que cada test saltado esté declarado en `SKIPS_DECLARADOS` — de socket, de
   `node` o de lo que sea. Esa no mira sintaxis: mira los reportes de la corrida.

El censo es **estático** (AST sobre todo lo que pytest colecta bajo `edge/tests/`:
`test_*.py` y `*_test.py`, subdirectorios incluidos), no una inspección de lo que
pytest colectó en esta corrida. Tres razones:

- corre igual con o sin Shake conectado, y también cuando se invoca este archivo
  solo (`pytest tests/test_hardware_gates.py`), donde los módulos de hardware ni
  siquiera se colectan;
- no importa los módulos gated, así que **no repite la sonda de socket** de
  `_reachable()` (0.6 s por archivo, ~1.2 s fijos ya hoy) ni la paga dos veces;
- ve el `skipif` aunque el archivo esté deseleccionado o marcado para no correr.

Los gates son los de `takab-docs/runbooks/RUNBOOK-auditoria-cierre.md §10`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent

#: id de test → gate que ese test acredita **sólo cuando corre contra el Shake real**.
#: Los de SeedLink son G-03 (soak/reconexión/resume); los de señal contra traza real
#: caen bajo el gate #3 del plan maestro (hardware físico presente).
GATES_HARDWARE: dict[str, str] = {
    "test_signal_hardware.py::test_features_algorithm_matches_obspy_on_real_trace": (
        "gate #3 · traza real: STA/LTA e integración coinciden con ObsPy (<1%)"
    ),
    "test_signal_hardware.py::test_compute_features_on_real_packet_is_sane": (
        "gate #3 · traza real: features del paquete real son sanas (sin dropout)"
    ),
    "test_seedlink_hardware.py::test_real_shake_streams_100sps": (
        "G-03 · el Shake entrega 100 sps y el stream se sostiene sin reconectar"
    ),
    "test_seedlink_hardware.py::test_lag_del_shake_llega_a_ser_bajo": (
        "G-03 · el dato LLEGA A TENER <3 s de antigüedad (mínimo de la ventana)"
    ),
    "test_seedlink_hardware.py::test_real_shake_backfills_via_seqnum_resume": (
        "G-03 · resume por número de secuencia = cero pérdida tras un hueco"
    ),
}

_MODULO_SONDA = """
import os
import socket

import pytest


def _reachable(host: str, port: int, timeout: float = 0.6) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
"""


def test_el_registro_declara_los_cinco_tests_del_gate_hardware() -> None:
    """(b) El número es parte del contrato: el resumen del conftest dice «N/5»."""
    assert len(GATES_HARDWARE) == 5, (
        "el registro dejó de tener 5 entradas; si el cambio es legítimo, actualiza "
        "también el resumen de gate en conftest.py y este número"
    )


def test_censo_de_skipif_de_socket_es_exactamente_el_registro(
    censo_gates_hardware: set[str],
) -> None:
    """(a) Un `skipif` de alcanzabilidad de socket sin registrar rompe el build."""
    registrados = set(GATES_HARDWARE)
    sin_registrar = sorted(censo_gates_hardware - registrados)
    fantasmas = sorted(registrados - censo_gates_hardware)
    assert censo_gates_hardware == registrados, (
        "el censo de tests gated por socket no coincide con GATES_HARDWARE.\n"
        f"  sin registrar (skipif nuevo, gate mudo): {sin_registrar}\n"
        f"  en el registro pero ya sin skipif: {fantasmas}\n"
        "Registra cada test nuevo con el gate que acredita, o bórralo del registro."
    )


def test_cada_entrada_del_registro_nombra_el_gate_que_acredita() -> None:
    for test_id, gate in GATES_HARDWARE.items():
        assert "G-03" in gate or "gate #3" in gate, f"{test_id} no dice qué gate acredita: {gate!r}"


def test_el_censo_ignora_un_skipif_que_no_toca_un_socket(
    escanear_gates_socket: Callable[[Path], set[str]], tmp_path: Path
) -> None:
    """El `skipif` de `node` de `test_local_api_panel.py` NO es un gate de hardware."""
    (tmp_path / "test_falso_node.py").write_text(
        "import shutil\n"
        "\n"
        "import pytest\n"
        "\n"
        "pytestmark = pytest.mark.skipif(shutil.which('node') is None, reason='sin node')\n"
        "\n"
        "def test_algo():\n"
        "    pass\n",
        encoding="utf-8",
    )
    assert escanear_gates_socket(tmp_path) == set()


def test_el_censo_detecta_un_skipif_de_socket_a_nivel_de_modulo(
    escanear_gates_socket: Callable[[Path], set[str]], tmp_path: Path
) -> None:
    (tmp_path / "test_falso_hw.py").write_text(
        _MODULO_SONDA + "\n"
        "pytestmark = pytest.mark.skipif(not _reachable('h', 1), reason='sin hw')\n"
        "\n"
        "def test_uno():\n"
        "    pass\n"
        "\n"
        "def test_dos():\n"
        "    pass\n"
        "\n"
        "def _ayudante():\n"
        "    pass\n",
        encoding="utf-8",
    )
    assert escanear_gates_socket(tmp_path) == {
        "test_falso_hw.py::test_uno",
        "test_falso_hw.py::test_dos",
    }


def test_el_censo_detecta_un_skipif_de_socket_en_un_solo_test(
    escanear_gates_socket: Callable[[Path], set[str]], tmp_path: Path
) -> None:
    """Un decorador suelto también apaga un gate: entra al censo igual."""
    (tmp_path / "test_falso_uno.py").write_text(
        _MODULO_SONDA + "\n"
        "@pytest.mark.skipif(not _reachable('h', 1), reason='sin hw')\n"
        "def test_gated():\n"
        "    pass\n"
        "\n"
        "def test_libre():\n"
        "    pass\n"
        "\n"
        "@pytest.mark.skipif(not _reachable('h', 1), reason='sin hw')\n"
        "class TestGated:\n"
        "    def test_metodo(self):\n"
        "        pass\n",
        encoding="utf-8",
    )
    assert escanear_gates_socket(tmp_path) == {
        "test_falso_uno.py::test_gated",
        "test_falso_uno.py::TestGated::test_metodo",
    }


# ---------------------------------------------------------------------------
# Capa 1 · las formas de escribir el MISMO gate que el censo no veía (F5)
# ---------------------------------------------------------------------------
#
# El censo original sólo reconocía la forma sintáctica EXACTA de los dos archivos
# reales: la sonda llamada dentro de la propia expresión del `skipif`, en un
# `def` de nivel de módulo, en un archivo directamente bajo `tests/`. La auditoría
# corrió `censar_gates_de_socket` contra archivos sintéticos y midió que 7 formas
# más devolvían `set()` — es decir, gate apagado y censo mudo. La primera de ellas
# (guardar la sonda en una constante) está a UNA línea de `test_signal_hardware.py`
# y es la manera más natural de escribirlo.


def test_el_censo_caza_la_sonda_guardada_en_una_constante(
    escanear_gates_socket: Callable[[Path], set[str]], tmp_path: Path
) -> None:
    """`SHAKE_UP = _reachable(...)` y `skipif(not SHAKE_UP)`: una línea de diferencia."""
    (tmp_path / "test_falso_const.py").write_text(
        _MODULO_SONDA + "\n"
        "SHAKE_UP = _reachable('h', 1)\n"
        "\n"
        "pytestmark = pytest.mark.skipif(not SHAKE_UP, reason='sin hw')\n"
        "\n"
        "def test_gated():\n"
        "    pass\n",
        encoding="utf-8",
    )
    assert escanear_gates_socket(tmp_path) == {"test_falso_const.py::test_gated"}


def test_el_censo_caza_la_sonda_propagada_por_una_segunda_constante(
    escanear_gates_socket: Callable[[Path], set[str]], tmp_path: Path
) -> None:
    """La negación intermedia (`SIN_SHAKE = not SHAKE_UP`) tampoco puede esconderla."""
    (tmp_path / "test_falso_const2.py").write_text(
        _MODULO_SONDA + "\n"
        "SHAKE_UP = _reachable('h', 1)\n"
        "SIN_SHAKE = not SHAKE_UP\n"
        "\n"
        "pytestmark = pytest.mark.skipif(SIN_SHAKE, reason='sin hw')\n"
        "\n"
        "def test_gated():\n"
        "    pass\n",
        encoding="utf-8",
    )
    assert escanear_gates_socket(tmp_path) == {"test_falso_const2.py::test_gated"}


def test_el_censo_caza_un_alias_de_marca(
    escanear_gates_socket: Callable[[Path], set[str]], tmp_path: Path
) -> None:
    """`SIN_HW = pytest.mark.skipif(...)` y luego `@SIN_HW` sobre cada test."""
    (tmp_path / "test_falso_alias.py").write_text(
        _MODULO_SONDA + "\n"
        "SIN_HW = pytest.mark.skipif(not _reachable('h', 1), reason='sin hw')\n"
        "\n"
        "@SIN_HW\n"
        "def test_gated():\n"
        "    pass\n"
        "\n"
        "def test_libre():\n"
        "    pass\n",
        encoding="utf-8",
    )
    assert escanear_gates_socket(tmp_path) == {"test_falso_alias.py::test_gated"}


def test_el_censo_caza_un_alias_de_marca_puesto_en_pytestmark(
    escanear_gates_socket: Callable[[Path], set[str]], tmp_path: Path
) -> None:
    """`pytestmark = [SIN_HW]` apaga el módulo entero igual que el `skipif` inline."""
    (tmp_path / "test_falso_alias_mod.py").write_text(
        _MODULO_SONDA + "\n"
        "SIN_HW = pytest.mark.skipif(not _reachable('h', 1), reason='sin hw')\n"
        "\n"
        "pytestmark = [SIN_HW]\n"
        "\n"
        "def test_gated():\n"
        "    pass\n",
        encoding="utf-8",
    )
    assert escanear_gates_socket(tmp_path) == {"test_falso_alias_mod.py::test_gated"}


def test_el_censo_caza_un_decorador_sobre_un_metodo(
    escanear_gates_socket: Callable[[Path], set[str]], tmp_path: Path
) -> None:
    """El decorador vive en el MÉTODO, no en la clase: `arbol.body` no lo veía."""
    (tmp_path / "test_falso_metodo.py").write_text(
        _MODULO_SONDA + "\n"
        "class TestGabinete:\n"
        "    @pytest.mark.skipif(not _reachable('h', 1), reason='sin hw')\n"
        "    def test_metodo(self):\n"
        "        pass\n"
        "\n"
        "    def test_libre(self):\n"
        "        pass\n",
        encoding="utf-8",
    )
    assert escanear_gates_socket(tmp_path) == {"test_falso_metodo.py::TestGabinete::test_metodo"}


def test_el_censo_caza_un_alias_de_import(
    escanear_gates_socket: Callable[[Path], set[str]], tmp_path: Path
) -> None:
    """`from socket import create_connection as abrir`: el nombre cambia, el socket no."""
    (tmp_path / "test_falso_import.py").write_text(
        "from socket import create_connection as abrir\n"
        "\n"
        "import pytest\n"
        "\n"
        "\n"
        "def _arriba(host, port):\n"
        "    try:\n"
        "        with abrir((host, port), timeout=0.6):\n"
        "            return True\n"
        "    except OSError:\n"
        "        return False\n"
        "\n"
        "\n"
        "pytestmark = pytest.mark.skipif(not _arriba('h', 1), reason='sin hw')\n"
        "\n"
        "def test_gated():\n"
        "    pass\n",
        encoding="utf-8",
    )
    assert escanear_gates_socket(tmp_path) == {"test_falso_import.py::test_gated"}


def test_el_censo_baja_a_los_subdirectorios(
    escanear_gates_socket: Callable[[Path], set[str]], tmp_path: Path
) -> None:
    """`glob` no entra en `tests/hardware/`; el id lleva la ruta para no colisionar."""
    sub = tmp_path / "hardware"
    sub.mkdir()
    (sub / "test_falso_sub.py").write_text(
        _MODULO_SONDA + "\n"
        "pytestmark = pytest.mark.skipif(not _reachable('h', 1), reason='sin hw')\n"
        "\n"
        "def test_gated():\n"
        "    pass\n",
        encoding="utf-8",
    )
    assert escanear_gates_socket(tmp_path) == {"hardware/test_falso_sub.py::test_gated"}


def test_el_censo_caza_una_sonda_que_vive_en_un_modulo_auxiliar(
    escanear_gates_socket: Callable[[Path], set[str]], tmp_path: Path
) -> None:
    """La sonda mudada a un helper (`_sondas.py`) sigue siendo una sonda de socket."""
    (tmp_path / "_sondas.py").write_text(
        "import socket\n"
        "\n"
        "\n"
        "def shake_arriba(host, port):\n"
        "    try:\n"
        "        with socket.create_connection((host, port), timeout=0.6):\n"
        "            return True\n"
        "    except OSError:\n"
        "        return False\n",
        encoding="utf-8",
    )
    (tmp_path / "test_falso_aux.py").write_text(
        "import pytest\n"
        "from _sondas import shake_arriba\n"
        "\n"
        "pytestmark = pytest.mark.skipif(not shake_arriba('h', 1), reason='sin hw')\n"
        "\n"
        "def test_gated():\n"
        "    pass\n",
        encoding="utf-8",
    )
    assert escanear_gates_socket(tmp_path) == {"test_falso_aux.py::test_gated"}


def test_el_censo_caza_un_veredicto_importado_de_un_modulo_auxiliar(
    escanear_gates_socket: Callable[[Path], set[str]], tmp_path: Path
) -> None:
    """Del helper no se importa la FUNCIÓN sino la constante ya resuelta.

    Es la hermana natural de la sonda mudada a un helper, y se escapaba: el censo
    propagaba desde el módulo auxiliar los nombres INVOCABLES, no los nombres cuyo
    valor ya venía de una sonda.
    """
    (tmp_path / "_sondas.py").write_text(
        "import socket\n"
        "\n"
        "\n"
        "def _alcanzable(host, port):\n"
        "    try:\n"
        "        with socket.create_connection((host, port), timeout=0.6):\n"
        "            return True\n"
        "    except OSError:\n"
        "        return False\n"
        "\n"
        "\n"
        "SHAKE_UP = _alcanzable('h', 1)\n",
        encoding="utf-8",
    )
    (tmp_path / "test_falso_valor.py").write_text(
        "import pytest\n"
        "from _sondas import SHAKE_UP\n"
        "\n"
        "pytestmark = pytest.mark.skipif(not SHAKE_UP, reason='sin hw')\n"
        "\n"
        "def test_gated():\n"
        "    pass\n",
        encoding="utf-8",
    )
    assert escanear_gates_socket(tmp_path) == {"test_falso_valor.py::test_gated"}


def test_el_censo_caza_una_sonda_por_http(
    escanear_gates_socket: Callable[[Path], set[str]], tmp_path: Path
) -> None:
    """El ringserver del Shake también responde por HTTP: `urlopen` es la misma sonda."""
    (tmp_path / "test_falso_http.py").write_text(
        "from urllib.request import urlopen\n"
        "\n"
        "import pytest\n"
        "\n"
        "\n"
        "def _arriba(url):\n"
        "    try:\n"
        "        urlopen(url, timeout=0.6)\n"
        "    except OSError:\n"
        "        return False\n"
        "    return True\n"
        "\n"
        "\n"
        "pytestmark = pytest.mark.skipif(not _arriba('http://h'), reason='sin hw')\n"
        "\n"
        "def test_gated():\n"
        "    pass\n",
        encoding="utf-8",
    )
    assert escanear_gates_socket(tmp_path) == {"test_falso_http.py::test_gated"}


def test_el_censo_caza_la_condicion_escrita_como_cadena(
    escanear_gates_socket: Callable[[Path], set[str]], tmp_path: Path
) -> None:
    """pytest evalúa `skipif('<expr>')` como código; el censo también debe leerlo."""
    (tmp_path / "test_falso_cadena.py").write_text(
        _MODULO_SONDA + "\n"
        'pytestmark = pytest.mark.skipif("not _reachable(\'h\', 1)", reason="sin hw")\n'
        "\n"
        "def test_gated():\n"
        "    pass\n",
        encoding="utf-8",
    )
    assert escanear_gates_socket(tmp_path) == {"test_falso_cadena.py::test_gated"}


# ---------------------------------------------------------------------------
# Capa 1 (segunda vuelta) · las formas que la PRIMERA vuelta seguía sin ver
# ---------------------------------------------------------------------------
#
# Re-auditar el censo ya ensanchado con 16 formas nuevas encontró 7 más que
# devolvían `set()`. Éstas son las que se cerraron; las que siguen abiertas están
# nombradas en `test_formas_que_el_censo_AST_no_puede_ver`, porque un "todo
# cerrado" falso es peor que un agujero conocido.


def test_el_censo_ve_los_archivos_que_pytest_colecta_como_algo_test_py(
    escanear_gates_socket: Callable[[Path], set[str]], tmp_path: Path
) -> None:
    """`python_files` por defecto es `test_*.py` **y** `*_test.py`; el censo sólo miraba el primero.

    No hay override de `python_files` en `edge/pyproject.toml`, así que un
    `shake_hardware_test.py` lo COLECTA pytest y lo ignoraba el censo entero.
    """
    (tmp_path / "shake_hardware_test.py").write_text(
        _MODULO_SONDA + "\n"
        "pytestmark = pytest.mark.skipif(not _reachable('h', 1), reason='sin hw')\n"
        "\n"
        "def test_gated():\n"
        "    pass\n",
        encoding="utf-8",
    )
    assert escanear_gates_socket(tmp_path) == {"shake_hardware_test.py::test_gated"}


def test_el_censo_caza_un_unittest_skipif(
    escanear_gates_socket: Callable[[Path], set[str]], tmp_path: Path
) -> None:
    """`unittest.skipIf` apaga el test igual que `pytest.mark.skipif` — sólo cambia la I."""
    (tmp_path / "test_falso_unittest.py").write_text(
        _MODULO_SONDA + "\n"
        "import unittest\n"
        "\n"
        "class TestGabinete(unittest.TestCase):\n"
        "    @unittest.skipIf(not _reachable('h', 1), 'sin hw')\n"
        "    def test_gated(self):\n"
        "        pass\n",
        encoding="utf-8",
    )
    assert escanear_gates_socket(tmp_path) == {"test_falso_unittest.py::TestGabinete::test_gated"}


def test_el_censo_caza_la_sonda_repartida_por_desempaquetado(
    escanear_gates_socket: Callable[[Path], set[str]], tmp_path: Path
) -> None:
    """`SHAKE_UP, ENDPOINT = _reachable(...), 'h:1'` — el target es un Tuple, no un Name."""
    (tmp_path / "test_falso_tupla.py").write_text(
        _MODULO_SONDA + "\n"
        "SHAKE_UP, ENDPOINT = _reachable('h', 1), 'h:1'\n"
        "\n"
        "pytestmark = pytest.mark.skipif(not SHAKE_UP, reason='sin hw')\n"
        "\n"
        "def test_gated():\n"
        "    pass\n",
        encoding="utf-8",
    )
    assert escanear_gates_socket(tmp_path) == {"test_falso_tupla.py::test_gated"}


def test_el_censo_caza_la_sonda_llamada_suelta_dentro_de_un_try(
    escanear_gates_socket: Callable[[Path], set[str]], tmp_path: Path
) -> None:
    """Sin función sonda: el socket se abre a pelo y el veredicto viaja por el `except`.

    Aquí ningún nombre recibe el RESULTADO de la sonda —`SHAKE_UP` se asigna a
    literales—, así que el rastreo de valores no lo veía. La pista es que el `try`
    contiene una llamada de red y de él salen los nombres que decide.
    """
    (tmp_path / "test_falso_try.py").write_text(
        "import socket\n"
        "\n"
        "import pytest\n"
        "\n"
        "try:\n"
        "    socket.create_connection(('h', 1), timeout=0.6).close()\n"
        "    SHAKE_UP = True\n"
        "except OSError:\n"
        "    SHAKE_UP = False\n"
        "\n"
        "pytestmark = pytest.mark.skipif(not SHAKE_UP, reason='sin hw')\n"
        "\n"
        "def test_gated():\n"
        "    pass\n",
        encoding="utf-8",
    )
    assert escanear_gates_socket(tmp_path) == {"test_falso_try.py::test_gated"}


def test_el_censo_caza_una_sonda_por_cliente_http(
    escanear_gates_socket: Callable[[Path], set[str]], tmp_path: Path
) -> None:
    """`httpx.get`/`requests.get` sondean el ringserver igual que `urlopen`."""
    (tmp_path / "test_falso_httpx.py").write_text(
        "import httpx\n"
        "\n"
        "import pytest\n"
        "\n"
        "\n"
        "def _arriba(url):\n"
        "    try:\n"
        "        httpx.get(url, timeout=0.6)\n"
        "    except Exception:\n"
        "        return False\n"
        "    return True\n"
        "\n"
        "\n"
        "pytestmark = pytest.mark.skipif(not _arriba('http://h'), reason='sin hw')\n"
        "\n"
        "def test_gated():\n"
        "    pass\n",
        encoding="utf-8",
    )
    assert escanear_gates_socket(tmp_path) == {"test_falso_httpx.py::test_gated"}


def test_el_censo_caza_un_skip_de_modulo_entero(
    escanear_gates_socket: Callable[[Path], set[str]], tmp_path: Path
) -> None:
    """`pytest.skip(..., allow_module_level=True)` apaga el módulo SIN escribir «skipif».

    El atajo textual («sin `skipif` no hay gate») lo daba por bueno y ni lo parseaba.
    """
    (tmp_path / "test_falso_modlevel.py").write_text(
        _MODULO_SONDA + "\n"
        "if not _reachable('h', 1):\n"
        "    pytest.skip('sin hw', allow_module_level=True)\n"
        "\n"
        "def test_gated():\n"
        "    pass\n"
        "\n"
        "def test_gated_dos():\n"
        "    pass\n",
        encoding="utf-8",
    )
    assert escanear_gates_socket(tmp_path) == {
        "test_falso_modlevel.py::test_gated",
        "test_falso_modlevel.py::test_gated_dos",
    }


def test_el_censo_no_confunde_un_skip_condicional_sin_sonda(
    escanear_gates_socket: Callable[[Path], set[str]], tmp_path: Path
) -> None:
    """El `allow_module_level` nuevo no puede volverse un cazamariposas."""
    (tmp_path / "test_falso_modlevel_libre.py").write_text(
        "import sys\n"
        "\n"
        "import pytest\n"
        "\n"
        "if sys.version_info < (3, 12):\n"
        "    pytest.skip('requiere 3.12', allow_module_level=True)\n"
        "\n"
        "def test_algo():\n"
        "    pass\n",
        encoding="utf-8",
    )
    assert escanear_gates_socket(tmp_path) == set()


def test_resumen_dice_que_no_acredita_cuando_se_saltan_todos(
    resumen_gate_hardware: Callable[..., str],
) -> None:
    linea = resumen_gate_hardware(
        total=5, seleccionados=5, saltados=5, endpoint="192.168.3.92:18000"
    )
    assert linea == (
        "GATE #3 (hardware): 5/5 tests SALTADOS — Shake no alcanzable en "
        "192.168.3.92:18000. Esta suite NO acredita el gate #3."
    )


def test_resumen_acredita_solo_cuando_corren_los_cinco(
    resumen_gate_hardware: Callable[..., str],
) -> None:
    linea = resumen_gate_hardware(total=5, seleccionados=5, saltados=0, endpoint=None)
    assert linea == "GATE #3 (hardware): 5/5 EJECUTADOS contra el Shake real."


def test_resumen_intermedio_lo_dice_tal_cual(
    resumen_gate_hardware: Callable[..., str],
) -> None:
    linea = resumen_gate_hardware(
        total=5, seleccionados=5, saltados=2, endpoint="192.168.3.92:18000"
    )
    assert "2/5 SALTADOS" in linea
    assert "3/5 ejecutados" in linea
    assert "NO acredita el gate #3" in linea


def test_resumen_no_miente_cuando_no_se_selecciono_ninguno(
    resumen_gate_hardware: Callable[..., str],
) -> None:
    """0 saltados NO es «todo corrió»: puede ser que ni se colectaran."""
    linea = resumen_gate_hardware(total=5, seleccionados=0, saltados=0, endpoint=None)
    assert "EJECUTADOS" not in linea
    assert "0/5 SELECCIONADOS" in linea
    assert "NO acredita el gate #3" in linea


class _ReporteFalso:
    """Un reporte de pytest se distingue de un item por tener `when`."""

    def __init__(self, nodeid: str, longrepr: object = "", when: str = "call") -> None:
        self.nodeid = nodeid
        self.longrepr = longrepr
        self.when = when


class _ItemFalso:
    def __init__(self, nodeid: str) -> None:
        self.nodeid = nodeid


def test_un_test_deseleccionado_no_cuenta_como_ejecutado(
    contar_gates_hardware: Callable[..., tuple[set[str], set[str], str | None]],
) -> None:
    """`stats["deselected"]` guarda ITEMS: `-k` no ejecuta nada y no acredita nada."""
    gated = {"test_hw.py::test_a", "test_hw.py::test_b"}
    stats = {
        "passed": [_ReporteFalso("tests/test_hw.py::test_a")],
        "deselected": [_ItemFalso("tests/test_hw.py::test_b")],
    }
    vistos, saltados, _ = contar_gates_hardware(stats, gated)
    assert vistos == {"test_hw.py::test_a"}
    assert saltados == set()


def test_el_endpoint_del_resumen_sale_del_motivo_real_del_skip(
    contar_gates_hardware: Callable[..., tuple[set[str], set[str], str | None]],
) -> None:
    """No se adivina desde el entorno si el propio skip ya dice dónde falló."""
    stats = {
        "skipped": [
            _ReporteFalso(
                "tests/test_hw.py::test_a[EHZ]",
                longrepr=(
                    "tests/test_hw.py",
                    10,
                    "Skipped: Raspberry Shake no alcanzable en 10.0.0.5:18000 (gate #3 hardware)",
                ),
                when="setup",
            )
        ],
        "warnings": [object()],  # sin nodeid: no debe reventar el conteo
    }
    vistos, saltados, endpoint = contar_gates_hardware(stats, {"test_hw.py::test_a"})
    assert vistos == saltados == {"test_hw.py::test_a"}
    assert endpoint == "10.0.0.5:18000"


# ---------------------------------------------------------------------------
# Capa 2 · la red que NO depende de la sintaxis (F5)
# ---------------------------------------------------------------------------
#
# La capa 1 reduce el agujero; no lo cierra. Un censo por reconocimiento de patrones
# siempre tendrá una forma que no vio — y hay formas que NINGÚN AST puede ver, como
# un `pytest.skip()` llamado en tiempo de ejecución dentro del cuerpo o desde un
# fixture. Por eso la segunda red no mira código: mira los REPORTES de la corrida y
# exige que cada test saltado esté declarado (archivo + motivo). Cualquier skip nuevo
# —de socket, de `node` o de lo que sea— pone la corrida en rojo hasta que se declare.
#
# El precedente es T-2.58: el `skipif` de `node` de `test_local_api_panel.py` saltaba
# 67 tests en silencio con el job en verde, y sólo se descubrió a mano.


def _correr_pytest_aislado(directorio: Path) -> subprocess.CompletedProcess[str]:
    """Corre pytest sobre `directorio` con ESTE conftest cargado como plugin.

    `-p conftest` + `PYTHONPATH=tests/` es la única forma de ejercer los hooks reales
    (`pytest_sessionfinish`) sin escribir dentro del árbol de tests del repo. Se mide
    el CÓDIGO DE SALIDA porque es lo único que CI mira: que el resumen imprima algo
    no rompe ningún build.
    """
    entorno = {
        **os.environ,
        "PYTHONPATH": str(_TESTS_DIR),
        "GPIOZERO_PIN_FACTORY": "mock",
    }
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "conftest",
            str(directorio),
        ],
        capture_output=True,
        text=True,
        env=entorno,
        cwd=str(directorio),
        check=False,
    )


def test_un_skip_nuevo_y_no_declarado_rompe_el_build(tmp_path: Path) -> None:
    """(a) De cualquier tipo: uno en tiempo de ejecución, invisible para todo AST."""
    (tmp_path / "test_intruso.py").write_text(
        "import pytest\n"
        "\n"
        "\n"
        "def test_se_salta_en_caliente():\n"
        "    pytest.skip('el gabinete nuevo no está cableado')\n"
        "\n"
        "\n"
        "@pytest.mark.skip(reason='pendiente de hardware')\n"
        "def test_se_salta_por_marca():\n"
        "    pass\n"
        "\n"
        "\n"
        "def test_normal():\n"
        "    assert True\n",
        encoding="utf-8",
    )
    res = _correr_pytest_aislado(tmp_path)
    assert res.returncode != 0, (
        "un skip no declarado dejó el build en VERDE:\n" + res.stdout + res.stderr
    )
    assert "SKIP NO DECLARADO" in res.stdout, res.stdout
    assert "test_intruso.py::test_se_salta_en_caliente" in res.stdout
    assert "test_intruso.py::test_se_salta_por_marca" in res.stdout
    assert "1 passed" in res.stdout, "los tests que sí corren tienen que seguir corriendo"


def test_un_skip_declarado_deja_el_build_en_verde(tmp_path: Path) -> None:
    """(b) La red no puede ser un freno de mano: lo declarado pasa."""
    # Mismo nombre de archivo y mismo motivo que la declaración real del panel: la
    # declaración es (archivo, motivo), no sólo motivo.
    (tmp_path / "test_local_api_panel.py").write_text(
        "import pytest\n"
        "\n"
        "\n"
        "def test_render_del_panel():\n"
        "    pytest.skip('node no está en el PATH: el render del panel no se puede ejecutar')\n"
        "\n"
        "\n"
        "def test_normal():\n"
        "    assert True\n",
        encoding="utf-8",
    )
    res = _correr_pytest_aislado(tmp_path)
    assert res.returncode == 0, (
        "un skip DECLARADO puso el build en rojo:\n" + res.stdout + res.stderr
    )
    assert "SKIP NO DECLARADO" not in res.stdout


def test_el_mismo_motivo_en_otro_archivo_no_esta_declarado(
    skips_huerfanos: Callable[[dict[str, list]], list[tuple[str, str]]],
) -> None:
    """El caso que la capa 1 no puede prometer: un gate NUEVO en un archivo NUEVO.

    Copiar el `skipif` del Shake a `test_gpio_hardware.py` escrito de una forma que el
    censo no reconozca deja el censo mudo — pero el skip sigue apareciendo en los
    reportes, y ahí no hay sintaxis que valga.
    """
    motivo = "Raspberry Shake no alcanzable en 192.168.3.92:18000 (gate #3 hardware)"
    stats = {
        "skipped": [
            _ReporteFalso(
                "tests/test_gpio_hardware.py::test_rele_real",
                longrepr=("tests/test_gpio_hardware.py", 10, f"Skipped: {motivo}"),
                when="setup",
            )
        ]
    }
    assert skips_huerfanos(stats) == [("test_gpio_hardware.py::test_rele_real", motivo)]


def test_los_skips_declarados_no_ensucian(
    skips_huerfanos: Callable[[dict[str, list]], list[tuple[str, str]]],
) -> None:
    sin_shake = "Raspberry Shake no alcanzable en 192.168.3.92:18000 (gate #3 hardware)"
    stats = {
        "skipped": [
            _ReporteFalso(
                "tests/test_signal_hardware.py::test_compute_features_on_real_packet_is_sane",
                longrepr=(
                    "tests/test_signal_hardware.py",
                    30,
                    f"Skipped: {sin_shake}",
                ),
                when="setup",
            ),
            _ReporteFalso(
                "tests/test_local_api_panel.py::test_panel_pinta_lo_que_dice[EHZ]",
                longrepr=(
                    "tests/test_local_api_panel.py",
                    34,
                    "Skipped: node no está en el PATH: el render del panel no se puede ejecutar",
                ),
                when="setup",
            ),
        ],
        "passed": [_ReporteFalso("tests/test_rules.py::test_algo")],
        "warnings": [object()],  # sin nodeid ni `when`: no debe reventar
    }
    assert skips_huerfanos(stats) == []


def test_el_veredicto_no_depende_de_si_el_shake_responde(
    skips_huerfanos: Callable[[dict[str, list]], list[tuple[str, str]]],
) -> None:
    """(c) CI (sin Shake, 5 saltados) y el gabinete (con Shake, 5 corriendo): igual.

    Lo declarado PUEDE saltarse, no TIENE que saltarse. Por eso no se compara contra
    un número esperado de skips: eso sí dependería del hardware.
    """
    motivo = "Raspberry Shake no alcanzable en 192.168.3.92:18000 (gate #3 hardware)"
    sin_shake = {
        "skipped": [
            _ReporteFalso(
                f"tests/{test_id.replace('::', '::')}",
                longrepr=(test_id.split("::")[0], 30, f"Skipped: {motivo}"),
                when="setup",
            )
            for test_id in GATES_HARDWARE
        ]
    }
    con_shake = {
        "passed": [_ReporteFalso(f"tests/{test_id}") for test_id in GATES_HARDWARE],
    }
    assert skips_huerfanos(sin_shake) == []
    assert skips_huerfanos(con_shake) == []


def test_un_xfail_no_es_un_skip(
    skips_huerfanos: Callable[[dict[str, list]], list[tuple[str, str]]],
) -> None:
    """`xfailed` tiene su propia categoría en `stats`; la red mira `skipped`."""
    stats = {
        "xfailed": [_ReporteFalso("tests/test_x.py::test_y", longrepr="", when="call")],
    }
    assert skips_huerfanos(stats) == []


def test_un_test_nuevo_en_un_archivo_YA_declarado_no_hereda_el_permiso(
    skips_huerfanos: Callable[[dict[str, list]], list[tuple[str, str]]],
) -> None:
    """El agujero que quedaba entre las dos capas, y por donde cabía el fallo entero.

    Añadir un SEXTO test a `test_signal_hardware.py` escrito de una forma que el AST
    no reconozca dejaba mudas a las dos redes a la vez: la capa 1 seguía censando 5
    (y su test de igualdad pasaba) y la capa 2 lo daba por declarado, porque el
    archivo y el motivo son los mismos que los de los cinco legítimos. Job verde
    cubriendo un gate menos — exactamente lo que T-2.63 existe para impedir.

    Por eso la declaración del gate #3 no es (archivo, motivo) sino (archivo, motivo,
    IDS): saltarse tiene permiso; saltarse SIN estar en el registro, no.
    """
    motivo = "Raspberry Shake no alcanzable en 192.168.3.92:18000 (gate #3 hardware)"
    intruso = "tests/test_signal_hardware.py::test_features_nuevo_sin_registrar"
    stats = {
        "skipped": [
            _ReporteFalso(
                intruso,
                longrepr=("tests/test_signal_hardware.py", 40, f"Skipped: {motivo}"),
                when="setup",
            )
        ]
    }
    assert skips_huerfanos(stats) == [
        ("test_signal_hardware.py::test_features_nuevo_sin_registrar", motivo)
    ]


def test_un_sexto_gate_en_el_archivo_declarado_rompe_el_BUILD(tmp_path: Path) -> None:
    """(a) de verdad: código de salida 1, que es lo único que CI mira.

    Reproduce el fallo completo en un árbol de mentira: mismo archivo declarado, mismo
    motivo palabra por palabra que los cinco legítimos, y un test que nadie registró.
    Antes salía verde por partida doble; ahora el proceso termina en rojo.

    No sondea nada, así que el veredicto es idéntico con Shake y sin Shake — el skip
    del intruso se escribe a mano en vez de depender de que el hardware falte.
    """
    (tmp_path / "test_signal_hardware.py").write_text(
        "import pytest\n"
        "\n"
        "_MOTIVO = 'Raspberry Shake no alcanzable en 192.168.3.92:18000 (gate #3 hardware)'\n"
        "\n"
        "\n"
        "def test_compute_features_on_real_packet_is_sane():\n"
        "    pytest.skip(_MOTIVO)\n"
        "\n"
        "\n"
        "def test_features_nuevo_que_nadie_registro():\n"
        "    pytest.skip(_MOTIVO)\n",
        encoding="utf-8",
    )
    res = _correr_pytest_aislado(tmp_path)
    assert res.returncode != 0, (
        "un gate NUEVO en un archivo ya declarado dejó el build en VERDE:\n"
        + res.stdout
        + res.stderr
    )
    assert "test_signal_hardware.py::test_features_nuevo_que_nadie_registro" in res.stdout
    assert (
        "test_signal_hardware.py::test_compute_features_on_real_packet_is_sane"
        not in (res.stdout.split("SKIP NO DECLARADO")[-1])
    ), "el permiso nominal de los cinco registrados no puede haberse perdido"


def test_los_cinco_del_registro_siguen_pudiendo_saltarse(
    skips_huerfanos: Callable[[dict[str, list]], list[tuple[str, str]]],
) -> None:
    """(b) La declaración por ids no puede convertirse en un freno de mano."""
    motivo = "Raspberry Shake no alcanzable en 192.168.3.92:18000 (gate #3 hardware)"
    stats = {
        "skipped": [
            _ReporteFalso(
                f"tests/{test_id}",
                longrepr=(test_id.split("::")[0], 30, f"Skipped: {motivo}"),
                when="setup",
            )
            for test_id in GATES_HARDWARE
        ]
    }
    assert skips_huerfanos(stats) == []


def test_la_declaracion_del_gate_hardware_lista_exactamente_el_registro(
    skips_declarados: tuple,
) -> None:
    """Las dos listas se vigilan mutuamente: si divergen, alguien tocó una sola.

    `GATES_HARDWARE` dice qué acredita cada test; la declaración de `conftest.py`
    dice quién puede saltarse. Un test nuevo tiene que entrar en las DOS.
    """
    declarados: set[str] = set()
    for declarado in skips_declarados:
        for sub_id in getattr(declarado, "ids", ()) or ():
            declarados.add(f"{declarado.archivo}::{sub_id}")
    assert declarados == set(GATES_HARDWARE), (
        "la declaración de skips del gate #3 y GATES_HARDWARE divergieron:\n"
        f"  declarados y no registrados: {sorted(declarados - set(GATES_HARDWARE))}\n"
        f"  registrados y no declarados: {sorted(set(GATES_HARDWARE) - declarados)}"
    )


def test_el_veredicto_por_ids_tampoco_depende_del_shake(
    skips_huerfanos: Callable[[dict[str, list]], list[tuple[str, str]]],
) -> None:
    """(c) La comprobación por ids es de SUBCONJUNTO, no de igualdad.

    Con Shake no se salta nadie (conjunto vacío ⊆ registro) y sin Shake se saltan los
    cinco (registro ⊆ registro): mismo veredicto verde. Un sexto sin registrar rompe
    en los dos escenarios en cuanto se salta, que es cuando el gate queda mudo.
    """
    motivo = "Raspberry Shake no alcanzable en 192.168.3.92:18000 (gate #3 hardware)"
    con_shake = {"passed": [_ReporteFalso(f"tests/{t}") for t in GATES_HARDWARE]}
    sin_shake = {
        "skipped": [
            _ReporteFalso(
                f"tests/{t}",
                longrepr=(t.split("::")[0], 30, f"Skipped: {motivo}"),
                when="setup",
            )
            for t in GATES_HARDWARE
        ]
    }
    assert skips_huerfanos(con_shake) == skips_huerfanos(sin_shake) == []


def test_formas_que_el_censo_AST_no_puede_ver(
    escanear_gates_socket: Callable[[Path], set[str]], tmp_path: Path
) -> None:
    """Inventario HONESTO de lo que la capa 1 sigue sin ver, para no leerla como cerrada.

    Un censo por reconocimiento de patrones nunca las ve todas; lo que no se puede
    permitir es creerse que sí. Estas tres se dejan abiertas a sabiendas y las cubre
    la capa 2, que mira los REPORTES y no la sintaxis:

    - **`subprocess`** (`nc -z`, `ping`): gate de hardware válido y el censo no lo ve.
      Se deja fuera a propósito — `subprocess.run` aparece en `test_local_api_panel.py`
      (lanza node) y en este mismo archivo, así que tratarlo como llamada de red
      convertiría el censo en un cazamariposas y el gate #3 pasaría a "acreditar"
      tests que jamás tocan el Shake. El falso positivo es peor que el falso negativo
      aquí, porque el falso positivo MIENTE en verde.
    - **`getattr` dinámico**: `_f = getattr(socket, 'create_connection')`. Ningún AST
      resuelve eso sin ejecutar el módulo, y ejecutarlo es justo lo que el censo evita
      (pagaría la sonda de 0.6 s por archivo, que es por lo que es estático).
    - **gate en un `conftest.py`**: un fixture autouse que llama `pytest.skip()`. El
      censo sólo recorre archivos de test; un `conftest.py` puede apagar toda una
      carpeta sin aparecer en él.
    """
    (tmp_path / "test_falso_subproc.py").write_text(
        "import subprocess\n"
        "\n"
        "import pytest\n"
        "\n"
        "\n"
        "def _arriba(host, port):\n"
        "    hecho = subprocess.run(['nc', '-z', host, str(port)], check=False)\n"
        "    return hecho.returncode == 0\n"
        "\n"
        "\n"
        "pytestmark = pytest.mark.skipif(not _arriba('h', 1), reason='sin hw')\n"
        "\n"
        "def test_gated():\n"
        "    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "test_falso_getattr.py").write_text(
        "import socket\n"
        "\n"
        "import pytest\n"
        "\n"
        "_abrir = getattr(socket, 'create_connection')\n"
        "\n"
        "\n"
        "def _arriba(host, port):\n"
        "    try:\n"
        "        _abrir((host, port), timeout=0.6).close()\n"
        "    except OSError:\n"
        "        return False\n"
        "    return True\n"
        "\n"
        "\n"
        "pytestmark = pytest.mark.skipif(not _arriba('h', 1), reason='sin hw')\n"
        "\n"
        "def test_gated():\n"
        "    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "conftest.py").write_text(
        "import socket\n"
        "\n"
        "import pytest\n"
        "\n"
        "\n"
        "@pytest.fixture(autouse=True)\n"
        "def _gate_de_hardware():\n"
        "    try:\n"
        "        socket.create_connection(('h', 1), timeout=0.6).close()\n"
        "    except OSError:\n"
        "        pytest.skip('sin hw')\n",
        encoding="utf-8",
    )
    (tmp_path / "test_falso_por_fixture.py").write_text(
        "def test_gated():\n    pass\n", encoding="utf-8"
    )
    assert escanear_gates_socket(tmp_path) == set(), (
        "si esto empieza a pasar, el censo ganó cobertura: quita del inventario la "
        "forma que ya se caza y conviértela en un test de los de arriba"
    )


def test_cada_skip_declarado_apunta_a_un_archivo_que_existe(
    skips_declarados: tuple,
) -> None:
    """Una declaración huérfana es un permiso abierto para siempre: que se note."""
    assert skips_declarados, "sin declaraciones, la red no protege nada"
    for declarado in skips_declarados:
        assert (_TESTS_DIR / declarado.archivo).is_file(), (
            f"la declaración de skip apunta a {declarado.archivo}, que ya no existe: "
            "bórrala o corrígela"
        )
        assert declarado.porque.strip(), f"{declarado.archivo} no dice POR QUÉ puede saltarse"
