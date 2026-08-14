"""T-2.73 · El verificador de integridad de un restore, roto a propósito.

`RUNBOOK-backup-restore-db.md:3` dice "RESTORE JAMÁS PROBADO". El §5 de ese
runbook lista en prosa qué mirar tras restaurar; este módulo lo convierte en
aserciones con veredicto. Pero un verificador que nunca has visto fallar es
exactamente el mismo error que un respaldo que nunca has restaurado: por eso
**cada comprobación tiene aquí su mutación**, la que rompe esa invariante
concreta y demuestra que el verificador la caza.

Cómo se rompen las cosas sin dejar rastro: todas las mutaciones son DDL dentro
de la transacción del fixture `conn`, que hace ROLLBACK al terminar. En
PostgreSQL el DDL es transaccional —incluido `DROP TABLE` de una hypertable,
`ALTER ROLE ... RENAME` y hasta un `UPDATE pg_index`— así que la base queda
intacta. Verificado a mano antes de escribir esto: `hypertables` vuelve de 2 a
3 y `takab_app` reaparece tras el ROLLBACK.

Lo que estos tests NO cubren, y por eso existe el ensayo de
`takab_api.ops.restore_drill`: que un `pg_restore` real produzca una base sana.
Aquí se ejercita el verificador; allí se ejercita el procedimiento.
"""

from __future__ import annotations

import psycopg
import pytest

from conftest import SITE_A, TENANT_A, TENANT_B
from takab_api.ops.restore_check import (
    FAIL,
    INDETERMINADO,
    PASS,
    ROJO,
    SKIP,
    WARN,
    Report,
    capture_baseline,
    declared_expectations,
    render,
    verify,
)

# --------------------------------------------------------------------------- utilidades


def _check(report: Report, name: str):
    """La comprobación por nombre, o un fallo legible si el verificador no la emitió."""
    found = [c for c in report.checks if c.name == name]
    assert found, (
        f"el verificador no emitió la comprobación {name!r}: {[c.name for c in report.checks]}"
    )
    return found[0]


def _status(conn: psycopg.Connection, name: str, **kw) -> str:
    return _check(verify(conn, **kw), name).status


# --------------------------------------------------------------------------- expectativas


def test_las_expectativas_se_derivan_del_esquema_no_de_una_lista_a_mano() -> None:
    """`db/schema.sql` es la fuente de verdad del DDL: de ahí salen, no de un literal."""
    exp = declared_expectations()
    assert {"timescaledb", "postgis", "pgcrypto"} <= exp.extensions
    # append-only: los triggers BEFORE UPDATE OR DELETE que declara el esquema
    assert {"audit_log", "evidence_objects", "dictamens", "incident_actions"} <= exp.append_only
    # RLS: tabla -> (enabled, forced). Las excepciones documentadas viajan con su forma.
    assert exp.rls["incidents"] == (True, True)
    assert exp.rls["device_health"] == (True, False), "hypertable con jobs: ENABLE sin FORCE"
    assert "waveform_features_1s" not in exp.rls, "tiene caggs: no puede llevar RLS"
    assert {"waveform_features_1s", "device_health", "rule_evaluations"} <= exp.hypertables
    assert "waveform_features_1s_secure" in exp.barrier_views
    assert {"takab_migrator", "takab_app", "takab_ingest"} <= exp.roles
    assert exp.policies["incidents"] >= 3
    # políticas de TimescaleDB: el `add_*_policy` del esquema, no una lista aparte
    assert ("policy_retention", "device_health") in exp.timescale_policies
    assert ("policy_refresh_continuous_aggregate", "site_metrics_1h") in exp.timescale_policies
    assert ("policy_compression", "site_metrics_1m") in exp.timescale_policies


# --------------------------------------------------------------------------- verde de base


def test_la_base_migrada_pasa_entera(seeded: psycopg.Connection) -> None:
    """El suelo: sobre una base sana no hay ni un FAIL, y ningún SKIP mudo."""
    report = verify(seeded)
    assert report.failed == (), render(report)
    for check in report.checks:
        if check.status == SKIP:
            assert check.detail, f"{check.name} se saltó sin decir por qué"


def test_el_informe_se_puede_leer(seeded: psycopg.Connection) -> None:
    texto = render(verify(seeded))
    assert "tenant_isolation" in texto
    assert "append_only_enforced" in texto


# --------------------------------------------------------------------------- no-vacuidad
# Una mutación por invariante. Si alguna no se puede romper, sospecha de la
# comprobación, no de la mutación.


def test_trigger_append_only_borrado(seeded: psycopg.Connection) -> None:
    """El modo de fallo más caro: conteos perfectos y la regla de oro 11 rota."""
    seeded.execute("DROP TRIGGER trg_audit_log_append_only ON audit_log")
    report = verify(seeded)
    assert _check(report, "append_only_triggers").status == FAIL
    assert "audit_log" in _check(report, "append_only_triggers").detail


