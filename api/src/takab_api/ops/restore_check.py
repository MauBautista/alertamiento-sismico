"""T-2.73 · Verificador de integridad de una base RESTAURADA.

`RUNBOOK-backup-restore-db.md:3` dice, literalmente, **"RESTORE JAMÁS PROBADO
(gate G-09)"**. Su §5 lista en prosa el checklist de verificación que un humano
teclea tras restaurar. Esto lo convierte en aserciones con veredicto.

**Por qué el §5 no basta, medido y no supuesto.** Restaurando una hypertable
cruda de features con el procedimiento tal como está escrito en el §3 del
runbook (`pg_restore -d takab_restore --no-owner`, sin
`timescaledb_pre_restore()`), sobre la misma imagen que corre en producción:

* **aborta el `COPY` de al menos un chunk y se pierden decenas de miles de
  filas, en silencio.** La MAGNITUD es variable por corrida —depende de qué
  chunk aborta y de cuánto se había copiado—, así que no hay una cifra fija que
  citar: tres mediciones sobre 600 000 filas dieron −11 471, −28 730 y −30 000.
  Lo reproducible es la pérdida, no su tamaño;
* desaparecen las PRIMARY KEY de las tres hypertables
  (`ONLY option not supported on hypertable operations`) — y sin PK muere la
  idempotencia del edge (regla de oro 3: `ON CONFLICT DO NOTHING` sobre qué);
* cambia la propiedad de todos los objetos y el rol de migraciones deja de poder
  migrar (`must be owner of table sites`): el siguiente despliegue muere;
* **el checklist del §5 sale entero en verde**: `max(ts)` fresco, extensión
  presente, 3 hypertables, RLS con sus dos banderas. (Se puede ver con los dos
  ojos a la vez: `restore_drill --como-el-runbook` imprime el §5 literal debajo
  del veredicto real.)

Un checklist que no ve decenas de miles de filas perdidas ni tres claves
primarias desaparecidas no es una verificación: es una ceremonia.

**Cómo se compone.** Dos capas, y la diferencia entre ellas importa:

1. **Invariantes absolutas** — se comprueban con la base restaurada delante y
   nada más. Es lo único disponible en un desastre real, cuando el origen ya no
   existe. Salen de derivar `db/schema.sql` (la fuente de verdad del DDL) y del
   propio catálogo de Postgres, no de una lista escrita a mano.
2. **Comparación contra el ORIGEN** (`baseline`) — la huella tomada antes del
   dump. Es la única forma de saber que no falta *nada*: una tabla entera que no
   viajó no deja hueco visible en el catálogo restaurado. Sin `baseline` estas
   comprobaciones se declaran SALTADAS con su razón; jamás se dan por buenas.

**Las comprobaciones negativas son las que valen.** `append_only_enforced` pasa
sólo si un `UPDATE` real de una fila **FALLA**. Contar filas en `pg_trigger`
daba verde con el trigger `DISABLE`d; leer `relrowsecurity` daba verde con una
política reescrita a `USING (true)`. Por eso el aislamiento entre tenants se
ejerce conectándose como `takab_app` y mirando si ve al vecino, que es la
diferencia entre "la bandera está puesta" y "el aislamiento funciona".

Nada de aquí entra jamás en el camino de disparo de actuadores (regla de oro 1).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql

# --------------------------------------------------------------------------- veredictos

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"
INFO = "INFO"
SKIP = "SKIP"

#: Sólo `FAIL` tumba el veredicto a ROJO. `WARN` es una observación que hay que
#: leer, no un rojo: si un aviso pudiera parar un restore, el operador aprendería
#: a ignorarlos, que es como mueren las alarmas.
_RED = (FAIL,)

#: Los tres veredictos. `INDETERMINADO` es el que faltaba y el que más importa.
VERDE = "VERDE"
ROJO = "ROJO"
INDETERMINADO = "INDETERMINADO"

#: MEDIO-1 · derivar de un fichero que puede leerse vacío es peor que enumerar.
#: Cuatro comprobaciones ya degradaban a SKIP cuando su expectativa venía vacía
#: (`roles`, `hypertables`, `barrier_views`, `timescale_policies`) y tres daban
#: PASS silencioso sobre CUALQUIER base. Y no hace falta que `db/schema.sql` se
#: lea vacío: basta un reformateo del DDL que rompa una regex de espacios fijos.
_SIN_EXPECTATIVA = (
    "no se pudo derivar del esquema ninguna expectativa de {que}. Con la expectativa "
    "vacía esta comprobación pasaría sobre cualquier base, así que NO se ejerce: "
    "revisa que `db/schema.sql` sea legible y que su DDL siga el formato que se parsea."
)

_SIN_VERIFICAR = (
    "una base con comprobaciones SIN EJERCER no está verificada. Un SKIP no es un PASS: "
    "el operador que lee VERDE hace el swap, y lo que no se comprobó no deja de estar roto "
    "por no haberlo mirado."
)

# --------------------------------------------------------------------------- enumerados
# Todo lo que NO se puede derivar vive aquí, con su razón. Un punto ciego
# declarado es un activo; uno escondido en una constante muda es una trampa.

ENUMERATED: dict[str, str] = {
    "la vista de aislamiento del crudo (`…_secure`)": (
        "La hypertable cruda de features no puede llevar RLS: TimescaleDB la prohíbe en una "
        "hypertable con continuous aggregates (timescale/timescaledb#6827) y ésta los tiene. "
        "Su aislamiento lo da la vista security_barrier `…_secure` + el REVOKE de la tabla "
        "base a takab_app, y por eso `tenant_isolation` mira POR LA VISTA. Cuál es la vista "
        "sí se enumera: se llama como la tabla más el sufijo, y ese sufijo está escrito aquí."
    ),
    "esquema `public`": (
        "Todas las consultas de catálogo se acotan a `public`. Lo que TimescaleDB guarda en "
        "`_timescaledb_catalog`/`_timescaledb_internal` (chunks, materializaciones) NO se "
        "inventaría objeto a objeto: se comprueba por sus efectos "
        "(`hypertables`, `row_counts`, `data_tip`)."
    ),
    "roles del clúster": (
        "Los roles son objetos de CLÚSTER: un `pg_dump` de una base NO los lleva dentro. La "
        "lista esperada se deriva de los `CREATE ROLE` de la migración 0001, que es donde el "
        "código los declara."
    ),
}

# --------------------------------------------------------------------------- modelo


@dataclass(frozen=True)
class Check:
    """Una comprobación con veredicto. `detail` NUNCA puede ir vacío.

    Un `SKIP` anónimo es cobertura falsa: quien lea el informe tiene que poder
    saber qué dejó de comprobarse y por qué, sin abrir el código.
    """

    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class Report:
    checks: tuple[Check, ...]

    @property
    def failed(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if c.status in _RED)

    @property
    def warned(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if c.status == WARN)

    @property
    def skipped(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if c.status == SKIP)

    @property
    def verdict(self) -> str:
        """VERDE sólo si TODO se ejerció y nada falló.

        El tercer estado no es cosmético. Sin él, `--baseline` es opcional y el
        módulo admite que hoy el cron no escribe la huella: eso significaba que
        el comando documentado para un incidente REAL podía imprimir VERDE sobre
        una base a la que le faltaba el 75 % de la telemetría y una tabla entera,
        y salir con código 0. Ahora eso es INDETERMINADO, y no es verde.
        """
        if self.failed:
            return ROJO
        if self.skipped:
            return INDETERMINADO
        return VERDE

    @property
    def ok(self) -> bool:
        """Verde de verdad: ni fallos ni comprobaciones sin ejercer."""
        return self.verdict == VERDE


@dataclass(frozen=True)
class Expectations:
    """Lo que la base restaurada DEBERÍA tener, derivado de la fuente de verdad."""

    extensions: frozenset[str] = frozenset()
    append_only: frozenset[str] = frozenset()
    guard_function: str = "forbid_update_delete"
    rls: Mapping[str, tuple[bool, bool]] = field(default_factory=dict)
    #: [T-2.73.b] Tablas cuyo esquema **declara EXPLÍCITAMENTE** que no llevan
    #: FORCE (`ALTER TABLE … NO FORCE ROW LEVEL SECURITY`). No es lo mismo que
    #: «no aparece su línea de FORCE»: eso es un olvido y tiene que seguir
    #: avisando. Esto es una decisión escrita en la fuente de verdad, y por eso
    #: es lo único que exime del aviso de `rls_on_tenant_tables`.
    no_force: frozenset[str] = frozenset()
    policies: Mapping[str, int] = field(default_factory=dict)
    hypertables: frozenset[str] = frozenset()
    barrier_views: frozenset[str] = frozenset()
    roles: frozenset[str] = frozenset()
    #: (proc_name, hypertable) de cada política de TimescaleDB: retención,
    #: compresión y refresco de caggs. Se pierden sin dejar hueco visible.
    timescale_policies: frozenset[tuple[str, str]] = frozenset()
    #: [T-2.80.c] LA RENDIJA. ``(rol, tabla) → columnas`` sobre las que el esquema
    #: concede ``UPDATE`` **por columna**. Hoy solo hay una —``life_checkins.geom``,
    #: la anonimización de ARCO— y por eso mismo hace falta declararla: es la
    #: única excepción al «esta tabla no se toca», y su TAMAÑO es lo que nadie
    #: comprobaba tras un restore. Ver ``_check_column_grants``.
    column_grants: Mapping[tuple[str, str], frozenset[str]] = field(default_factory=dict)

    def merged_with(self, other: Expectations) -> Expectations:
        rls = {**self.rls, **other.rls}
        policies = dict(self.policies)
        for table, count in other.policies.items():
            policies[table] = max(policies.get(table, 0), count)
        return Expectations(
            extensions=self.extensions | other.extensions,
            append_only=self.append_only | other.append_only,
            guard_function=other.guard_function or self.guard_function,
            rls=rls,
            no_force=self.no_force | other.no_force,
            policies=policies,
            hypertables=self.hypertables | other.hypertables,
            barrier_views=self.barrier_views | other.barrier_views,
            roles=self.roles | other.roles,
            timescale_policies=self.timescale_policies | other.timescale_policies,
            # UNIÓN por clave y no `{**a, **b}`: si el esquema y el origen
            # declararan rendijas distintas sobre la misma tabla, quedarse con
            # una de las dos ENSANCHARÍA o ESTRECHARÍA la expectativa en
            # silencio. Con la unión, cualquier discrepancia se convierte en un
            # FAIL que alguien tiene que leer.
            column_grants={
                clave: frozenset(self.column_grants.get(clave, ()))
                | frozenset(other.column_grants.get(clave, ()))
                for clave in set(self.column_grants) | set(other.column_grants)
            },
        )


# --------------------------------------------------------------------------- derivación


#: `add_*_policy(...)` del esquema → `proc_name` con que el catálogo de
#: TimescaleDB registra el job. Es la única traducción escrita a mano de este
#: módulo; el conjunto de políticas sale de leer el esquema, no de una lista.
_POLICY_PROC = {
    "add_retention_policy": "policy_retention",
    "add_compression_policy": "policy_compression",
    "add_continuous_aggregate_policy": "policy_refresh_continuous_aggregate",
}


def _repo_root() -> Path:
    # …/api/src/takab_api/ops/restore_check.py → …/
    return Path(__file__).resolve().parents[4]


def declared_roles(repo_root: Path | None = None) -> frozenset[str]:
    """Los roles de conexión que el código declara, leídos de la migración 0001.

    Vive aparte de `declared_expectations` por una razón operativa, no de estilo:
    **la imagen de la nube co-locada lleva `api/migrations` dentro y NO lleva
    `db/schema.sql`** (`api/Dockerfile`). `capture_baseline` corre ahí cada noche
    (T-2.73.a) y necesita esta lista y nada más del repo; si tuviera que pasar
    por `declared_expectations`, moriría con `FileNotFoundError` la primera
    madrugada — y el hueco solo se vería en la ventana AWS.
    """
    root = repo_root or _repo_root()
    initial = (root / "api" / "migrations" / "versions" / "0001_initial_schema.py").read_text(
        encoding="utf-8"
    )
    return frozenset(re.findall(r"CREATE ROLE (\w+)", initial))


def declared_expectations(repo_root: Path | None = None) -> Expectations:
    """Deriva las expectativas de `db/schema.sql` y de la migración inicial.

    Se lee el DDL, no un inventario paralelo: una tabla nueva con su trigger
    append-only entra sola en la expectativa el día que alguien la escriba. Lo
    que el esquema consolidado NO cubre son las tablas que añaden las migraciones
    0002+; ese hueco lo tapa el `baseline` (ver `capture_baseline`).
    """
    root = repo_root or _repo_root()
    schema = (root / "db" / "schema.sql").read_text(encoding="utf-8")

    extensions = frozenset(re.findall(r"CREATE EXTENSION IF NOT EXISTS (\w+)", schema))

    # Triggers append-only: BEFORE UPDATE OR DELETE ... EXECUTE FUNCTION <guard>()
    append_only: set[str] = set()
    guards: set[str] = set()
    for table, guard in re.findall(
        r"CREATE TRIGGER\s+\w+\s+BEFORE UPDATE OR DELETE ON (\w+)\s+"
        r"FOR EACH ROW EXECUTE FUNCTION (\w+)\(\)",
        schema,
    ):
        append_only.add(table)
        guards.add(guard)

    enabled = set(re.findall(r"ALTER TABLE (\w+) ENABLE ROW LEVEL SECURITY", schema))
    forced = set(re.findall(r"ALTER TABLE (\w+) FORCE\s+ROW LEVEL SECURITY", schema))
    # [T-2.73.b] El `NO FORCE` EXPLÍCITO es otra cosa que la ausencia de FORCE:
    # es la decisión escrita. (La regex de arriba no lo confunde: exige el nombre
    # de tabla pegado a `FORCE`, y aquí en medio va el `NO`.)
    no_force = frozenset(re.findall(r"ALTER TABLE (\w+) NO FORCE\s+ROW LEVEL SECURITY", schema))
    rls = {table: (True, table in forced) for table in enabled}

    policies: dict[str, int] = {}
    for table in re.findall(r"CREATE POLICY \w+\s+ON (\w+)", schema):
        policies[table] = policies.get(table, 0) + 1

    hypertables = frozenset(re.findall(r"create_hypertable\('(\w+)'", schema))
    barrier_views = frozenset(
        re.findall(r"CREATE (?:OR REPLACE )?VIEW (\w+) WITH \(security_barrier = true\)", schema)
    )
    roles = declared_roles(root)

    # Políticas de TimescaleDB: el esquema las declara con su `add_*_policy` y el
    # catálogo las expone con el `proc_name` que ejecutan. La traducción es el
    # único puente que hay que escribir; el CONJUNTO se deriva.
    ts_policies = {
        (proc, ht)
        for fn, proc in _POLICY_PROC.items()
        for ht in re.findall(rf"{fn}\s*\(\s*'(\w+)'", schema)
    }

    # [T-2.80.c] La rendija de ARCO, derivada del DDL igual que todo lo demás.
    # `GRANT UPDATE (geom) ON life_checkins TO takab_app` es la ÚNICA excepción
    # al «esta tabla no se toca», y lo que hay que conservar tras un restore no
    # es que exista sino que sea del MISMO TAMAÑO. Se deriva y no se enumera por
    # lo de siempre: la segunda rendija que alguien abra entra sola.
    column_grants: dict[tuple[str, str], frozenset[str]] = {}
    for columnas, tabla, rol in re.findall(
        r"GRANT\s+UPDATE\s*\(([^)]*)\)\s+ON\s+(\w+)\s+TO\s+(\w+)", schema
    ):
        clave = (rol, tabla)
        cols = frozenset(c.strip() for c in columnas.split(",") if c.strip())
        column_grants[clave] = column_grants.get(clave, frozenset()) | cols

    return Expectations(
        extensions=extensions,
        append_only=frozenset(append_only),
        guard_function=sorted(guards)[0] if guards else "forbid_update_delete",
        rls=rls,
        no_force=no_force,
        policies=policies,
        hypertables=hypertables,
        barrier_views=barrier_views,
        roles=roles,
        timescale_policies=frozenset(ts_policies),
        column_grants=column_grants,
    )


def _baseline_expectations(baseline: Mapping[str, Any]) -> Expectations:
    """Las expectativas que sólo el ORIGEN conoce (tablas de migraciones 0002+)."""
    tables = baseline.get("tables", {})
    return Expectations(
        extensions=frozenset(baseline.get("extensions", {})),
        append_only=frozenset(t for t, v in tables.items() if v.get("append_only")),
        rls={t: tuple(v["rls"]) for t, v in tables.items() if v["rls"][0]},  # type: ignore[misc]
        policies={t: v["policies"] for t, v in tables.items() if v["policies"]},
        hypertables=frozenset(baseline.get("hypertables", ())),
        barrier_views=frozenset(
            v_name for v_name, v in baseline.get("views", {}).items() if v.get("security_barrier")
        ),
        roles=frozenset(baseline.get("roles", ())),
        timescale_policies=frozenset((p[0], p[1]) for p in baseline.get("timescale_policies", ())),
        # [T-2.80.c] La rendija tal y como estaba EN EL ORIGEN. Cubre el hueco
        # que `db/schema.sql` no puede cubrir —una rendija abierta por una
        # migración 0002+— y, sobre todo, existe porque la imagen de la nube
        # co-locada NO lleva `db/schema.sql` dentro (ver `declared_roles`).
        column_grants={(g[0], g[1]): frozenset(g[2]) for g in baseline.get("column_grants", ())},
    )


# --------------------------------------------------------------------------- catálogo


def _rows(conn: psycopg.Connection, query: Any, params: Sequence[Any] | None = None) -> list[tuple]:
    # `params=None` (y no `()`): con una tupla vacía psycopg interpreta los `%` del
    # SQL como marcadores, y un `LIKE '%…%'` explota con un error que no dice eso.
    with conn.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchall()


def _scalar(conn: psycopg.Connection, query: Any, params: Sequence[Any] | None = None) -> Any:
    row = _rows(conn, query, params)
    return row[0][0] if row else None


_Q_TABLES = """
SELECT c.relname,
       pg_get_userbyid(c.relowner),
       c.relrowsecurity,
       c.relforcerowsecurity,
       (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid)
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
ORDER BY 1
"""

_Q_VIEWS = """
SELECT c.relname, pg_get_userbyid(c.relowner),
       'security_barrier=true' = ANY(coalesce(c.reloptions, '{}'))
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'v'
ORDER BY 1
"""

_Q_APPEND_ONLY = """
SELECT c.relname, t.tgname, t.tgenabled
FROM pg_trigger t
JOIN pg_class c ON c.oid = t.tgrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_proc p ON p.oid = t.tgfoid
WHERE NOT t.tgisinternal AND n.nspname = 'public' AND p.proname = %s
ORDER BY 1
"""

#: `BEFORE UPDATE OR DELETE ... FOR EACH ROW`, dicho en bits de `pg_trigger.tgtype`
#: en vez de en texto: ROW=1, BEFORE=2, DELETE=8, UPDATE=16 (`src/include/catalog/
#: pg_trigger.h`). Es la MISMA frase que la regex de `declared_expectations` busca
#: en `db/schema.sql`, y por eso el desacoplamiento no pierde nada:
#: `life_checkin_arco_guard` es BEFORE UPDATE a secas y queda fuera de las dos.
_Q_GUARD_FUNCTION = """
SELECT DISTINCT p.proname
FROM pg_trigger t
JOIN pg_class c ON c.oid = t.tgrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_proc p ON p.oid = t.tgfoid
WHERE NOT t.tgisinternal AND n.nspname = 'public'
  AND (t.tgtype & 1) = 1 AND (t.tgtype & 2) = 2
  AND (t.tgtype & 8) = 8 AND (t.tgtype & 16) = 16
