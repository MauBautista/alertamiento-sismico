"""T-2.73.a · La huella del origen tiene que poder tomarse DONDE vive el dump.

El cron de las 08:00 corre en el EC2 de la DB. Allí no hay checkout del repo:
lo único que sabe ejecutar código Python de TAKAB es el contenedor de la nube
co-locada, que corre la imagen `takab/cloud` construida con `api/Dockerfile`.

La ficha declaraba como "incógnita real" si ese contenedor tiene el código para
invocar `restore_check`. Lo tiene —`COPY api/src api/src` y `psycopg[binary]` es
dependencia de runtime, no de dev— pero **le falta el dato**: `db/schema.sql` no
viaja en la imagen, y `capture_baseline()` lo leía para dos cosas (el nombre de
la función guarda y la lista de roles). Resultado: el comando documentado en el
§9.1 del runbook moría con `FileNotFoundError` la primera noche, y el fallo solo
se habría visto EN LA VENTANA AWS.

Estos tests fijan la frontera. La lista de lo que la imagen lleva dentro **se
deriva del propio `api/Dockerfile`**: si mañana alguien añade o quita un `COPY`,
esto se entera. Enumerarla a mano habría sido escribir por segunda vez lo que ya
está escrito, y las dos copias divergen.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import psycopg
import pytest

from takab_api.ops import restore_check as rc
from takab_api.ops.restore_check import capture_baseline, declared_expectations

REPO = Path(__file__).resolve().parents[3]
DOCKERFILE = REPO / "api" / "Dockerfile"


# --------------------------------------------------------------------------- la imagen


def rutas_de_la_imagen(dockerfile: Path = DOCKERFILE) -> set[str]:
    """Qué rutas del repo acaban DENTRO de la imagen, leído de sus `COPY`.

    Se derivan, no se enumeran: un `COPY` nuevo entra solo y uno borrado
    desaparece solo. Devuelve rutas relativas a la raíz del repo, que es también
    el layout que la imagen replica bajo `/takab` (`WORKDIR /takab` + destinos
    con el mismo nombre que el origen — condición que este mismo módulo exige
    más abajo).
    """
    rutas: set[str] = set()
    texto = dockerfile.read_text(encoding="utf-8")
    # Continuaciones de línea primero: un COPY partido en varias líneas es un
    # solo COPY.
    texto = re.sub(r"\\\n\s*", " ", texto)
    for linea in texto.splitlines():
        if not linea.strip().upper().startswith("COPY "):
            continue
        tokens = [t for t in linea.split()[1:] if not t.startswith("--")]
        *origenes, destino = tokens
        for origen in origenes:
            if destino.endswith("/"):
                rutas.add(f"{destino.rstrip('/')}/{Path(origen).name}")
            else:
                rutas.add(destino)
    return rutas


def en_la_imagen(ruta: str) -> bool:
    return any(ruta == p or ruta.startswith(f"{p}/") for p in rutas_de_la_imagen())


def test_el_dockerfile_copia_al_mismo_sitio_del_que_viene() -> None:
    """`_repo_root()` sube 4 niveles desde el módulo: eso solo vale si el destino
    dentro de la imagen se llama igual que el origen en el repo.

    Si un `COPY api/src /app/src` entrara aquí, `Path(__file__).parents[4]` ya no
    apuntaría a una raíz de repo y todo el razonamiento de este archivo se
    quedaría sin suelo — sin que nada se pusiera rojo.
    """
    texto = re.sub(r"\\\n\s*", " ", DOCKERFILE.read_text(encoding="utf-8"))
    for linea in texto.splitlines():
        if not linea.strip().upper().startswith("COPY "):
            continue
        tokens = [t for t in linea.split()[1:] if not t.startswith("--")]
        *origenes, destino = tokens
        for origen in origenes:
            esperado = (
                f"{destino.rstrip('/')}/{Path(origen).name}" if destino.endswith("/") else destino
            )
            assert esperado == origen, (
                f"el Dockerfile copia {origen!r} a {esperado!r}: la imagen deja de replicar el "
                "layout del repo y `_repo_root()` (parents[4]) apunta a otra cosa"
            )


def test_la_imagen_lleva_el_codigo_y_la_migracion_inicial_pero_NO_el_ddl() -> None:
    """La frontera exacta, escrita para que la ventana AWS no la descubra sola."""
    assert en_la_imagen("api/src/takab_api/ops/restore_check.py"), (
        "sin el módulo en la imagen no hay nada que invocar desde el cron"
    )
    assert en_la_imagen("api/migrations/versions/0001_initial_schema.py"), (
        "de aquí salen los roles declarados; si dejara de viajar, la huella no "
        "podría registrar privilegios"
    )
    assert not en_la_imagen("db/schema.sql"), (
        "si algún día el DDL entra en la imagen, revisa este archivo entero: la "
        "razón de ser del desacoplamiento de `capture_baseline` desaparece"
    )


def test_psycopg_es_dependencia_de_runtime_no_de_dev() -> None:
    """Un `pip install -e ./api` sin extras tiene que traer el driver.

    Ya pasó una vez con `httpx` (comentario en `api/pyproject.toml`): estaba solo
    en el extra `dev` y el worker `notify` moría al arrancar en la nube.
    """
    texto = (REPO / "api" / "pyproject.toml").read_text(encoding="utf-8")
    principales = texto.split("[project.optional-dependencies]")[0]
    assert "psycopg" in principales


# --------------------------------------------------------------------------- la huella


@pytest.fixture
def raiz_como_la_imagen(tmp_path: Path) -> Path:
    """Una raíz que contiene EXACTAMENTE lo que la imagen lleva dentro.

    Enlaces simbólicos a los originales: el test mide la ausencia de `db/`, no
    el coste de copiar el árbol.
    """
    raiz = tmp_path / "takab"
    for prefijo in sorted(rutas_de_la_imagen()):
        origen = REPO / prefijo
        if not origen.exists():
            continue
        destino = raiz / prefijo
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.symlink_to(origen, target_is_directory=origen.is_dir())
    assert not (raiz / "db" / "schema.sql").exists()
    return raiz


def test_la_huella_se_toma_con_lo_unico_que_la_imagen_lleva_dentro(
    seeded: psycopg.Connection, raiz_como_la_imagen: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El test que estaba en rojo: dentro del contenedor no hay `db/schema.sql`.

    Antes de T-2.73.a esto moría con
    `FileNotFoundError: .../db/schema.sql`, y la primera noche que el cron
    intentara escribir la huella no habría huella — pero sí un dump, o sea un
    veredicto INDETERMINADO en el peor momento posible.
    """
    monkeypatch.setattr(rc, "_repo_root", lambda: raiz_como_la_imagen)
    huella = capture_baseline(seeded)
    assert huella["tables"], "una huella sin tablas no acredita nada"
    assert huella["privileges"], "sin privilegios registrados, `_check_privileges` se salta"
    assert any(v["append_only"] for v in huella["tables"].values()), (
        "sin tablas append-only marcadas se pierde la expectativa de compliance del origen"
    )