def test_trigger_append_only_presente_pero_DESACTIVADO(seeded: psycopg.Connection) -> None:
    """`ALTER TABLE ... DISABLE TRIGGER` deja la fila en pg_trigger: existe y no protege.

    Contar triggers habría dado verde. Por eso la comprobación es NEGATIVA: se
    intenta un UPDATE real de una fila y sólo pasa si FALLA.
    """
    seeded.execute("ALTER TABLE audit_log DISABLE TRIGGER trg_audit_log_append_only")
    report = verify(seeded)
    assert _check(report, "append_only_enforced").status == FAIL
    assert "audit_log" in _check(report, "append_only_enforced").detail


def test_el_update_de_prueba_no_deja_rastro(seeded: psycopg.Connection) -> None:
    """La aserción negativa toca datos de compliance: tiene que revertirlos siempre.

    Subconjunto y no igualdad: en la suite completa hay escrituras de auditoría
    ASÍNCRONAS de otros tests que confirman mientras este corre, y bajo READ
    COMMITTED cada sentencia ve un snapshot nuevo. Lo que se afirma es lo que
    importa —ninguna fila anterior desapareció ni cambió—, no que el mundo se
    quedara quieto.
    """
    antes = set(seeded.execute("SELECT audit_id, verb FROM audit_log").fetchall())
    verify(seeded)
    despues = set(seeded.execute("SELECT audit_id, verb FROM audit_log").fetchall())
    assert antes <= despues, f"el sondeo borró o alteró filas de auditoría: {antes - despues}"


def test_rls_apagada(seeded: psycopg.Connection) -> None:
    seeded.execute("ALTER TABLE incidents DISABLE ROW LEVEL SECURITY")
    assert _status(seeded, "rls_flags") == FAIL


def test_rls_sin_FORCE(seeded: psycopg.Connection) -> None:
    """Sin FORCE el DUEÑO de la tabla se salta su propia política.

    Es justo el escenario de un restore con `--no-owner`, donde la propiedad
    cambia: leer sólo `relrowsecurity` daría verde.
    """
    seeded.execute("ALTER TABLE incidents NO FORCE ROW LEVEL SECURITY")
    report = verify(seeded)
    assert _check(report, "rls_flags").status == FAIL
    assert "incidents" in _check(report, "rls_flags").detail


def test_politica_rls_borrada(seeded: psycopg.Connection) -> None:
    """RLS encendida y sin políticas: la bandera está puesta y la tabla no se lee."""
    for pol in ("incidents_read", "incidents_write", "incidents_admin"):
        seeded.execute(f"DROP POLICY {pol} ON incidents")
    assert _status(seeded, "rls_policies") == FAIL


def test_politica_rls_permisiva_deja_ver_al_vecino(seeded: psycopg.Connection) -> None:
    """La diferencia entre "la bandera está puesta" y "el aislamiento funciona".

    Las políticas siguen ahí y las banderas también; sólo el USING miente. Un
    verificador que lea `pg_class` da verde y un tenant ve al otro.
    """
    seeded.execute("DROP POLICY sites_read ON sites")
    seeded.execute("CREATE POLICY sites_read ON sites FOR SELECT USING (true)")
    report = verify(seeded)
    assert _check(report, "rls_flags").status == PASS
    assert _check(report, "tenant_isolation").status == FAIL


def test_aislamiento_se_salta_por_la_vista_del_waveform(seeded: psycopg.Connection) -> None:
    """El crudo no lleva RLS: lo aísla la vista security_barrier + el JOIN a sites."""
    seeded.execute("DROP VIEW waveform_features_1s_secure")
    seeded.execute(
        "CREATE VIEW waveform_features_1s_secure WITH (security_barrier = true) AS "
        "SELECT * FROM waveform_features_1s"
    )
    seeded.execute("GRANT SELECT ON waveform_features_1s_secure TO takab_app")
    assert _status(seeded, "tenant_isolation") == FAIL


def test_vista_sin_security_barrier(seeded: psycopg.Connection) -> None:
    """Sin la opción, el planificador puede empujar un qual del usuario por debajo
    del JOIN a `sites` y filtrar filas ajenas por canal lateral."""
    seeded.execute("ALTER VIEW waveform_features_1s_secure RESET (security_barrier)")
    report = verify(seeded)
    assert _check(report, "barrier_views").status == FAIL
    assert "waveform_features_1s_secure" in _check(report, "barrier_views").detail


def test_hypertable_convertida_en_tabla_plana(seeded: psycopg.Connection) -> None:
    """Mismos datos, mismo count(*), y las políticas de retención desaparecidas."""
    seeded.execute("DROP TABLE rule_evaluations CASCADE")
    seeded.execute(
        "CREATE TABLE rule_evaluations (ts timestamptz NOT NULL, gateway_id uuid NOT NULL)"
    )
    report = verify(seeded)
    assert _check(report, "hypertables").status == FAIL
    assert "rule_evaluations" in _check(report, "hypertables").detail


