"""T-2.73.a · La huella y el dump tienen que ver LA MISMA base.

`_check_row_counts` compara fila a fila y exige igualdad exacta — es la
comprobación que caza las «decenas de miles de filas perdidas en silencio» del
§4.1 del runbook. Esa exactitud tiene un precio que la ficha no nombraba:

La base de producción **no está quieta**. Los latidos de la flota escriben cada
minuto y la telemetría entra en continuo. Si la huella se toma a las 08:00:00 y
el `pg_dump` termina a las 08:04, el dump trae más filas que la huella y el
verificador declara **ROJO** sobre un restore perfecto. Un falso rojo el día del
desastre es peor que un INDETERMINADO: enseña al operador a desconfiar del
verificador, y entonces el verificador ya no sirve para nada.

La solución no es aflojar la comprobación (ahí está justamente su valor), sino
que las dos lecturas compartan **el mismo snapshot**: la huella abre una
transacción REPEATABLE READ, exporta su snapshot con `pg_export_snapshot()` y la
mantiene abierta mientras `pg_dump --snapshot=<id>` lo consume. Coste extra
sobre la base: ninguno — `pg_dump` ya mantiene abierta una transacción idéntica
durante todo el volcado.

Y el fallo tiene que ser fail-open PARA EL RESPALDO y fail-closed PARA LA HUELLA:
si la coordinación se rompe, el `.dump` sube igual (no se toca el respaldo que
hoy funciona) y la huella NO se escribe. Sin huella el veredicto es
INDETERMINADO, que es la verdad; con una huella desalineada sería ROJO, que es
mentira.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

import psycopg
import pytest

from takab_api.ops import restore_check as rc

REPO = Path(__file__).resolve().parents[3]
TABLA = "huella_anclada_t273a"


def _dsn() -> str:
    url = os.environ["DATABASE_URL"]
    return url.replace("postgresql+psycopg://", "postgresql://")


def _base() -> str:
    return psycopg.conninfo.conninfo_to_dict(_dsn())["dbname"]


@pytest.fixture
def tabla_testigo():
    """Una tabla COMETIDA (fuera de la transacción del fixture `conn`).

    El anclaje solo se puede demostrar contra escrituras que de verdad se
    confirmen mientras la huella está a medias: dentro de una transacción propia
    no hay nada que el snapshot pudiera dejar fuera.
    """
    admin = psycopg.connect(_dsn(), autocommit=True)
    admin.execute(f"DROP TABLE IF EXISTS {TABLA}")
    admin.execute(f"CREATE TABLE {TABLA} (n int)")
    admin.execute(f"INSERT INTO {TABLA} VALUES (1)")
    try:
        yield admin
    finally:
        admin.execute(f"DROP TABLE IF EXISTS {TABLA}")
        admin.close()


def _cli_en_hilo(argv: list[str]) -> tuple[threading.Thread, dict]:
    salida: dict = {}

    def correr() -> None:
        try:
            salida["rc"] = rc._cli(argv)
        except SystemExit as exc:  # argparse
            salida["rc"] = exc.code
        except BaseException as exc:  # noqa: BLE001 — el hilo no debe morir mudo
            salida["error"] = exc

    hilo = threading.Thread(target=correr, daemon=True)
    hilo.start()
    return hilo, salida


def _esperar(ruta: Path, segundos: float = 30.0) -> None:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if ruta.exists() and ruta.stat().st_size:
            return
        time.sleep(0.05)
    raise AssertionError(f"{ruta} no apareció en {segundos} s")


# --------------------------------------------------------------------------- el anclaje


def test_la_huella_queda_anclada_al_instante_que_ve_el_dump(
    tabla_testigo: psycopg.Connection, tmp_path: Path
) -> None:
    """El test que estaba en rojo: hoy el flag no existe y la huella deriva.

    Se comprueban LOS DOS extremos del cable:
      1. que `pg_dump --snapshot=<id>` vería exactamente 1 fila (se ejerce
         consumiendo el snapshot igual que lo haría él), y
      2. que la huella escrita registra 1 fila y no 3, pese a que las otras dos
         se confirmaron mientras la coordinación estaba abierta.
    """
    coord = tmp_path / "coord"
    coord.mkdir()
    huella = tmp_path / "huella.json"

    hilo, salida = _cli_en_hilo(
        [
            "--database",
            _base(),
            "--save-baseline",
            str(huella),
            "--coordinate-with-dump",
            str(coord),
        ]
    )
    _esperar(coord / "snapshot.id")
    snapshot = (coord / "snapshot.id").read_text(encoding="utf-8").strip()
    assert snapshot, "sin id de snapshot el `pg_dump` no tiene a qué anclarse"

    # Escrituras CONFIRMADAS después del snapshot: el ruido de una base viva.
    tabla_testigo.execute(f"INSERT INTO {TABLA} VALUES (2), (3)")
    assert tabla_testigo.execute(f"SELECT count(*) FROM {TABLA}").fetchone()[0] == 3

    # 1. Lo que vería `pg_dump --snapshot=<id>`.
    lector = psycopg.connect(_dsn())
    try:
        lector.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        lector.execute(f"SET TRANSACTION SNAPSHOT '{snapshot}'")
        assert lector.execute(f"SELECT count(*) FROM {TABLA}").fetchone()[0] == 1, (
            "el snapshot exportado no es el que la huella está leyendo"
        )
    finally:
        lector.rollback()
        lector.close()

    (coord / "dump.done").touch()
    hilo.join(timeout=120)
    assert not hilo.is_alive()
    assert "error" not in salida, salida.get("error")
    assert salida["rc"] == 0

    # 2. Lo que la huella registró.
    datos = json.loads(huella.read_text(encoding="utf-8"))
    assert datos["tables"][TABLA]["rows"] == 1, (
        "la huella se movió con la base: contra un dump anclado, `row_counts` "
        "declararía ROJO sobre un restore perfecto"
    )


def test_sin_la_marca_del_dump_no_se_escribe_media_huella(tmp_path: Path) -> None:
    """Fail-closed para la huella: si el dump no confirmó, no hay huella.

    Una huella escrita "por si acaso" cuando el dump falló es una huella que no
    corresponde a ningún dump del bucket, y el día del restore produce un ROJO
    inexplicable.
    """
    coord = tmp_path / "coord"
    coord.mkdir()
    huella = tmp_path / "huella.json"

    codigo = rc._cli(
        [
            "--database",
            _base(),
            "--save-baseline",
            str(huella),
            "--coordinate-with-dump",
            str(coord),
            "--coordination-timeout",
            "1",
        ]
    )
    assert codigo != 0
    assert not huella.exists()


def test_una_coordinacion_rancia_se_rechaza_antes_de_abrir_nada(tmp_path: Path) -> None:
    """`dump.done` de una corrida anterior ancla la huella al dump equivocado."""
    coord = tmp_path / "coord"
    coord.mkdir()
    (coord / "dump.done").touch()
    huella = tmp_path / "huella.json"

    codigo = rc._cli(
        [
            "--database",
            _base(),
            "--save-baseline",
            str(huella),
            "--coordinate-with-dump",
            str(coord),
        ]
    )
    assert codigo != 0
    assert not huella.exists()


def test_la_huella_sin_anclar_sigue_funcionando_y_lo_advierte(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """El camino de siempre (ensayo local, base quieta) no cambia de conducta."""
    huella = tmp_path / "huella.json"
    assert rc._cli(["--database", _base(), "--save-baseline", str(huella)]) == 0
    assert huella.exists()
    assert "sin anclar" in capsys.readouterr().out.lower()


def test_una_captura_que_revienta_no_deja_media_huella_en_el_disco(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El `aws s3 cp` que viene detrás no sabe distinguir un JSON truncado.

    La huella se escribe en un temporal del mismo directorio y se renombra:
    `rename(2)` es atómico dentro del mismo sistema de ficheros, así que o sube
    la huella entera o no sube nada.
    """
    huella = tmp_path / "huella.json"

    def revienta(*_args, **_kw):
        raise RuntimeError("la base se cayó a mitad del conteo")

    monkeypatch.setattr(rc, "capture_baseline", revienta)
    with pytest.raises(RuntimeError):
        rc._cli(["--database", _base(), "--save-baseline", str(huella)])
    assert not huella.exists()
    assert not list(tmp_path.iterdir()), f"quedó basura: {list(tmp_path.iterdir())}"


