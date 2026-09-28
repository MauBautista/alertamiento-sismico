"""Migración 0073 · quién firmó y en qué banda (T-9.31 · D-43).

``signed_by NOT NULL`` sigue significando «firmado» (así el reingreso lo libera sin
tocar su regla), pero QUIÉN firmó se lee de ``signature_kind``. Las filas viejas
quedan en NULL: no se inventa un firmante que no consta.
"""

from __future__ import annotations

import importlib.util
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

from takab_api.dictamen.sistema import SYSTEM_DICTAMEN_SIGNER_UUID
from tests.dictamen.test_service import _dsn

RUTA = (
    Path(__file__).resolve().parents[2] / "migrations/versions/0073_firma_y_banda_del_dictamen.py"
)


def _mig():
    spec = importlib.util.spec_from_file_location("mig0073", RUTA)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    c = psycopg.connect(_dsn(), autocommit=False)
    try:
        yield c
    finally:
        c.rollback()
        c.close()


def _incidente(conn: psycopg.Connection) -> tuple[str, str]:
    tenant, site, inc = (str(uuid.uuid4()) for _ in range(3))
    conn.execute(
        "INSERT INTO tenants (tenant_id, code, name) VALUES (%s,%s,'M73')", (tenant, tenant[:8])
    )
    conn.execute(
        "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES (%s,%s,%s,'S', "
        "ST_SetSRID(ST_MakePoint(-99.5, 12.5),4326)::geography)",
        (site, tenant, f"M-{site[:8]}"),
    )
    conn.execute(
        "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, opened_at, "
        "severity, trigger) VALUES (%s,%s,%s,%s,now(),'info','local_threshold')",
        (inc, str(uuid.uuid4()), tenant, site),
    )
    return tenant, inc


def _insert(conn, tenant, inc, *, kind, band, signed_by) -> None:
    conn.execute(
        "INSERT INTO dictamens (tenant_id, incident_id, status, basis, signed_by, "
        "signature_kind, band) VALUES (%s,%s,'normal_operation','{}'::jsonb,%s,%s,%s)",
        (tenant, inc, signed_by, kind, band),
    )


def test_la_constante_del_firmante_es_UNA_y_la_cita_la_migracion() -> None:
    assert SYSTEM_DICTAMEN_SIGNER_UUID == _mig().SYSTEM_DICTAMEN_SIGNER_UUID
    uuid.UUID(SYSTEM_DICTAMEN_SIGNER_UUID)  # es un UUID válido


def test_las_columnas_existen_y_las_viejas_quedan_en_NULL(conn) -> None:
    tenant, inc = _incidente(conn)
    conn.execute(
        "INSERT INTO dictamens (tenant_id, incident_id, status, basis) "
        "VALUES (%s,%s,'normal_operation','{}'::jsonb)",
        (tenant, inc),
    )
    row = conn.execute(
        "SELECT signature_kind, band FROM dictamens WHERE incident_id = %s", (inc,)
    ).fetchone()
    assert row == (None, None)


@pytest.mark.parametrize(
    ("kind", "band", "signed_by"),
    [
        ("otro", "verde", "u"),
        ("inspector", "morado", "u"),
        ("inspector", "verde", None),  # un tipo de firma sin firmante no existe
        ("system", "verde", "u"),  # el sistema firma SOLO con su identidad fija
        ("inspector", "verde", "sys"),  # y nadie más firma con ella
    ],
)
def test_los_CHECK_rechazan(conn, kind, band, signed_by) -> None:
    tenant, inc = _incidente(conn)
    firmante = {"u": str(uuid.uuid4()), "sys": SYSTEM_DICTAMEN_SIGNER_UUID, None: None}[signed_by]
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(conn, tenant, inc, kind=kind, band=band, signed_by=firmante)


@pytest.mark.parametrize(
    ("kind", "signed_by"),
    [("inspector", "u"), ("confirmation", "u"), ("system", "sys"), (None, None)],
)
def test_los_CHECK_admiten(conn, kind, signed_by) -> None:
    tenant, inc = _incidente(conn)
    firmante = {"u": str(uuid.uuid4()), "sys": SYSTEM_DICTAMEN_SIGNER_UUID, None: None}[signed_by]
    _insert(conn, tenant, inc, kind=kind, band="amarillo", signed_by=firmante)


def test_la_migracion_es_idempotente_con_el_rol_de_la_nube(conn) -> None:
    """Re-ejecutar cada bloque sobre una base que ya la tiene no rompe nada."""
    mod = _mig()
    for sql in mod.BLOQUES:
        conn.execute(sql)
    for sql in mod.BLOQUES:
        conn.execute(sql)