def test_politica_de_retencion_perdida(seeded: psycopg.Connection) -> None:
    """La hypertable sigue siéndolo y su política ya no está: `count(*)` idéntico.

    Sin retención el volumen se llena semanas después y nadie ata los cabos;
    sin refresco, el cagg se congela y la consola pinta cifras viejas como si
    fueran de ahora (regla de oro 7).
    """
    seeded.execute("SELECT remove_retention_policy('device_health')")
    report = verify(seeded)
    assert _check(report, "hypertables").status == PASS, (
        "sigue siendo hypertable: ahí está la trampa"
    )
    assert _check(report, "timescale_policies").status == FAIL
    assert "device_health" in _check(report, "timescale_policies").detail


def test_politica_de_refresco_del_cagg_perdida(seeded: psycopg.Connection) -> None:
    seeded.execute("SELECT remove_continuous_aggregate_policy('site_metrics_1h')")
    report = verify(seeded)
    assert _check(report, "timescale_policies").status == FAIL
    assert "site_metrics_1h" in _check(report, "timescale_policies").detail


def test_extension_ausente(seeded: psycopg.Connection) -> None:
    seeded.execute("DROP EXTENSION pgcrypto CASCADE")
    report = verify(seeded)
    assert _check(report, "extensions").status == FAIL
    assert "pgcrypto" in _check(report, "extensions").detail


def test_secuencia_por_detras_del_dato(seeded: psycopg.Connection) -> None:
    """El fallo que llega DESPUÉS del "todo verde": el primer INSERT viola la PK."""
    seeded.execute("CREATE TABLE probe_seq (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY)")
    seeded.execute("INSERT INTO probe_seq DEFAULT VALUES")
    seeded.execute("INSERT INTO probe_seq DEFAULT VALUES")
    seeded.execute("SELECT setval(pg_get_serial_sequence('probe_seq','id'), 1, false)")
    report = verify(seeded)
    assert _check(report, "sequences").status == FAIL
    assert "probe_seq" in _check(report, "sequences").detail


def test_constraint_sin_validar(seeded: psycopg.Connection) -> None:
    """Un NOT VALID no comprueba las filas que ya están: la integridad es aparente."""
    seeded.execute(
        "ALTER TABLE incidents ADD CONSTRAINT probe_chk CHECK (severity IS NOT NULL) NOT VALID"
    )
    report = verify(seeded)
    assert _check(report, "constraints_validated").status == FAIL
    assert "probe_chk" in _check(report, "constraints_validated").detail


def test_indice_invalido(seeded: psycopg.Connection) -> None:
    """Un CREATE INDEX interrumpido deja el índice en el catálogo y sin usar."""
    seeded.execute(
        "UPDATE pg_index SET indisvalid = false WHERE indexrelid = 'idx_wf_site_ts'::regclass"
    )
    report = verify(seeded)
    assert _check(report, "indexes_valid").status == FAIL
    assert "idx_wf_site_ts" in _check(report, "indexes_valid").detail


def test_rol_de_conexion_ausente(seeded: psycopg.Connection) -> None:
    """Los roles son de CLÚSTER: un `pg_dump` de una base no los lleva dentro.

    Restaurar en una instancia nueva y limpia (el Procedimiento B del runbook)
    es exactamente donde desaparecen, y con ellos todos los GRANT.
    """
    seeded.execute("ALTER ROLE takab_app RENAME TO takab_app_probe")
    report = verify(seeded)
    assert _check(report, "roles").status == FAIL
    assert "takab_app" in _check(report, "roles").detail


def test_dueño_con_bypassrls_y_sin_force(seeded: psycopg.Connection) -> None:
    """Un rol que se salta la RLS como dueño de una tabla sin FORCE: aviso, no fallo.

    No rompe a la API (se conecta como `takab_app`, que no es dueño), pero sí a
    quien se conecte con el rol dueño.
    """
    seeded.execute("ALTER TABLE incidents NO FORCE ROW LEVEL SECURITY")
    seeded.execute("ALTER TABLE incidents OWNER TO takab")
    report = verify(seeded)
    assert _check(report, "rls_owner_escape").status == WARN
    assert "incidents" in _check(report, "rls_owner_escape").detail


# --------------------------------------------------------------------------- con baseline
# El baseline es la huella de la base ORIGEN tomada antes del dump. Sin él, un
# restore que perdió una tabla entera no tiene contra qué compararse.


def test_baseline_verde_contra_si_mismo(seeded: psycopg.Connection) -> None:
    base = capture_baseline(seeded)
    report = verify(seeded, baseline=base)
    assert report.failed == (), render(report)


def test_filas_perdidas(seeded: psycopg.Connection) -> None:
    base = capture_baseline(seeded)
    seeded.execute("DELETE FROM waveform_features_1s")
    report = verify(seeded, baseline=base)
    assert _check(report, "row_counts").status == FAIL
    assert "waveform_features_1s" in _check(report, "row_counts").detail


