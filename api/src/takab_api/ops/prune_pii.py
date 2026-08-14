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
es el ``WHERE`` explícito más el informe por tenant, donde una fuga se ve. Con
``user_profiles`` pasa lo mismo y por la misma razón (``user_profiles_admin`` es
``FOR ALL USING (app_is_takab_internal())``, sin filtro de cliente): estrechar
esa política para este job rompería el acceso interno que ya existe, así que se
declara cuál es el mecanismo en vez de fingir que es estructural.

[T-2.81.a] QUIÉN LO LLAMA, Y DÓNDE QUEDA ESCRITO QUE CORRIÓ
──────────────────────────────────────────────────────────
Este bloque decía "no se programa solo… colgarlo de un EventBridge/cron es
trabajo de infraestructura aparte". Ya está hecho: lo llama a diario el documento
SSM ``takab-<env>-retencion-pii`` (``infra/terraform/modules/database``), con el
mismo vehículo que el respaldo lógico y el PITR, y con el DSN de ``takab_app``
—el rol al que el job se degradaría de todas formas—, así que en la nube la
degradación es un no-op comprobable en vez de una red que nadie ejerce.

Corre con ``--apply``, y es seguro: sin ``TAKAB_API_RETENTION_*_DAYS`` cada regla
queda **deshabilitada** y la corrida no toca una fila. O sea que el cron se puede
desplegar antes de que los plazos estén decididos (son decisión de negocio, no de
programador), y lo único que hace mientras tanto es dejar constancia de que el
reloj se revisó.

**Cada corrida deja fila en ``pii_retention_runs``, incluido el simulacro que no
borró nada, e incluido el fallo.** Y se escribe **fuera** de la transacción del
job: la corrida se revierte entera si algo no cuadra, así que una constancia
escrita dentro desaparecería con el rollback justo en el caso que alguien
necesita leer. De esa tabla sale la métrica ``PiiRetentionAgeSeconds`` (edad de
la última corrida que terminó BIEN) y de la métrica, la alarma.

TOPES DE ESPERA: EL DE LOCK SÍ, EL DE SENTENCIA NO
──────────────────────────────────────────────────
Este job no conecta ni por ``db/session.py`` (request) ni por ``db/pool.py``
(workers): abre su propio ``psycopg.connect``, así que ninguno de los topes de
``T-2.130``/``T-2.131``/``T-2.132``/``T-2.136`` le aplicaba. Comprobado, no
supuesto — y la respuesta no es la misma para los dos relojes:

* **``statement_timeout`` no**, y no es pereza. La corrida es UNA transacción por
  diseño (el conteo previo es la autorización de la poda). **Medido el
  2026-08-14 sobre 1 000 000 de filas: 38.9 s**, lineales. Cualquiera de los
  topes de sentencia existentes (20 s / 15 s) mataría esa corrida legítima a
  mitad: convertir trabajo correcto en fallo no es una mejora.
* **``lock_timeout`` sí**, porque es otro modo de fallo: no mide lo que tarda la
  sentencia sino lo que pasa ESPERANDO. Sin él, una fila bloqueada por otra
  sesión deja al job esperando para siempre dentro de una transacción que ya
  sostiene el horizonte de ``xmin`` y los locks de todo lo podado. El número
  vive en ``db/session.JOB_LOCK_TIMEOUT_MS`` con el resto de la política.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg import sql

from ..db.session import JOB_LOCK_TIMEOUT_MS
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

    # [T-2.81.a] El tope de ESPERA POR LOCK, dentro de la transacción del job y
    # antes de leer nada. `SET LOCAL` y no `SET`: si el llamador (los tests, una
    # consola) tenía el suyo, se lo devolvemos al salir.
    #
    # No lleva `statement_timeout` a propósito y la razón está medida, no
    # supuesta: la corrida entera es UNA transacción por diseño y tarda 38.9 s
    # sobre un millón de filas. Ver `db/session.JOB_LOCK_TIMEOUT_MS`.
    conn.execute(sql.SQL("SET LOCAL lock_timeout = {}").format(sql.Literal(JOB_LOCK_TIMEOUT_MS)))

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
# [T-2.81.a] LA CONSTANCIA · una fila por corrida, incluida la que falló
# ---------------------------------------------------------------------------

