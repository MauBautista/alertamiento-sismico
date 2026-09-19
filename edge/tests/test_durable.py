"""[T-7.59] Que lo que promete sobrevivir a un corte de luz lo sobreviva.

⚠️ **POR QUÉ ESTE FICHERO NO PUEDE LIMITARSE A RELEER LO ESCRITO.** Una prueba
que escriba y vuelva a leer pasa en verde con `write_text` a pelo, con
`tmp + replace`, y con la versión durable — las tres. Es exactamente la prueba
que había, y por eso el defecto llegó al gabinete real: el 2026-09-19 se
desconectó el Pi para moverlo de sitio y `episodio.json` volvió con CERO BYTES.

Lo que hay que fijar es que las llamadas al sistema OCURREN, y en el orden que
las hace útiles:

    fsync(fichero)  →  rename  →  fsync(directorio)

Invertir las dos primeras deja el nombre apuntando a datos que aún no están en
el disco. Saltarse la tercera deja los datos en el disco y el nombre sólo en la
caché. Los dos fallos dan un fichero que se relee perfectamente… hasta el corte.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from takab_edge.durable import escribir_durable, fsync_dir


class _Espia:
    """Anota las llamadas al sistema en el ORDEN en que ocurren."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, destino: Path) -> None:
        self.traza: list[str] = []
        self.destino = destino
        real_fsync, real_replace = os.fsync, os.replace

        def fsync(fd: int) -> None:
            # Un fd de directorio y uno de fichero se distinguen por `fstat`.
            modo = os.fstat(fd).st_mode
            self.traza.append("fsync:dir" if os.path.stat.S_ISDIR(modo) else "fsync:fichero")
            real_fsync(fd)

        def replace(src, dst, **kw):  # noqa: ANN001, ANN003 - firma de os.replace
            self.traza.append("rename")
            return real_replace(src, dst, **kw)

        monkeypatch.setattr(os, "fsync", fsync)
        monkeypatch.setattr(os, "replace", replace)
        monkeypatch.setattr(Path, "replace", lambda s, d: replace(s, d))


def test_el_ORDEN_es_fsync_rename_fsync_del_directorio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El contrato entero, y es un orden, no un conjunto.

    · `fsync` del fichero ANTES del rename — si no, el nombre apunta a datos que
      todavía no están en el disco y el corte deja cero bytes.
    · `fsync` del directorio DESPUÉS — si no, los datos están pero el nombre no.
    """
    destino = tmp_path / "episodio.json"
    espia = _Espia(monkeypatch, destino)

    escribir_durable(destino, json.dumps({"event_id": "ev-1"}))

    assert espia.traza == ["fsync:fichero", "rename", "fsync:dir"], (
        "el orden es el contrato: los datos al disco, luego el nombre, luego la "
        f"entrada del directorio. Se observó {espia.traza}"
    )


def test_un_rename_SIN_fsync_no_pasa_esta_prueba(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La prueba de la prueba: que sepa distinguir el código defectuoso.

    Ésta es la versión que estuvo en producción y que perdió el episodio. Si
    este test dejara de fallar contra ella, el de arriba sería ceremonia.
    """
    destino = tmp_path / "episodio.json"
    espia = _Espia(monkeypatch, destino)

    def escribir_como_antes(path: Path, contenido: str) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(contenido, encoding="utf-8")
        tmp.replace(path)  # atómico, pero NO durable

    escribir_como_antes(destino, json.dumps({"event_id": "ev-1"}))

    assert espia.traza == ["rename"]
    assert "fsync:fichero" not in espia.traza
    assert "fsync:dir" not in espia.traza
    # Y sin embargo relee perfectamente: por eso una prueba de ida y vuelta no
    # ve nada. El fichero está bien HASTA que se corta la luz.
    assert json.loads(destino.read_text()) == {"event_id": "ev-1"}


def test_el_temporal_no_sobrevive_ni_pisa_el_glob(tmp_path: Path) -> None:
    """El `.tmp` desaparece, y mientras existe NO casa con `*.json`.

    `backfill` barre su directorio con `*.json` y manda a cuarentena lo que no
    parsea: un temporal visible desde ese barrido sería evidencia legítima
    apartada. `with_suffix(suffix + ".tmp")` da `x.json.tmp`, que no casa.
    """
    destino = tmp_path / "ev-1.json"
    escribir_durable(destino, "{}")

    assert destino.exists()
    assert list(tmp_path.glob("*.json")) == [destino]
    assert list(tmp_path.glob("*.tmp")) == []