def test_tabla_entera_perdida(seeded: psycopg.Connection) -> None:
    base = capture_baseline(seeded)
    seeded.execute("DROP TABLE quorum_votes CASCADE")
    report = verify(seeded, baseline=base)
    assert _check(report, "object_inventory").status == FAIL
    assert "quorum_votes" in _check(report, "object_inventory").detail


def test_indice_perdido(seeded: psycopg.Connection) -> None:
    """Un índice que no viaja no rompe ninguna consulta: sólo las hace lentas."""
    base = capture_baseline(seeded)
    seeded.execute("DROP INDEX idx_wf_site_ts")
    report = verify(seeded, baseline=base)
    assert _check(report, "object_inventory").status == FAIL
    assert "idx_wf_site_ts" in _check(report, "object_inventory").detail


def test_propiedad_cambiada(seeded: psycopg.Connection) -> None:
    """`--no-owner` deja al rol de migraciones sin poder migrar. Verde en el §5.

    Medido a mano sobre una base restaurada con el procedimiento del runbook:
    `SET ROLE takab_migrator; ALTER TABLE sites ADD COLUMN x text;`
    → `ERROR: must be owner of table sites`. El siguiente despliegue muere.
    """
    base = capture_baseline(seeded)
    seeded.execute("ALTER TABLE sites OWNER TO takab")
    report = verify(seeded, baseline=base)
    assert _check(report, "ownership").status == FAIL
    assert "sites" in _check(report, "ownership").detail


def test_sin_baseline_la_comparacion_se_declara_ausente(seeded: psycopg.Connection) -> None:
    """Callar aquí sería lo peor: sin huella del origen NO se sabe si falta algo."""
    report = verify(seeded)
    for name in ("row_counts", "object_inventory", "ownership"):
        check = _check(report, name)
        assert check.status == SKIP
        assert "baseline" in check.detail.lower()


def test_la_punta_del_dato_mide_el_rpo(seeded: psycopg.Connection) -> None:
    base = capture_baseline(seeded)
    report = verify(seeded, baseline=base)
    tip = _check(report, "data_tip")
    assert tip.status in (PASS, WARN, SKIP)
    assert "waveform_features_1s" in tip.detail


# --------------------------------------------------------------------------- honestidad


def test_ningun_skip_es_anonimo(seeded: psycopg.Connection) -> None:
    """Un "N saltados" que no dice QUÉ dejó de comprobarse es cobertura falsa."""
    report = verify(seeded, baseline=capture_baseline(seeded))
    assert all(c.detail.strip() for c in report.checks)


def test_el_veredicto_solo_lo_tumban_los_FAIL(seeded: psycopg.Connection) -> None:
    seeded.execute("ALTER TABLE incidents NO FORCE ROW LEVEL SECURITY")
    seeded.execute("ALTER TABLE incidents OWNER TO takab")
    report = verify(seeded)
    assert any(c.status == WARN for c in report.checks)
    # rls_flags también cae por el NO FORCE: el veredicto es rojo por ESO, no por el WARN.
    assert not report.ok
    solo_warn = tuple(c for c in report.checks if c.status == WARN)
    assert solo_warn, "la mutación tenía que producir al menos un aviso"


@pytest.mark.parametrize("tabla", ["audit_log", "evidence_objects", "dictamens"])
def test_cada_tabla_de_compliance_se_ejerce_de_verdad(
    seeded: psycopg.Connection, tabla: str
) -> None:
    """La regla de oro 11 no admite muestreo: se prueba tabla por tabla."""
    seeded.execute(f"ALTER TABLE {tabla} DISABLE TRIGGER USER")
    report = verify(seeded)
    assert _check(report, "append_only_enforced").status == FAIL
    assert tabla in _check(report, "append_only_enforced").detail


def test_tabla_append_only_vacia_se_declara_no_ejercida(conn: psycopg.Connection) -> None:
    """Un trigger FOR EACH ROW sobre una tabla vacía no se puede ejercer.

    Sin filas la aserción negativa es vacía: hay que DECIRLO, no dar verde.

    La tabla vacía se CREA aquí en vez de vaciar `audit_log`: además de no tocar
    nada compartido, demuestra de paso que la lista de tablas append-only sale
    del catálogo y no de un literal — esta tabla no existe en ningún esquema y
    aun así el verificador la encuentra y la reporta.
    """
    conn.execute("CREATE TABLE probe_append_only (id int PRIMARY KEY, nota text)")
    conn.execute(
        "CREATE TRIGGER trg_probe_append_only BEFORE UPDATE OR DELETE ON probe_append_only "
        "FOR EACH ROW EXECUTE FUNCTION forbid_update_delete()"
    )
    report = verify(conn)
    check = _check(report, "append_only_enforced")
    assert "probe_append_only" in check.detail
    assert "sin filas" in check.detail.lower()


def test_lo_que_queda_enumerado_esta_declarado() -> None:
    """Donde no se puede derivar, se enumera — y se dice qué queda fuera."""
    from takab_api.ops.restore_check import ENUMERATED

    assert ENUMERATED, "la lista de excepciones enumeradas no puede estar vacía"
    for nombre, razon in ENUMERATED.items():
        assert razon.strip(), f"la excepción {nombre!r} no dice por qué"