_Q_CONSTANCIA = """
INSERT INTO pii_retention_runs
  (started_at, finished_at, mode, ok, total_due, total_applied, report, error)
VALUES (%(started)s, now(), %(mode)s, %(ok)s, %(due)s, %(applied)s, %(report)s, %(error)s)
RETURNING run_id
"""


def registrar_corrida(
    conn: psycopg.Connection,
    *,
    started_at: datetime,
    informe: Informe | None = None,
    error: str | None = None,
    mode: str | None = None,
) -> str | None:
    """Deja fila de esta corrida y devuelve su ``run_id``.

    **Va en su PROPIA transacción, y ahí está todo el asunto.** La corrida se
    revierte entera cuando algo no cuadra; una constancia escrita dentro de esa
    transacción desaparecería con el rollback justo en el caso que alguien
    necesita leer. Así que se escribe después, cuando la del job ya se cerró —
    por commit o por rollback, da igual.

    El contexto de aplicación se vuelve a fijar porque el ``set_config(...,
    true)`` del job era LOCAL a aquella transacción: sin esto, la RLS de
    ``pii_retention_runs`` (interna, default-deny) rechazaría la fila cuando el
    DSN sea ``takab_app``, que es como corre en la nube.
    """
    with conn.transaction():
        conn.execute("SELECT set_config('app.role', %s, true)", (JOB_APP_ROLE,))
        fila = conn.execute(
            _Q_CONSTANCIA,
            {
                "started": started_at,
                "mode": mode or (informe.mode if informe else SIMULACRO),
                "ok": error is None,
                "due": informe.total_due if informe else 0,
                "applied": informe.total_applied if informe else 0,
                "report": json.dumps(_informe_json(informe), ensure_ascii=False)
                if informe
                else "{}",
                "error": error,
            },
        ).fetchone()
    return str(fila[0]) if fila else None


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
    p.add_argument(
        "--sin-constancia",
        action="store_true",
        help="NO escribe la fila de `pii_retention_runs`. Solo para depurar a mano: sin "
        "constancia, la métrica que vigila la retención no se mueve y la alarma suena.",
    )
    return p


def _dsn(valor: str | None) -> str:
    crudo = valor or os.environ.get("DATABASE_URL", "")
    if not crudo:
        raise SystemExit("falta el DSN: pasa --dsn o exporta DATABASE_URL")
    return crudo.replace("postgresql+psycopg://", "postgresql://")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    plazos = {r.key: args.days for r in RETENTION_PLAN} if args.days is not None else None
    modo = APLICADO if args.apply else SIMULACRO
    arranque = datetime.now(UTC)
    informe: Informe | None = None
    fallo: str | None = None

    with psycopg.connect(_dsn(args.dsn), autocommit=False) as conn:
        try:
            informe = run(
                conn,
                apply=args.apply,
                role=args.role,
                days=plazos,
                tenants=tuple(args.tenants) if args.tenants else None,
            )
            conn.commit()
        # `psycopg.Error` además de `RetentionUnsafe`: el criterio 2 de la ficha
        # es "un fallo del job SE VE", y un fallo de la base —un `lock_timeout`
        # agotado, la conexión caída a mitad— es tan fallo como una regla ilegal.
        # Sin esta rama, la traza subía y NO quedaba constancia de nada.
        except (RetentionUnsafe, psycopg.Error) as exc:
            fallo = f"{type(exc).__name__}: {exc}"
            print(f"RETENCIÓN ABORTADA · {exc}", file=sys.stderr)
            conn.rollback()

        if not args.sin_constancia:
            try:
                registrar_corrida(
                    conn, started_at=arranque, informe=informe, error=fallo, mode=modo
                )
                conn.commit()
            except psycopg.Error as exc:
                # Que la constancia falle NO puede enmascarar el resultado real de
                # la corrida, pero tampoco puede pasar callando: sin fila, la
                # métrica no se mueve y la alarma va a sonar sin que nadie sepa
                # por qué. Se dice aquí, que es donde el cron lo escribe al log.
                conn.rollback()
                print(f"AVISO · no se pudo dejar constancia de la corrida: {exc}", file=sys.stderr)

    if fallo is not None:
        return 2

    assert informe is not None
    print(render(informe))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(_informe_json(informe), fh, indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