def test_el_worker_puede_leer_los_reportes_de_dano(conn) -> None:
    """En una base EXISTENTE `damage_reports` (0018) no tenía GRANT a takab_ingest;
    la 0001 sólo lo da en base nueva. El worker v2 los lee."""
    assert conn.execute(
        "SELECT has_table_privilege('takab_ingest', 'damage_reports', 'SELECT')"
    ).fetchone()[0]
    assert any("GRANT SELECT ON damage_reports TO takab_ingest" in b for b in _mig().BLOQUES)


def test_el_espejo_de_schema_sql_cita_la_misma_identidad() -> None:
    esquema = (Path(__file__).resolve().parents[3] / "db/schema.sql").read_text()
    assert f"'{SYSTEM_DICTAMEN_SIGNER_UUID}'::uuid" in esquema
    assert "GRANT SELECT ON damage_reports TO takab_ingest" in esquema


def test_la_identidad_del_sistema_SIN_tipo_tambien_se_rechaza(conn) -> None:
    """[F3·r2] El CHECK ata las DOS direcciones también con ``signature_kind`` NULL:
    ``signed_by`` = la identidad del sistema ⇔ ``signature_kind = 'system'``. Se
    re-ejecuta la migración primero: una base que corrió la 0073 VIEJA (sin esta
    dirección) tiene que quedar con la definición nueva."""
    for sql in _mig().BLOQUES:
        conn.execute(sql)
    tenant, inc = _incidente(conn)
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(conn, tenant, inc, kind=None, band="verde", signed_by=SYSTEM_DICTAMEN_SIGNER_UUID)


def test_el_espejo_de_schema_sql_ata_las_dos_direcciones() -> None:
    esquema = (Path(__file__).resolve().parents[3] / "db/schema.sql").read_text()
    bloque = esquema[esquema.index("CONSTRAINT ck_dictamens_firmante") :][:500]
    assert "IS NOT DISTINCT FROM 'system'" in bloque
    assert f"IS NOT DISTINCT FROM '{SYSTEM_DICTAMEN_SIGNER_UUID}'::uuid" in bloque
    assert "IS NOT DISTINCT FROM 'system'" in "".join(_mig().BLOQUES)


def _oid_firmante(conn: psycopg.Connection) -> int:
    return conn.execute(
        "SELECT oid FROM pg_constraint WHERE conrelid = 'dictamens'::regclass "
        "AND conname = 'ck_dictamens_firmante'"
    ).fetchone()[0]


def test_la_SEGUNDA_corrida_NO_hace_DROP_ni_ADD_del_firmante(conn) -> None:
    """[F3·r3] La guarda buscaba 'IS NOT DISTINCT FROM' en `pg_get_constraintdef`, y
    Postgres lo deparsea como `NOT (x IS DISTINCT FROM y)`: cada corrida hacía DROP +
    ADD (ACCESS EXCLUSIVE y revalidar toda la tabla). Un DROP/ADD cambia el `oid` de
    la restricción; una guarda que es no-op lo deja igual."""
    mod = _mig()
    for sql in mod.BLOQUES:
        conn.execute(sql)
    antes = _oid_firmante(conn)
    for sql in mod.BLOQUES:
        conn.execute(sql)
    assert _oid_firmante(conn) == antes, "la 2ª corrida recreó ck_dictamens_firmante"


def test_una_base_con_el_firmante_VIEJO_queda_con_el_nuevo(conn) -> None:
    """La versión anterior de la 0073 (no NULL-segura) se sustituye una vez."""
    conn.execute("SET ROLE takab_migrator")
    conn.execute("ALTER TABLE dictamens DROP CONSTRAINT ck_dictamens_firmante")
    conn.execute(
        "ALTER TABLE dictamens ADD CONSTRAINT ck_dictamens_firmante CHECK "
        "(signature_kind IS NULL OR (signed_by IS NOT NULL AND "
        f"(signature_kind = 'system') = (signed_by = '{SYSTEM_DICTAMEN_SIGNER_UUID}'::uuid)))"
    )
    conn.execute("RESET ROLE")
    for sql in _mig().BLOQUES:
        conn.execute(sql)
    tenant, inc = _incidente(conn)
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(conn, tenant, inc, kind=None, band="verde", signed_by=SYSTEM_DICTAMEN_SIGNER_UUID)


def test_el_espejo_de_schema_sql_lleva_la_MARCA_del_firmante() -> None:
    """Una base nueva (0001 = schema.sql) no debe recrear la restricción al correr la
    0073: lleva la misma marca que la guarda busca."""
    esquema = (Path(__file__).resolve().parents[3] / "db/schema.sql").read_text()
    assert f"'{_mig().MARCA_FIRMANTE}'" in esquema
