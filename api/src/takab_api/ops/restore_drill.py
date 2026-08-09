"""T-2.73 · Ensayo de restore que mide su propio RTO.

Un solo comando: construye (o toma) una base origen, la vuelca, la restaura en
una instancia limpia que **él mismo crea**, verifica la integridad de lo
restaurado con `restore_check` y publica el RTO desglosado por fases.

    cd api && uv run python -m takab_api.ops.restore_drill
    make restore-drill

**Por qué existe.** `RUNBOOK-backup-restore-db.md:3` dice "RESTORE JAMÁS
PROBADO (gate G-09)" y su §2 dice "RTO: NO MEDIDO". Mientras eso siga así el
respaldo es una hipótesis. Esto no cierra G-09 —eso exige la ventana AWS de
T-2.74— pero convierte el ensayo en algo que se puede repetir a diario contra la
DB local, que corre **la misma imagen que producción**
(`timescale/timescaledb-ha:pg16`, `docker-compose.yml:3` y
`modules/database/user_data.sh.tpl:67`).

---

**Dónde arranca y dónde para el reloj.** Para en el VERDE DEL VERIFICADOR, no
en el `pg_restore`. Una base restaurada y no verificada no es un servicio
recuperado: el operador no puede devolverla a los usuarios sin saber si el
trigger append-only sobrevivió o si el aislamiento entre tenants sigue en pie.
Medir hasta el `pg_restore` mide una etapa técnica; el RTO es un compromiso de
servicio.

Y arranca **cuando el dump ya existe**, porque en el incidente real el dump ya
está en S3: fabricarlo aquí es andamiaje del ensayo, no recuperación. Esa etapa
se cronometra igual y se imprime aparte, marcada como fuera del RTO.

**La etapa que aquí NO se puede medir** es la descarga del dump desde S3. Se
declara como hueco en la salida en vez de inventarse un número: un RTO de 40
minutos del que 35 son descarga se arregla de una forma completamente distinta a
uno donde 35 son el `pg_restore`, y confundirlos es peor que no medir.

**Sobre extrapolar.** No se extrapola. El tiempo de un restore no es lineal en
el tamaño del dump —la reconstrucción de índices es superlineal, la etapa de red
es ancho de banda y no tiene nada que ver con el resto—, así que multiplicar el
número local por la razón de tamaños produciría una cifra con aspecto de
medición y valor de adivinanza. Lo que sí se imprime, siempre pegado al tiempo,
es la ESCALA: tamaño del dump y filas restauradas. Un número sin su escala es
una mentira cómoda.

---

**La guardia es POSITIVA.** No hay lista negra de nombres prohibidos: una lista
queda ciega al siguiente entorno, y el día que exista `prod` la guardia dejaría
pasar el restore. Aquí el ensayo **sólo escribe en una base que él mismo acaba
de crear en esta ejecución**, con un nombre que él genera y un marcador que él
escribe en el comentario de la base. Antes de cada paso destructivo re-lee ese
marcador desde el catálogo: si no está, o no es el de esta corrida, aborta sin
tocar un byte. Suma la lección de `demo/run.py::_assert_exclusive_db` (hallazgo
A-3): cualquier otro cliente conectado a la base destino aborta el paso.

**El ensayo NO hace el SWAP.** El paso `ALTER DATABASE takab RENAME TO …` del §3
del runbook es destructivo por naturaleza y es una decisión humana dentro de una
ventana, con la API parada. Restaura, verifica, mide y se para ahí. Lo que el
swap probaría de más —que la app arranca contra la base restaurada— no lo prueba
un rename: lo prueba levantar la app, y eso es T-2.74.

---

**Lo que este ensayo ya encontró** (medido, no supuesto — ver el informe de la
tarea): el Procedimiento A del runbook, ejecutado tal como está escrito, pierde
datos en silencio. Reprodúcelo con ``--como-el-runbook``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import psycopg
from psycopg import conninfo, sql

from takab_api.ops.restore_check import (
    INDETERMINADO,
    ROJO,
    VERDE,
    capture_baseline,
    render,
    verify,
)

# --------------------------------------------------------------------------- nombres

#: El ensayo sólo reconoce como suyas las bases que encajan aquí. No es la
#: guardia (la guardia es el marcador); es el primer filtro barato.
DRILL_NAME_RE = re.compile(r"^takab_drill_(src|dst)_\d{8}t\d{6}_[0-9a-f]{8}$")

_MARKER_PREFIX = "takab restore drill"


def new_drill_name(kind: str, run_id: str) -> str:
    """Nombre generado por ESTA corrida. `kind` ∈ {src, dst}."""
    if kind not in ("src", "dst"):
        raise ValueError(f"kind inválido: {kind!r}")
    return f"takab_drill_{kind}_{run_id}"


def new_run_id() -> str:
    return f"{datetime.now(UTC):%Y%m%dt%H%M%S}_{secrets.token_hex(4)}"


def marker_for(run_id: str) -> str:
    return f"{_MARKER_PREFIX} {run_id} · base de usar y tirar · NO es producción"


# --------------------------------------------------------------------------- guardia


class GuardError(RuntimeError):
    """La guardia se negó. Nada se tocó."""


def assert_drill_target(admin: psycopg.Connection, dbname: str, marker: str) -> None:
    """La guardia POSITIVA: esta base la creó ESTA corrida, o no se toca.

    Cuatro condiciones, y las cuatro tienen que darse:

    1. el nombre encaja con el patrón que sólo este módulo genera;
    2. la base existe (no se restaura sobre lo que no está);
    3. su comentario es EXACTAMENTE el marcador de esta corrida — es la prueba
       positiva de autoría: nadie más escribe ese texto;
    4. no hay otro cliente conectado (lección A-3 de la auditoría de cierre: un
       worker residente contaminó una acreditación entera y produjo fallos
       deterministas sin pista del porqué).

    No hay lista negra de nombres. Una lista de hostnames o de bases prohibidas
    queda ciega al siguiente entorno; esto no.
    """
    if not DRILL_NAME_RE.match(dbname):
        raise GuardError(
            f"restore_drill: {dbname!r} no es una base de ensayo. El ensayo SÓLO escribe "
            f"en bases que él mismo crea en esta corrida (patrón {DRILL_NAME_RE.pattern}). "
            f"Aborto sin tocar nada."
        )
    fila = admin.execute(
        "SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname = %s",
        (dbname,),
    ).fetchone()
    if fila is None:
        raise GuardError(f"restore_drill: la base {dbname!r} no existe. Aborto sin tocar nada.")
    if fila[0] != marker:
        raise GuardError(
            f"restore_drill: la base {dbname!r} NO lleva el marcador de esta corrida "
            f"(esperado {marker!r}, encontrado {fila[0]!r}). Esta base no la creó este "
            f"ensayo. Aborto sin tocar nada."
        )
    ajenos = admin.execute(
        "SELECT pid, usename, coalesce(application_name, ''), state "
        "FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid() "
        "AND backend_type = 'client backend'",
        (dbname,),
    ).fetchall()
    if ajenos:
        detalle = "\n".join(
            f"    pid={pid} user={user} app={app!r} state={state}"
            for pid, user, app, state in ajenos
        )
        raise GuardError(
            f"restore_drill: la base {dbname!r} tiene OTROS clientes conectados y el ensayo "
            f"exige exclusividad (RUNBOOK-auditoria-cierre, hallazgo A-3). Aborto:\n{detalle}"
        )


# --------------------------------------------------------------------------- fases


@dataclass
class Phase:
    name: str
    seconds: float
    in_rto: bool
    note: str = ""


@dataclass
class DrillResult:
    run_id: str
    phases: list[Phase] = field(default_factory=list)
    dump_bytes: int = 0
    source_rows: int = 0
    restore_rc: int = 0
    restore_stderr: str = ""
    report_text: str = ""
    checklist_crudo: str = ""
    verifier_ok: bool = False
    verifier_verdict: str = INDETERMINADO
    failed_checks: tuple[str, ...] = ()
    skipped_checks: tuple[str, ...] = ()
    warned_checks: tuple[str, ...] = ()
    budget_min: float = 60.0
    procedure: str = ""

    @property
    def rto_seconds(self) -> float:
        return sum(p.seconds for p in self.phases if p.in_rto)

    @property
    def scaffolding_seconds(self) -> float:
        return sum(p.seconds for p in self.phases if not p.in_rto)

    @property
    def ok(self) -> bool:
        """Verde de verdad: verificador VERDE (nada sin ejercer) y restore limpio."""
        return (
            self.verifier_verdict == VERDE
            and self.restore_rc == 0
            and not self.restore_stderr.strip()
        )

    @property
    def verdict(self) -> str:
        """Tres estados, como el verificador. Un ensayo con comprobaciones sin
        ejercer no es verde ni rojo: no está verificado, y decir otra cosa es la
        clase de mentira que esta tarea existe para matar."""
        if self.restore_rc != 0 or self.restore_stderr.strip() or self.verifier_verdict == ROJO:
            return ROJO
        if self.verifier_verdict == INDETERMINADO:
            return INDETERMINADO
        return VERDE

    @property
    def within_budget(self) -> bool:
        return self.rto_seconds <= self.budget_min * 60


# --------------------------------------------------------------------------- herramientas


@dataclass(frozen=True)
class PgTools:
    """Cómo invocar `pg_dump`/`pg_restore`/`psql` contra ESTE servidor.

    Importa la versión: un cliente más nuevo que el servidor emite `SET`s que el
    servidor no conoce (`transaction_timeout` de PG17+ contra PG16) y
    `pg_restore` los da por "errores ignorados" y sigue. Medido en esta máquina:
    cliente 18.4 contra servidor 16 → `unrecognized configuration parameter
    "transaction_timeout"`. Por eso se exige coincidencia de major.
    """

    kind: str  # "local" | "docker"
    prefix: tuple[str, ...]  # lo que va antes del binario (p.ej. `docker exec -i takab-db`)
    bindir: str  # prefijo de RUTA del binario, con su barra final, o ""
    version: str
    detail: str

    def cmd(self, binario: str, *args: str) -> list[str]:
        return [*self.prefix, f"{self.bindir}{binario}", *args]


_VERSION_RE = re.compile(r"(\d+)(?:\.(\d+))?")


def _limpia_version(texto: str) -> str:
    """`pg_dump (PostgreSQL) 16.14-1.pgdg22.04+1` → `16.14`.

    Las builds de distribución cuelgan su propia versión detrás de la de
    Postgres; quedarse con el último token daba `16.14-1.pgdg22.04+1)`.
    """
    m = _VERSION_RE.search(texto)
    if not m:
        raise RuntimeError(f"no se pudo leer la versión de: {texto!r}")
    return m.group(0)


def _major(version: str) -> str:
    return _limpia_version(version).split(".")[0]


def resolve_pg_tools(
    server_version: str,
    *,
    container: str,
    system_identifier: int | None = None,
    env: dict[str, str] | None = None,
) -> PgTools:
    """Elige un cliente cuyo major coincida con el del servidor, o se niega.

    Orden: `TAKAB_PG_BIN` explícito → ruta versionada de Debian/Ubuntu → binario
    del PATH si el major cuadra → `docker exec` en el contenedor que HOSPEDA este
    mismo clúster (que es exactamente lo que hace el §3 del runbook en el EC2).
    """
    env = env if env is not None else dict(os.environ)
    major = _major(server_version)

    explicito = env.get("TAKAB_PG_BIN")
    if explicito:
        binario = Path(explicito) / "pg_dump"
        if binario.exists():
            v = _binary_version(str(binario))
            if _major(v) != major:
                raise RuntimeError(
                    f"TAKAB_PG_BIN apunta a pg_dump {v} y el servidor es {server_version}: "
                    f"un cliente de otro major mete `SET`s que el servidor ignora con un "
                    f"error que `pg_restore` se traga. Apunta a un cliente {major}.x."
                )
            return PgTools("local", (), f"{explicito.rstrip('/')}/", v, f"TAKAB_PG_BIN={explicito}")

    versionado = Path(f"/usr/lib/postgresql/{major}/bin/pg_dump")
    if versionado.exists():
        return PgTools(
            "local",
            (),
            f"{versionado.parent}/",
            _binary_version(str(versionado)),
            f"cliente versionado {versionado.parent}",
        )

    en_path = shutil.which("pg_dump")
    if en_path:
        v = _binary_version(en_path)
        if _major(v) == major:
            return PgTools("local", (), "", v, f"pg_dump del PATH ({en_path})")

    if shutil.which("docker") and _container_running(container):
        v = _docker_version(container)
        if _major(v) != major:
            raise RuntimeError(
                f"el contenedor {container!r} trae pg_dump {v} y el servidor es {server_version}."
            )
        if system_identifier is not None:
            propio = _docker_system_identifier(container)
            if propio != system_identifier:
                raise RuntimeError(
                    f"el contenedor {container!r} NO hospeda el clúster al que apunta "
                    f"DATABASE_URL (system_identifier {propio} ≠ {system_identifier}). "
                    f"Usar sus binarios apuntaría al servidor equivocado."
                )
        return PgTools(
            "docker", ("docker", "exec", "-i", container), "", v, f"docker exec {container}"
        )

    raise RuntimeError(
        f"no hay cliente de PostgreSQL {major}.x disponible.\n"
        f"  · instala `postgresql-client-{major}` (queda en /usr/lib/postgresql/{major}/bin), o\n"
        f"  · levanta el contenedor de la DB (`make db`) para usar sus binarios, o\n"
        f"  · exporta TAKAB_PG_BIN=/ruta/al/bin de un cliente {major}.x.\n"
        f"El cliente del PATH es {shutil.which('pg_dump') or 'inexistente'}; un major distinto "
        f"produce restores con errores que `pg_restore` reporta como 'ignorados'."
    )


def _binary_version(path: str) -> str:
    salida = subprocess.run(  # noqa: S603
        [path, "--version"], capture_output=True, text=True, check=True
    ).stdout
    return _limpia_version(salida.split(")", 1)[-1])


def _container_running(name: str) -> bool:
    try:
        out = subprocess.run(
            ["docker", "ps", "--filter", f"name=^{name}$", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return name in out.stdout.split()


def _docker_version(container: str) -> str:
    out = subprocess.run(  # noqa: S603
        ["docker", "exec", container, "pg_dump", "--version"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return _limpia_version(out.split(")", 1)[-1])


def _docker_system_identifier(container: str) -> int:
    out = subprocess.run(
        [
            "docker",
            "exec",
            container,
            "psql",
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-tAc",
            "SELECT system_identifier FROM pg_control_system()",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        # el usuario `postgres` puede no existir; se reintenta con el del compose
        out = subprocess.run(
            [
                "docker",
                "exec",
                container,
                "psql",
                "-U",
                "takab",
                "-d",
                "postgres",
                "-tAc",
                "SELECT system_identifier FROM pg_control_system()",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    return int(out.stdout.strip())


# --------------------------------------------------------------------------- DSN


@dataclass(frozen=True)
class Target:
    """Los datos de conexión, sacados de `DATABASE_URL`. Sin secretos en git."""

    host: str
    port: str
    user: str
    password: str
    database: str

    def dsn(self, database: str | None = None) -> str:
        return conninfo.make_conninfo(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password or None,
            dbname=database or self.database,
        )

    def sqlalchemy_url(self, database: str) -> str:
        """La forma que alembic espera (`env.py` la mete en `sqlalchemy.url`)."""
        credencial = self.user + (f":{self.password}" if self.password else "")
        return f"postgresql+psycopg://{credencial}@{self.host}:{self.port}/{database}"

    def client_args(self, tools: PgTools, database: str) -> list[str]:
        """Argumentos de conexión para pg_dump/pg_restore/psql.

        Con el backend `docker` el binario corre DENTRO del servidor y va por su
        socket local (igual que el §3 del runbook en el EC2): no se le pasa host
        ni puerto, porque el 127.0.0.1 del contenedor no es el del anfitrión.
        """
        if tools.kind == "docker":
            return ["-U", self.user, "-d", database]
        return ["-h", self.host, "-p", self.port, "-U", self.user, "-d", database]

    def env(self) -> dict[str, str]:
        entorno = dict(os.environ)
        if self.password:
            entorno["PGPASSWORD"] = self.password
        return entorno


def target_from_url(url: str) -> Target:
    partes = urlsplit(url.replace("postgresql+psycopg://", "postgresql://"))
    return Target(
        host=partes.hostname or "127.0.0.1",
        port=str(partes.port or 5432),
        user=unquote(partes.username or "postgres"),
        password=unquote(partes.password or ""),
        database=(partes.path or "/postgres").lstrip("/") or "postgres",
    )


# --------------------------------------------------------------------------- siembra

#: La semilla vive en `db/seeds/restore_drill.sql`, con los demás seeds, y no
#: aquí dentro. Dos contratos del repositorio —correctos ambos— lo exigen:
#: `takab_api.audit` es el ÚNICO escritor de `audit_log`, y la superficie de
#: LECTURA de la API jamás nombra la hypertable cruda de features. Una semilla
#: de datos no es la API. El fichero explica por qué existe cada fila.
SEED_PATH = Path(__file__).resolve().parents[4] / "db" / "seeds" / "restore_drill.sql"


def seed_source(*, rows: int) -> str:
    """La semilla, con su volumen. El SQL lee `takab.drill_rows`, así que el
    fichero sigue siendo ejecutable a mano con `psql -f`."""
    return f"SET takab.drill_rows = {int(rows)};\n" + SEED_PATH.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- ensayo


def _run(
    cmd: list[str], *, env: dict[str, str], stdin=None, stdout=None
) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 — comandos construidos aquí, sin shell
        cmd, env=env, stdin=stdin, stdout=stdout, stderr=subprocess.PIPE, text=True, check=False
    )


def _psql(target: Target, tools: PgTools, database: str, sql_text: str) -> None:
    """`stdout` capturado: `timescaledb_pre_restore()` devuelve una fila, y esa
    fila suelta en medio del informe lo vuelve ilegible."""
    proc = _run(
        tools.cmd(
            "psql",
            *target.client_args(tools, database),
            "-v",
            "ON_ERROR_STOP=1",
            "-qtA",
            "-c",
            sql_text,
        ),
        env=target.env(),
        stdout=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"psql falló en {database}: {proc.stderr.strip()}")


class _Terminado(BaseException):
    """SIGTERM. `BaseException` a propósito: nadie de aquí abajo debe tragárselo."""


def _rearmar_sigterm() -> Any:
    """SIGTERM tiene que pasar por el `finally` que borra las bases del ensayo.

    Por defecto SIGTERM mata el proceso sin desenrollar la pila: el `finally` no
    corre y queda una `takab_drill_src_…` viva ocupando disco, con su marcador
    puesto y sin nadie que la reclame. Y SIGTERM no es exótico: es lo que mandan
    systemd al parar una unidad, `timeout`, y la cancelación de un job de CI —
    justo los tres sitios donde este ensayo tiene sentido correr desatendido.
    SIGINT (Ctrl-C) ya limpiaba, porque Python lo convierte en KeyboardInterrupt.
    """
    import signal

    def _morir(_sig: int, _frm: Any) -> None:
        raise _Terminado("SIGTERM: se limpian las bases del ensayo antes de salir")

    try:
        return signal.signal(signal.SIGTERM, _morir)
    except ValueError:  # pragma: no cover — hilo secundario
        return None


def assert_owned_by_this_run(admin: psycopg.Connection, dbname: str, marker: str) -> None:
    """La MITAD de la guardia: nombre + marcador, sin la cláusula de exclusividad.

    Se usa SÓLO para borrar al final. La exclusividad protege el paso destructivo
    de ESCRIBIR (restaurar encima de algo que otro está usando), y ahí no se
    negocia. Pero al limpiar es justo lo contrario: medido con SIGTERM real, el
    cliente muere y el servidor sigue ejecutando el INSERT de la siembra, así que
    la exclusividad se convierte en la razón por la que la base huérfana
    sobrevive. Y esas conexiones sólo pueden ser nuestras: la base la creó esta
    corrida hace segundos, con un nombre que nadie más genera.
    """
    if not DRILL_NAME_RE.match(dbname):
        raise GuardError(f"restore_drill: {dbname!r} no es una base de ensayo. No se toca.")
    fila = admin.execute(
        "SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname = %s",
        (dbname,),
    ).fetchone()
    if fila is None:
        return  # ya no está: nada que borrar
    if fila[0] != marker:
        raise GuardError(
            f"restore_drill: {dbname!r} no lleva el marcador de esta corrida. No se borra."
        )


def drop_drill_db(admin: psycopg.Connection, dbname: str, marker: str) -> bool:
    """Borra una base de ESTA corrida, cerrando antes sus conexiones abandonadas."""
    assert_owned_by_this_run(admin, dbname, marker)
    if not admin.execute(
        "SELECT count(*) FROM pg_database WHERE datname = %s", (dbname,)
    ).fetchone()[0]:
        return False
    admin.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE datname = %s AND pid <> pg_backend_pid()",
        (dbname,),
    )
    admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(dbname)))
    return True


def sweep_orphans(admin: psycopg.Connection, *, older_than_hours: float = 1.0) -> list[str]:
    """Barrido de arranque: bases de ensayo abandonadas por corridas anteriores.

    Segunda red por si la primera falla (SIGKILL, corte de luz, OOM). Sólo toca
    lo que lleva el marcador de ESTE ensayo —la misma prueba positiva de autoría
    que la guardia— y sólo si es vieja: una base con menos de una hora podría ser
    de una corrida VIVA en paralelo.
    """
    borradas: list[str] = []
    for nombre, comentario in admin.execute(
        "SELECT d.datname, shobj_description(d.oid, 'pg_database') "
        "FROM pg_database d WHERE d.datname LIKE 'takab\\_drill\\_%'"
    ).fetchall():
        if not comentario or not comentario.startswith(_MARKER_PREFIX):
            continue  # el nombre no basta: sin marcador, no es nuestra
        if not DRILL_NAME_RE.match(nombre):
            continue
        try:
            sello = nombre.rsplit("_", 2)[-2]  # …_YYYYMMDDtHHMMSS_xxxxxxxx
            nacida = datetime.strptime(sello, "%Y%m%dt%H%M%S").replace(tzinfo=UTC)
        except (ValueError, IndexError):
            continue
        if (datetime.now(UTC) - nacida).total_seconds() < older_than_hours * 3600:
            continue
        if admin.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE datname = %s", (nombre,)
        ).fetchone()[0]:
            continue  # alguien la está usando: no es huérfana
        admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(nombre)))
        borradas.append(nombre)  # noqa: PERF401
    return borradas


#: El §5 del runbook, consulta por consulta. No es la verificación —para eso
#: está `restore_check`—: es la PRUEBA de que ese checklist sale verde sobre una
#: base mutilada. Sin las dos salidas juntas, la mitad del hallazgo («y el §5 da
#: verde») hay que demostrarla aparte.
#:
#: La primera consulta lleva `{}` en vez del nombre de la hypertable cruda: se
#: resuelve del catálogo (la hypertable que tiene continuous aggregates, que es
#: la que el esquema no puede proteger con RLS). Dos razones, y las dos buenas:
#: un contrato del repositorio prohíbe nombrar esa tabla en `src/takab_api`
#: fuera de la ruta de ingesta (`tests/contracts/test_waveform_view.py`), y así
#: el checklist sigue al esquema si algún día se renombra.
_CHECKLIST_RUNBOOK: tuple[tuple[str, str], ...] = (
    ("La punta del dato", "SELECT max(ts) FROM {}"),
    ("Incidentes", "SELECT count(*) FROM incidents"),
    ("Auditoría", "SELECT count(*) FROM audit_log"),
    ("Evidencias", "SELECT count(*) FROM evidence_objects"),
    ("Timescale", "SELECT extversion FROM pg_extension WHERE extname='timescaledb'"),
    ("Hypertables", "SELECT count(*) FROM timescaledb_information.hypertables"),
    (
        "RLS viva",
        "SELECT string_agg(relname || '=' || relrowsecurity || '/' || relforcerowsecurity, ' ') "
        "FROM pg_class WHERE relname IN ('incidents','audit_log')",
    ),
)


def _hypertable_cruda(conn: psycopg.Connection) -> str | None:
    """La hypertable de features: la única con continuous aggregates."""
    fila = conn.execute(
        "SELECT hypertable_name FROM timescaledb_information.continuous_aggregates LIMIT 1"
    ).fetchone()
    return fila[0] if fila else None


def run_runbook_checklist(conn: psycopg.Connection) -> str:
    """Corre el §5 tal cual y devuelve lo que el operador leería."""
    cruda = _hypertable_cruda(conn)
    lineas = ["El §5 del runbook, LITERAL, sobre esta misma base restaurada:"]
    for etiqueta, consulta in _CHECKLIST_RUNBOOK:
        try:
            if "{}" in consulta:
                if cruda is None:
                    lineas.append(f"  {etiqueta:<14} <sin hypertable de features que medir>")
                    continue
                stmt = sql.SQL(consulta).format(sql.Identifier(cruda))  # type: ignore[arg-type]
            else:
                stmt = sql.SQL(consulta)  # type: ignore[assignment]
            valor = conn.execute(stmt).fetchone()[0]
        except psycopg.Error as exc:  # pragma: no cover — el §5 no debería fallar
            valor = f"<error: {exc.__class__.__name__}>"
        lineas.append(f"  {etiqueta:<14} {valor}")
    lineas.append("  → El §5 no mira conteos contra el ORIGEN, ni claves primarias, ni propiedad,")
    lineas.append("    ni privilegios, ni políticas de retención. Por eso puede salir entero en")
    lineas.append("    verde sobre una base a la que le faltan filas y PRIMARY KEY.")
    return "\n".join(lineas)


def _create_marked_db(admin: psycopg.Connection, dbname: str, marker: str) -> None:
    """Crea la base y le escribe el marcador de esta corrida en el catálogo.

    `COMMENT ON … IS` no admite parámetros (es una sentencia de utilidad), así
    que el literal se escapa con `sql.Literal` en vez de interpolarse a mano.
    """
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
    admin.execute(
        sql.SQL("COMMENT ON DATABASE {} IS {}").format(sql.Identifier(dbname), sql.Literal(marker))
    )


def run_drill(args: argparse.Namespace, *, out=sys.stdout) -> DrillResult:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "falta DATABASE_URL (la misma env BARE que usa alembic). Ej.: "
            "DATABASE_URL=postgresql+psycopg://takab:…@127.0.0.1:5433/takab"
        )
    target = target_from_url(url)
    run_id = new_run_id()
    marker = marker_for(run_id)
    result = DrillResult(run_id=run_id, budget_min=args.rto_budget_min)

    admin = psycopg.connect(target.dsn("postgres"), autocommit=True)
    sigterm_previo = _rearmar_sigterm()
    huerfanas = sweep_orphans(admin)
    if huerfanas:
        print(
            f"  barrido        : bases de ensayo huérfanas borradas: {', '.join(huerfanas)}",
            file=out,
        )
    server_version = admin.execute("SHOW server_version").fetchone()[0]
    sysid = admin.execute("SELECT system_identifier FROM pg_control_system()").fetchone()[0]
    tools = resolve_pg_tools(
        server_version, container=args.docker_container, system_identifier=sysid
    )

    helpers = not args.sin_timescale_helpers
    no_owner = args.no_owner
    exit_on_error = not args.no_exit_on_error
    result.procedure = (
        f"pg_restore{' --no-owner' if no_owner else ''}"
        f"{' --exit-on-error' if exit_on_error else ''}"
        f"{' · con' if helpers else ' · SIN'} timescaledb_pre/post_restore()"
    )

    print(f"ensayo de restore · corrida {run_id}", file=out)
    print(f"  servidor      : PostgreSQL {server_version} (system_identifier {sysid})", file=out)
    print(f"  cliente       : pg_dump {tools.version} vía {tools.detail}", file=out)
    print(f"  procedimiento : {result.procedure}", file=out)

    src = new_drill_name("src", run_id) if args.source_db is None else args.source_db
    dst = new_drill_name("dst", run_id)
    dump_path = Path(args.dump or f"/tmp/{dst}.dump")
    creadas: list[str] = []

    try:
        # ---------------------------------------------- andamiaje (FUERA del RTO)
        if args.source_db is None:
            t = time.monotonic()
            _create_marked_db(admin, src, marker)
            creadas.append(src)
            assert_drill_target(admin, src, marker)
            entorno = {**os.environ, "DATABASE_URL": target.sqlalchemy_url(src)}
            proc = subprocess.run(  # noqa: S603
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=Path(__file__).resolve().parents[4] / "api",
                env=entorno,
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"alembic falló sobre {src}: {proc.stderr[-2000:]}")
            with psycopg.connect(target.dsn(src)) as c:
                c.execute(seed_source(rows=args.rows))
                c.commit()
            # Los caggs se materializan FUERA de transacción (`refresh_continuous_
            # aggregate() cannot run inside a transaction block`), y hay que
            # materializarlos: un cagg vacío no ejercita el restore de su
            # hypertable de materialización, que es donde vive el dato agregado.
            with psycopg.connect(target.dsn(src), autocommit=True) as c:
                for cagg in ("site_metrics_1m", "site_metrics_1h"):
                    c.execute(f"CALL refresh_continuous_aggregate('{cagg}', NULL, NULL)")
            result.phases.append(
                Phase(
                    "origen sintético (alembic + siembra)",
                    time.monotonic() - t,
                    False,
                    f"{args.rows} filas de waveform en ~4 días · andamiaje del ensayo",
                )
            )

        # baseline + dump: en el incidente real ya existen, no cuentan al RTO
        t = time.monotonic()
        with psycopg.connect(target.dsn(src)) as c:
            baseline = capture_baseline(c)
        result.source_rows = sum(x["rows"] for x in baseline["tables"].values())
        chunks = 0
        with psycopg.connect(target.dsn(src)) as c:
            chunks = c.execute("SELECT count(*) FROM timescaledb_information.chunks").fetchone()[0]
        result.phases.append(
            Phase(
                "huella del origen (baseline)",
                time.monotonic() - t,
                False,
                f"{result.source_rows} filas · {chunks} chunks · se guarda JUNTO al dump",
            )
        )

        t = time.monotonic()
        with dump_path.open("wb") as fh:
            proc = _run(
                tools.cmd("pg_dump", *target.client_args(tools, src), "-Fc"),
                env=target.env(),
                stdout=fh,
            )
        if proc.returncode != 0:
            raise RuntimeError(f"pg_dump falló: {proc.stderr[-2000:]}")
        result.dump_bytes = dump_path.stat().st_size
        result.phases.append(
            Phase(
                "pg_dump del origen",
                time.monotonic() - t,
                False,
                "en producción esto ya ocurrió: el cron de las 08:00 dejó el .dump en S3",
            )
        )

        # ---------------------------------------------- RTO (aquí SÍ cuenta el reloj)
        t = time.monotonic()
        _create_marked_db(admin, dst, marker)
        creadas.append(dst)
        assert_drill_target(admin, dst, marker)
        if helpers:
            _psql(target, tools, dst, "CREATE EXTENSION IF NOT EXISTS timescaledb;")
            _psql(target, tools, dst, "SELECT timescaledb_pre_restore();")
        result.phases.append(
            Phase(
                "crear instancia limpia",
                time.monotonic() - t,
                True,
                f"base {dst} creada por esta corrida y marcada como suya",
            )
        )

        t = time.monotonic()
        assert_drill_target(admin, dst, marker)  # re-lee el marcador ANTES de escribir
        flags = ["--no-owner"] if no_owner else []
        if exit_on_error:
            flags.append("--exit-on-error")
        with dump_path.open("rb") as fh:
            proc = _run(
                tools.cmd("pg_restore", *target.client_args(tools, dst), *flags),
                env=target.env(),
                stdin=fh,
            )
        result.restore_rc = proc.returncode
        result.restore_stderr = proc.stderr
        if helpers:
            _psql(target, tools, dst, "SELECT timescaledb_post_restore();")
        result.phases.append(
            Phase(
                "pg_restore",
                time.monotonic() - t,
                True,
                f"rc={proc.returncode}" + (" · CON ERRORES" if proc.stderr.strip() else ""),
            )
        )

        t = time.monotonic()
        with psycopg.connect(target.dsn(dst)) as c:
            report = verify(c, baseline=baseline)
            result.report_text = render(report)
            result.verifier_ok = report.ok
            result.verifier_verdict = report.verdict
            result.failed_checks = tuple(x.name for x in report.failed)
            result.skipped_checks = tuple(x.name for x in report.skipped)
            result.warned_checks = tuple(x.name for x in report.warned)
            c.rollback()
        result.phases.append(
            Phase(
                "verificación de integridad",
                time.monotonic() - t,
                True,
                f"{len(report.checks)} comprobaciones · el reloj para AQUÍ",
            )
        )

        if args.checklist_crudo:
            with psycopg.connect(target.dsn(dst)) as c:
                result.checklist_crudo = run_runbook_checklist(c)
                c.rollback()
    finally:
        if args.keep:
            print(f"\n--keep: quedan en pie {', '.join(creadas)}", file=out)
        else:
            for nombre in reversed(creadas):
                try:
                    drop_drill_db(admin, nombre, marker)
                except GuardError as exc:
                    print(f"\nAVISO: no se borró {nombre}: {exc}", file=out)
            if args.dump is None and dump_path.exists():
                dump_path.unlink()
        admin.close()
        if sigterm_previo is not None:
            import signal

            signal.signal(signal.SIGTERM, sigterm_previo)

    return result


# --------------------------------------------------------------------------- salida


def _humano(n: int) -> str:
    valor = float(n)
    for unidad in ("B", "KiB", "MiB", "GiB"):
        if valor < 1024 or unidad == "GiB":
            return f"{n} B" if unidad == "B" else f"{valor:.1f} {unidad}"
        valor /= 1024
    return f"{n} B"


def render_result(result: DrillResult) -> str:
    ancho = max(len(p.name) for p in result.phases) if result.phases else 20
    lineas = [
        "",
        "=" * 78,
        "VERIFICACIÓN DE INTEGRIDAD DE LO RESTAURADO",
        "=" * 78,
        result.report_text,
        "",
        "=" * 78,
        "RTO MEDIDO",
        "=" * 78,
    ]
    for p in result.phases:
        marca = "RTO" if p.in_rto else "   "
        lineas.append(f"  {marca}  {p.name.ljust(ancho)}  {p.seconds:8.2f} s   {p.note}")
    lineas += [
        "  " + "-" * (ancho + 40),
        f"       {'RTO MEDIDO (total)'.ljust(ancho)}  {result.rto_seconds:8.2f} s",
        f"       {'andamiaje (fuera del RTO)'.ljust(ancho)}  {result.scaffolding_seconds:8.2f} s",
        "",
        f"  presupuesto declarado (runbook §2): {result.budget_min:.0f} min  →  "
        + (
            "NO COMPARABLE · ese presupuesto es de PRODUCCIÓN (dump real + descarga "
            "desde S3). Este número no lo acredita; lo acredita T-2.74."
            if result.within_budget
            else f"EXCEDIDO INCLUSO EN LOCAL ({result.rto_seconds / 60:.1f} min): si el "
            "ensayo de juguete ya no cabe, producción tampoco"
        ),
        "",
        "ESCALA DE ESTA MEDICIÓN (sin ella el número no significa nada)",
        f"  · dump                : {_humano(result.dump_bytes)}",
        f"  · filas en el origen  : {result.source_rows}",
        f"  · procedimiento       : {result.procedure}",
        "",
        "HONESTIDAD DEL ENSAYO",
        "  · Este RTO sale de un dump local pequeño: NO es el RTO de producción.",
        "    Este ensayo no acredita el gate G-09: eso exige la ventana AWS de T-2.74.",
        "  · NO se extrapola. El restore no es lineal en el tamaño del dump (los índices",
        "    se reconstruyen en tiempo superlineal) y la etapa de red no guarda relación",
        "    con el resto: multiplicar por la razón de tamaños daría una cifra con",
        "    aspecto de medición y valor de adivinanza.",
        "  · Etapa NO medida aquí: la DESCARGA del dump desde S3 (`aws s3 cp`), que en",
        "    el Procedimiento A va delante de todo esto. Se mide en T-2.74.",
        "  · El ensayo NO hace el SWAP del §3 (el renombrado de la base viva): es una",
        "    decisión humana dentro de una ventana, con la API parada.",
        "",
    ]
    if result.checklist_crudo:
        lineas += [
            "=" * 78,
            "EL CHECKLIST §5 DEL RUNBOOK, TAL COMO ESTÁ ESCRITO",
            "=" * 78,
            result.checklist_crudo,
            "",
        ]
    if result.restore_stderr.strip():
        lineas += [
            f"SALIDA DE ERROR DE pg_restore (rc={result.restore_rc})",
            *(f"  {ln}" for ln in result.restore_stderr.strip().splitlines()[:20]),
            "",
        ]
    lineas.append(f"VEREDICTO: {result.verdict}")
    if result.verdict == INDETERMINADO:
        lineas.append(
            "  el ensayo NO acredita nada: hubo comprobaciones que no se pudieron ejercer."
        )
    if result.failed_checks:
        lineas.append(f"  comprobaciones en FALLO: {', '.join(result.failed_checks)}")
    if result.skipped_checks:
        lineas.append(f"  SIN EJERCER: {', '.join(result.skipped_checks)}")
    if result.warned_checks:
        lineas.append(f"  avisos (no tumban el veredicto): {', '.join(result.warned_checks)}")
    return "\n".join(lineas)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m takab_api.ops.restore_drill",
        description="Ensaya un restore contra la DB local, verifica la integridad y mide el RTO.",
    )
    p.add_argument(
        "--source-db",
        default=None,
        help="base EXISTENTE a volcar (sólo se lee, nunca se escribe). Por defecto el ensayo "
        "construye su propio origen sintético, que es hermético y repetible.",
    )
    p.add_argument(
        "--rows",
        type=int,
        default=20000,
        help="filas de waveform del origen sintético (default 20000, ~4 días).",
    )
    p.add_argument(
        "--rto-budget-min",
        type=float,
        default=60.0,
        help="objetivo de RTO en minutos (runbook §2: 60).",
    )
    p.add_argument("--keep", action="store_true", help="no borrar las bases del ensayo.")
    p.add_argument("--dump", default=None, help="ruta del .dump (default: temporal que se borra).")
    p.add_argument(
        "--docker-container",
        default="takab-db",
        help="contenedor que hospeda el servidor, si hay que usar sus binarios.",
    )
    p.add_argument("--json", default=None, help="además, escribe el resultado como JSON aquí.")
    p.add_argument(
        "--sin-timescale-helpers",
        action="store_true",
        help="NO llamar a timescaledb_pre/post_restore(). Reproduce el §3 del runbook tal como "
        "está escrito hoy: pierde filas de chunk y las PRIMARY KEY de las hypertables.",
    )
    p.add_argument(
        "--no-owner",
        action="store_true",
        help="pasar --no-owner a pg_restore (como el §3): cambia la propiedad de todo.",
    )
    p.add_argument(
        "--no-exit-on-error",
        action="store_true",
        help="no pasar --exit-on-error: `pg_restore` sigue tras un error, como el §3.",
    )
    p.add_argument(
        "--checklist-crudo",
        action="store_true",
        help="además, corre el §5 del runbook LITERAL sobre lo restaurado y lo imprime. "
        "Sirve para ver con los dos ojos a la vez qué pierde el §3 y qué NO ve el §5.",
    )
    p.add_argument(
        "--como-el-runbook",
        action="store_true",
        help="atajo: los tres anteriores a la vez. Reproduce el Procedimiento A VERBATIM.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.como_el_runbook:
        args.sin_timescale_helpers = True
        args.no_owner = True
        args.no_exit_on_error = True
        # Las dos mitades del hallazgo en una sola salida: lo que el §3 pierde y
        # lo que el §5 NO ve. Por separado, cada una convence a medias.
        args.checklist_crudo = True
    result = run_drill(args)
    print(render_result(result))
    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {
                    "run_id": result.run_id,
                    "rto_seconds": result.rto_seconds,
                    "verdict": result.verdict,
                    "ok": result.ok,
                    "dump_bytes": result.dump_bytes,
                    "source_rows": result.source_rows,
                    "procedure": result.procedure,
                    "phases": [
                        {"name": p.name, "seconds": p.seconds, "in_rto": p.in_rto, "note": p.note}
                        for p in result.phases
                    ],
                    "failed_checks": list(result.failed_checks),
                    "skipped_checks": list(result.skipped_checks),
                    "warned_checks": list(result.warned_checks),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return {VERDE: 0, ROJO: 1, INDETERMINADO: 2}[result.verdict]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


# ---------------------------------------------------------------------------
# NOTA DELIBERADA — este módulo no contiene, y no puede contener, un SWAP.
# El §3 del runbook termina con `ALTER DATABASE takab RENAME TO takab_pre_restore`.
# Ese paso vive fuera del ensayo a propósito y hay un test que se pone rojo si la
# palabra aparece aquí (`test_el_ensayo_no_puede_hacer_swap`).
# ---------------------------------------------------------------------------