def test_el_aislamiento_se_declara_no_probado_sin_dos_tenants(
    seeded: psycopg.Connection,
) -> None:
    """Sin dos tenants privados SIN visibilidad cruzada, el cruce no prueba nada.

    Se le concede a cada tenant una visibilidad sobre todos los demás: entonces
    ver al vecino es legítimo y el sondeo dejaría de significar nada. La forma
    correcta de reaccionar es DECIR que no se probó, no dar verde.

    (Se hace con un INSERT y no vaciando `tenants`: un `TRUNCATE … CASCADE`
    sobre una tabla raíz toma un ACCESS EXCLUSIVE que puede quedarse esperando
    detrás de cualquier conexión que la suite haya dejado abierta.)
    """
    seeded.execute(
        "INSERT INTO visibility_grants "
        "(grantee_tenant_id, target_all, can_view_metadata, can_view_data, created_by) "
        "SELECT tenant_id, true, true, true, %s FROM tenants",
        (TENANT_A,),
    )
    report = verify(seeded)
    check = _check(report, "tenant_isolation")
    assert check.status == SKIP
    assert "tenant" in check.detail.lower()


def test_el_baseline_es_serializable(seeded: psycopg.Connection) -> None:
    """Se guarda junto al dump: si no es JSON, no acompaña al respaldo."""
    import json

    base = capture_baseline(seeded)
    assert json.loads(json.dumps(base)) == base


def test_el_baseline_ve_los_dos_tenants(seeded: psycopg.Connection) -> None:
    base = capture_baseline(seeded)
    assert base["tables"]["tenants"]["rows"] >= 2
    assert TENANT_A != TENANT_B and SITE_A  # los fixtures que sostienen el resto


# ===========================================================================
# AUDITORÍA ADVERSARIAL (2026-08-08) — los seis daños que salían VERDE, el
# verde-por-omisión, el rechazo por la razón equivocada y el dueño que escapa.
# Ninguno de estos escenarios estaba cubierto antes.
# ===========================================================================


def test_un_skip_jamas_puede_leerse_como_verde(seeded: psycopg.Connection) -> None:
    """El verde por OMISIÓN: sin baseline se borraba una tabla entera y salía VERDE.

    Un SKIP no es un PASS. Sin la huella del origen hay comprobaciones que no se
    pueden ejercer, y un veredicto que no las distingue de las ejercidas es
    exactamente el fallo que esta tarea existe para matar. El estado correcto no
    es VERDE ni ROJO: es INDETERMINADO, y no sale por la puerta del 0.
    """
    report = verify(seeded)  # sin baseline
    assert report.skipped, "sin baseline hay comprobaciones que no se pueden ejercer"
    assert report.verdict == INDETERMINADO
    assert not report.ok, "una base con comprobaciones sin ejercer NO está verificada"


def test_el_daño_del_auditor_ya_no_pasa_por_omision(seeded: psycopg.Connection) -> None:
    """El escenario exacto del auditor: tabla entera fuera y sin baseline."""
    seeded.execute("DROP TABLE quorum_votes CASCADE")
    report = verify(seeded)
    assert report.verdict == INDETERMINADO
    assert not report.ok


def test_un_error_que_no_es_la_guarda_no_cuenta_como_rechazo(
    seeded: psycopg.Connection,
) -> None:
    """Se daba por buena CUALQUIER excepción: permiso, lock, solo lectura…"""
    from psycopg import sql as _sql

    from takab_api.ops.restore_check import _rejected_by_guard

    real = _sql.SQL(
        "UPDATE audit_log SET {c} = {c} WHERE audit_id IN (SELECT audit_id FROM audit_log LIMIT 1)"
    ).format(c=_sql.Identifier("verb"))
    assert _rejected_by_guard(seeded, real) is True

    otro = _sql.SQL("UPDATE tabla_que_no_existe SET x = 1")
    assert _rejected_by_guard(seeded, otro) is False


def test_guarda_rota_en_transaccion_de_solo_lectura(seeded: psycopg.Connection) -> None:
    """El escenario B del auditor: guarda NEUTRALIZADA + error 25006 → daba PASS.

    Verificar la base lateral con `default_transaction_read_only` antes del swap
    es justo lo que hace un operador prudente, y bajo ese modo TODA escritura
    falla — con la guarda puesta o sin ella. El verificador no puede leer eso
    como "la tabla rechaza escrituras".
    """
    seeded.execute("ALTER TABLE audit_log DISABLE TRIGGER trg_audit_log_append_only")
    seeded.execute(
        "CREATE FUNCTION probe_solo_lectura() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN RAISE EXCEPTION 'cannot execute UPDATE in a read-only transaction' "
        "USING ERRCODE = '25006'; END $$"
    )
    seeded.execute(
        "CREATE TRIGGER trg_probe_solo_lectura BEFORE UPDATE OR DELETE ON audit_log "
        "FOR EACH ROW EXECUTE FUNCTION probe_solo_lectura()"
    )
    report = verify(seeded)
    check = _check(report, "append_only_enforced")
    assert check.status == FAIL, "un 25006 no es la guarda append-only"
    assert "audit_log" in check.detail