def test_sobrescribir_deja_el_contenido_NUEVO_entero(tmp_path: Path) -> None:
    destino = tmp_path / "config-cache.json"
    escribir_durable(destino, json.dumps({"v": 1}))
    escribir_durable(destino, json.dumps({"v": 2, "mas": "largo que el anterior"}))

    assert json.loads(destino.read_text())["v"] == 2


def test_crea_el_directorio_que_falte(tmp_path: Path) -> None:
    destino = tmp_path / "sin" / "crear" / "x.json"
    escribir_durable(destino, "{}")
    assert destino.read_text() == "{}"


def test_fsync_dir_falla_RUIDOSAMENTE_si_el_directorio_no_existe(tmp_path: Path) -> None:
    """No se traga el error: quien llama decide, y en el gabinete la decisión
    suele ser «seguir sin persistir» — pero eso se escribe en el llamador, no
    se esconde aquí."""
    with pytest.raises(OSError):
        fsync_dir(tmp_path / "no-existe")


# ───────────────────────────────────── el censo, DERIVADO y no escrito a mano


def _escrituras_sin_durabilidad() -> list[str]:
    """Todo sitio de `takab_edge/` que escribe un fichero sin pasar por el helper.

    Se deriva del ÁRBOL, no de una lista: la próxima escritura la añade alguien
    que no leyó `T-7.59`, y una lista a mano no la ve. Mismo mecanismo que los
    censos de la consola y de la app.
    """
    import ast

    raiz = Path(__file__).resolve().parents[1] / "takab_edge"
    # Los que escriben a propósito SIN durabilidad, cada uno con su razón. La
    # lista se compara por IGUALDAD: arreglar uno obliga a borrar su línea.
    exentos = {
        # Ring de forma de onda: append continuo a 100 sps. Un fsync por paquete
        # es I/O en el camino de detección (regla de oro 1), y lo que se pierde
        # en un corte es el último segundo de un fichero que se reconstruye solo.
        "buffer/__init__.py",
        # Capturas del CCTV: cientos por incidente, y se regeneran del clip.
        "cctv/instantanea.py",
        # El grabador escribe con ffmpeg, no con Python.
        "cctv/recorder.py",
        # Generador de los JSON Schema: script de construcción, no corre en el
        # gabinete. Su salida se comitea y la vigila `make drift`.
        "schemas.py",
        # Acta del reflejo: reescribe el fichero ENTERO leyendo y recortando a
        # 200 filas. Su defecto NO es el fsync sino el read-modify-write, y se
        # arregla pasándolo a append como el ledger. Fichado aparte.
        "audit/reflejo.py",
    }
    sospechosos: list[str] = []
    for fichero in sorted(raiz.rglob("*.py")):
        rel = fichero.relative_to(raiz).as_posix()
        if rel in exentos or rel == "durable.py":
            continue
        arbol = ast.parse(fichero.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call) or not isinstance(nodo.func, ast.Attribute):
                continue
            # `x.write_text(...)` / `x.write_bytes(...)` sobre una ruta
            if nodo.func.attr in {"write_text", "write_bytes"}:
                sospechosos.append(f"{rel}:{nodo.lineno} → .{nodo.func.attr}()")
    return sospechosos


def test_CENSO_ninguna_escritura_nueva_se_salta_la_durabilidad() -> None:
    """La guarda que sobrevive a esta ficha.

    El defecto de `T-7.59` no fue no saber hacerlo: `cloud/` llevaba la receta
    correcta desde el principio y `rules/episode.py` tenía su propia versión sin
    los `fsync`. Dos copias de un procedimiento con una trampa dentro se separan
    solas, y nadie lo ve hasta que se va la luz.
    """
    sospechosos = _escrituras_sin_durabilidad()
    assert sospechosos == [], (
        "ESCRITURA A DISCO SIN PASAR POR `takab_edge.durable`.\n\n  "
        + "\n  ".join(sospechosos)
        + "\n\nSi el fichero PROMETE sobrevivir a un reinicio, usa "
        "`escribir_durable()`. Si se puede reconstruir, decláralo en `exentos` "
        "de este test CON SU RAZÓN: un fsync cuesta I/O bloqueante y hay caminos "
        "de este gabinete donde no se puede pagar."
    )