ORDER BY 1
"""


def catalog_guard_function(conn: psycopg.Connection) -> str | None:
    """La función guarda append-only, leída del CATÁLOGO de la base que se mira.

    `None` cuando no hay ningún trigger de esa forma — y `None` es la respuesta
    correcta, no `"forbid_update_delete"`: inventar el nombre haría que la huella
    de una base sin guardas dijera "aquí no hay tablas append-only" por la razón
    equivocada, que es exactamente el verde mentiroso que este módulo persigue.

    Se toma `[0]` del orden alfabético igual que hace `declared_expectations`, y
    por la misma razón: si algún día hubiera dos guardas, las dos derivaciones
    tienen que elegir la misma.
    """
    nombres = sorted(r[0] for r in _rows(conn, _Q_GUARD_FUNCTION))
    return nombres[0] if nombres else None


def _timescale_policies(conn: psycopg.Connection) -> set[tuple[str, str]]:
    """Retención, compresión y refresco de caggs **que de verdad van a correr**.

    `AND scheduled` no es un detalle: un job con `scheduled => false` sigue en el
    catálogo, se cuenta, se lista… y no corre nunca. La retención deja de podar y
    el volumen se llena semanas después, o el cagg deja de refrescarse y la
    consola pinta cifras viejas como si fueran de ahora (regla de oro 7). Contar
    jobs sin mirar esta columna daba VERDE sobre las dos averías.

    Se filtra además por `hypertable_name IS NOT NULL` para quedarse con las
    políticas del ESQUEMA y dejar fuera los jobs internos de la extensión
    (telemetría, poda del historial de jobs), que no son nuestros y cambian con
    la versión.
    """
    if not _scalar(conn, "SELECT count(*) FROM pg_extension WHERE extname = 'timescaledb'"):
        return set()
    return {
        (r[0], r[1])
        for r in _rows(
            conn,
            "SELECT proc_name, hypertable_name FROM timescaledb_information.jobs "
            "WHERE hypertable_name IS NOT NULL AND scheduled",
        )
    }


def _caggs(conn: psycopg.Connection) -> list[tuple[str, str, str]]:
    """(vista, esquema de materialización, hypertable de materialización).

    Se cuenta la MATERIALIZACIÓN y no la vista: con agregación en tiempo real la
    vista recalcula del crudo y taparía una materialización vacía.
    """
    if not _scalar(conn, "SELECT count(*) FROM pg_extension WHERE extname = 'timescaledb'"):
        return []
    return [
        (r[0], r[1], r[2])
        for r in _rows(
            conn,
            "SELECT view_name, materialization_hypertable_schema, "
            "materialization_hypertable_name "
            "FROM timescaledb_information.continuous_aggregates ORDER BY 1",
        )
    ]


def _columns(conn: psycopg.Connection) -> dict[str, list[list[str]]]:
    """Columna a columna, con su tipo. Una columna que no viaja no deja hueco.

    `DROP COLUMN incidents.closed_at` mantiene la tabla, su conteo de filas y
    todo el inventario de objetos: sólo desaparece el dato de negocio.
    """
    salida: dict[str, list[list[str]]] = {}
    for table, column, tipo in _rows(
        conn,
        "SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod) "
        "FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') "
        "AND a.attnum > 0 AND NOT a.attisdropped ORDER BY 1, a.attnum",
    ):
        salida.setdefault(table, []).append([column, tipo])
    return salida


def _constraints(conn: psycopg.Connection) -> dict[str, list[str]]:
    """CHECK, FK, UNIQUE y PK por nombre. Verificado: sin el CHECK de `severity`
    entra en `incidents` un valor que el esquema prohíbe."""
    return {
        r[0]: [r[1], r[2]]
        for r in _rows(
            conn,
            "SELECT c.conname, c.conrelid::regclass::text, c.contype "
            "FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace "
            "WHERE n.nspname = 'public' ORDER BY 1",
        )
    }


#: Privilegios que la API y los workers necesitan de verdad. Se comparan contra
#: el ORIGEN, no contra una lista: lo que importa es que el restore no los pierda.
_PRIVS = ("SELECT", "INSERT", "UPDATE", "DELETE")


def _privileges(conn: psycopg.Connection, roles: Iterable[str]) -> dict[str, dict[str, list[str]]]:
    """Qué puede hacer cada rol de conexión sobre cada tabla.

    El daño más caro de los seis que encontró la auditoría: un
    `REVOKE ALL ON incidents FROM takab_app` deja las 19 comprobaciones en verde
    y la consola sin arrancar. El dato no está roto; el acceso sí.
    """
    existentes = {r[0] for r in _rows(conn, "SELECT rolname FROM pg_roles")}
    objetivo = sorted(set(roles) & existentes)
    if not objetivo:
        return {}
    salida: dict[str, dict[str, list[str]]] = {}
    for table, *_ in _rows(conn, _Q_TABLES):
        por_rol: dict[str, list[str]] = {}
        for rol in objetivo:
            concedidos = [
                p
                for p in _PRIVS
                if _scalar(conn, "SELECT has_table_privilege(%s, %s, %s)", (rol, table, p))
            ]
            if concedidos:
                por_rol[rol] = concedidos
        salida[table] = por_rol
    return salida


#: [T-2.80.c] Columnas sobre las que un rol tiene `UPDATE` EFECTIVO.
#:
#: `has_column_privilege` responde `true` tanto por un grant de columna como por
#: uno de TABLA, y eso es exactamente lo que hace falta: el conjunto que devuelve
#: es la superficie real de escritura. Si alguien restaura con `GRANT UPDATE ON
#: life_checkins` a nivel de tabla, aquí salen TODAS las columnas y la
#: comprobación lo canta. Con `information_schema.column_privileges` no valdría:
#: esa vista solo muestra los grants donde el usuario que pregunta es el
#: concedente o el concedido, así que desde una sesión de verificación puede
#: devolver el conjunto vacío y dar verde sobre una base rota.
_Q_COLUMNAS_CON_UPDATE = """
SELECT a.attname
FROM pg_attribute a
WHERE a.attrelid = %s::regclass AND a.attnum > 0 AND NOT a.attisdropped
  AND has_column_privilege(%s, a.attrelid, a.attnum, 'UPDATE')