def test_job_de_retencion_presente_pero_DESACTIVADO(seeded: psycopg.Connection) -> None:
    """`scheduled => false`: la política está en el catálogo y no corre nunca."""
    seeded.execute(
        "SELECT alter_job((SELECT job_id FROM timescaledb_information.jobs "
        "WHERE proc_name = 'policy_retention' AND hypertable_name = 'device_health'), "
        "scheduled => false)"
    )
    report = verify(seeded)
    assert _check(report, "timescale_policies").status == FAIL
    assert "device_health" in _check(report, "timescale_policies").detail


def test_check_constraint_perdida(seeded: psycopg.Connection) -> None:
    """Verificado por el auditor: sin el CHECK entra `severity='BASURA…'`."""
    base = capture_baseline(seeded)
    seeded.execute("ALTER TABLE incidents DROP CONSTRAINT incidents_severity_check")
    report = verify(seeded, baseline=base)
    assert _check(report, "constraints").status == FAIL
    assert "incidents_severity_check" in _check(report, "constraints").detail


def test_clave_foranea_perdida(seeded: psycopg.Connection) -> None:
    base = capture_baseline(seeded)
    seeded.execute("ALTER TABLE sites DROP CONSTRAINT sites_tenant_id_fkey")
    report = verify(seeded, baseline=base)
    assert _check(report, "constraints").status == FAIL
    assert "sites_tenant_id_fkey" in _check(report, "constraints").detail


def test_columna_de_negocio_perdida(seeded: psycopg.Connection) -> None:
    """Una columna que no viaja: mismos conteos, mismo inventario de tablas."""
    base = capture_baseline(seeded)
    seeded.execute("ALTER TABLE incidents DROP COLUMN closed_at")
    report = verify(seeded, baseline=base)
    assert _check(report, "columns").status == FAIL
    assert "incidents.closed_at" in _check(report, "columns").detail


def test_continuous_aggregate_vaciado(seeded: psycopg.Connection) -> None:
    """El cagg existe, es cagg, y está VACÍO: la consola pinta cifras viejas.

    `row_counts` filtraba `relkind IN ('r','p')`, así que los caggs no se
    contaban nunca. Se cuenta su hypertable de MATERIALIZACIÓN, no la vista: la
    vista con agregación en tiempo real recalcularía del crudo y taparía el hueco.
    """
    # Se materializa a mano una fila —exactamente lo que escribe un refresh, que
    # no puede correr dentro de una transacción— para que el vaciado posterior
    # tenga algo que vaciar.
    from psycopg import sql as _sql

    esquema, tabla = seeded.execute(
        "SELECT materialization_hypertable_schema, materialization_hypertable_name "
        "FROM timescaledb_information.continuous_aggregates WHERE view_name = 'site_metrics_1m'"
    ).fetchone()
    mat = _sql.SQL("{}.{}").format(_sql.Identifier(esquema), _sql.Identifier(tabla))
    seeded.execute(
        _sql.SQL(
            "INSERT INTO {} (bucket, tenant_id, site_id, max_pga_g) VALUES (now(), %s, %s, 0.5)"
        ).format(mat),
        (TENANT_A, SITE_A),
    )
    borrar = _sql.SQL("DELETE FROM {}").format(mat)

    base = capture_baseline(seeded)
    assert base["cagg_rows"]["site_metrics_1m"] == 1, "la huella tiene que ver el cagg"

    seeded.execute(borrar)
    report = verify(seeded, baseline=base)
    assert _check(report, "row_counts").status == FAIL
    assert "site_metrics_1m" in _check(report, "row_counts").detail


def test_grant_revocado_a_la_api(seeded: psycopg.Connection) -> None:
    """El peor de los seis: la consola no arranca y las 19 salían en verde."""
    base = capture_baseline(seeded)
    seeded.execute("REVOKE ALL ON incidents FROM takab_app")
    report = verify(seeded, baseline=base)
    assert _check(report, "privileges").status == FAIL
    assert "takab_app" in _check(report, "privileges").detail
    assert "incidents" in _check(report, "privileges").detail


def test_el_dueño_superusuario_escapa_de_la_RLS_aunque_haya_FORCE(
    seeded: psycopg.Connection,
) -> None:
    """Retractación medida: FORCE **no** sujeta a un superusuario.

    Comprobado sobre una base migrada: dueño superusuario, `relforcerowsecurity`
    puesto, `app.tenant_id` ajeno → la fila se ve igual. `FORCE` obliga al dueño
    NORMAL; `BYPASSRLS` (y todo superusuario lo tiene) se salta la RLS con FORCE
    o sin él. El filtro `AND NOT relforcerowsecurity` volvía ciega esta
    comprobación justo en el caso que produce un `pg_restore --no-owner`.
    """
    seeded.execute("ALTER TABLE incidents OWNER TO takab")  # takab es superusuario
    report = verify(seeded)
    check = _check(report, "rls_owner_escape")
    assert check.status == WARN
    assert "incidents" in check.detail
    assert _check(report, "rls_flags").status == PASS, "y conserva su FORCE: ése es el punto"