# --------------------------------------------------------------------------- el contrato

TPL = REPO / "infra" / "terraform" / "modules" / "database" / "backup_setup.sh.tpl"


def test_el_script_del_cron_y_el_cli_hablan_el_mismo_idioma() -> None:
    """El acoplamiento invisible: bash llama a Python por nombres de flag.

    Un `--save-baseline` renombrado en Python deja el cron muriendo cada noche a
    las 08:00 contra el correo de root de un EC2, o sea contra ningún sitio. Los
    flags que el script usa se derivan del propio script y se contrastan con el
    parser real.
    """
    script = TPL.read_text(encoding="utf-8")
    assert "takab_api.ops.restore_check" in script, "el script del cron ya no invoca el verificador"

    # Desde el nombre del módulo (los flags de `docker run` van ANTES y no son
    # suyos) hasta la primera línea que no continúa.
    lineas: list[str] = []
    for linea in script[script.index("takab_api.ops.restore_check") :].splitlines():
        lineas.append(linea)
        if not linea.rstrip().endswith("\\"):
            break
    usados = set(re.findall(r"(--[a-z][a-z0-9-]+)", "\n".join(lineas)))
    assert usados, "no se pudo leer ni un flag: el bloque de invocación cambió de forma"

    aceptados = {
        opcion for accion in rc.build_parser()._actions for opcion in accion.option_strings
    }
    desconocidos = sorted(usados - aceptados)
    assert not desconocidos, (
        f"el cron pasa flags que `restore_check` no acepta: {desconocidos} · "
        f"acepta {sorted(aceptados)}"
    )


def test_el_script_del_cron_toma_la_huella_anclada_al_dump() -> None:
    """No basta con que la escriba: tiene que escribirla anclada."""
    script = TPL.read_text(encoding="utf-8")
    assert "--coordinate-with-dump" in script
    assert "--snapshot=" in script, "el `pg_dump` del cron no consume el snapshot exportado"
