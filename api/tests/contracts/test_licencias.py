"""La guarda de licencias (T-3.10.b · `D-24`) — y sobre todo que PUEDA fallar.

Una guarda que nunca ha fallado no es una guarda: es una función que nadie ha ejercido.
El criterio de la ficha lo pide con esas palabras («prueba negativa»), así que la mitad de
este archivo son casos que TIENEN que salir en rojo.
"""

from __future__ import annotations

import importlib.util
import textwrap
from pathlib import Path

_CI = Path(__file__).resolve().parents[3] / "ci" / "licencias.py"
_spec = importlib.util.spec_from_file_location("licencias", _CI)
lic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lic)


class _Meta:
    def __init__(self, nombre: str, clasificadores: list[str], licencia: str = "") -> None:
        self._n, self._c, self._l = nombre, clasificadores, licencia

    def get(self, clave: str, defecto=None):
        return {"Name": self._n, "License": self._l}.get(clave, defecto)

    def get_all(self, clave: str):
        return self._c if clave == "Classifier" else []


class _Dist:
    def __init__(
        self, nombre: str, clasificadores=(), licencia: str = "", version: str = "1.0"
    ) -> None:
        self.metadata = _Meta(nombre, list(clasificadores), licencia)
        self.version = version


# --------------------------------------------------- lo que TIENE que fallar


def test_la_AGPL_se_detecta_por_su_classifier() -> None:
    d = _Dist("cosa", ["License :: OSI Approved :: GNU Affero General Public License v3"])
    assert lic.licencia_de(d)[0] == "copyleft-fuerte"


def test_la_GPL_tambien() -> None:
    d = _Dist("cosa", ["License :: OSI Approved :: GNU General Public License v3 (GPLv3)"])
    assert lic.licencia_de(d)[0] == "copyleft-fuerte"


def test_sin_classifier_se_detecta_por_SPDX() -> None:
    assert lic.licencia_de(_Dist("cosa", licencia="AGPL-3.0-or-later"))[0] == "copyleft-fuerte"
    assert lic.licencia_de(_Dist("cosa", licencia="GPLv2"))[0] == "copyleft-fuerte"


def test_un_uv_lock_que_resuelva_ultralytics_pone_el_build_en_ROJO(tmp_path: Path) -> None:
    """La prueba negativa que pide la ficha: instalar un prohibido a propósito."""
    lock = tmp_path / "uv.lock"
    lock.write_text(
        textwrap.dedent("""
            version = 1
            [[package]]
            name = "ultralytics"
            version = "8.3.0"
            [[package]]
            name = "numpy"
            version = "2.0.0"
        """),
        encoding="utf-8",
    )
    fallos = lic.revisar_lock(lock)
    assert len(fallos) == 1
    assert "ultralytics" in fallos[0]
    assert "AGPL" in fallos[0]


def test_el_lock_ve_lo_TRANSITIVO_aunque_este_job_no_lo_tenga_instalado(tmp_path: Path) -> None:
    """`uv.lock` lista la resolución completa: un prohibido que entra como dependencia de
    una dependencia sale aquí igual."""
    lock = tmp_path / "uv.lock"
    lock.write_text(
        'version = 1\n[[package]]\nname = "deep-sort-realtime"\nversion = "1.3"\n', encoding="utf-8"
    )
    assert lic.revisar_lock(lock)


def test_un_onnx_con_AGPL_en_los_metadatos_se_caza(tmp_path: Path) -> None:
    """Un peso no trae `setup.py`: ningún escáner de paquetes lo ve."""
    (tmp_path / "modelo.onnx").write_bytes(b"\x08\x07protobuf...license:AGPL-3.0...")
    fallos = lic.revisar_onnx(tmp_path)
    assert len(fallos) == 1 and "AGPL" in fallos[0]


# ------------------------------------------- lo que NO puede dar falso positivo


def test_matplotlib_y_scipy_NO_se_marcan_aunque_su_texto_mencione_la_GPL() -> None:
    """El falso positivo real, medido en este árbol: las dos vuelcan el TEXTO COMPLETO de
    su licencia en el campo `License`, y ese texto habla de la GPL para decir que son
    compatibles. Con un `grep GPL` las dos salían marcadas — y un guard que grita en falso
    enseña a ignorarlo."""
    matplotlib = _Dist(
        "matplotlib",
        ["License :: OSI Approved :: Python Software Foundation License"],
        licencia=(
            "License agreement for matplotlib versions 1.3.0 and later\n"
            "...compatible with the GPL..."
        ),
    )
    assert lic.licencia_de(matplotlib)[0] == "permisiva"


def test_la_LGPL_no_hace_fallar_el_build() -> None:
    """Y no es un descuido: `D-24` eligió ffmpeg **LGPL** invocado como subproceso. Marcarla
    como prohibida haría fallar el build por el binario que la propia decisión escogió."""
    d = _Dist("algo", ["License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)"])
    assert lic.licencia_de(d)[0] == "permisiva"


def test_LGPL_en_texto_libre_tampoco_cuenta_como_GPL() -> None:
    """Sin la frontera por la izquierda, `LGPL-3.0` casaría contra `GPL-3.0`."""
    assert lic.licencia_de(_Dist("algo", licencia="LGPL-3.0-only"))[0] == "permisiva"


def test_una_licencia_permisiva_normal_pasa() -> None:
    assert (
        lic.licencia_de(_Dist("algo", ["License :: OSI Approved :: MIT License"]))[0] == "permisiva"
    )


# ------------------------------------------------------------ el árbol REAL


def test_el_arbol_de_hoy_esta_limpio() -> None:
    """Si esto se pone rojo, alguien metió copyleft fuerte — o la clasificación se rompió."""
    fallos, inventario = lic.revisar_entorno()
    assert fallos == [], f"licencias no permitidas en el entorno: {fallos}"
    assert len(inventario) > 20, "el inventario está sospechosamente vacío"


def test_los_dos_locks_del_repo_no_resuelven_ningun_prohibido() -> None:
    raiz = Path(__file__).resolve().parents[3]
    for lock in (raiz / "api" / "uv.lock", raiz / "edge" / "uv.lock"):
        assert lock.exists(), f"falta {lock}"
        assert lic.revisar_lock(lock) == []


def test_los_avisos_de_terceros_se_GENERAN(tmp_path: Path) -> None:
    """Escritos a mano envejecerían en silencio, que es como envejecen todos los censos."""
    destino = tmp_path / "THIRD_PARTY_NOTICES.txt"
    lic.escribir_avisos([("numpy", "2.0", "BSD")], destino)
    texto = destino.read_text(encoding="utf-8")
    assert "numpy 2.0" in texto
    assert "No editar a mano" in texto


def test_la_lista_de_prohibidos_cubre_lo_que_la_decision_nombra() -> None:
    """`D-24` los nombra uno a uno; si alguien borra una entrada, este test lo dice."""
    for paquete in ("ultralytics", "deep-sort-realtime", "yolov6", "yolov7"):
        assert paquete in lic.PROHIBIDOS, f"{paquete} salió de la lista de prohibidos"


def test_toda_excepcion_lleva_su_razon_escrita() -> None:
    """Hoy no hay ninguna, a propósito: el día que haga falta una, que cueste escribirla."""
    for nombre, razon in lic.EXCEPCIONES.items():
        assert len(razon) >= 40, f"la excepción de {nombre} no explica por qué"
