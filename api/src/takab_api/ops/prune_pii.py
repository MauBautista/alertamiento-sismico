"""T-2.81 · El job de retención de PII. Simulacro por defecto; podar se pide.

    uv run python -m takab_api.ops.prune_pii              # simulacro con conteos
    uv run python -m takab_api.ops.prune_pii --apply      # poda de verdad

CON QUÉ ROL CORRE ESTE JOB (lo más importante del archivo)
──────────────────────────────────────────────────────────
La T-2.80 dejó ``REVOKE DELETE`` sobre doce tablas para ``takab_app``. Esa capa
protege a la API porque la API se conecta como ``takab_app``. **Un job no tiene
por qué**: los jobs de este repo se invocan a mano, desde una sesión SSM o desde
un runner, con el DSN que tenga el operador delante — y el DSN de desarrollo, el
de los tests y el de una consola de emergencia son **superusuario**. Con ese DSN
el `REVOKE` no existe, la RLS no existe y hasta los triggers se pueden apagar con
``session_replication_role``. Heredar el rol del DSN habría dejado la excepción
de compliance escrita en la esperanza de que nadie ejecute el job desde la
consola equivocada.

Así que el job **se degrada a sí mismo**. ``harden_session`` es lo primero que
corre, dentro de la transacción y antes de leer un solo dato:

1. ``SET LOCAL ROLE takab_app`` — a partir de ahí PostgreSQL evalúa privilegios
   contra ``takab_app`` aunque la sesión se abriera como superusuario, y la RLS
   vuelve a aplicar porque ``takab_app`` no es dueño de ninguna tabla;
2. comprueba contra ``pg_roles`` que el rol resultante **no** es superusuario y
   **no** tiene ``BYPASSRLS`` (``takab_ingest`` no lo tiene, tiene lo segundo, y
   por eso tampoco puede correr este job);
3. pregunta al catálogo, **tabla por tabla y sobre el rol efectivo**, qué le
   niega el ``DELETE``: o le falta el privilegio, o hay un trigger guard ACTIVO
   (``tgenabled <> 'D'``; uno deshabilitado sigue en el catálogo y no para nada).
   Basta con uno de los dos, porque los dos son reales y ninguno cubre lo del
   otro: en ``rule_evaluations`` el privilegio quedó concedido y es el trigger
   quien la salva, y el privilegio, al revés, es lo único que alcanza a una tabla
   que nazca sin trigger. Lo que el job **no** acepta es una tabla sin ninguno.

El paso 3 es la excepción de compliance codificada: no es un `if` que rodea a un
`DELETE` —eso lo borra cualquiera en un refactor— es la **precondición para que
el job arranque**. Correr exige demostrarle a PostgreSQL que no puede podar
evidencia. Si alguien revierte el ``REVOKE`` de la T-2.80, este job deja de
funcionar y lo dice; no empieza a borrar auditoría en silencio.

Y ese paso tiene su propio suelo, porque si no se aprobaría a sí mismo: una tabla
a la que se le conceda ``DELETE`` y se le quite el trigger no queda "sin
mecanismo", queda **fuera del conjunto derivado**, y un job que solo revisa lo
que derivó seguiría en verde. Por eso ``COMPLIANCE_ANCHOR`` nombra las cinco
tablas de la regla de oro 11 y ``validar_proteccion`` aborta si alguna falta.

Y por si las capas anteriores fallaran a la vez, la última no es de este archivo:
los triggers ``forbid_update_delete()`` cubren también al dueño de la tabla.

EL SIMULACRO NO ES UN MODO, ES LA AUTORIZACIÓN
──────────────────────────────────────────────
``--apply`` no salta el conteo: lo exige. Para cada regla y cada tenant el job
cuenta primero las filas que cumplen el plazo, ejecuta después con **el mismo
predicado** y compara ``ROW_COUNT`` con el conteo. Si no cuadran —porque otra
sesión escribió en medio— revierte la transacción entera y falla. Podar una
cantidad de filas que nadie contó no es un estado alcanzable.

TENANTS
───────
El job recorre los tenants de uno en uno, fija ``app.tenant_id`` en la sesión y
además filtra por ``tenant_id`` en cada sentencia. Sobre ``life_checkins`` el
confinamiento es estructural: su política de retención exige ``tenant_id =
app_tenant_id()``, así que la RLS misma acota la sentencia. Sobre ``push_tokens``
la política interna preexistente (``pt_admin``) es global, y ahí el confinamiento
es el ``WHERE`` explícito más el informe por tenant, donde una fuga se ve.

LO QUE ESTE ARCHIVO NO HACE
───────────────────────────
No se programa solo. No hay scheduler en ``infra/terraform/modules/`` y esta
tarea no lo añade: el job queda **invocable**, como ``ops/restore_drill``, y
colgarlo de un EventBridge/cron es trabajo de infraestructura aparte.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg import sql

from ..privacy.retention import (
    COMPLIANCE_ANCHOR,
    DELETE_ROWS,
    IDENT,
    JOB_APP_ROLE,
    JOB_ROLE,
    REDACT,
    RETENTION_PLAN,
    RetentionRule,
    RetentionUnsafe,
    dias_configurados,
    protection_report,
    validar_proteccion,
)

SIMULACRO = "simulacro"
APLICADO = "aplicado"


@dataclass(frozen=True)
class SessionFacts:
    """Lo que el job pudo demostrar sobre su propia sesión antes de empezar."""

    role: str
    superuser: bool
    bypassrls: bool
    protected: tuple[str, ...]
    #: Por cada tabla del suelo de compliance, QUÉ le niega el DELETE al job.
    anchor: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class Conteo:
    """``due`` es lo que el simulacro promete; ``applied``, lo que la poda hizo."""

    rule: str
    tenant_id: str
    table: str
    due: int
    applied: int = 0


@dataclass(frozen=True)
class Informe:
    mode: str
    role: str
    superuser: bool
    bypassrls: bool
    protected: tuple[str, ...]
    windows: dict[str, int | None]
    counts: tuple[Conteo, ...] = ()
    tenants: tuple[str, ...] = ()
    disabled: tuple[str, ...] = field(default_factory=tuple)
    #: La evidencia de que la excepción de compliance se comprobó CONTRA LA BASE
    #: en esta corrida, y no se dio por supuesta. Va en el informe para que quede
    #: en el JSON del simulacro, que es lo que un auditor lee después.
    anchor: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def total_due(self) -> int:
        return sum(c.due for c in self.counts)

    @property
    def total_applied(self) -> int:
        return sum(c.applied for c in self.counts)


# ---------------------------------------------------------------------------
# La degradación de privilegios y su verificación
# ---------------------------------------------------------------------------

_Q_YO = """
SELECT current_user, r.rolsuper, r.rolbypassrls
FROM pg_roles r WHERE r.rolname = current_user
"""


def harden_session(conn: psycopg.Connection, *, role: str = JOB_ROLE) -> SessionFacts:
    """Degrada la sesión al rol del job y **demuestra** que quedó desarmada.

    Devolver sin excepción significa exactamente esto: la sesión que sigue no es
    superusuario, no tiene BYPASSRLS, y PostgreSQL le niega el ``DELETE`` —por
    privilegio ausente o por trigger guard activo— sobre todas las tablas del
    conjunto protegido, entre las que están, comprobadas y no supuestas, las cinco
    de ``COMPLIANCE_ANCHOR``. Es la precondición de todo lo demás; ejecutar una
    regla sin haber pasado por aquí no es posible porque ``run`` no ofrece otro
    camino.
    """
    if not IDENT.match(role):
        raise RetentionUnsafe(
            f"nombre de rol inadmisible {role!r}: el job no compone identificadores "
            "que no sean un identificador SQL simple."
        )
    try:
        conn.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
    except psycopg.Error as exc:
        raise RetentionUnsafe(
            f"el job no pudo degradarse al rol {role!r} ({exc}). Correr con el rol "
            "del DSN es exactamente lo que este job no hace."
        ) from exc

    fila = conn.execute(_Q_YO).fetchone()
    if fila is None:  # pragma: no cover - current_user siempre está en pg_roles
        raise RetentionUnsafe("no se pudo leer el rol efectivo de la sesión")
    efectivo, superuser, bypassrls = fila[0], bool(fila[1]), bool(fila[2])

    if superuser:
        raise RetentionUnsafe(
            f"el rol efectivo {efectivo!r} es SUPERUSUARIO: se salta el REVOKE de la "
            "T-2.80, la RLS y —vía session_replication_role— los triggers "
            "append-only. El job no corre con él."
        )
    if bypassrls:
        raise RetentionUnsafe(
            f"el rol efectivo {efectivo!r} tiene BYPASSRLS: convertiría un job "
            "acotado por tenant en un job global sin que nada lo grite (regla de "
            "oro 5). El job no corre con él."
        )

    # La excepción de compliance, codificada como PRECONDICIÓN de arrancar.
    #
    # `protection_report` pregunta al catálogo, sobre el rol EFECTIVO y no sobre
    # el que alguien esperaba, qué mecanismo le niega el `DELETE` a cada tabla; y
    # `validar_proteccion` se niega a devolver un conjunto que no contenga el
    # suelo de la regla de oro 11. Entre las dos: correr este job exige
    # demostrarle a PostgreSQL que no puede podar evidencia.
    #
    # Se miran DOS mecanismos y basta con uno, porque los dos son reales y
    # ninguno cubre lo del otro: hay tablas —`rule_evaluations`— donde el
    # privilegio `DELETE` quedó concedido y es el trigger append-only el que las
    # salva; y el privilegio, al revés, es lo único que alcanza a una tabla que
    # nazca sin trigger.
    mecanismos = protection_report(conn, role=efectivo)
    protegidas = validar_proteccion(mecanismos)

    # Contexto de aplicación: interno para poder recorrer todos los tenants,
    # sin titular (este job no actúa en nombre de ninguna persona).
    conn.execute("SELECT set_config('app.role', %s, true)", (JOB_APP_ROLE,))
    conn.execute("SELECT set_config('app.user_id', '', true)")
    conn.execute("SELECT set_config('app.tenant_id', '', true)")

    return SessionFacts(
        role=efectivo,
        superuser=superuser,
        bypassrls=bypassrls,
        protected=tuple(sorted(protegidas)),
        # Se lleva al informe SOLO el suelo de la regla de oro 11: cinco filas
        # que un auditor puede leer y contrastar, en vez de un volcado de
        # cincuenta tablas donde no se nota si falta una.
        anchor={t: mecanismos[t] for t in COMPLIANCE_ANCHOR},
    )


# ---------------------------------------------------------------------------
# Validación del plan contra lo que la base permite HOY
# ---------------------------------------------------------------------------


def _validar_reglas(
    conn: psycopg.Connection, plan: tuple[RetentionRule, ...], protegidas: frozenset[str] | set[str]
) -> None:
    """Rechaza el plan ENTERO si alguna regla es ilegal. Antes de contar nada.

    No se salta la regla mala y se sigue: un plan con una regla que quiere borrar
    evidencia es un plan en el que no se puede confiar, y correr las demás daría
    un informe verde de una corrida que nadie debería haber pedido.
    """
    for regla in plan:
        if regla.mode == DELETE_ROWS and regla.table in protegidas:
            raise RetentionUnsafe(
                f"la regla {regla.key!r} pide BORRAR FILAS de {regla.table!r}, que el "
                "catálogo declara protegida (guard append-only o DELETE revocado). "
                "Regla de oro 11: auditoría, evidencia de incidentes y dictámenes "
                "nunca se podan por retención. El plan entero queda rechazado."
            )
        fila = conn.execute(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s AND column_name = 'tenant_id'",
            (regla.table,),
        ).fetchone()
        if fila[0] != 1:
            raise RetentionUnsafe(
                f"la regla {regla.key!r} apunta a {regla.table!r}, que no existe o no "
                "tiene `tenant_id`: una regla que no se puede confinar a un tenant es "
                "una fuga (regla de oro 5)."
            )


# ---------------------------------------------------------------------------
# Composición de las sentencias. Único sitio del módulo que produce un verbo SQL.
# ---------------------------------------------------------------------------


def _sql_contar(regla: RetentionRule) -> sql.Composed:
    return sql.SQL("SELECT count(*) FROM {t} WHERE tenant_id = %(tenant)s AND ({c})").format(
        t=sql.Identifier(regla.table), c=sql.SQL(regla.clock)
    )


def _sql_ejecutar(regla: RetentionRule) -> sql.Composed:
    """El verbo sale del modo de la regla, y los modos son dos constantes.

    No hay ninguna otra función en este módulo que emita DML, y ninguna acepta
    SQL desde fuera: para que este job borrara algo que no debe haría falta
    escribir una regla nueva… que ``_validar_reglas`` rechaza si la tabla está
    protegida, y que el privilegio ausente rechazaría de todos modos.
    """
    if regla.mode == REDACT:
        return sql.SQL("UPDATE {t} SET {s} WHERE tenant_id = %(tenant)s AND ({c})").format(
            t=sql.Identifier(regla.table),
            s=sql.SQL(regla.set_clause),
            c=sql.SQL(regla.clock),
        )
    if regla.mode == DELETE_ROWS:
        return sql.SQL("DELETE FROM {t} WHERE tenant_id = %(tenant)s AND ({c})").format(
            t=sql.Identifier(regla.table), c=sql.SQL(regla.clock)
        )
    raise RetentionUnsafe(f"modo desconocido en {regla.key!r}: {regla.mode!r}")  # pragma: no cover


# ---------------------------------------------------------------------------
# La corrida
# ---------------------------------------------------------------------------


def _tenants(conn: psycopg.Connection, elegidos: tuple[str, ...] | None) -> tuple[str, ...]:
    if elegidos:
        return tuple(elegidos)
    filas = conn.execute("SELECT tenant_id::text FROM tenants ORDER BY tenant_id").fetchall()
    return tuple(f[0] for f in filas)


def run(
    conn: psycopg.Connection,
    *,
    apply: bool = False,
    plan: tuple[RetentionRule, ...] = RETENTION_PLAN,
    role: str = JOB_ROLE,
    days: dict[str, int | None] | None = None,
    tenants: tuple[str, ...] | None = None,
) -> Informe:
    """Simula (por defecto) o poda (con ``apply=True``) y devuelve el informe.

    ``days`` sustituye a las variables de entorno; ``{}`` significa "ninguna
    regla configurada", que es el default de producción hasta que alguien decida
    los plazos, y no poda nada.
    """
    ventanas: dict[str, int | None] = {
        r.key: (days.get(r.key) if days is not None else dias_configurados(r)) for r in plan
    }

    with conn.transaction():
        hechos = harden_session(conn, role=role)
        _validar_reglas(conn, plan, set(hechos.protected))

        lista = _tenants(conn, tenants)
        conteos: list[Conteo] = []

        for regla in plan:
            dias = ventanas[regla.key]
            if dias is None:
                continue
            corte = conn.execute("SELECT now() - make_interval(days => %s)", (dias,)).fetchone()[0]
            contar, ejecutar = _sql_contar(regla), _sql_ejecutar(regla)

            for tenant in lista:
                conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant,))
                params = {"tenant": tenant, "cutoff": corte}
                due = conn.execute(contar, params).fetchone()[0]
                hechas = 0
                if apply and due:
                    cur = conn.execute(ejecutar, params)
                    hechas = cur.rowcount
                    if hechas != due:
                        # Revierte la transacción ENTERA: la corrida deja de ser
                        # la que el conteo autorizó.
                        raise RetentionUnsafe(
                            f"{regla.key} / tenant {tenant}: el conteo previo dijo "
                            f"{due} filas y la sentencia tocó {hechas}. Otra sesión "
                            "escribió en medio; se revierte todo."
                        )
                conteos.append(
                    Conteo(
                        rule=regla.key,
                        tenant_id=tenant,
                        table=regla.table,
                        due=due,
                        applied=hechas,
                    )
                )

    # Fuera de la transacción del job: la degradación es local a ella, pero el
    # `SET LOCAL` sobrevive en la transacción del LLAMADOR si la hubiera.
    conn.execute("RESET ROLE")

    return Informe(
        mode=APLICADO if apply else SIMULACRO,
        role=hechos.role,
        superuser=hechos.superuser,
        bypassrls=hechos.bypassrls,
        protected=hechos.protected,
        windows=ventanas,
        counts=tuple(conteos),
        tenants=lista,
        disabled=tuple(k for k, v in ventanas.items() if v is None),
        anchor=hechos.anchor,
    )


# ---------------------------------------------------------------------------
# Presentación
# ---------------------------------------------------------------------------


def render(informe: Informe) -> str:
    lineas = [
        f"retención de PII · {informe.mode.upper()}",
        f"  rol efectivo      : {informe.role} "
        f"(superuser={informe.superuser}, bypassrls={informe.bypassrls})",
        f"  tablas protegidas : {len(informe.protected)} derivadas del catálogo vivo",
        f"  tenants           : {len(informe.tenants)}",
        "  regla de oro 11 — qué le niega el DELETE al job, comprobado ahora:",
        *(f"      {t:<18} {'+'.join(m)}" for t, m in sorted(informe.anchor.items())),
    ]
    for clave, dias in sorted(informe.windows.items()):
        if dias is None:
            lineas.append(f"  · {clave}: DESHABILITADA (sin plazo configurado) — no poda nada")
        else:
            lineas.append(f"  · {clave}: plazo {dias} d")
    lineas.append("")
    lineas.append("  regla / tenant                                        due   aplicadas")
    for c in informe.counts:
        if c.due or c.applied:
            lineas.append(f"  {c.rule:<28} {c.tenant_id:<20} {c.due:>6} {c.applied:>10}")
    lineas.append("")
    lineas.append(f"  TOTAL due={informe.total_due} aplicadas={informe.total_applied}")
    if informe.mode == SIMULACRO:
        lineas.append("  (simulacro: no se tocó ni una fila. Podar exige --apply)")
    return "\n".join(lineas)


def _informe_json(informe: Informe) -> dict[str, Any]:
    return {
        "mode": informe.mode,
        "role": informe.role,
        "superuser": informe.superuser,
        "bypassrls": informe.bypassrls,
        "protected": list(informe.protected),
        "compliance_anchor": {t: list(m) for t, m in informe.anchor.items()},
        "windows": informe.windows,
        "disabled": list(informe.disabled),
        "tenants": list(informe.tenants),
        "counts": [
            {
                "rule": c.rule,
                "tenant_id": c.tenant_id,
                "table": c.table,
                "due": c.due,
                "applied": c.applied,
            }
            for c in informe.counts
        ],
        "total_due": informe.total_due,
        "total_applied": informe.total_applied,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m takab_api.ops.prune_pii",
        description=(
            "Retención de PII. SIMULACRO por defecto: cuenta y no toca nada. Podar exige --apply."
        ),
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="poda de verdad. Sin este flag el job solo cuenta (criterio 3 de T-2.81).",
    )
    p.add_argument(
        "--dsn",
        default=None,
        help="DSN de la base. Por defecto DATABASE_URL. El rol del DSN NO es el rol "
        "con el que corre el job: ver la cabecera del módulo.",
    )
    p.add_argument(
        "--role",
        default=JOB_ROLE,
        help=f"rol al que el job se degrada al abrir la transacción (default: {JOB_ROLE}).",
    )
    p.add_argument(
        "--days",
        type=int,
        default=None,
        help="plazo uniforme, en días, para TODAS las reglas. Sin esto cada regla lee "
        "su variable de entorno, y la que no la tenga queda deshabilitada.",
    )
    p.add_argument(
        "--tenant",
        action="append",
        default=None,
        dest="tenants",
        help="acota a un tenant (repetible). Por defecto, todos.",
    )
    p.add_argument("--json", default=None, help="además, escribe el informe como JSON aquí.")
    return p


def _dsn(valor: str | None) -> str:
    crudo = valor or os.environ.get("DATABASE_URL", "")
    if not crudo:
        raise SystemExit("falta el DSN: pasa --dsn o exporta DATABASE_URL")
    return crudo.replace("postgresql+psycopg://", "postgresql://")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    plazos = {r.key: args.days for r in RETENTION_PLAN} if args.days is not None else None
    with psycopg.connect(_dsn(args.dsn), autocommit=False) as conn:
        try:
            informe = run(
                conn,
                apply=args.apply,
                role=args.role,
                days=plazos,
                tenants=tuple(args.tenants) if args.tenants else None,
            )
        except RetentionUnsafe as exc:
            print(f"RETENCIÓN ABORTADA · {exc}", file=sys.stderr)
            conn.rollback()
            return 2
        conn.commit()

    print(render(informe))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(_informe_json(informe), fh, indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
