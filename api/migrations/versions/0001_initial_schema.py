"""T-1.16 · esquema inicial + roles + RLS + gov_ack_incident

Reproduce ``db/schema.sql`` (fuente de verdad única del DDL, v1.1) y añade lo que
el schema documenta pero delega a esta migración (schema §0 y §8):

  * los 3 roles de conexión (``takab_migrator`` dueño, ``takab_app`` API,
    ``takab_ingest`` BYPASSRLS para workers de ingesta);
  * el cuerpo del schema se crea **bajo el rol ``takab_migrator``**, de modo que
    las tablas de negocio queden dueñas de un rol NO-superusuario — sin esto
    ``FORCE ROW LEVEL SECURITY`` sería inverificable (un superusuario salta RLS);
  * los GRANT del modelo de conexión;
  * la función ``gov_ack_incident`` (SECURITY DEFINER, dueño ``takab_ingest``),
    única vía de escritura de ``gov_operator`` (acuse open→acked con auditoría).

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-06
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# db/schema.sql relativo a este archivo: versions -> migrations -> api -> repo.
_SCHEMA_SQL = Path(__file__).resolve().parents[3] / "db" / "schema.sql"

# Roles de conexión (schema §0). Idempotente y sin passwords (regla de oro 6):
# en local los tests hacen SET ROLE desde el superusuario; producción los
# provisiona con LOGIN/PASSWORD vía Terraform + Secrets Manager.
_ROLES = """
DO $$
BEGIN
  -- LOGIN: es dueño de las hypertables y TimescaleDB exige LOGIN para correr sus
  -- background jobs (compresión/retención/refresh de caggs) como el owner. Sin
  -- password (regla de oro 6): el bgworker no lo necesita y los tests usan SET ROLE.
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'takab_migrator') THEN
    CREATE ROLE takab_migrator LOGIN NOSUPERUSER;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'takab_app') THEN
    CREATE ROLE takab_app NOLOGIN NOSUPERUSER;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'takab_ingest') THEN
    CREATE ROLE takab_ingest NOLOGIN NOSUPERUSER BYPASSRLS;
  END IF;
END $$;
"""

_EXTENSIONS = """
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
"""

# GRANTs del modelo de conexión. La API (takab_app) recibe DML amplio pero la RLS
# default-deny + los triggers append-only son el guardián real: donde no hay política
# de escritura (device_health/rule_evaluations solo tienen policy de lectura) RLS niega
# el INSERT aunque el GRANT exista. El crudo waveform se aísla por vista (REVOKE base
# abajo). takab_ingest salta RLS (BYPASSRLS).
_GRANTS = """
GRANT USAGE ON SCHEMA public TO takab_app, takab_ingest;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO takab_app;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO takab_ingest;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO takab_app, takab_ingest;

-- [ANALISIS-00 v1.2] waveform_features_1s no puede llevar RLS (tiene caggs): la API
-- (takab_app) lee el crudo SOLO por la vista security_barrier, nunca la tabla base.
-- takab_ingest (BYPASSRLS) conserva el acceso a la base para escribir features.
REVOKE ALL ON waveform_features_1s FROM takab_app;
"""

# gov_ack_incident: única escritura de gov_operator. SECURITY DEFINER + dueño
# takab_ingest (BYPASSRLS) para poder tocar el incidente de OTRO tenant, pero con
# validación dura dentro: rol = gov_operator, tenant visibility = 'gov_shared',
# transición open->acked, y traza en audit_log (schema §8).
_GOV_ACK = """
CREATE FUNCTION gov_ack_incident(p_incident_id uuid) RETURNS void
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
  v_tenant uuid;
  v_state  text;
  v_vis    text;
  v_actor  text;
BEGIN
  IF app_role() <> 'gov_operator' THEN
    RAISE EXCEPTION 'gov_ack_incident: solo gov_operator (rol actual=%)', app_role();
  END IF;

  SELECT i.tenant_id, i.state, t.visibility
    INTO v_tenant, v_state, v_vis
    FROM incidents i JOIN tenants t ON t.tenant_id = i.tenant_id
   WHERE i.incident_id = p_incident_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'gov_ack_incident: incidente % inexistente', p_incident_id;
  END IF;
  IF v_vis <> 'gov_shared' THEN
    RAISE EXCEPTION 'gov_ack_incident: tenant no es gov_shared';
  END IF;
  IF v_state <> 'open' THEN
    RAISE EXCEPTION 'gov_ack_incident: transicion invalida % -> acked', v_state;
  END IF;

  UPDATE incidents SET state = 'acked' WHERE incident_id = p_incident_id;

  v_actor := 'gov:' || coalesce(nullif(current_setting('app.user_id', true), ''), 'unknown');
  INSERT INTO audit_log (tenant_id, actor, verb, object, meta)
  VALUES (v_tenant, v_actor, 'ack', 'incident:' || p_incident_id::text,
          jsonb_build_object('via', 'gov_ack_incident'));
END $fn$;