def test_expectativa_vacia_no_puede_dar_PASS(seeded: psycopg.Connection) -> None:
    """MEDIO-1: derivar de un fichero que puede leerse vacío es peor que enumerar."""
    from takab_api.ops.restore_check import Expectations

    report = verify(seeded, expectations=Expectations())
    for nombre in (
        "extensions",
        "append_only_triggers",
        "rls_flags",
        "rls_policies",
        "roles",
        "hypertables",
        "barrier_views",
        "timescale_policies",
    ):
        check = _check(report, nombre)
        assert check.status == SKIP, f"{nombre} dio {check.status} sin expectativa"
        assert check.detail.strip()
    assert report.verdict == INDETERMINADO


def test_la_punta_del_dato_atrasada_es_FALLO_no_aviso(seeded: psycopg.Connection) -> None:
    """BAJO: la punta del dato ES la medida del RPO (R-5 del §6 del runbook)."""
    base = capture_baseline(seeded)
    seeded.execute("DELETE FROM waveform_features_1s")
    report = verify(seeded, baseline=base)
    assert _check(report, "data_tip").status == FAIL
    assert "waveform_features_1s" in _check(report, "data_tip").detail


def test_sin_PK_la_guarda_de_compliance_no_se_ejerce_y_eso_es_FALLO(
    seeded: psycopg.Connection,
) -> None:
    """MEDIO-4: el daño que la herramienta persigue apagaba otra comprobación.

    Al perderse la PRIMARY KEY (lo que el §3 del runbook hace con las tres
    hypertables), la aserción negativa deja de poder direccionar una fila. Con
    filas dentro eso NO es un aviso: es una tabla de la regla de oro 11 sin
    verificar, y salía WARN — que no tumba el veredicto.
    """
    seeded.execute("ALTER TABLE audit_log DROP CONSTRAINT audit_log_pkey")
    report = verify(seeded)
    check = _check(report, "append_only_enforced")
    assert check.status == FAIL
    assert "audit_log" in check.detail
    assert "SIN PK" in check.detail


# ===========================================================================
# [T-2.80.c] LA RENDIJA DE ARCO: que siga siendo del TAMAÑO que era
#
# T-2.80 abrió en `life_checkins` una excepción de UNA sola columna (anular
# `geom`, la anonimización del titular) y esa tabla dejó de ser append-only puro.
# El verificador tuvo que dejar de tratarla como tal — correcto entonces, hueco
# ahora: tras un restore nadie comprobaba el TAMAÑO de la rendija.
# ===========================================================================


def _rendija(conn: psycopg.Connection) -> set[str]:
    """Columnas de `life_checkins` sobre las que `takab_app` puede escribir HOY."""
    return {
        r[0]
        for r in conn.execute(
            "SELECT a.attname FROM pg_attribute a "
            "WHERE a.attrelid = 'life_checkins'::regclass AND a.attnum > 0 "
            "AND NOT a.attisdropped "
            "AND has_column_privilege('takab_app', a.attrelid, a.attnum, 'UPDATE')"
        ).fetchall()
    }


def test_la_rendija_se_deriva_del_esquema_y_es_exactamente_geom() -> None:
    """La expectativa sale de `db/schema.sql`, no de un literal en el verificador."""
    exp = declared_expectations()
    assert exp.column_grants[("takab_app", "life_checkins")] == frozenset({"geom"})


def test_sobre_una_base_sana_la_rendija_esta_donde_tiene_que_estar(
    seeded: psycopg.Connection,
) -> None:
    report = verify(seeded)
    assert _check(report, "column_grants").status == PASS, render(report)
    assert _check(report, "column_grant_enforced").status == PASS, render(report)