def _sin_lo_que_mueve_el_reloj(huella: dict) -> dict:
    """La huella menos lo único que cambia por el mero paso del tiempo.

    Dos capturas consecutivas sobre una base VIVA no pueden tener los mismos
    conteos: en READ COMMITTED cada sentencia toma su propio snapshot y
    cualquier escritura confirmada en medio se cuela. Que esa parte se mueva no
    es el defecto — es justo la razón de ser del anclaje al dump, y quien lo
    demuestra es `test_huella_anclada_al_dump.py`. Aquí se compara todo lo
    demás, que es donde vivía el acoplamiento con `db/schema.sql`.
    """
    copia = json.loads(json.dumps(huella))
    for volatil in ("captured_at", "data_tip", "cagg_rows", "sequences"):
        copia.pop(volatil, None)
    for tabla in copia["tables"].values():
        tabla.pop("rows", None)
    return copia


def test_la_huella_de_la_imagen_es_LA_MISMA_que_la_del_repo(
    seeded: psycopg.Connection, raiz_como_la_imagen: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un camino que solo se ejerce en producción es un camino sin probar.

    La huella que toma el cron dentro del contenedor y la que toma
    `restore_drill` desde el repo tienen que ser el mismo documento. Si
    divergieran, el ensayo local dejaría de acreditar el procedimiento real: el
    verde de `make restore-drill` estaría hablando de otra cosa.
    """
    # Se lee ANTES de parchear la raíz: con la raíz de la imagen puesta,
    # `declared_expectations` no puede leer `db/schema.sql` — que es justamente
    # lo que este archivo demuestra.
    roles_del_repo = declared_expectations().roles
    desde_el_repo = capture_baseline(seeded)
    monkeypatch.setattr(rc, "_repo_root", lambda: raiz_como_la_imagen)
    desde_la_imagen = capture_baseline(seeded)

    assert _sin_lo_que_mueve_el_reloj(desde_la_imagen) == _sin_lo_que_mueve_el_reloj(desde_el_repo)
    # Y explícitamente lo que el desacoplamiento podría haber roto en silencio:
    # las marcas append-only (venían de la función guarda del esquema) y los
    # roles cuyos privilegios se registran.
    assert {t for t, v in desde_la_imagen["tables"].items() if v["append_only"]} == {
        t for t, v in desde_el_repo["tables"].items() if v["append_only"]
    }
    assert {rol for por_rol in desde_la_imagen["privileges"].values() for rol in por_rol} == (
        roles_del_repo & set(desde_la_imagen["roles"])
    )


def test_sin_la_migracion_inicial_la_huella_se_niega_a_medias_tintas(
    seeded: psycopg.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La otra mitad del desacoplamiento: lo que SÍ sigue siendo obligatorio.

    Los roles salen de la migración 0001, que la imagen sí lleva. Si un día
    dejara de llevarla, la huella no puede salir "casi bien" con la sección de
    privilegios vacía: eso convertiría `privileges` en un SKIP silencioso el día
    del restore.
    """
    monkeypatch.setattr(rc, "_repo_root", lambda: tmp_path)
    with pytest.raises(FileNotFoundError):
        capture_baseline(seeded)


# --------------------------------------------------------------------------- la guarda


def test_la_funcion_guarda_sale_del_catalogo_y_dice_lo_mismo_que_el_esquema(
    seeded: psycopg.Connection,
) -> None:
    """Derivada de `pg_trigger`, no leída de `db/schema.sql` — y coinciden.

    El esquema la reconoce por el texto `BEFORE UPDATE OR DELETE ... FOR EACH
    ROW`; el catálogo, por los bits de `tgtype`. Son la misma frase dicha en dos
    idiomas, y por eso el desacoplamiento no pierde nada: `life_checkin_arco_guard`
    es BEFORE UPDATE a secas y queda fuera de las dos.
    """
    assert rc.catalog_guard_function(seeded) == declared_expectations().guard_function
    assert rc.catalog_guard_function(seeded) == "forbid_update_delete"


def test_la_guarda_derivada_del_catalogo_no_es_una_constante(
    seeded: psycopg.Connection,
) -> None:
    """No-vacuidad: si no hay triggers de esa forma, no se inventa un nombre."""
    seeded.execute(
        "DO $$ DECLARE t record; BEGIN "
        "FOR t IN SELECT c.relname AS tabla, tg.tgname AS trg FROM pg_trigger tg "
        "JOIN pg_class c ON c.oid = tg.tgrelid JOIN pg_namespace n ON n.oid = c.relnamespace "
        "JOIN pg_proc p ON p.oid = tg.tgfoid "
        "WHERE NOT tg.tgisinternal AND n.nspname = 'public' "
        "AND p.proname = 'forbid_update_delete' LOOP "
        "EXECUTE format('DROP TRIGGER %I ON %I', t.trg, t.tabla); END LOOP; END $$"
    )
    assert rc.catalog_guard_function(seeded) is None


def test_la_huella_pierde_la_marca_append_only_si_el_trigger_no_esta(
    seeded: psycopg.Connection,
) -> None:
    """La marca del origen sale del catálogo del origen, no de una lista."""
    antes = capture_baseline(seeded)
    assert antes["tables"]["audit_log"]["append_only"] is True
    seeded.execute("DROP TRIGGER trg_audit_log_append_only ON audit_log")
    despues = capture_baseline(seeded)
    assert despues["tables"]["audit_log"]["append_only"] is False


# --------------------------------------------------------------------------- runbook

RUNBOOK = REPO / "takab-docs" / "runbooks" / "RUNBOOK-backup-restore-db.md"


def test_el_runbook_ya_no_declara_el_hueco_que_esta_ficha_cierra() -> None:
    """El §9.1 decía "el cron de las 08:00 sube el `.dump` y nada más"."""
    texto = RUNBOOK.read_text(encoding="utf-8")
    assert "--save-baseline" in texto
    assert "fingerprint.json" in texto
    assert "sube el `.dump` y nada más" not in texto, (
        "el hueco está cerrado: si el §9.1 lo sigue declarando abierto, o el "
        "runbook miente o la tarea no está hecha"
    )


def test_el_ensayo_local_sigue_siendo_el_espejo_del_cron() -> None:
    """`make restore-drill` toma la huella con el mismo código que el cron."""
    drill = (REPO / "api" / "src" / "takab_api" / "ops" / "restore_drill.py").read_text(
        encoding="utf-8"
    )
    assert "capture_baseline" in drill
