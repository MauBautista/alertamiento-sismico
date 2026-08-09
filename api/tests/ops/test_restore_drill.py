"""T-2.73 · La guardia del ensayo, y el reloj que dice la verdad.

La guardia de `demo/run.py::_assert_exclusive_db` nació del hallazgo A-3: un
worker residente contaminó una acreditación entera y produjo fallos
deterministas sin pista del porqué. La de aquí protege algo peor —una base de
producción restaurada encima— y por eso es **positiva**: el ensayo sólo escribe
en una base que él mismo creó en esta corrida, con un marcador que él escribió.
Una lista negra de nombres prohibidos quedaría ciega el día que exista `prod`.

Estos tests rompen la guardia de las cuatro maneras en que se puede romper, y
comprueban que aborta ANTES de tocar un byte.

Lo que NO vive aquí, a propósito: la corrida completa del ensayo (dump →
restore → verificación). Necesita binarios `pg_dump`/`pg_restore` del MISMO
major que el servidor —o el contenedor de la DB— y crea y borra bases: no es
hermética para la suite del api, que corre en cada PR contra un servicio
compartido. Vive en `make restore-drill`, y en el módulo está escrito por qué.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import psycopg
import pytest

from conftest import _dsn
from takab_api.ops import restore_drill
from takab_api.ops.restore_check import INDETERMINADO, ROJO, VERDE
from takab_api.ops.restore_drill import (
    DRILL_NAME_RE,
    DrillResult,
    GuardError,
    PgTools,
    Phase,
    Target,
    assert_drill_target,
    marker_for,
    new_drill_name,
    new_run_id,
    resolve_pg_tools,
    target_from_url,
)


@pytest.fixture
def admin() -> psycopg.Connection:
    c = psycopg.connect(_dsn(), autocommit=True)
    try:
        yield c
    finally:
        c.close()


@pytest.fixture
def base_de_ensayo(admin: psycopg.Connection):
    """Una base creada por ESTA corrida, con su marcador. Se borra al terminar."""
    run_id = new_run_id()
    nombre = new_drill_name("dst", run_id)
    marca = marker_for(run_id)
    restore_drill._create_marked_db(admin, nombre, marca)
    try:
        yield nombre, marca
    finally:
        admin.execute(f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)')


# --------------------------------------------------------------------------- la guardia


def test_la_guardia_acepta_la_base_que_el_ensayo_creo(admin, base_de_ensayo) -> None:
    nombre, marca = base_de_ensayo
    assert_drill_target(admin, nombre, marca)  # no levanta


def test_la_guardia_se_niega_ante_una_base_de_produccion(admin) -> None:
    """El caso que importa: restaurar encima de la base real. Aborta por el NOMBRE.

    `takab` es el nombre de la base de producción y el de la de desarrollo. No
    encaja con el patrón que este módulo genera, así que muere en el primer
    filtro, sin haber consultado siquiera el catálogo.
    """
    with pytest.raises(GuardError) as exc:
        assert_drill_target(admin, "takab", marker_for(new_run_id()))
    assert "no es una base de ensayo" in str(exc.value)
    assert "sin tocar nada" in str(exc.value)


@pytest.mark.parametrize(
    "nombre",
    [
        "takab",
        "takab_prod",
        "postgres",
        "takab_restore",  # el nombre que usa el propio §3 del runbook
        "takab_drill",  # parece del ensayo y no lo es
        "takab_drill_dst_sin_fecha_ni_hex",
    ],
)
def test_la_guardia_no_reconoce_nada_que_no_haya_generado_ella(admin, nombre: str) -> None:
    with pytest.raises(GuardError):
        assert_drill_target(admin, nombre, marker_for(new_run_id()))


def test_una_base_con_el_nombre_correcto_pero_SIN_marcador_se_rechaza(admin) -> None:
    """El nombre no es la guardia: el marcador lo es.

    Alguien podría llamar a su base como el patrón. Lo que no puede es haber
    escrito el marcador de ESTA corrida, porque el run_id se genera aquí.
    """
    nombre = new_drill_name("dst", new_run_id())
    admin.execute(f'CREATE DATABASE "{nombre}"')
    try:
        with pytest.raises(GuardError) as exc:
            assert_drill_target(admin, nombre, marker_for(new_run_id()))
        assert "NO lleva el marcador de esta corrida" in str(exc.value)
    finally:
        admin.execute(f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)')


def test_el_marcador_de_OTRA_corrida_no_vale(admin, base_de_ensayo) -> None:
    nombre, _ = base_de_ensayo
    with pytest.raises(GuardError):
        assert_drill_target(admin, nombre, marker_for(new_run_id()))


def test_una_base_que_no_existe_no_se_restaura(admin) -> None:
    run_id = new_run_id()
    with pytest.raises(GuardError) as exc:
        assert_drill_target(admin, new_drill_name("dst", run_id), marker_for(run_id))
    assert "no existe" in str(exc.value)


def test_otro_cliente_conectado_aborta_el_paso(admin, base_de_ensayo) -> None:
    """Lección A-3: exclusividad o nada. Un worker ajeno escribiendo en la base
    destino mientras se restaura produce una verificación que no significa nada.
    """
    nombre, marca = base_de_ensayo
    intruso = psycopg.connect(
        psycopg.conninfo.make_conninfo(_dsn(), dbname=nombre), autocommit=True
    )
    try:
        with pytest.raises(GuardError) as exc:
            assert_drill_target(admin, nombre, marca)
        assert "OTROS clientes conectados" in str(exc.value)
        assert "A-3" in str(exc.value)
    finally:
        intruso.close()


def test_los_nombres_generados_son_unicos_y_reconocibles() -> None:
    nombres = {new_drill_name("dst", new_run_id()) for _ in range(50)}
    assert len(nombres) == 50
    assert all(DRILL_NAME_RE.match(n) for n in nombres)


def test_el_ensayo_no_puede_hacer_swap() -> None:
    """El §3 del runbook termina en `ALTER DATABASE … RENAME TO …`. Aquí no.

    El swap es destructivo y es una decisión humana dentro de una ventana con la
    API parada; el ensayo restaura, verifica, mide y se para. Se comprueba sobre
    los literales de cadena del módulo (con `ast`, no con grep): la documentación
    —docstrings y comentarios— sí nombra el swap para explicar por qué no está,
    pero ninguna cadena EJECUTABLE puede contener la sentencia.
    """
    arbol = ast.parse(Path(inspect.getfile(restore_drill)).read_text(encoding="utf-8"))
    # Un docstring es una cadena suelta como sentencia (`ast.Expr`); todo lo demás
    # es una cadena que el módulo usa para algo.
    documentacion = {
        id(n.value)
        for n in ast.walk(arbol)
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
    }
    ejecutables = [
        n.value
        for n in ast.walk(arbol)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in documentacion
    ]
    culpables = [s for s in ejecutables if "ALTER DATABASE" in s.upper()]
    assert not culpables, f"el ensayo NO puede renombrar ni alterar bases: {culpables}"


# --------------------------------------------------------------------------- el reloj


def _resultado(*fases: Phase) -> DrillResult:
    """Un resultado de ensayo con el verificador en VERDE, para medir el reloj.

    `verifier_verdict` explícito: por defecto es INDETERMINADO —el estado
    correcto para un resultado a medio construir— y estos tests miden otra cosa.
    """
    return DrillResult(run_id="x", phases=list(fases), verifier_ok=True, verifier_verdict=VERDE)


def test_el_reloj_para_en_el_verde_del_verificador_no_en_pg_restore() -> None:
    """Una base restaurada y no verificada no es un servicio recuperado."""
    r = _resultado(
        Phase("crear instancia limpia", 1.0, True),
        Phase("pg_restore", 10.0, True),
        Phase("verificación de integridad", 4.0, True),
    )
    assert r.rto_seconds == 15.0, "la verificación cuenta: sin ella no hay servicio"


def test_el_andamiaje_del_ensayo_no_cuenta_en_el_rto() -> None:
    """En el incidente real el dump ya existe en S3: fabricarlo aquí no es recuperar."""
    r = _resultado(
        Phase("origen sintético (alembic + siembra)", 30.0, False),
        Phase("pg_dump del origen", 20.0, False),
        Phase("pg_restore", 5.0, True),
    )
    assert r.rto_seconds == 5.0
    assert r.scaffolding_seconds == 50.0


def test_el_desglose_por_fases_sobrevive_al_informe() -> None:
    """Un RTO de 40 min con 35 de descarga se arregla distinto que uno con 35 de restore."""
    r = _resultado(
        Phase("crear instancia limpia", 1.0, True, "nota A"),
        Phase("pg_restore", 10.0, True, "nota B"),
        Phase("verificación de integridad", 4.0, True, "nota C"),
    )
    r.report_text = "(informe)"
    texto = restore_drill.render_result(r)
    for trozo in ("pg_restore", "verificación de integridad", "nota B", "RTO MEDIDO"):
        assert trozo in texto


def test_el_informe_declara_la_etapa_que_no_midio() -> None:
    """Un hueco declarado es un activo; uno callado es una mentira cómoda."""
    r = _resultado(Phase("pg_restore", 1.0, True))
    texto = restore_drill.render_result(r)
    assert "DESCARGA del dump desde S3" in texto
    assert "NO se extrapola" in texto
    assert "no acredita el gate G-09" in texto


def test_el_numero_viaja_siempre_con_su_escala() -> None:
    r = _resultado(Phase("pg_restore", 1.0, True))
    r.dump_bytes = 5_645_282
    r.source_rows = 600_000
    texto = restore_drill.render_result(r)
    assert "5.4 MiB" in texto
    assert "600000" in texto


def test_pasarse_del_presupuesto_INCLUSO_EN_LOCAL_se_dice_con_todas_las_letras() -> None:
    """Si el ensayo de juguete ya no cabe en el presupuesto, producción tampoco.

    Al revés NO vale como acreditación, y por eso el caso "cabe" ya no imprime
    «DENTRO» (ver `test_el_presupuesto_local_ya_no_dice_DENTRO`).
    """
    r = _resultado(Phase("pg_restore", 3601.0, True))
    r.budget_min = 60.0
    assert not r.within_budget
    texto = restore_drill.render_result(r)
    assert "EXCEDIDO INCLUSO EN LOCAL" in texto


def test_un_restore_con_errores_no_puede_salir_verde() -> None:
    """`pg_restore` puede terminar dejando un rastro de errores "ignorados"."""
    r = _resultado(Phase("pg_restore", 1.0, True))
    r.restore_stderr = 'pg_restore: error: COPY failed for table "_hyper_1_1_chunk"'
    assert not r.ok
    assert "ROJO" in restore_drill.render_result(r)


# --------------------------------------------------------------------------- entorno


def test_el_dsn_sale_de_la_env_y_no_lleva_secretos_al_codigo() -> None:
    t = target_from_url("postgresql+psycopg://usuario:c%40ve@10.0.0.5:5433/takab")
    assert (t.host, t.port, t.user, t.database) == ("10.0.0.5", "5433", "usuario", "takab")
    assert t.password == "c@ve"
    assert "dbname=otra" in t.dsn("otra")
    assert t.sqlalchemy_url("otra").endswith("@10.0.0.5:5433/otra")


def test_un_cliente_de_otro_major_se_rechaza_en_vez_de_producir_basura(tmp_path: Path) -> None:
    """Medido: cliente 18.4 contra servidor 16 →
    `unrecognized configuration parameter "transaction_timeout"`, y `pg_restore`
    lo reporta como "errores ignorados" y sigue. Es exactamente el verde
    mentiroso que esta tarea persigue.
    """
    falso = tmp_path / "pg_dump"
    falso.write_text('#!/bin/sh\necho "pg_dump (PostgreSQL) 18.4"\n')
    falso.chmod(0o755)
    with pytest.raises(RuntimeError) as exc:
        resolve_pg_tools("16.10", container="no-existe", env={"TAKAB_PG_BIN": str(tmp_path)})
    assert "18.4" in str(exc.value)
    assert "16" in str(exc.value)


def test_el_backend_docker_no_le_pasa_host_al_binario() -> None:
    """Dentro del contenedor, 127.0.0.1 es OTRA máquina: se va por el socket local,
    igual que hace el §3 del runbook dentro del EC2."""
    t = Target("127.0.0.1", "5433", "takab", "x", "takab")
    docker = PgTools("docker", ("docker", "exec", "-i", "takab-db"), "", "16.10", "d")
    local = PgTools("local", (), "", "16.10", "l")
    assert t.client_args(docker, "d1") == ["-U", "takab", "-d", "d1"]
    assert "-h" in t.client_args(local, "d1")
    assert docker.cmd("pg_dump", "-Fc")[:4] == ["docker", "exec", "-i", "takab-db"]


def test_sin_cliente_compatible_el_mensaje_dice_como_arreglarlo() -> None:
    with pytest.raises(RuntimeError) as exc:
        resolve_pg_tools("99.1", container="no-existe", env={})
    texto = str(exc.value)
    assert "postgresql-client-99" in texto
    assert "TAKAB_PG_BIN" in texto


def test_como_el_runbook_reproduce_el_procedimiento_documentado() -> None:
    """El atajo que reproduce el §3 VERBATIM: es la no-vacuidad del propio ensayo."""
    args = restore_drill.build_parser().parse_args(["--como-el-runbook"])
    assert args.como_el_runbook
    # main() las expande; aquí se fija el contrato de las tres piezas del §3
    assert {"sin_timescale_helpers", "no_owner", "no_exit_on_error"} <= set(vars(args))
    assert "checklist_crudo" in vars(args)


# ===========================================================================
# AUDITORÍA ADVERSARIAL (2026-08-08)
# ===========================================================================


def test_un_ensayo_con_comprobaciones_sin_ejercer_no_es_verde() -> None:
    """El ensayo hereda los tres estados del verificador: un SKIP no es verde."""
    r = _resultado(Phase("pg_restore", 1.0, True))
    r.verifier_verdict = INDETERMINADO
    r.skipped_checks = ("row_counts", "ownership")
    assert r.verdict == INDETERMINADO
    assert not r.ok
    texto = restore_drill.render_result(r)
    assert "INDETERMINADO" in texto
    assert "row_counts" in texto


def test_el_codigo_de_salida_distingue_los_tres_estados() -> None:
    """0 sólo para VERDE. El 2 del INDETERMINADO existe para que un `&&` en un
    script no lo confunda con un éxito."""
    verde = _resultado(Phase("x", 1.0, True))
    verde.verifier_verdict = VERDE
    rojo = _resultado(Phase("x", 1.0, True))
    rojo.verifier_verdict = ROJO
    indet = _resultado(Phase("x", 1.0, True))
    indet.verifier_verdict = INDETERMINADO
    codigos = {VERDE: 0, ROJO: 1, INDETERMINADO: 2}
    assert [codigos[r.verdict] for r in (verde, rojo, indet)] == [0, 1, 2]


def test_el_presupuesto_local_ya_no_dice_DENTRO() -> None:
    """«DENTRO» era la única palabra del informe que se leía como acreditación.

    2,28 s de un dump de 572 KiB contra un presupuesto de PRODUCCIÓN de 60 min no
    es "dentro": es no comparable, y quien cite el informe citará esa palabra.
    """
    r = _resultado(Phase("pg_restore", 2.28, True))
    r.verifier_verdict = VERDE
    texto = restore_drill.render_result(r)
    assert "NO COMPARABLE" in texto
    assert "DENTRO" not in texto


def test_el_barrido_solo_toca_lo_que_lleva_el_marcador(admin) -> None:
    """MEDIO-3, segunda red: SIGKILL no deja correr ningún `finally`.

    El barrido borra bases de ensayo VIEJAS, y sólo si llevan el marcador: el
    nombre no basta (la misma prueba positiva de autoría que la guardia).
    """
    # una base con nombre de ensayo, ANTIGUA y SIN marcador: no se toca
    impostora = "takab_drill_dst_20200101t000000_deadbeef"
    admin.execute(f'CREATE DATABASE "{impostora}"')
    # una base con marcador y ANTIGUA: sí se barre
    vieja = "takab_drill_src_20200101t000000_cafe1234"
    restore_drill._create_marked_db(admin, vieja, marker_for("20200101t000000_cafe1234"))
    # una base con marcador y RECIENTE: podría ser de una corrida viva
    reciente_id = new_run_id()
    reciente = new_drill_name("dst", reciente_id)
    restore_drill._create_marked_db(admin, reciente, marker_for(reciente_id))
    try:
        borradas = restore_drill.sweep_orphans(admin)
        assert vieja in borradas
        assert impostora not in borradas, "sin marcador no es nuestra, aunque se llame igual"
        assert reciente not in borradas, "una corrida viva no se barre a sí misma"
    finally:
        for n in (impostora, vieja, reciente):
            admin.execute(f'DROP DATABASE IF EXISTS "{n}" WITH (FORCE)')


def test_el_borrado_final_cierra_las_conexiones_abandonadas(admin) -> None:
    """Medido con un SIGTERM real: el cliente muere y el servidor sigue con el
    INSERT de la siembra, así que la cláusula de exclusividad —correcta para
    ESCRIBIR— se convertía en la razón por la que la huérfana sobrevivía.

    Al BORRAR es al revés: la base la creó esta corrida hace segundos con un
    nombre que nadie más genera, así que sus conexiones sólo pueden ser nuestras.
    """
    run_id = new_run_id()
    nombre = new_drill_name("src", run_id)
    marca = marker_for(run_id)
    restore_drill._create_marked_db(admin, nombre, marca)
    abandonada = psycopg.connect(
        psycopg.conninfo.make_conninfo(_dsn(), dbname=nombre), autocommit=True
    )
    try:
        with pytest.raises(GuardError):
            assert_drill_target(admin, nombre, marca)  # para ESCRIBIR sigue negándose
        assert restore_drill.drop_drill_db(admin, nombre, marca) is True
        assert not admin.execute(
            "SELECT count(*) FROM pg_database WHERE datname = %s", (nombre,)
        ).fetchone()[0]
    finally:
        abandonada.close()
        admin.execute(f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)')


def test_el_borrado_final_sigue_sin_tocar_lo_ajeno(admin) -> None:
    """Cerrar conexiones no relaja la prueba de autoría: nombre y marcador siguen."""
    with pytest.raises(GuardError):
        restore_drill.drop_drill_db(admin, "takab", marker_for(new_run_id()))
    nombre = new_drill_name("dst", new_run_id())
    admin.execute(f'CREATE DATABASE "{nombre}"')  # sin marcador
    try:
        with pytest.raises(GuardError):
            restore_drill.drop_drill_db(admin, nombre, marker_for(new_run_id()))
    finally:
        admin.execute(f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)')


def test_sigterm_deja_correr_la_limpieza() -> None:
    """SIGTERM mata sin desenrollar la pila: el `finally` no corría y quedaba una
    base viva. systemd, `timeout` y la cancelación de un job de CI mandan SIGTERM.
    """
    import signal

    previo = restore_drill._rearmar_sigterm()
    try:
        handler = signal.getsignal(signal.SIGTERM)
        assert callable(handler), "SIGTERM tiene que pasar por un handler de Python"
        with pytest.raises(BaseException) as exc:
            handler(signal.SIGTERM, None)
        assert isinstance(exc.value, restore_drill._Terminado)
    finally:
        if previo is not None:
            signal.signal(signal.SIGTERM, previo)


def test_el_checklist_del_runbook_es_el_del_runbook(admin) -> None:
    """El §5 literal, ejecutable, para enseñar las dos mitades del hallazgo juntas."""
    consultas = " ".join(q for _, q in restore_drill._CHECKLIST_RUNBOOK)
    for trozo in (
        "max(ts) FROM {}",  # la hypertable cruda se resuelve del catálogo
        "count(*) FROM incidents",
        "count(*) FROM audit_log",
        "count(*) FROM evidence_objects",
        "extname='timescaledb'",
        "timescaledb_information.hypertables",
        "relrowsecurity",
    ):
        assert trozo in consultas, f"el §5 del runbook incluye {trozo!r}"
    texto = restore_drill.run_runbook_checklist(admin)
    assert "La punta del dato" in texto
    assert "no mira conteos contra el ORIGEN" in texto