def test_una_base_restaurada_con_el_GRANT_A_NIVEL_DE_TABLA_es_ROJA(
    seeded: psycopg.Connection,
) -> None:
    """EL escenario de la ficha, y con la prueba de que antes NO se veía.

    `pg_restore` reconstruye los ACL del dump. Una base restaurada con `GRANT
    UPDATE ON life_checkins` a nivel de TABLA en vez de por columna deja
    `status` y `user_id` de un check-in de vida reescribibles desde la API: se
    podría cambiar «necesito ayuda» por «estoy bien» en la evidencia de un
    rescate. Lo pararía el trigger, sí — pero la protección habría pasado de dos
    capas a una, EN SILENCIO.

    La segunda mitad del test es la que hace que valga: se toma la huella del
    ORIGEN sano y se comprueba que `privileges` —la comprobación que ya existía—
    sigue en PASS sobre la base rota. No es un defecto suyo: compara con
    `has_table_privilege`, que devuelve `false` para un grant de columna, y solo
    mira en la dirección de lo que FALTA. Lo que sobra no lo veía nadie.
    """
    baseline = capture_baseline(seeded)
    assert _rendija(seeded) == {"geom"}, "el arnés no partió de la rendija esperada"

    seeded.execute("GRANT UPDATE ON life_checkins TO takab_app")
    assert len(_rendija(seeded)) > 1, "el arnés NO ensanchó la rendija: no se está midiendo nada"

    report = verify(seeded, baseline=baseline)
    check = _check(report, "column_grants")
    assert check.status == FAIL, render(report)
    assert "life_checkins" in check.detail and "TABLA" in check.detail
    assert report.verdict == ROJO

    assert _check(report, "privileges").status == PASS, (
        "si `privileges` cazara esto, la comprobación nueva sobraría — y no lo caza: "
        "compara con has_table_privilege y solo mira lo que FALTA"
    )


def test_una_rendija_que_CRECIO_una_columna_es_ROJA(seeded: psycopg.Connection) -> None:
    """Sin llegar al grant de tabla: basta con una columna de más.

    `status` es «estoy bien» / «necesito ayuda» en la evidencia de un rescate.
    """
    seeded.execute("GRANT UPDATE (status) ON life_checkins TO takab_app")
    check = _check(verify(seeded), "column_grants")
    assert check.status == FAIL
    assert "status" in check.detail and "MÁS" in check.detail


def test_una_rendija_que_se_CERRO_tambien_es_roja(seeded: psycopg.Connection) -> None:
    """El otro lado, que es igual de restore roto: sin la rendija, ARCO deja de
    poder anonimizar y el titular pierde su derecho sin que nada se queje."""
    seeded.execute("REVOKE UPDATE (geom) ON life_checkins FROM takab_app")
    check = _check(verify(seeded), "column_grants")
    assert check.status == FAIL
    assert "geom" in check.detail and "MENOS" in check.detail


def test_el_guard_de_la_rendija_sigue_rechazando_el_UPDATE_QUE_NO_CAMBIA_NADA(
    seeded: psycopg.Connection,
) -> None:
    """La segunda capa, ejercida con el caso que más fácil se cuela.

    Un `SET c = c` sobre una tabla de evidencia parece inofensivo, y aceptarlo
    significaría que `life_checkin_arco_guard()` compara mal: exige la
    transición REAL (`geom` con valor → NULL), no solo que `NEW.geom` sea NULL.
    """
    seeded.execute("ALTER TABLE life_checkins DISABLE TRIGGER trg_life_checkins_arco_guard")
    check = _check(verify(seeded), "column_grant_enforced")
    assert check.status == FAIL, "un guard DESACTIVADO sigue en pg_trigger y no para nada"
    assert "life_checkins" in check.detail and "UPDATE (no-op)" in check.detail


def test_para_BORRAR_la_tabla_de_la_rendija_no_tiene_excepcion_alguna(
    seeded: psycopg.Connection,
) -> None:
    """La rendija es de UPDATE. El DELETE lo sigue vetando el guard canónico."""
    seeded.execute("DROP TRIGGER trg_life_checkins_append_only ON life_checkins")
    check = _check(verify(seeded), "column_grant_enforced")
    assert check.status == FAIL
    assert "DELETE" in check.detail


def test_un_SKIP_de_la_rendija_no_cuenta_como_PASS(seeded: psycopg.Connection) -> None:
    """La lección de la Fase 2.6, aplicada a esta comprobación concreta.

    Si la expectativa no se puede derivar —`db/schema.sql` ilegible, el DDL
    reformateado de forma que la regex no case— la comprobación NO se da por
    buena: pasaría sobre cualquier base. Se declara SALTADA con su razón, y una
    base con comprobaciones sin ejercer no está verificada.
    """
    from dataclasses import replace

    exp = replace(declared_expectations(), column_grants={})
    report = verify(seeded, expectations=exp)

    for nombre in ("column_grants", "column_grant_enforced"):
        check = _check(report, nombre)
        assert check.status == SKIP and check.detail, nombre
    assert report.verdict == INDETERMINADO
    assert not report.ok


def test_la_huella_del_origen_registra_la_rendija(seeded: psycopg.Connection) -> None:
    """`privileges` no la ve (usa `has_table_privilege`), así que si la huella no
    la llevara aparte, una base restaurada en la nube —donde el verificador no
    tiene `db/schema.sql` dentro de la imagen— no tendría contra qué compararla."""
    huella = capture_baseline(seeded)
    rendijas = {(g[0], g[1]): set(g[2]) for g in huella["column_grants"]}
    assert rendijas[("takab_app", "life_checkins")] == {"geom"}
    assert "UPDATE" not in huella["privileges"]["life_checkins"].get("takab_app", []), (
        "si `privileges` registrara el UPDATE de la rendija, el origen y la base rota "
        "se verían iguales"
    )