ORDER BY a.attnum
"""


def _column_grants(conn: psycopg.Connection) -> list[list]:
    """`[[rol, tabla, [columnas]], …]` de toda rendija de UPDATE por columna.

    Se deriva del catálogo, para la huella del ORIGEN. Solo aparecen las tablas
    donde el rol NO tiene `UPDATE` de tabla pero SÍ sobre alguna columna: eso es,
    por definición, una rendija — y es lo que hay que poder comparar después.
    """
    roles = sorted(declared_roles())
    existentes = {r[0] for r in _rows(conn, "SELECT rolname FROM pg_roles")}
    salida: list[list] = []
    for table, *_ in _rows(conn, _Q_TABLES):
        for rol in roles:
            if rol not in existentes:
                continue
            if _scalar(conn, "SELECT has_table_privilege(%s, %s, 'UPDATE')", (rol, table)):
                continue
            cols = [r[0] for r in _rows(conn, _Q_COLUMNAS_CON_UPDATE, (table, rol))]
            if cols:
                salida.append([rol, table, cols])
    return salida


def _hypertables(conn: psycopg.Connection) -> set[str]:
    if not _scalar(conn, "SELECT count(*) FROM pg_extension WHERE extname = 'timescaledb'"):
        return set()
    return {
        r[0] for r in _rows(conn, "SELECT hypertable_name FROM timescaledb_information.hypertables")
    }


def _pk_columns(conn: psycopg.Connection, table: str) -> list[str]:
    return [
        r[0]
        for r in _rows(
            conn,
            "SELECT a.attname FROM pg_index i "
            "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
            "WHERE i.indrelid = %s::regclass AND i.indisprimary ORDER BY a.attnum",
            (table,),
        )
    ]


def _updatable_column(conn: psycopg.Connection, table: str) -> str | None:
    """Una columna que se pueda escribir: ni identidad ni generada.

    `SET audit_id = audit_id` sobre un GENERATED ALWAYS AS IDENTITY falla por
    razones que no tienen nada que ver con el trigger, y ese falso rojo
    escondería el verdadero.
    """
    return _scalar(
        conn,
        "SELECT a.attname FROM pg_attribute a "
        "WHERE a.attrelid = %s::regclass AND a.attnum > 0 AND NOT a.attisdropped "
        "AND a.attidentity = '' AND a.attgenerated = '' ORDER BY a.attnum LIMIT 1",
        (table,),
    )


# --------------------------------------------------------------------------- baseline


def capture_baseline(conn: psycopg.Connection) -> dict[str, Any]:
    """Huella de la base ORIGEN, para guardar JUNTO al dump.

    Sin esto, un restore que perdió una tabla entera no tiene contra qué
    compararse: el catálogo restaurado es internamente coherente y no deja hueco
    visible. `count(*)` exacto por tabla cuesta un escaneo completo — es
    deliberado: `reltuples` es una estimación y una estimación no acredita nada.

    **No lee `db/schema.sql`, y eso es un requisito, no una casualidad**
    (T-2.73.a). Quien toma esta huella todas las noches es el contenedor de la
    nube co-locada, y su imagen no lleva el DDL dentro (`api/Dockerfile`). Una
    huella es el retrato de lo que el origen TIENE; las expectativas —lo que el
    esquema dice que debería tener— son cosa de `verify()`, que sí corre con el
    repo delante. Mezclarlas acoplaba el retrato a un fichero que no está donde
    se toma. Lo único que sigue viniendo del repo son los roles, y salen de la
    migración 0001, que la imagen SÍ lleva.
    """
    guard = catalog_guard_function(conn)
    append_only = {r[0] for r in _rows(conn, _Q_APPEND_ONLY, (guard,))} if guard else set()

    tables: dict[str, Any] = {}
    for name, owner, rls, force, policies in _rows(conn, _Q_TABLES):
        tables[name] = {
            "owner": owner,
            "rls": [bool(rls), bool(force)],
            "policies": int(policies),
            "append_only": name in append_only,
            "rows": int(
                _scalar(conn, sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(name)))
            ),
        }

    views = {
        name: {"owner": owner, "security_barrier": bool(barrier)}
        for name, owner, barrier in _rows(conn, _Q_VIEWS)
    }

    hypertables = sorted(_hypertables(conn))
    data_tip: dict[str, str | None] = {}
    for ht in hypertables:
        if _scalar(
            conn,
            "SELECT count(*) FROM pg_attribute WHERE attrelid = %s::regclass AND attname = 'ts' "
            "AND attnum > 0 AND NOT attisdropped",
            (ht,),
        ):
            tip = _scalar(conn, sql.SQL("SELECT max(ts) FROM {}").format(sql.Identifier(ht)))
            data_tip[ht] = tip.isoformat() if isinstance(tip, datetime) else None

    # Los caggs se cuentan por su hypertable de MATERIALIZACIÓN: `_Q_TABLES`
    # filtra `relkind IN ('r','p')` y una vista de cagg nunca entraba ahí, así
    # que un cagg vaciado no movía ni un conteo.
    cagg_rows: dict[str, int] = {}
    for view, mat_schema, mat_table in _caggs(conn):
        cagg_rows[view] = int(
            _scalar(
                conn,
                sql.SQL("SELECT count(*) FROM {}.{}").format(
                    sql.Identifier(mat_schema), sql.Identifier(mat_table)
                ),
            )
        )

    return {
        "database": _scalar(conn, "SELECT current_database()"),
        "server_version": _scalar(conn, "SHOW server_version"),
        "captured_at": datetime.now().astimezone().isoformat(),
        "extensions": {
            r[0]: r[1] for r in _rows(conn, "SELECT extname, extversion FROM pg_extension")
        },
        "roles": sorted(
            r[0]
            for r in _rows(conn, "SELECT rolname FROM pg_roles WHERE NOT rolname LIKE 'pg\\_%'")
        ),
        "tables": tables,
        "views": views,
        "columns": _columns(conn),
        "constraints": _constraints(conn),
        "privileges": _privileges(conn, declared_roles()),
        # [T-2.80.c] La rendija de ARCO. `privileges` NO la ve: usa
        # `has_table_privilege`, que responde `false` para un grant de columna —
        # medido, `has_table_privilege('takab_app','life_checkins','UPDATE')` es
        # `f` con la rendija abierta. O sea que sin esta línea el origen no
        # registra que la rendija existía y nada puede comparar su tamaño.
        "column_grants": _column_grants(conn),
        "cagg_rows": cagg_rows,
        "hypertables": hypertables,
        "continuous_aggregates": sorted(
            r[0]
            for r in _rows(
                conn,
                "SELECT view_name FROM timescaledb_information.continuous_aggregates"
                if hypertables
                else "SELECT NULL WHERE false",
            )
        ),
        "indexes": sorted(
            r[0]
            for r in _rows(
                conn,
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind = 'i'",
            )
        ),
        "sequences": {
            r[0]: (int(r[1]) if r[1] is not None else None)
            for r in _rows(
                conn,
                "SELECT sequencename, last_value FROM pg_sequences WHERE schemaname = 'public'",
            )
        },
        "timescale_policies": sorted(list(p) for p in _timescale_policies(conn)),
        "data_tip": data_tip,
    }


# --------------------------------------------------------------------------- comprobaciones


def _check_extensions(conn: psycopg.Connection, exp: Expectations) -> Check:
    if not exp.extensions:
        return Check("extensions", SKIP, _SIN_EXPECTATIVA.format(que="extensiones"))
    found = {r[0]: r[1] for r in _rows(conn, "SELECT extname, extversion FROM pg_extension")}
    missing = sorted(exp.extensions - set(found))
    if missing:
        return Check("extensions", FAIL, f"faltan extensiones: {', '.join(missing)}")
    detalle = ", ".join(f"{n} {v}" for n, v in sorted(found.items()) if n in exp.extensions)
    return Check("extensions", PASS, detalle or "sin extensiones declaradas")


def _check_append_only_triggers(conn: psycopg.Connection, exp: Expectations) -> Check:
    if not exp.append_only:
        return Check(
            "append_only_triggers", SKIP, _SIN_EXPECTATIVA.format(que="tablas append-only")
        )
    catalog = {r[0] for r in _rows(conn, _Q_APPEND_ONLY, (exp.guard_function,))}
    missing = sorted(exp.append_only - catalog)
    if missing:
        return Check(
            "append_only_triggers",
            FAIL,
            f"sin guarda append-only: {', '.join(missing)} "
            f"(regla de oro 11: la auditoría no se poda ni se altera)",
        )
    return Check(
        "append_only_triggers",
        PASS,
        f"{len(catalog)} tablas con guarda `{exp.guard_function}`: {', '.join(sorted(catalog))}",
    )


class _NotRejected(Exception):
    """La operación que TENÍA que fallar no falló."""


#: SQLSTATE que levanta `RAISE EXCEPTION` de PL/pgSQL sin `ERRCODE` explícito:
#: es el que emite la guarda `forbid_update_delete`. Cualquier otro SQLSTATE
#: significa que la operación falló por OTRA razón.
_GUARD_SQLSTATE = "P0001"

#: …y además su texto, porque un `RAISE EXCEPTION` de cualquier otro trigger
#: comparte SQLSTATE. La guarda dice literalmente
#: «tabla append-only: <t> no permite <OP>» (db/schema.sql, `forbid_update_delete`).
_GUARD_TEXTO = "append-only"


def _rejection_reason(conn: psycopg.Connection, statement: sql.Composed) -> str | None:
    """`None` si la rechazó LA GUARDA; si no, por qué NO cuenta como rechazo.

    Devolver el SQLSTATE en vez de un booleano es lo que hace el informe
    accionable: un `25006` dice "estás verificando en una sesión de solo lectura,
    repite sin `default_transaction_read_only`" y un `42501` dice "te falta un
    permiso", mientras que "no rechazado" a secas manda a leer el código.
    """
    try:
        with conn.transaction():
            conn.execute(statement)
            raise _NotRejected
    except _NotRejected:
        return "ACEPTADO (la guarda no existe o está desactivada)"
    except psycopg.Error as exc:
        if exc.sqlstate == _GUARD_SQLSTATE and _GUARD_TEXTO in str(exc):
            return None
        return f"falló con SQLSTATE {exc.sqlstate}, que NO es la guarda append-only"


def _rejected_by_guard(conn: psycopg.Connection, statement: sql.Composed) -> bool:
    """¿La rechazó LA GUARDA? Ejecuta y revierte SIEMPRE.

    Antes bastaba con que Postgres levantara cualquier excepción, y eso convertía
    en PASS escenarios donde la guarda estaba NEUTRALIZADA y el error venía de
    otra parte: una transacción de solo lectura (`25006`), un permiso denegado
    (`42501`), un lock, una conexión muerta. Verificar la base lateral con
    `default_transaction_read_only` antes del swap es justo lo que hace un
    operador prudente — y bajo ese modo TODA escritura falla, con guarda o sin
    ella. Ahí el verificador leía "la tabla rechaza escrituras" y daba verde.

    Es el mismo error que ya se había matado un nivel más arriba (contar filas en
    `pg_trigger` daba verde con el trigger `DISABLE`d), reintroducido un nivel
    más abajo: aceptar una señal cualquiera como prueba de la señal concreta.
    """
    return _rejection_reason(conn, statement) is None


def _check_append_only_enforced(conn: psycopg.Connection, exp: Expectations) -> Check:
    """Aserción NEGATIVA: pasa sólo si el UPDATE y el DELETE fallan **por la guarda**.

    Contar triggers da verde con el trigger `DISABLE`d, que es una fila en
    `pg_trigger` que no protege nada; y aceptar cualquier excepción da verde en
    una transacción de solo lectura. Se exige el SQLSTATE y el texto de la guarda.
    """
    tablas = {r[0] for r in _rows(conn, _Q_APPEND_ONLY, (exp.guard_function,))} | exp.append_only
    rotas: list[str] = []
    sin_pk: list[str] = []
    vacias: list[str] = []
    ejercidas: list[str] = []

    for table in sorted(tablas):
        if not _scalar(
            conn, "SELECT count(*) FROM pg_class WHERE relname = %s AND relkind = 'r'", (table,)
        ):
            continue  # la ausencia de la tabla la reporta `object_inventory`
        if not _scalar(conn, sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))):
            vacias.append(table)
            continue
        pk = _pk_columns(conn, table)
        col = _updatable_column(conn, table)
        if not pk or not col:
            # CON filas y sin PK: eso NO es una tabla que no toque ejercer, es una
            # tabla de compliance que se ha quedado sin cómo direccionar una fila
            # — exactamente lo que produce el §3 del runbook al perder las PK de
            # las hypertables. El daño que esta herramienta persigue no puede
            # apagar otra comprobación y quedarse en aviso.
            sin_pk.append(f"{table} (con filas y SIN PK: no se puede direccionar una fila)")
            continue
        cols = sql.SQL(", ").join(sql.Identifier(c) for c in pk)
        where = sql.SQL("({}) IN (SELECT {} FROM {} LIMIT 1)").format(
            cols, cols, sql.Identifier(table)
        )
        upd = sql.SQL("UPDATE {} SET {} = {} WHERE {}").format(
            sql.Identifier(table), sql.Identifier(col), sql.Identifier(col), where
        )
        dele = sql.SQL("DELETE FROM {} WHERE {}").format(sql.Identifier(table), where)
        fallos = [
            f"{verbo} {razon}"
            for verbo, stmt in (("UPDATE", upd), ("DELETE", dele))
            if (razon := _rejection_reason(conn, stmt)) is not None
        ]
        if fallos:
            rotas.append(f"{table}: " + "; ".join(fallos))
        else:
            ejercidas.append(table)

    if rotas or sin_pk:
        return Check(
            "append_only_enforced",
            FAIL,
            "guarda append-only sin ejercer o rota (regla de oro 11): "
            + "; ".join([*rotas, *sin_pk]),
        )
    detalle = f"{len(ejercidas)} tablas rechazan UPDATE y DELETE de 1 fila: {', '.join(ejercidas)}"
    if vacias:
        return Check(
            "append_only_enforced",
            SKIP,
            detalle + " · NO EJERCIDAS por estar VACÍAS (el trigger es FOR EACH ROW): "
            f"{', '.join(vacias)}. Sin filas la aserción negativa no prueba nada.",
        )
    if not ejercidas:
        return Check("append_only_enforced", SKIP, "no hay ninguna tabla append-only que ejercer")
    return Check("append_only_enforced", PASS, detalle)


# --------------------------------------------------------------------------- [T-2.80.c]
# LA RENDIJA DE ARCO: que siga siendo del TAMAÑO que era
#
# T-2.80 abrió en `life_checkins` una excepción de UNA sola columna —anular
# `geom`, la anonimización del titular— y por eso esa tabla dejó de ser
# append-only puro. El verificador tuvo que dejar de tratarla como tal: correcto
# entonces, hueco ahora. Lo que quedó sin comprobar tras un restore es el TAMAÑO
# de la rendija.
#
# El escenario concreto, y no es teórico: `pg_restore` reconstruye los ACL a
# partir del dump. Una base restaurada con `GRANT UPDATE ON life_checkins TO
# takab_app` —a nivel de TABLA en vez de por columna— pasaba TODAS las
# comprobaciones. Y no por descuido de `_check_privileges`: esa función compara
# contra el origen con `has_table_privilege`, que devuelve `false` para un grant
# de columna (medido), así que el origen registraba «takab_app no tiene UPDATE
# sobre life_checkins» y la base rota registraba «sí lo tiene» — una diferencia
# que solo se mira en la dirección de lo que FALTA, nunca de lo que SOBRA.
#
# Con la tabla entera abierta, `status` y `user_id` de un check-in de vida serían
# reescribibles desde la API: se podría cambiar «necesito ayuda» por «estoy bien»
# en la evidencia de un rescate. Lo pararía el trigger, sí — pero entonces la
# protección de esa tabla habría pasado de dos capas a una, en silencio, y el
# chequeo de DR habría dicho VERDE.


def _check_column_grants(conn: psycopg.Connection, exp: Expectations) -> Check:
    """El privilegio de la rendija es POR COLUMNA, y son EXACTAMENTE éstas.

    Dos aserciones y las dos hacen falta:

    * ``has_table_privilege(..., 'UPDATE')`` tiene que ser **falso**. Si es
      cierto, el grant volvió a ser de tabla y la rendija es la tabla entera;
    * el conjunto de columnas con ``UPDATE`` efectivo tiene que ser **igual** al
      declarado. Ni una de más (la rendija creció) ni una de menos (la rendija se
      cerró y ARCO dejó de poder anonimizar, que también es un restore roto).
    """
    if not exp.column_grants:
        return Check(
            "column_grants", SKIP, _SIN_EXPECTATIVA.format(que="rendijas de UPDATE por columna")
        )
    malas: list[str] = []
    revisadas: list[str] = []
    for (rol, tabla), esperadas in sorted(exp.column_grants.items()):
        if not _scalar(
            conn, "SELECT count(*) FROM pg_class WHERE relname = %s AND relkind = 'r'", (tabla,)
        ):
            continue  # la ausencia de la tabla la reporta `object_inventory`
        if not _scalar(conn, "SELECT count(*) FROM pg_roles WHERE rolname = %s", (rol,)):
            continue  # la ausencia del rol la reporta `roles`
        if _scalar(conn, "SELECT has_table_privilege(%s, %s, 'UPDATE')", (rol, tabla)):
            malas.append(
                f"{rol} tiene UPDATE de TABLA sobre {tabla}: la rendija de ARCO "
                f"(solo {', '.join(sorted(esperadas))}) es ahora la tabla entera"
            )
            continue
        actuales = {r[0] for r in _rows(conn, _Q_COLUMNAS_CON_UPDATE, (tabla, rol))}
        if actuales != set(esperadas):
            sobran = sorted(actuales - set(esperadas))
            faltan = sorted(set(esperadas) - actuales)
            detalle = "; ".join(
                p
                for p in (
                    f"columnas de MÁS: {', '.join(sobran)}" if sobran else "",
                    f"columnas de MENOS: {', '.join(faltan)}" if faltan else "",
                )
                if p
            )
            malas.append(f"{rol} sobre {tabla} — {detalle}")
            continue
        revisadas.append(f"{rol}:{tabla}({', '.join(sorted(esperadas))})")
    if malas:
        return Check(
            "column_grants",
            FAIL,
            "la rendija de UPDATE cambió de tamaño (regla de oro 11): " + "; ".join(malas),
        )
    if not revisadas:
        return Check(
            "column_grants",
            SKIP,
            "ninguna de las rendijas declaradas se pudo ejercer: ni la tabla ni el rol "
            "existen en esta base (lo reportan `object_inventory` y `roles`)",
        )
    return Check(
        "column_grants",
        PASS,
        f"{len(revisadas)} rendija(s) de UPDATE siguen siendo por COLUMNA y del mismo "
        f"tamaño: {', '.join(revisadas)}",
    )


def _updatable_column_outside(
    conn: psycopg.Connection, table: str, excluidas: Iterable[str]
) -> str | None:
    """Una columna escribible que NO esté en la rendija.

    Escribir sobre la columna de la rendija probaría lo contrario de lo que hace
    falta: hay que ejercer lo que el guard tiene que RECHAZAR.
    """
    fuera = set(excluidas)
    for fila in _rows(
        conn,
        "SELECT a.attname FROM pg_attribute a "
        "WHERE a.attrelid = %s::regclass AND a.attnum > 0 AND NOT a.attisdropped "
        "AND a.attidentity = '' AND a.attgenerated = '' ORDER BY a.attnum",
        (table,),
    ):
        if fila[0] not in fuera:
            return fila[0]
    return None


def _check_column_grant_enforced(conn: psycopg.Connection, exp: Expectations) -> Check:
    """Aserción NEGATIVA sobre la tabla de la rendija: todo lo demás sigue vetado.

    El privilegio es una capa; el trigger es la otra. Esta comprobación ejerce la
    segunda **con el mismo UPDATE que la ficha nombra**: ``SET c = c``, el que no
    cambia nada. Es el caso importante y el que más fácil se cuela — un no-op
    sobre una tabla de evidencia parece inofensivo, y aceptarlo significaría que
    el guard compara mal (`life_checkin_arco_guard` exige la transición REAL
    ``geom`` con valor → NULL, no solo que ``NEW.geom`` sea NULL).

    Y el DELETE también, porque la rendija es de UPDATE: para borrar, la tabla
    sigue siendo append-only sin excepción alguna.
    """
    if not exp.column_grants:
        return Check(
            "column_grant_enforced",
            SKIP,
            _SIN_EXPECTATIVA.format(que="rendijas de UPDATE por columna"),
        )
    rotas: list[str] = []
    vacias: list[str] = []
    ejercidas: list[str] = []
    sin_columna: list[str] = []

    for tabla in sorted({t for _, t in exp.column_grants}):
        if not _scalar(
            conn, "SELECT count(*) FROM pg_class WHERE relname = %s AND relkind = 'r'", (tabla,)
        ):
            continue
        if not _scalar(conn, sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(tabla))):
            vacias.append(tabla)
            continue
        rendija = set().union(*(c for (_, t), c in exp.column_grants.items() if t == tabla))
        pk = _pk_columns(conn, tabla)
        col = _updatable_column_outside(conn, tabla, rendija)
        if not pk or not col:
            sin_columna.append(
                f"{tabla} (con filas y sin PK o sin columna fuera de la rendija: "
                "no se puede ejercer el rechazo)"
            )
            continue
        cols = sql.SQL(", ").join(sql.Identifier(c) for c in pk)
        where = sql.SQL("({}) IN (SELECT {} FROM {} LIMIT 1)").format(
            cols, cols, sql.Identifier(tabla)
        )
        upd = sql.SQL("UPDATE {} SET {} = {} WHERE {}").format(
            sql.Identifier(tabla), sql.Identifier(col), sql.Identifier(col), where
        )
        dele = sql.SQL("DELETE FROM {} WHERE {}").format(sql.Identifier(tabla), where)
        fallos = [
            f"{verbo} {razon}"
            for verbo, stmt in (("UPDATE (no-op)", upd), ("DELETE", dele))
            if (razon := _rejection_reason(conn, stmt)) is not None
        ]
        if fallos:
            rotas.append(f"{tabla}: " + "; ".join(fallos))
        else:
            ejercidas.append(f"{tabla} (columna ejercida: {col})")

    if rotas or sin_columna:
        return Check(
            "column_grant_enforced",
            FAIL,
            "la tabla de la rendija acepta lo que tenía que rechazar (regla de oro 11): "
            + "; ".join([*rotas, *sin_columna]),
        )
    detalle = f"{len(ejercidas)} tabla(s) siguen rechazando el UPDATE que no cambia nada y el "
    detalle += f"DELETE: {', '.join(ejercidas)}"
    if vacias:
        return Check(
            "column_grant_enforced",
            SKIP,
            detalle + " · NO EJERCIDAS por estar VACÍAS (el guard es FOR EACH ROW): "
            f"{', '.join(vacias)}. Sin filas la aserción negativa no prueba nada.",
        )
    if not ejercidas:
        return Check("column_grant_enforced", SKIP, "no hay ninguna tabla con rendija que ejercer")
    return Check("column_grant_enforced", PASS, detalle)


def _check_rls_flags(conn: psycopg.Connection, exp: Expectations) -> Check:
    if not exp.rls:
        return Check("rls_flags", SKIP, _SIN_EXPECTATIVA.format(que="tablas con RLS"))
    actual = {r[0]: (bool(r[2]), bool(r[3])) for r in _rows(conn, _Q_TABLES)}
    malas: list[str] = []
    for table, (want_rls, want_force) in sorted(exp.rls.items()):
        if table not in actual:
            continue  # tabla ausente: lo dice `object_inventory`
        got_rls, got_force = actual[table]
        if (got_rls, got_force) != (want_rls, want_force):
            malas.append(
                f"{table}: esperado enable={want_rls}/force={want_force}, "
                f"obtenido enable={got_rls}/force={got_force}"
            )
    if malas:
        return Check(
            "rls_flags",
            FAIL,
            "RLS alterada (regla de oro 5) — " + "; ".join(malas),
        )
    return Check(
        "rls_flags",
        PASS,
        f"{len(exp.rls)} tablas con RLS declarada conservan enable/force",
    )


def _check_rls_on_tenant_tables(conn: psycopg.Connection, exp: Expectations) -> Check:
    """Derivada del catálogo: toda tabla con `tenant_id` debe llevar RLS.

    No enumera ni las tablas ni sus excepciones: las DEDUCE, y por eso una tabla
    nueva con `tenant_id` entra sola en la comprobación el día que exista.

    * Una hypertable **con continuous aggregates** no puede llevar RLS
      (TimescaleDB lo prohíbe — timescale/timescaledb#6827). Se pregunta al
      catálogo cuáles son, no se escribe su nombre.
    * Una hypertable **sin** caggs lleva RLS pero NO FORCE: los jobs de
      TimescaleDB (retención, refresh) corren como el OWNER y con FORCE verían
      0 filas, así que la retención dejaría de podar.
    * [T-2.73.b] Y una tabla cuyo esquema declara **explícitamente** el
      `NO FORCE` (`exp.no_force`). Hoy solo `tenant_retire_codes`, y su razón se
      midió antes de exentarla: su `SELECT` lo hacen funciones `SECURITY
      DEFINER` que corren como el DUEÑO, y `SECURITY DEFINER` cambia el usuario
      pero **no los GUC** — con FORCE el dueño queda sujeto a una política que
      exige `takab_superadmin`, y `app_verify_retire_code` devuelve **false para
      un código correcto**. Poner FORCE ahí no endurece nada: deja sin poder
      retirar un gabinete a quien tiene derecho. Lo mide
      `tests/ops/test_rls_no_force_declarada.py`, no este párrafo.

    La exención sale de `db/schema.sql`, **no de una lista dentro de este
    módulo**, y del `NO FORCE` ESCRITO — no de la ausencia de la línea de FORCE,
    que es lo que produce un olvido. Para saltarse esta comprobación hay que
    declararlo en la fuente de verdad, que es donde se revisa.

    Una tabla normal que aparezca con RLS y sin FORCE no encaja en ninguna de
    las tres y sale como AVISO, que es lo que se quiere: su dueño se salta su
    propia política.
    """
    sin_rls: list[str] = []
    sin_force: list[str] = []
    hts = _hypertables(conn)
    con_cagg = {
        r[0]
        for r in _rows(
            conn,
            "SELECT hypertable_name FROM timescaledb_information.continuous_aggregates"
            if hts
            else "SELECT NULL WHERE false",
        )
    }
    exentas_rls = con_cagg
    exentas_force = (hts - con_cagg) | set(exp.no_force)
    filas = _rows(
        conn,
        "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'tenant_id' "
        "  AND a.attnum > 0 AND NOT a.attisdropped "
        "WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY 1",
    )
    for name, rls, force in filas:
        if not rls and name not in exentas_rls:
            sin_rls.append(name)
        elif rls and not force and name not in exentas_force:
            sin_force.append(name)
    if sin_rls:
        return Check(
            "rls_on_tenant_tables",
            FAIL,
            f"tablas con tenant_id y SIN RLS: {', '.join(sin_rls)}",
        )
    if sin_force:
        return Check(
            "rls_on_tenant_tables",
            WARN,
            f"{len(filas)} tablas con tenant_id llevan RLS; sin FORCE (su DUEÑO se salta la "
            f"política), sin ser hypertable y sin `NO FORCE` declarado en db/schema.sql: "
            f"{', '.join(sin_force)}",
        )
    return Check(
        "rls_on_tenant_tables",
        PASS,
        f"{len(filas)} tablas con tenant_id llevan RLS; las excepciones son las documentadas "
        f"({len(exentas_force)} sin FORCE: hypertables + {len(exp.no_force)} declaradas)",
    )


def _check_rls_policies(conn: psycopg.Connection, exp: Expectations) -> Check:
    if not exp.policies:
        return Check("rls_policies", SKIP, _SIN_EXPECTATIVA.format(que="políticas RLS"))
    actual = {r[0]: (bool(r[2]), int(r[4])) for r in _rows(conn, _Q_TABLES)}
    vacias = [t for t, (rls, pols) in sorted(actual.items()) if rls and pols == 0]
    if vacias:
        return Check(
            "rls_policies",
            FAIL,
            "RLS encendida y SIN políticas (default-deny: la tabla deja de leerse): "
            + ", ".join(vacias),
        )
    perdidas = [
        f"{t}: esperadas ≥{n}, hay {actual[t][1]}"
        for t, n in sorted(exp.policies.items())
        if t in actual and actual[t][1] < n
    ]
    if perdidas:
        return Check("rls_policies", FAIL, "políticas perdidas — " + "; ".join(perdidas))
    total = sum(p for _, p in actual.values())
    return Check("rls_policies", PASS, f"{total} políticas RLS presentes, ninguna tabla vacía")


def _check_rls_owner_escape(conn: psycopg.Connection) -> Check:
    """Un dueño con BYPASSRLS se salta la RLS de su tabla, **con FORCE o sin él**.

    Corrección medida (auditoría 2026-08-08). Esta comprobación filtraba
    `AND NOT relforcerowsecurity` porque yo daba por hecho que FORCE sujetaba
    también al superusuario. Es FALSO, y se comprueba en dos líneas: tabla con
    `relforcerowsecurity` puesto, dueño superusuario, `app.tenant_id` ajeno →
    la fila se ve igual. `FORCE ROW LEVEL SECURITY` obliga al dueño NORMAL;
    `BYPASSRLS` —que todo superusuario tiene— va por delante de esa decisión.

    Consecuencia del filtro viejo: en una base restaurada con `--no-owner` como
    superusuario nombraba 3 tablas donde había 40, y su mensaje de PASS
    («ninguna tabla con RLS deja escapar a su dueño») era literalmente falso.

    Sigue siendo AVISO y no FALLO porque no rompe el camino de la API: `takab_app`
    no es dueño de nada ni tiene BYPASSRLS, así que su aislamiento no depende de
    esto (medido: tras un `--no-owner`, `tenant_isolation` sigue en verde). Rompe
    a quien se conecte CON el rol dueño — psql de operación, el migrador, un
    script suelto.
    """
    malas = _rows(
        conn,
        "SELECT c.relname, pg_get_userbyid(c.relowner), c.relforcerowsecurity "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "JOIN pg_roles r ON r.oid = c.relowner "
        "WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relrowsecurity "
        "AND (r.rolsuper OR r.rolbypassrls) ORDER BY 1",
    )
    if malas:
        dueños = sorted({o for _, o, _ in malas})
        return Check(
            "rls_owner_escape",
            WARN,
            f"{len(malas)} tablas con RLS cuyo DUEÑO se la salta por BYPASSRLS/superusuario "
            f"(FORCE no lo impide): dueños {', '.join(dueños)} — "
            + ", ".join(t for t, _, _ in malas[:8])
            + (" …" if len(malas) > 8 else ""),
        )
    return Check(
        "rls_owner_escape",
        PASS,
        "ningún dueño de una tabla con RLS tiene BYPASSRLS ni es superusuario",
    )


def _check_barrier_views(conn: psycopg.Connection, exp: Expectations) -> Check:
    actual = {r[0]: (r[1], bool(r[2])) for r in _rows(conn, _Q_VIEWS)}
    malas: list[str] = []
    for view in sorted(exp.barrier_views):
        if view not in actual:
            malas.append(f"{view} (no existe)")
        elif not actual[view][1]:
            malas.append(f"{view} (sin security_barrier)")
    if malas:
        return Check(
            "barrier_views",
            FAIL,
            "vistas de aislamiento rotas — " + "; ".join(malas),
        )
    if not exp.barrier_views:
        return Check("barrier_views", SKIP, "el esquema no declara vistas security_barrier")
    return Check(
        "barrier_views",
        PASS,
        f"{len(exp.barrier_views)} vistas security_barrier intactas: "
        + ", ".join(sorted(exp.barrier_views)),
    )


def _check_tenant_isolation(conn: psycopg.Connection) -> Check:
    """El aislamiento se EJERCE: se entra como `takab_app` y se mira si ve al vecino.

    Leer `relrowsecurity` de `pg_class` da verde con una política reescrita a
    `USING (true)`. Regla de oro 5: un test que cruce tenants DEBE fallar.
    """
    if not _scalar(conn, "SELECT count(*) FROM pg_roles WHERE rolname = 'takab_app'"):
        return Check(
            "tenant_isolation", SKIP, "no existe el rol takab_app: no hay con quién probar"
        )
    candidatos = [
        r[0]
        for r in _rows(
            conn,
            "SELECT t.tenant_id FROM tenants t "
            "WHERE t.visibility = 'private' "
            "  AND EXISTS (SELECT 1 FROM sites s WHERE s.tenant_id = t.tenant_id) "
            "  AND NOT EXISTS (SELECT 1 FROM visibility_grants g "
            "                  WHERE g.grantee_tenant_id = t.tenant_id) "
            "ORDER BY t.tenant_id",
        )
    ]
    if len(candidatos) < 2:
        return Check(
            "tenant_isolation",
            SKIP,
            f"hacen falta 2 tenants privados con sitios y sin visibility_grants; hay "
            f"{len(candidatos)}. Sin vecino al que espiar, la prueba de cruce no prueba nada.",
        )
    viewer = candidatos[0]
    fugas: list[str] = []
    probado: list[str] = []
    try:
        with conn.transaction():
            conn.execute("SET LOCAL ROLE takab_app")
            conn.execute("SELECT set_config('app.tenant_id', %s, true)", (str(viewer),))
            conn.execute("SELECT set_config('app.role', 'soc_operator', true)")
            conn.execute(
                "SELECT set_config('app.user_id', '00000000-0000-0000-0000-000000000000', true)"
            )
            for relacion in ("sites", "waveform_features_1s_secure"):
                try:
                    ajenas = _scalar(
                        conn,
                        sql.SQL("SELECT count(*) FROM {} WHERE tenant_id <> %s").format(
                            sql.Identifier(relacion)
                        ),
                        (viewer,),
                    )
                except psycopg.Error as exc:
                    fugas.append(f"{relacion}: no se pudo leer ({exc.__class__.__name__})")
                    raise _NotRejected from None
                probado.append(relacion)
                if ajenas:
                    fugas.append(f"{relacion}: {ajenas} filas de OTRO tenant visibles")
            raise _NotRejected  # revierte el SET ROLE y el contexto de sesión
    except _NotRejected:
        pass

    if fugas:
        return Check(
            "tenant_isolation",
            FAIL,
            f"CRUCE DE TENANTS como takab_app/tenant {viewer} — " + "; ".join(fugas),
        )
    return Check(
        "tenant_isolation",
        PASS,
        f"takab_app con tenant {viewer} no ve ni una fila ajena en: {', '.join(probado)}",
    )


def _check_hypertables(conn: psycopg.Connection, exp: Expectations) -> Check:
    if not exp.hypertables:
        return Check("hypertables", SKIP, "el esquema no declara hypertables")
    actual = _hypertables(conn)
    if not actual and not _scalar(
        conn, "SELECT count(*) FROM pg_extension WHERE extname = 'timescaledb'"
    ):
        return Check("hypertables", FAIL, "TimescaleDB no está instalada: no hay hypertables")
    perdidas = sorted(exp.hypertables - actual)
    if perdidas:
        return Check(
            "hypertables",
            FAIL,
            "hypertables degradadas a tabla plana (mismos datos, retención y compresión "
            "perdidas): " + ", ".join(perdidas),
        )
    caggs = [
        r[0]
        for r in _rows(
            conn, "SELECT view_name FROM timescaledb_information.continuous_aggregates ORDER BY 1"
        )
    ]
    return Check(
        "hypertables",
        PASS,
        f"{len(actual)} hypertables + {len(caggs)} continuous aggregates ({', '.join(caggs)})",
    )


def _check_timescale_policies(conn: psycopg.Connection, exp: Expectations) -> Check:
    """Las hypertables pueden sobrevivir a un restore y perder sus POLÍTICAS.

    Es el modo de fallo silencioso más largo de todos: sin la política de
    retención el volumen se llena semanas después y nadie relaciona una cosa con
    la otra; sin el refresco, los continuous aggregates se congelan y la consola
    pinta cifras viejas como si fueran de ahora (regla de oro 7). El §5 del
    runbook no mira aquí, y `count(*)` sobre la hypertable sale idéntico.
    """
    if not exp.timescale_policies:
        return Check("timescale_policies", SKIP, "el esquema no declara políticas de TimescaleDB")
    actual = _timescale_policies(conn)
    faltan = sorted(exp.timescale_policies - actual)
    if faltan:
        return Check(
            "timescale_policies",
            FAIL,
            "políticas de TimescaleDB ausentes (retención que no poda / cagg que no refresca): "
            + ", ".join(f"{proc} sobre {ht}" for proc, ht in faltan),
        )
    return Check(
        "timescale_policies",
        PASS,
        f"{len(exp.timescale_policies)} políticas presentes: "
        + ", ".join(
            f"{proc.removeprefix('policy_')}→{ht}" for proc, ht in sorted(exp.timescale_policies)
        ),
    )


def _check_sequences(conn: psycopg.Connection) -> Check:
    """Una secuencia por detrás del dato revienta en el PRIMER INSERT posterior.

    Es el fallo que llega DESPUÉS del "todo verde": el restore terminó, el
    checklist pasó, y el sistema muere con una violación de PK cuando vuelve el
    tráfico.
    """
    filas = _rows(
        conn,
        "SELECT s.sequencename, s.last_value, s.start_value, "
        "       d.refobjid::regclass::text, a.attname "
        "FROM pg_sequences s "
        "JOIN pg_class c ON c.relname = s.sequencename "
        "  AND c.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = s.schemaname) "
        "LEFT JOIN pg_depend d ON d.objid = c.oid AND d.deptype IN ('a', 'i') "
        "  AND d.classid = 'pg_class'::regclass AND d.refclassid = 'pg_class'::regclass "
        "LEFT JOIN pg_attribute a ON a.attrelid = d.refobjid AND a.attnum = d.refobjsubid "
        "WHERE s.schemaname = 'public' ORDER BY 1",
    )
    atrasadas: list[str] = []
    revisadas = 0
    for seq, last, start, table, column in filas:
        if not table or not column:
            continue
        siguiente = int(last) + 1 if last is not None else int(start)
        maximo = _scalar(
            conn,
            sql.SQL("SELECT max({}) FROM {}").format(
                sql.Identifier(column), sql.Identifier(table.split(".")[-1].strip('"'))
            ),
        )
        revisadas += 1
        if maximo is not None and siguiente <= int(maximo):
            atrasadas.append(
                f"{seq} → próximo {siguiente} ≤ max({table}.{column})={maximo}: "
                f"el siguiente INSERT viola la PK"
            )
    if atrasadas:
        return Check("sequences", FAIL, "secuencias por detrás del dato — " + "; ".join(atrasadas))
    return Check(
        "sequences",
        PASS,
        f"{revisadas} secuencias asociadas a una columna van por delante del dato",
    )


def _check_constraints_validated(conn: psycopg.Connection) -> Check:
    malas = _rows(
        conn,
        "SELECT c.conname, c.conrelid::regclass::text FROM pg_constraint c "
        "JOIN pg_namespace n ON n.oid = c.connamespace "
        "WHERE n.nspname = 'public' AND NOT c.convalidated ORDER BY 1",
    )
    if malas:
        return Check(
            "constraints_validated",
            FAIL,
            "constraints NOT VALID (no comprueban las filas ya existentes): "
            + ", ".join(f"{c} en {t}" for c, t in malas),
        )
    total = _scalar(
        conn,
        "SELECT count(*) FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace "
        "WHERE n.nspname = 'public'",
    )
    return Check("constraints_validated", PASS, f"{total} constraints, todas validadas")


def _check_indexes_valid(conn: psycopg.Connection) -> Check:
    malas = _rows(
        conn,
        "SELECT c.relname, i.indisvalid, i.indisready FROM pg_index i "
        "JOIN pg_class c ON c.oid = i.indexrelid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND (NOT i.indisvalid OR NOT i.indisready) ORDER BY 1",
    )
    if malas:
        return Check(
            "indexes_valid",
            FAIL,
            "índices en el catálogo que el planificador NO usa: "
            + ", ".join(f"{n} (valid={v}, ready={r})" for n, v, r in malas),
        )
    total = _scalar(
        conn,
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'i'",
    )
    return Check("indexes_valid", PASS, f"{total} índices válidos y listos")


def _check_roles(conn: psycopg.Connection, exp: Expectations) -> Check:
    if not exp.roles:
        return Check("roles", SKIP, "no se pudieron derivar los roles esperados")
    presentes = {r[0] for r in _rows(conn, "SELECT rolname FROM pg_roles")}
    faltan = sorted(exp.roles - presentes)
    if faltan:
        return Check(
            "roles",
            FAIL,
            f"roles de conexión ausentes: {', '.join(faltan)}. Los roles son de CLÚSTER y un "
            f"`pg_dump` de una base NO los lleva: restaurar en una instancia limpia "
            f"(Procedimiento B) los pierde, y con ellos todos los GRANT.",
        )
    return Check("roles", PASS, f"roles presentes: {', '.join(sorted(exp.roles))}")


# ------------------------------------------------------- comparación contra el ORIGEN


_SIN_BASELINE = (
    "sin baseline del ORIGEN no se puede saber si falta algo: el catálogo restaurado es "
    "internamente coherente aunque haya perdido una tabla entera. Captura la huella junto "
    "al dump (`capture_baseline`)."
)


def _check_row_counts(conn: psycopg.Connection, baseline: Mapping[str, Any] | None) -> Check:
    if baseline is None:
        return Check("row_counts", SKIP, _SIN_BASELINE)
    esperado = baseline.get("tables", {})
    actuales = {r[0] for r in _rows(conn, _Q_TABLES)}
    difs: list[str] = []
    comparadas = 0
    total = 0
    for table, info in sorted(esperado.items()):
        if table not in actuales:
            continue  # la ausencia la reporta `object_inventory`
        got = int(_scalar(conn, sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))))
        comparadas += 1
        total += got
        if got != int(info["rows"]):
            difs.append(
                f"{table}: origen {info['rows']} → restaurado {got} ({got - info['rows']:+d})"
            )
    # Los continuous aggregates NO son tablas y `_Q_TABLES` nunca los veía: un
    # cagg vaciado dejaba todos los conteos idénticos mientras la consola pintaba
    # cifras viejas como vivas (regla de oro 7). Se cuenta la materialización.
    esperados_cagg = baseline.get("cagg_rows", {})
    actuales_cagg = {v: (s, t) for v, s, t in _caggs(conn)}
    for view, filas in sorted(esperados_cagg.items()):
        if view not in actuales_cagg:
            continue  # la ausencia la reporta `object_inventory`
        mat_schema, mat_table = actuales_cagg[view]
        got = int(
            _scalar(
                conn,
                sql.SQL("SELECT count(*) FROM {}.{}").format(
                    sql.Identifier(mat_schema), sql.Identifier(mat_table)
                ),
            )
        )
        comparadas += 1
        total += got
        if got != int(filas):
            difs.append(
                f"{view} (cagg materializado): origen {filas} → restaurado {got} "
                f"({got - int(filas):+d})"
            )

    if difs:
        return Check("row_counts", FAIL, "conteos que no cuadran — " + "; ".join(difs))
    return Check(
        "row_counts",
        PASS,
        f"{comparadas} relaciones (tablas + caggs materializados) cuadran fila a fila "
        f"con el origen ({total} filas en total)",
    )


def _check_columns(conn: psycopg.Connection, baseline: Mapping[str, Any] | None) -> Check:
    """Una columna que no viaja no deja hueco: misma tabla, mismos conteos."""
    if baseline is None:
        return Check("columns", SKIP, _SIN_BASELINE)
    esperado = baseline.get("columns", {})
    actual = _columns(conn)
    faltan: list[str] = []
    cambiadas: list[str] = []
    for table, cols in sorted(esperado.items()):
        if table not in actual:
            continue  # la ausencia de la tabla la reporta `object_inventory`
        tengo = {c[0]: c[1] for c in actual[table]}
        for nombre, tipo in cols:
            if nombre not in tengo:
                faltan.append(f"{table}.{nombre}")
            elif tengo[nombre] != tipo:
                cambiadas.append(f"{table}.{nombre}: {tipo} → {tengo[nombre]}")
    if faltan or cambiadas:
        partes = []
        if faltan:
            partes.append("columnas del origen que NO llegaron: " + ", ".join(faltan))
        if cambiadas:
            partes.append("columnas con otro tipo: " + "; ".join(cambiadas))
        return Check("columns", FAIL, " · ".join(partes))
    total = sum(len(c) for c in esperado.values())
    return Check(
        "columns", PASS, f"{total} columnas presentes y con su tipo en {len(esperado)} tablas"
    )


def _check_constraints(conn: psycopg.Connection, baseline: Mapping[str, Any] | None) -> Check:
    """CHECK, FK, UNIQUE y PK. Sin el CHECK de `severity` entra un valor prohibido."""
    if baseline is None:
        return Check("constraints", SKIP, _SIN_BASELINE)
    esperado = baseline.get("constraints", {})
    actual = _constraints(conn)
    tablas_vivas = {r[0] for r in _rows(conn, _Q_TABLES)}
    faltan = [
        f"{nombre} ({tipo_legible(info[1])} sobre {info[0]})"
        for nombre, info in sorted(esperado.items())
        if nombre not in actual and info[0] in tablas_vivas
    ]
    if faltan:
        return Check(
            "constraints",
            FAIL,
            "constraints del origen que NO llegaron: " + ", ".join(faltan),
        )
    return Check("constraints", PASS, f"{len(esperado)} constraints presentes con su nombre")


def tipo_legible(contype: str) -> str:
    return {
        "c": "CHECK",
        "f": "FOREIGN KEY",
        "p": "PRIMARY KEY",
        "u": "UNIQUE",
        "x": "EXCLUDE",
    }.get(contype, contype)


def _check_privileges(conn: psycopg.Connection, baseline: Mapping[str, Any] | None) -> Check:
    """El dato puede estar entero y el acceso no.

    `REVOKE ALL ON incidents FROM takab_app` deja todas las demás comprobaciones
    en verde y la consola sin arrancar. No es corrupción: es un restore que no
    trajo los GRANT.
    """
    if baseline is None:
        return Check("privileges", SKIP, _SIN_BASELINE)
    esperado = baseline.get("privileges", {})
    if not esperado:
        return Check("privileges", SKIP, "el origen no registró privilegios que comparar")
    roles = sorted({rol for por_rol in esperado.values() for rol in por_rol})
    actual = _privileges(conn, roles)
    perdidos: list[str] = []
    for table, por_rol in sorted(esperado.items()):
        if table not in actual:
            continue  # la ausencia la reporta `object_inventory`
        for rol, privs in sorted(por_rol.items()):
            faltan = sorted(set(privs) - set(actual[table].get(rol, [])))
            if faltan:
                perdidos.append(f"{rol} perdió {'/'.join(faltan)} sobre {table}")
    if perdidos:
        # Truncado como en `ownership`: un `--no-owner` deja al rol de migraciones
        # sin privilegios sobre las 39 tablas a la vez, y volcar las 39 líneas
        # entierra el resto del informe.
        return Check(
            "privileges",
            FAIL,
            f"{len(perdidos)} privilegios que el restore NO trajo (quien los perdió se queda "
            f"sin acceso): " + "; ".join(perdidos[:6]) + (" …" if len(perdidos) > 6 else ""),
        )
    concedidos = sum(len(p) for por_rol in esperado.values() for p in por_rol.values())
    return Check(
        "privileges",
        PASS,
        f"{concedidos} privilegios de {', '.join(roles)} intactos sobre {len(esperado)} tablas",
    )


def _check_object_inventory(conn: psycopg.Connection, baseline: Mapping[str, Any] | None) -> Check:
    if baseline is None:
        return Check("object_inventory", SKIP, _SIN_BASELINE)
    faltan: list[str] = []
    sobran: list[str] = []

    def _cmp(etiqueta: str, esperados: Iterable[str], actuales: Iterable[str]) -> None:
        e, a = set(esperados), set(actuales)
        faltan.extend(f"{etiqueta}:{x}" for x in sorted(e - a))
        sobran.extend(f"{etiqueta}:{x}" for x in sorted(a - e))

    _cmp("tabla", baseline.get("tables", {}), (r[0] for r in _rows(conn, _Q_TABLES)))
    _cmp("vista", baseline.get("views", {}), (r[0] for r in _rows(conn, _Q_VIEWS)))
    _cmp(
        "índice",
        baseline.get("indexes", ()),
        (
            r[0]
            for r in _rows(
                conn,
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind = 'i'",
            )
        ),
    )
    _cmp("hypertable", baseline.get("hypertables", ()), _hypertables(conn))
    _cmp(
        "secuencia",
        baseline.get("sequences", {}),
        (
            r[0]
            for r in _rows(
                conn, "SELECT sequencename FROM pg_sequences WHERE schemaname = 'public'"
            )
        ),
    )
    if faltan:
        return Check(
            "object_inventory",
            FAIL,
            f"objetos del origen que NO llegaron: {', '.join(faltan)}"
            + (f" · además sobran: {', '.join(sobran)}" if sobran else ""),
        )
    if sobran:
        return Check(
            "object_inventory",
            WARN,
            f"objetos que el origen no tenía (¿restore sobre una base no vacía?): "
            f"{', '.join(sobran)}",
        )
    return Check(
        "object_inventory",
        PASS,
        f"inventario completo contra el origen: {len(baseline.get('tables', {}))} tablas, "
        f"{len(baseline.get('views', {}))} vistas, {len(baseline.get('indexes', ()))} índices, "
        f"{len(baseline.get('sequences', {}))} secuencias",
    )


def _check_ownership(conn: psycopg.Connection, baseline: Mapping[str, Any] | None) -> Check:
    """La propiedad no es cosmética: es quién podrá migrar la base mañana.

    Medido sobre una base restaurada con el `--no-owner` del §3 del runbook:
    `SET ROLE takab_migrator; ALTER TABLE sites ADD COLUMN x text;` →
    `ERROR: must be owner of table sites`. El siguiente `alembic upgrade head`
    del despliegue muere, y el §5 no lo ve.
    """
    if baseline is None:
        return Check("ownership", SKIP, _SIN_BASELINE)
    actual = {r[0]: r[1] for r in _rows(conn, _Q_TABLES)}
    actual.update({r[0]: r[1] for r in _rows(conn, _Q_VIEWS)})
    esperado: dict[str, str] = {t: v["owner"] for t, v in baseline.get("tables", {}).items()}
    esperado.update({v: info["owner"] for v, info in baseline.get("views", {}).items()})
    cambios = [
        f"{obj}: {owner} → {actual[obj]}"
        for obj, owner in sorted(esperado.items())
        if obj in actual and actual[obj] != owner
    ]
    if cambios:
        return Check(
            "ownership",
            FAIL,
            f"la propiedad cambió en {len(cambios)} objetos (¿`pg_restore --no-owner`?): "
            + "; ".join(cambios[:12])
            + (" …" if len(cambios) > 12 else "")
            + " · el rol de migraciones deja de poder alterar sus tablas y el siguiente "
            "despliegue falla con `must be owner of table …`",
        )
    return Check(
        "ownership",
        PASS,
        f"{len(esperado)} objetos conservan su dueño del origen",
    )


def _check_data_tip(conn: psycopg.Connection, baseline: Mapping[str, Any] | None) -> Check:
    """La punta del dato: hasta cuándo hay telemetría. Es la medida del RPO real."""
    puntas: dict[str, datetime | None] = {}
    for ht in sorted(_hypertables(conn)):
        if _scalar(
            conn,
            "SELECT count(*) FROM pg_attribute WHERE attrelid = %s::regclass AND attname = 'ts' "
            "AND attnum > 0 AND NOT attisdropped",
            (ht,),
        ):
            puntas[ht] = _scalar(conn, sql.SQL("SELECT max(ts) FROM {}").format(sql.Identifier(ht)))
    if not puntas:
        return Check("data_tip", SKIP, "no hay hypertables con columna `ts` que medir")
    texto = ", ".join(f"{k}={v.isoformat() if v else 'sin datos'}" for k, v in puntas.items())
    if baseline is None:
        return Check("data_tip", INFO, f"punta del dato (sin origen con qué comparar): {texto}")
    atrasos: list[str] = []
    for ht, tip in puntas.items():
        origen = baseline.get("data_tip", {}).get(ht)
        if origen and tip and datetime.fromisoformat(origen) > tip:
            delta = datetime.fromisoformat(origen) - tip
            atrasos.append(f"{ht}: {delta} por detrás del origen")
        elif origen and not tip:
            atrasos.append(f"{ht}: el origen tenía datos hasta {origen} y aquí no hay ninguno")
    if atrasos:
        # La punta del dato ES la medida del RPO (R-5 del §6 del runbook). Una
        # regresión aquí es dato perdido, no una observación de color.
        return Check(
            "data_tip", FAIL, f"punta del dato ({texto}) — RPO PERDIDO: " + "; ".join(atrasos)
        )
    return Check("data_tip", PASS, f"punta del dato igual a la del origen: {texto}")


# --------------------------------------------------------------------------- orquestación


def verify(
    conn: psycopg.Connection,
    *,
    baseline: Mapping[str, Any] | None = None,
    expectations: Expectations | None = None,
) -> Report:
    """Corre TODAS las comprobaciones y devuelve el informe.

    `conn` debe estar en una transacción (no autocommit): las comprobaciones
    negativas usan savepoints y revierten siempre lo que tocan, incluido el
    `UPDATE` de prueba sobre tablas de compliance.
    """
    exp = expectations or declared_expectations()
    if baseline is not None:
        exp = exp.merged_with(_baseline_expectations(baseline))

    checks = [
        _check_extensions(conn, exp),
        _check_roles(conn, exp),
        _check_object_inventory(conn, baseline),
        _check_columns(conn, baseline),
        _check_constraints(conn, baseline),
        _check_privileges(conn, baseline),
        _check_ownership(conn, baseline),
        _check_row_counts(conn, baseline),
        _check_hypertables(conn, exp),
        _check_timescale_policies(conn, exp),
        _check_data_tip(conn, baseline),
        _check_append_only_triggers(conn, exp),
        _check_append_only_enforced(conn, exp),
        _check_column_grants(conn, exp),
        _check_column_grant_enforced(conn, exp),
        _check_rls_flags(conn, exp),
        _check_rls_on_tenant_tables(conn, exp),
        _check_rls_policies(conn, exp),
        _check_rls_owner_escape(conn),
        _check_barrier_views(conn, exp),
        _check_tenant_isolation(conn),
        _check_sequences(conn),
        _check_constraints_validated(conn),
        _check_indexes_valid(conn),
    ]
    return Report(tuple(checks))


_MARCA = {PASS: "  ok  ", FAIL: " FALLO", WARN: " aviso", INFO: " info ", SKIP: "SALTADA"}


def render(report: Report) -> str:
    ancho = max(len(c.name) for c in report.checks)
    lineas = [
        f"{_MARCA.get(c.status, c.status):>7}  {c.name.ljust(ancho)}  {c.detail}"
        for c in report.checks
    ]
    resumen = (
        f"{len(report.checks)} comprobaciones · "
        f"{sum(1 for c in report.checks if c.status == PASS)} ok · "
        f"{len(report.failed)} FALLO · {len(report.warned)} aviso · "
        f"{len(report.skipped)} SIN EJERCER"
    )
    lineas.append("-" * (ancho + 12))
    lineas.append(resumen)
    lineas.append(f"veredicto del verificador: {report.verdict}")
    if report.verdict == INDETERMINADO:
        lineas.append(f"  {_SIN_VERIFICAR}")
        lineas.append("  sin ejercer: " + ", ".join(c.name for c in report.skipped))
    return "\n".join(lineas)


# --------------------------------------------------------------------------- anclaje
# [T-2.73.a] La huella y el dump tienen que ver LA MISMA base.
#
# `_check_row_counts` exige igualdad EXACTA fila a fila — es lo que caza las
# decenas de miles de filas que el procedimiento viejo perdía en silencio (§4.1
# del runbook). Esa exactitud tiene una consecuencia que hay que respetar en el
# otro extremo: la base de producción no está quieta. Los latidos de la flota
# escriben cada minuto. Si la huella se toma a las 08:00:00 y el `pg_dump`
# termina a las 08:04, el dump trae más filas que la huella y el verificador
# declara ROJO sobre un restore perfecto.
#
# Aflojar la comprobación sería quitarle justo lo que la hace valer. Lo que se
# comparte es el SNAPSHOT: aquí se abre una transacción REPEATABLE READ, se
# exporta con `pg_export_snapshot()` y se mantiene abierta mientras
# `pg_dump --snapshot=<id>` la consume. Coste extra sobre la base: ninguno —
# `pg_dump` ya sostiene una transacción idéntica durante todo el volcado.

#: Nombres de los dos ficheros del apretón de manos, dentro del directorio que
#: comparten el contenedor (por bind-mount) y el script del cron.
_COORD_SNAPSHOT = "snapshot.id"
_COORD_DUMP_DONE = "dump.done"

#: Salida propia: ni 0 (verde), ni 1 (rojo), ni 2 (indeterminado). "No hay
#: huella" no es un veredicto sobre ninguna base.
SALIDA_SIN_HUELLA = 3


class AnclajeFallido(RuntimeError):
    """No se pudo anclar la huella al dump. Entonces NO se escribe huella.

    Deliberadamente asimétrico con el respaldo: el `.dump` sube igual (fail-open
    — no se toca el mecanismo que hoy funciona) y la huella no (fail-closed).
    Sin huella el veredicto es INDETERMINADO, que es la verdad; con una huella
    desalineada sería ROJO, que es mentira, y un falso rojo el día del desastre
    enseña al operador a desconfiar del verificador.
    """


def _escribir_atomico(destino: Path, contenido: str) -> None:
    """Temporal en el MISMO directorio + `rename(2)`.

    El `aws s3 cp` que viene detrás no sabe distinguir un JSON truncado de uno
    entero: o sube la huella completa o no sube nada.
    """
    tmp = destino.with_name(f".{destino.name}.parcial")
    tmp.write_text(contenido, encoding="utf-8")
    os.replace(tmp, destino)


def capture_baseline_pinned_to_dump(
    dsn: str, coord: Path, *, timeout: float = 3600.0
) -> dict[str, Any]:
    """Huella del origen anclada al mismo instante que verá el `pg_dump`.

    Protocolo, en dos ficheros dentro de `coord`:

    1. aquí se abre la transacción y se escribe `snapshot.id`;
    2. el script del cron lanza `pg_dump --snapshot=$(cat snapshot.id)`, sube el
       `.dump` y sólo entonces crea `dump.done`;
    3. al ver `dump.done` se toma la huella —dentro de la MISMA transacción, o
       sea sobre el mismo snapshot— y se devuelve.

    Si el paso 2 no llega, esto levanta `AnclajeFallido` sin escribir nada.
    """
    snap_path = coord / _COORD_SNAPSHOT
    done_path = coord / _COORD_DUMP_DONE
    if not coord.is_dir():
        raise AnclajeFallido(f"el directorio de coordinación {coord} no existe")
    for rancio in (snap_path, done_path):
        if rancio.exists():
            raise AnclajeFallido(
                f"{rancio} ya existía: la coordinación es de una corrida anterior y la huella "
                "quedaría anclada al dump equivocado. Usa un directorio nuevo por corrida."
            )

    with psycopg.connect(dsn) as conn:
        # Primera sentencia de la transacción: psycopg abre el BEGIN implícito
        # justo aquí, y `SET TRANSACTION` sólo vale antes de cualquier lectura.
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        snapshot = _scalar(conn, "SELECT pg_export_snapshot()")
        if not snapshot:
            raise AnclajeFallido("Postgres no devolvió ningún snapshot que exportar")
        _escribir_atomico(snap_path, f"{snapshot}\n")

        limite = time.monotonic() + timeout
        while not done_path.exists():
            if time.monotonic() >= limite:
                raise AnclajeFallido(
                    f"el dump no confirmó en {timeout:.0f} s (no apareció {done_path}). "
                    "El respaldo puede haber subido igual; la huella NO se escribe, porque "
                    "una huella que no corresponde a ningún dump del bucket produce un ROJO "
                    "inexplicable el día del restore."
                )
            time.sleep(0.1)

        huella = capture_baseline(conn)
        conn.rollback()
    return huella


# --------------------------------------------------------------------------- CLI
# Para que el §5 del runbook deje de ser SQL que un humano teclea y compara a
# ojo, y pase a ser un comando con veredicto y código de salida:
#
#   # tras un restore REAL (Procedimiento A o B), contra la base lateral:
#   cd api && DATABASE_URL=postgresql+psycopg://…/postgres \
#     uv run python -m takab_api.ops.restore_check --database takab_restore \
#       --baseline /tmp/takab-YYYY-MM-DD.fingerprint.json
#
#   # y el otro lado del par: la huella que viaja JUNTO al dump. Desde T-2.73.a
#   # la escribe el mismo cron de las 08:00, anclada al snapshot del dump:
#   … --database takab --save-baseline /out/huella.json --coordinate-with-dump /out


def build_parser() -> argparse.ArgumentParser:
    """El parser, aparte del `_cli`, para que se pueda inspeccionar sin ejecutarlo.

    Lo usa la guardia que contrasta los flags que el script del cron teclea
    contra los que este comando de verdad acepta: ese acoplamiento entre bash y
    Python es invisible, y un flag renombrado dejaría el cron muriendo cada
    noche contra el correo de root de un EC2, o sea contra ningún sitio.
    """
    p = argparse.ArgumentParser(
        prog="python -m takab_api.ops.restore_check",
        description="Verifica la integridad de una base restaurada (§5 del runbook de backup).",
    )
    p.add_argument("--database", required=True, help="base a verificar (o de la que tomar huella).")
    p.add_argument("--baseline", default=None, help="huella del ORIGEN con la que comparar.")
    p.add_argument("--save-baseline", default=None, help="escribe aquí la huella y termina.")
    p.add_argument(
        "--coordinate-with-dump",
        default=None,
        metavar="DIR",
        help=(
            "ancla la huella al snapshot que consumirá `pg_dump --snapshot=`. "
            f"Escribe {_COORD_SNAPSHOT} en DIR y espera a {_COORD_DUMP_DONE}."
        ),
    )
    p.add_argument(
        "--coordination-timeout",
        type=float,
        default=3600.0,
        metavar="SEGUNDOS",
        help="cuánto esperar a que el dump confirme (por omisión 3600).",
    )
    return p


def _cli(argv: list[str] | None = None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    if args.coordinate_with_dump and not args.save_baseline:
        p.error("--coordinate-with-dump sólo tiene sentido junto a --save-baseline")

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("falta DATABASE_URL (la misma env BARE que usa alembic)")
    dsn = psycopg.conninfo.make_conninfo(
        url.replace("postgresql+psycopg://", "postgresql://"), dbname=args.database
    )

    if args.save_baseline:
        destino = Path(args.save_baseline)
        if args.coordinate_with_dump:
            try:
                huella = capture_baseline_pinned_to_dump(
                    dsn, Path(args.coordinate_with_dump), timeout=args.coordination_timeout
                )
            except AnclajeFallido as exc:
                print(f"HUELLA NO ESCRITA — {exc}", file=sys.stderr)
                return SALIDA_SIN_HUELLA
        else:
            with psycopg.connect(dsn) as conn:
                huella = capture_baseline(conn)
                conn.rollback()
            print(
                "AVISO: huella SIN anclar a ningún dump. Sólo es comparable contra un dump "
                "tomado sobre una base quieta (ensayo local); contra el dump de una base viva, "
                "`row_counts` daría ROJO por la deriva. Para anclarla: --coordinate-with-dump."
            )
        _escribir_atomico(destino, json.dumps(huella, indent=2, ensure_ascii=False))
        print(f"huella de {args.database} escrita en {destino}")
        return 0

    with psycopg.connect(dsn) as conn:
        baseline = (
            json.loads(Path(args.baseline).read_text(encoding="utf-8")) if args.baseline else None
        )
        report = verify(conn, baseline=baseline)
        conn.rollback()
    print(render(report))
    if report.verdict == ROJO:
        print("\nVEREDICTO: ROJO — la base restaurada NO se puede devolver a servicio.")
        return 1
    if report.verdict == INDETERMINADO:
        # Salida 2 y no 0: sin la huella del origen no se pudo comprobar que no
        # falte nada, y un 0 aquí es la licencia para hacer el swap a ciegas.
        print(
            "\nVEREDICTO: INDETERMINADO — NO está verificada.\n"
            f"  {_SIN_VERIFICAR}\n"
            "  Pasa `--baseline <huella>.json` del ORIGEN (se toma con --save-baseline\n"
            "  y debe viajar JUNTO al dump). Sin ella, esto no acredita un restore."
        )
        return 2
    print("\nVEREDICTO: VERDE")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_cli())