ALTER FUNCTION gov_ack_incident(uuid) OWNER TO takab_ingest;
REVOKE EXECUTE ON FUNCTION gov_ack_incident(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION gov_ack_incident(uuid) TO takab_app;
"""


def _schema_body() -> str:
    """Cuerpo de db/schema.sql sin las líneas CREATE EXTENSION.

    Las extensiones exigen superusuario y se crean aparte; el resto corre bajo
    ``takab_migrator``. Se aplica verbatim: schema.sql es la fuente de verdad.
    """
    text = _SCHEMA_SQL.read_text(encoding="utf-8")
    if "TAKAB Technology" not in text:
        raise RuntimeError(f"db/schema.sql no encontrado o inesperado en {_SCHEMA_SQL}")
    body = "\n".join(
        ln for ln in text.splitlines() if not ln.strip().startswith("CREATE EXTENSION")
    )
    # Los caggs se crean WITH NO DATA (forma migration-safe): en una DB nueva no hay
    # filas que materializar → equivalente a WITH DATA, y la refresh policy backfillea
    # después. Evita además el materializado síncrono durante la migración. (Los dos
    # caggs terminan en este mismo GROUP BY; no hay otras materialized views.)
    marker = "GROUP BY bucket, tenant_id, site_id;"
    if body.count(marker) != 2:
        raise RuntimeError(f"esperaba 2 continuous aggregates; encontré {body.count(marker)}")
    body = body.replace(marker, "GROUP BY bucket, tenant_id, site_id\nWITH NO DATA;")
    return body


_DOLLAR = re.compile(r"\$[A-Za-z0-9_]*\$")


def _split_statements(sql: str) -> list[str]:
    """Divide SQL en sentencias por ``;`` de nivel superior.

    Respeta comentarios de línea (``--``) y de bloque (``/* */``), strings entre
    comillas simples (con ``''`` escapado) y cuerpos dollar-quoted (``$$``/``$fn$``),
    que contienen ``;`` internos que NO separan sentencias. Necesario para poder
    correr cada sentencia en su propia transacción (ver upgrade()).
    """
    stmts: list[str] = []
    buf: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]
        if c == "-" and i + 1 < n and sql[i + 1] == "-":  # comentario de línea
            j = sql.find("\n", i)
            j = n if j == -1 else j
            buf.append(sql[i:j])
            i = j
        elif c == "/" and i + 1 < n and sql[i + 1] == "*":  # comentario de bloque
            j = sql.find("*/", i + 2)
            j = n if j == -1 else j + 2
            buf.append(sql[i:j])
            i = j
        elif c == "'":  # string
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            buf.append(sql[i:j])
            i = j
        elif c == "$" and (m := _DOLLAR.match(sql, i)):  # cuerpo dollar-quoted
            tag = m.group(0)
            end = sql.find(tag, i + len(tag))
            end = n if end == -1 else end + len(tag)
            buf.append(sql[i:end])
            i = end
        elif c == ";":  # fin de sentencia
            stmt = "".join(buf).strip()
            if _has_sql(stmt):
                stmts.append(stmt)
            buf = []
            i += 1
        else:
            buf.append(c)
            i += 1
    tail = "".join(buf).strip()
    if _has_sql(tail):
        stmts.append(tail)
    return stmts


def _has_sql(stmt: str) -> bool:
    """True si al quitar comentarios queda algo ejecutable (no solo comentarios)."""
    no_line = re.sub(r"--[^\n]*", "", stmt)
    no_block = re.sub(r"/\*.*?\*/", "", no_line, flags=re.DOTALL)
    return bool(no_block.strip())


def _exec_all(sql: str) -> None:
    """Ejecuta cada sentencia de ``sql`` por separado, en su propia transacción.

    Se usa dentro de un ``autocommit_block``: TimescaleDB prohíbe crear continuous
    aggregates y habilitar compresión (columnstore) dentro de la misma transacción,
    así que no podemos correr el schema como un único comando. Cada sentencia va por
    el cursor psycopg SIN params (protocolo simple): el cuerpo tiene ``%`` (RAISE) y
    ``:`` (comentarios) que el binding de parámetros interpretaría como placeholders.
    """
    dbapi = op.get_bind().connection.dbapi_connection
    for stmt in _split_statements(sql):
        with dbapi.cursor() as cur:
            cur.execute(stmt)


def upgrade() -> None:
    # autocommit_block: cada sentencia commitea sola. Imprescindible para los
    # continuous aggregates de TimescaleDB (no van dentro de una transacción junto
    # a la compresión). Contrapartida: la migración inicial NO es atómica; si algo
    # falla a mitad, `alembic downgrade base` (DROP OWNED) limpia el estado parcial.
    with op.get_context().autocommit_block():
        _exec_all(_ROLES)
        _exec_all(_EXTENSIONS)
        # takab_migrator debe poder crear objetos en public y ser dueño de ellos.
        _exec_all("GRANT CREATE, USAGE ON SCHEMA public TO takab_migrator;")
        # El cuerpo del DDL se crea como takab_migrator (dueño no-superusuario).
        # SET ROLE (no LOCAL) persiste en la conexión entre sentencias en autocommit.
        _exec_all("SET ROLE takab_migrator;")
        _exec_all(_schema_body())
        _exec_all("RESET ROLE;")
        _exec_all(_GRANTS)
        _exec_all(_GOV_ACK)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        _exec_all("RESET ROLE;")
        # DROP OWNED barre tablas, hypertables, caggs, funciones, políticas y los
        # privilegios concedidos a cada rol; deja intacta alembic_version (dueño: el
        # superusuario de migración). Extensiones se dejan (infra de cluster).
        _exec_all("DROP OWNED BY takab_migrator, takab_app, takab_ingest CASCADE;")
        _exec_all("DROP ROLE IF EXISTS takab_app;")
        _exec_all("DROP ROLE IF EXISTS takab_ingest;")
        _exec_all("DROP ROLE IF EXISTS takab_migrator;")
