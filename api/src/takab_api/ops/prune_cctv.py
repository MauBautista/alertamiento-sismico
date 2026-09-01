"""T-3.10 · La poda del vídeo. Simulacro por defecto; podar se pide.

    uv run python -m takab_api.ops.prune_cctv              # simulacro con el censo
    uv run python -m takab_api.ops.prune_cctv --apply      # poda de verdad

POR QUÉ ES UN JOB PROPIO Y NO UNA ``RetentionRule``
───────────────────────────────────────────────────
No es preferencia de estilo: meterlo en ``RETENTION_PLAN`` habría arrastrado media
capa de privacidad. ``retention._validar_plan()`` corre **en el import** y exige que
toda columna de una regla esté en ``PII_INVENTORY`` con ``action == "erase"``; eso
mete a ``cctv_clips`` en ``ERASED_TABLES``, que ``test_privacy_erasure`` compara
**por igualdad**, y de ahí a que ARCO tenga que tocar la tabla y cambien las claves
``affected`` de la constancia que se le entrega a un titular. Radio de explosión
enorme, y en la dirección contraria a la que hace falta.

Y hay una razón de fondo, no solo de acoplamiento: **la retención de PII redacta
columnas dentro de una transacción, y esto no**. Aquí hay un efecto externo e
irreversible —destruir bytes en S3— que ninguna transacción de Postgres puede
deshacer. Un job que finja lo contrario está mintiendo sobre su propia atomicidad.

LAS DOS MITADES, Y **EL ORDEN ES LA FICHA ENTERA**
──────────────────────────────────────────────────
Podar un vídeo son dos cosas: anular la referencia (``s3_key → NULL`` + ``purged_at``)
y **destruir el objeto**. Hacerlas en el orden equivocado produce dos estados muy
distintos, y solo uno es tolerable:

* **Fila primero, bytes después.** Si el borrado falla, la base dice ``PURGADO`` y la
  imagen de las personas sigue en S3. Es el fallo que la ficha nombra: *«peor que
  ninguno, porque se declara cumplido»*. **Prohibido.**
* **Bytes primero, fila después.** Si el ``UPDATE`` falla, quedan bytes muertos sin
  referencia y una fila que apunta a nada. Es un huérfano: molesto, visible, y
  **no miente sobre lo que se destruyó**.

Así que se borra primero y se anula después, y el informe **distingue los tres
desenlaces por nombre** —``completo``, ``huerfano``, ``fallido``— en vez de sumar un
total que los confundiría. Un huérfano y un fallido son problemas opuestos: en el
primero la imagen ya no existe, en el segundo sí.

De ahí también que la transacción sea **por objeto** y no una por corrida. Con una
sola transacción, un fallo en el objeto 40 revertiría las 39 filas ya anuladas cuyos
bytes están destruidos de verdad — convertiría 39 podas correctas en 39 huérfanos de
golpe. Es lo contrario de lo que hace ``prune_pii``, y a propósito: allí la corrida
entera es reversible y el conteo previo la autoriza; aquí no lo es.

LO QUE ESTE JOB LE DEMUESTRA A POSTGRES ANTES DE TOCAR NADA
───────────────────────────────────────────────────────────
Se degrada a ``takab_app`` con el mismo ``harden_session`` de ``prune_pii`` —el
mismo, importado, no una copia: dos comprobaciones de compliance que se creen la una
a la otra acaban divergiendo— y sobre eso añade la suya, que es específica del vídeo:

**la rendija tiene que estar viva**. ``cctv_purge_guard`` es un ``BEFORE UPDATE`` que
solo admite la transición ``s3_key`` de tener valor a ``NULL``, con el resto de la
fila idéntica. Mientras ese trigger esté activo, este job **no puede** hacerle a
``cctv_clips`` nada que no sea podar, aunque el código se lo proponga. Si alguien lo
deshabilita, la garantía desaparece **en silencio** —un trigger apagado sigue en el
catálogo— así que se comprueba ``tgenabled <> 'D'`` en cada corrida y el job se niega
a arrancar sin ella. Es el análogo exacto del suelo de ``COMPLIANCE_ANCHOR``.

Entre las dos: correr esto exige demostrarle a PostgreSQL que **no puede** borrar
evidencia y que **solo** puede anular una clave de S3.

EL RELOJ CUENTA DESDE LA CAPTURA, NO DESDE EL REGISTRO
──────────────────────────────────────────────────────
``ended_at`` para el clip y ``captured_at`` para la captura, nunca ``created_at``. La
fila nace cuando S3 avisa, que puede ser **días** después de grabar: un gabinete que
estuvo sin enlace sube su clip al reconectar. Contar desde el registro le daría a esa
imagen un plazo extra que nadie autorizó, y el plazo es sobre cuánto tiempo puede
existir la imagen de una persona, no sobre cuándo nos enteramos.

La consecuencia incómoda, dicha en voz alta: **un clip puede llegar ya vencido y
podarse sin que nadie lo haya visto**. Es la política funcionando, no un defecto — y
por eso el plazo es una decisión de negocio y no un default de programador.

LO QUE FALTA, Y NO ES CÓDIGO
────────────────────────────
1. **La retención es GLOBAL, y el blueprint la pide POR SITIO.** Hoy no hay dónde
   escribirla: ni ``sites`` ni ``cameras`` tienen columna de plazo. Se implementa lo
   expresable —una ventana por tabla, por variable de entorno— y se declara el hueco
   en vez de fingir que la variable global es «por sitio».
2. **El rol de la instancia NO tiene ``s3:DeleteObject``**, y eso es deliberado
   (`modules/database`): la cadena PITR tiene un solo podador. Esa decisión es sobre
   el bucket de RESPALDOS y sigue en pie; para que este job corra en la nube hace
   falta abrirle el borrado **sobre el bucket de evidencia y bajo el prefijo
   ``evidence/`` únicamente**. Hasta entonces el job falla en cada objeto, lo dice, y
   **no anula ni una fila** — que es la conducta correcta, no un accidente.
   Fichado en ``PENDIENTES-MAURICIO``.

SIN PLAZO, NO CORRE
───────────────────
Sin ``TAKAB_API_RETENTION_CCTV_*_DAYS`` cada tabla queda **deshabilitada** y la
corrida no toca un byte. O sea que el cron se puede desplegar antes de que los plazos
estén decididos, igual que el de PII.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg import sql

from ..audit import audit
from ..privacy.retention import IDENT, JOB_ROLE, RetentionUnsafe
from ..routers._s3 import delete_all_versions
from ..settings import Settings
from .prune_pii import harden_session

SIMULACRO = "simulacro"
APLICADO = "aplicado"

#: El verbo de la bitácora. Hermano de `cctv_egress` (la subida) y `cctv_download`
#: (la descarga): las tres cosas que le pueden pasar a una imagen de personas quedan
#: en `audit_log`, que es la única tabla que NO se poda jamás. Cuando el objeto ya no
#: exista, esta fila será la constancia de que existió y de que se destruyó.
VERBO = "cctv_purge"
ACTOR = "system:prune_cctv"

_ENV_PREFIX = "TAKAB_API_RETENTION_"


# ---------------------------------------------------------------------------
# El plan: qué tablas llevan vídeo y con qué reloj
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TablaDeVideo:
    """Una tabla con objeto en S3 y rendija de poda.

    ``tabla``, ``pk`` y ``reloj`` son fragmentos de CÓDIGO, no de datos: viven en este
    módulo, no vienen de una petición, y aun así pasan por ``IDENT`` — porque el día
    que alguien los componga desde otro sitio, la guarda ya está puesta.
    """

    key: str
    tabla: str
    pk: str
    reloj: str
    kind: str
    why: str

    def __post_init__(self) -> None:
        for campo in (self.tabla, self.pk, self.reloj):
            if not IDENT.match(campo):
                raise RetentionUnsafe(f"{self.key}: identificador inadmisible {campo!r}")

    @property
    def env_var(self) -> str:
        """``cctv_clips`` → ``TAKAB_API_RETENTION_CCTV_CLIPS_DAYS``."""
        return _ENV_PREFIX + self.key.upper() + "_DAYS"


CLIPS = TablaDeVideo(
    key="cctv_clips",
    tabla="cctv_clips",
    pk="clip_id",
    # El final de la ventana grabada. Ver la cabecera: NUNCA `created_at`.
    reloj="ended_at",
    kind="clip",
    why=(
        "Once minutos de vídeo de un edificio evacuando. Es lo más sensible que guarda "
        "el sistema y lo que menos tiempo debe existir: el hecho sobrevive en la fila "
        "—sha256, ventana, cobertura—, la imagen no."
    ),
)

STILLS = TablaDeVideo(
    key="cctv_stills",
    tabla="cctv_stills",
    pk="still_id",
    reloj="captured_at",
    kind="captura",
    why=(
        "El goteo de capturas y las cuatro que elige el reporte. Menos bytes que el "
        "clip y la misma naturaleza: son personas. Van con su propio plazo porque la "
        "del reingreso es la que fecha un hallazgo, y esa decisión es de negocio."
    ),
)

PLAN_DE_VIDEO: tuple[TablaDeVideo, ...] = (CLIPS, STILLS)


def dias_configurados(t: TablaDeVideo, env: dict[str, str] | None = None) -> int | None:
    """Plazo de la tabla, o ``None`` si nadie lo configuró.

    ``None`` no es "cero días": es "esta tabla no se poda". Un valor no entero o
    negativo también deshabilita y **no cae a un default** — un plazo mal tecleado
    tiene que dejar la imagen en su sitio, no destruirla antes de tiempo.
    """
    crudo = (env if env is not None else os.environ).get(t.env_var, "").strip()
    if not crudo:
        return None
    try:
        dias = int(crudo)
    except ValueError:
        return None
    return dias if dias > 0 else None


# ---------------------------------------------------------------------------
# Lo que se mide
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Objetivo:
    """Una fila vencida con objeto vivo. Lo que el simulacro promete."""

    key: str
    tabla: str
    row_id: str
    tenant_id: str
    s3_key: str
    kind: str


@dataclass(frozen=True)
class Podado:
    """El desenlace de UN objetivo, con las dos mitades separadas a propósito."""

    objetivo: Objetivo
    bytes_borrados: bool
    fila_anulada: bool
    versiones: int = 0
    error: str | None = None

    @property
    def completo(self) -> bool:
        """Las dos mitades. Lo único que se puede llamar podado."""
        return self.bytes_borrados and self.fila_anulada

    @property
    def huerfano(self) -> bool:
        """Bytes destruidos y fila intacta. Visible y molesto, pero no miente."""
        return self.bytes_borrados and not self.fila_anulada

    @property
    def fallido(self) -> bool:
        """S3 se negó. La imagen sigue ahí y la fila también lo dice."""
        return not self.bytes_borrados


@dataclass(frozen=True)
class Informe:
    mode: str
    role: str
    superuser: bool
    bypassrls: bool
    rendija: dict[str, bool]
    ventanas: dict[str, int | None]
    objetivos: tuple[Objetivo, ...] = ()
    podados: tuple[Podado, ...] = ()
    disabled: tuple[str, ...] = ()

    @property
    def completos(self) -> tuple[Podado, ...]:
        return tuple(p for p in self.podados if p.completo)

    @property
    def huerfanos(self) -> tuple[Podado, ...]:
        return tuple(p for p in self.podados if p.huerfano)

    @property
    def fallidos(self) -> tuple[Podado, ...]:
        return tuple(p for p in self.podados if p.fallido)

    @property
    def ok(self) -> bool:
        """Una corrida sin huérfanos ni fallidos. Cualquier otra cosa **se ve**."""
        return not self.huerfanos and not self.fallidos


# ---------------------------------------------------------------------------
# La precondición específica del vídeo: la rendija tiene que estar VIVA
# ---------------------------------------------------------------------------

#: Trigger de UPDATE, no deshabilitado, ejecutando `cctv_purge_guard`. Las tres
#: condiciones cuentan: `tgtype & 16` es UPDATE (bit 4 de `pg_trigger.tgtype`), y
#: `tgenabled <> 'D'` porque un trigger apagado sigue listado en el catálogo — leerlo
#: sin ese filtro es el modo exacto en que una guarda desaparece sin que nada lo diga.
_Q_RENDIJA = """
SELECT EXISTS (
  SELECT 1
  FROM pg_trigger t
  JOIN pg_proc  p ON p.oid = t.tgfoid
  JOIN pg_class c ON c.oid = t.tgrelid
  WHERE c.relname = %(tabla)s
    AND NOT t.tgisinternal
    AND p.proname = 'cctv_purge_guard'
    AND (t.tgtype & 16) <> 0
    AND t.tgenabled <> 'D'
)
"""


def verificar_rendija(
    conn: psycopg.Connection, plan: tuple[TablaDeVideo, ...] = PLAN_DE_VIDEO
) -> dict[str, bool]:
    """Confirma que cada tabla del plan sigue teniendo su rendija activa, o revienta.

    Es lo que convierte «este job solo anula ``s3_key``» de promesa del código en
    hecho impuesto por la base. Sin el trigger, un ``UPDATE`` de este job podría
    reescribir cualquier columna de una tabla append-only y **nada lo pararía**;
    con él, la única mutación que Postgres acepta es la poda.

    Falla CERRADA: la ausencia de la guarda no se degrada a un aviso. Si alguien la
    desarmó, lo que hay que hacer es no correr.
    """
    estado = {t.key: bool(conn.execute(_Q_RENDIJA, {"tabla": t.tabla}).fetchone()[0]) for t in plan}
    if muertas := sorted(k for k, viva in estado.items() if not viva):
        raise RetentionUnsafe(
            f"la rendija de poda NO está activa en {muertas}: sin `cctv_purge_guard` "
            "en UPDATE, este job podría reescribir cualquier columna de una tabla "
            "append-only en vez de solo anular `s3_key`. El job no corre."
        )
    return estado


# ---------------------------------------------------------------------------
# El censo
# ---------------------------------------------------------------------------


def _sql_censar(t: TablaDeVideo) -> sql.Composed:
    # `s3_key IS NOT NULL` es la mitad de la idempotencia: una fila ya podada deja de
    # cumplir el predicado y la segunda corrida ve cero, sin llevar cuentas aparte.
    return sql.SQL(
        "SELECT {pk}::text, tenant_id::text, s3_key FROM {tabla} "
        "WHERE s3_key IS NOT NULL AND {reloj} < %(cutoff)s ORDER BY {reloj}"
    ).format(
        pk=sql.Identifier(t.pk),
        tabla=sql.Identifier(t.tabla),
        reloj=sql.Identifier(t.reloj),
    )


def censar(
    conn: psycopg.Connection,
    *,
    plan: tuple[TablaDeVideo, ...] = PLAN_DE_VIDEO,
    ventanas: dict[str, int | None],
) -> tuple[Objetivo, ...]:
    """Las filas vencidas con objeto vivo. Es lo que el simulacro enseña y la poda usa.

    Recorre TODOS los tenants de una vez: el job corre con ``app.role`` interno, así
    que la política ``*_admin`` le deja verlos, y el ``tenant_id`` viaja en cada
    objetivo para que el informe y la bitácora lo digan. Un job de retención que
    tuviera que enumerar tenants a mano se dejaría fuera al siguiente que se dé de alta.
    """
    objetivos: list[Objetivo] = []
    for t in plan:
        dias = ventanas[t.key]
        if dias is None:
            continue
        corte = conn.execute("SELECT now() - make_interval(days => %s)", (dias,)).fetchone()[0]
        for row_id, tenant_id, s3_key in conn.execute(_sql_censar(t), {"cutoff": corte}):
            objetivos.append(
                Objetivo(
                    key=t.key,
                    tabla=t.tabla,
                    row_id=row_id,
                    tenant_id=tenant_id,
                    s3_key=s3_key,
                    kind=t.kind,
                )
            )
    return tuple(objetivos)


# ---------------------------------------------------------------------------
# La poda de UN objeto: los bytes primero, la fila después
# ---------------------------------------------------------------------------


def _sql_anular(t: TablaDeVideo) -> sql.Composed:
    # `AND s3_key = %(s3_key)s` no es decoración: ata el UPDATE a la MISMA key cuyos
    # bytes se acaban de destruir. Sin esa condición, una fila que otra sesión hubiera
    # cambiado en medio se anularía igual y el job declararía podado un objeto que
    # sigue vivo. Con ella, ese caso sale por `rowcount == 0` y se cuenta huérfano.
    return sql.SQL(
        "UPDATE {tabla} SET s3_key = NULL, purged_at = now() "
        "WHERE {pk} = %(row_id)s AND s3_key = %(s3_key)s"
    ).format(tabla=sql.Identifier(t.tabla), pk=sql.Identifier(t.pk))


#: Firma del borrador de objetos. Es un seam para poder ejercer los dos desenlaces que
#: importan —el que borra y el que se niega— sin AWS delante.
Borrador = Callable[[Settings, str], int]


def podar_uno(
    conn: psycopg.Connection,
    settings: Settings,
    objetivo: Objetivo,
    tabla: TablaDeVideo,
    *,
    role: str = JOB_ROLE,
    borrar: Borrador = delete_all_versions,
) -> Podado:
    """Destruye el objeto y **luego** anula la referencia. Ese orden, y no el otro.

    Devuelve siempre un ``Podado``: los fallos de esta función son datos del informe,
    no excepciones, porque un objeto que S3 se niega a borrar no puede detener la poda
    de los otros veinte. Lo que sí detiene todo es que la base deje de ser segura —eso
    sube como ``RetentionUnsafe`` desde ``harden_session``.
    """
    try:
        versiones = borrar(settings, objetivo.s3_key)
    except Exception as exc:  # noqa: BLE001 — cualquier fallo de S3 es "no se borró"
        # La fila NO se toca. Es lo importante de esta rama: con los bytes vivos, una
        # referencia anulada sería la mentira que esta ficha existe para impedir.
        return Podado(objetivo, bytes_borrados=False, fila_anulada=False, error=str(exc))

    try:
        with conn.transaction():
            # La degradación es LOCAL a la transacción, así que se rehace en cada una.
            # Sale caro en consultas al catálogo y es deliberado: cada UPDATE ocurre en
            # una sesión que acaba de demostrar que no puede hacer otra cosa. Si alguien
            # desarma la guarda a mitad de corrida, la corrida se para ahí.
            harden_session(conn, role=role)
            verificar_rendija(conn, (tabla,))
            cur = conn.execute(
                _sql_anular(tabla), {"row_id": objetivo.row_id, "s3_key": objetivo.s3_key}
            )
            anulada = cur.rowcount == 1
            if anulada:
                # Dentro de la MISMA transacción que el UPDATE: la constancia y el hecho
                # viven o mueren juntos. Al revés que en `prune_pii`, donde la constancia
                # va fuera porque lo que hay que documentar es también el rollback.
                audit(
                    conn,
                    tenant_id=objetivo.tenant_id,
                    actor=ACTOR,
                    verb=VERBO,
                    obj=objetivo.s3_key,
                    meta={
                        "kind": objetivo.kind,
                        "tabla": objetivo.tabla,
                        "row_id": objetivo.row_id,
                        "versiones_borradas": versiones,
                    },
                )
    except psycopg.Error as exc:
        # **LOS BYTES YA NO EXISTEN.** Un error de base aquí no puede subir y matar la
        # corrida: se perdería la única noticia de que ese objeto se destruyó, y los
        # objetivos siguientes se quedarían sin procesar con su imagen viva. Es un
        # huérfano, y como huérfano se declara.
        #
        # `RetentionUnsafe` NO se captura, y la asimetría es el criterio: «este objeto
        # salió mal» se cuenta y se sigue; «la base dejó de ser segura» —la guarda
        # desarmada, el rol equivocado— para la corrida. Meterlos en el mismo `except`
        # convertiría lo segundo en una línea más del informe.
        return Podado(
            objetivo,
            bytes_borrados=True,
            fila_anulada=False,
            versiones=versiones,
            error=str(exc),
        )
    return Podado(objetivo, bytes_borrados=True, fila_anulada=anulada, versiones=versiones)


# ---------------------------------------------------------------------------
# La corrida
# ---------------------------------------------------------------------------


def run(
    conn: psycopg.Connection,
    *,
    settings: Settings | None = None,
    apply: bool = False,
    plan: tuple[TablaDeVideo, ...] = PLAN_DE_VIDEO,
    role: str = JOB_ROLE,
    days: dict[str, int | None] | None = None,
    borrar: Borrador = delete_all_versions,
) -> Informe:
    """Censa (siempre) y poda (solo con ``apply=True``). Devuelve el informe.

    ``days`` sustituye a las variables de entorno; ``{}`` significa "ninguna tabla
    configurada", que es el default de producción hasta que alguien decida los plazos.
    """
    ajustes = settings or Settings()
    ventanas: dict[str, int | None] = {
        t.key: (days.get(t.key) if days is not None else dias_configurados(t)) for t in plan
    }

    with conn.transaction():
        hechos = harden_session(conn, role=role)
        rendija = verificar_rendija(conn, plan)
        objetivos = censar(conn, plan=plan, ventanas=ventanas)

    podados: list[Podado] = []
    if apply:
        por_key = {t.key: t for t in plan}
        for objetivo in objetivos:
            podados.append(
                podar_uno(conn, ajustes, objetivo, por_key[objetivo.key], role=role, borrar=borrar)
            )

    # La degradación es local a cada transacción, pero un `SET LOCAL` hecho dentro de
    # una transacción ABIERTA DEL LLAMADOR le sobreviviría: por eso el reset. Va en
    # best-effort porque este job puede llegar aquí con la conexión ya caída —el mismo
    # fallo que acaba de producir un huérfano— y morir limpiando sería tirar el informe
    # que dice qué se destruyó.
    try:
        conn.execute("RESET ROLE")
    except psycopg.Error:
        pass

    return Informe(
        mode=APLICADO if apply else SIMULACRO,
        role=hechos.role,
        superuser=hechos.superuser,
        bypassrls=hechos.bypassrls,
        rendija=rendija,
        ventanas=ventanas,
        objetivos=objetivos,
        podados=tuple(podados),
        disabled=tuple(k for k, v in ventanas.items() if v is None),
    )


# ---------------------------------------------------------------------------
# Presentación
# ---------------------------------------------------------------------------


def render(informe: Informe) -> str:
    lineas = [
        f"poda de vídeo · {informe.mode.upper()}",
        f"  rol efectivo : {informe.role} "
        f"(superuser={informe.superuser}, bypassrls={informe.bypassrls})",
        "  rendija de poda viva (`cctv_purge_guard` en UPDATE), comprobada ahora:",
        *(f"      {k:<14} {'sí' if v else 'NO'}" for k, v in sorted(informe.rendija.items())),
    ]
    for clave, dias in sorted(informe.ventanas.items()):
        if dias is None:
            lineas.append(f"  · {clave}: DESHABILITADA (sin plazo configurado) — no poda nada")
        else:
            lineas.append(f"  · {clave}: plazo {dias} d")

    lineas += ["", f"  objetivos vencidos con objeto vivo: {len(informe.objetivos)}"]
    if informe.mode == SIMULACRO:
        lineas += [
            *(f"      {o.kind:<8} {o.s3_key}" for o in informe.objetivos),
            "",
            "  (simulacro: no se destruyó un byte ni se tocó una fila. Podar exige --apply)",
        ]
        return "\n".join(lineas)

    lineas += [
        "",
        f"  COMPLETOS (bytes destruidos + referencia anulada): {len(informe.completos)}",
        f"  HUÉRFANOS (bytes destruidos, fila intacta)       : {len(informe.huerfanos)}",
        f"  FALLIDOS  (S3 se negó; la imagen SIGUE AHÍ)      : {len(informe.fallidos)}",
    ]
    for p in informe.huerfanos:
        lineas.append(f"      HUÉRFANO · {p.objetivo.s3_key} — bytes muertos, fila sin anular")
    for p in informe.fallidos:
        lineas.append(f"      FALLIDO  · {p.objetivo.s3_key} — {p.error}")
    if not informe.ok:
        lineas += [
            "",
            "  ⚠ La corrida NO está limpia. Un fallido es una imagen que sigue "
            "existiendo; un huérfano, bytes sin dueño.",
        ]
    return "\n".join(lineas)


def _informe_json(informe: Informe) -> dict[str, Any]:
    return {
        "mode": informe.mode,
        "role": informe.role,
        "superuser": informe.superuser,
        "bypassrls": informe.bypassrls,
        "rendija": informe.rendija,
        "windows": informe.ventanas,
        "disabled": list(informe.disabled),
        "objetivos": [
            {
                "table": o.tabla,
                "row_id": o.row_id,
                "tenant_id": o.tenant_id,
                "s3_key": o.s3_key,
                "kind": o.kind,
            }
            for o in informe.objetivos
        ],
        "podados": [
            {
                "s3_key": p.objetivo.s3_key,
                "table": p.objetivo.tabla,
                "row_id": p.objetivo.row_id,
                "tenant_id": p.objetivo.tenant_id,
                "bytes_borrados": p.bytes_borrados,
                "fila_anulada": p.fila_anulada,
                "versiones": p.versiones,
                "error": p.error,
            }
            for p in informe.podados
        ],
        "total_objetivos": len(informe.objetivos),
        "completos": len(informe.completos),
        "huerfanos": len(informe.huerfanos),
        "fallidos": len(informe.fallidos),
        "ok": informe.ok,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m takab_api.ops.prune_cctv",
        description=(
            "Poda de vídeo de CCTV: destruye el objeto en S3 y anula la referencia. "
            "SIMULACRO por defecto: censa y no toca nada. Podar exige --apply."
        ),
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="poda de verdad. IRREVERSIBLE: destruye todas las versiones del objeto.",
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
        help=f"rol al que el job se degrada al abrir cada transacción (default: {JOB_ROLE}).",
    )
    p.add_argument(
        "--days",
        type=int,
        default=None,
        help="plazo uniforme, en días, para TODAS las tablas de vídeo. Sin esto cada "
        "tabla lee su variable de entorno, y la que no la tenga queda deshabilitada.",
    )
    p.add_argument("--json", default=None, help="además, escribe el informe como JSON aquí.")
    return p


def _dsn(valor: str | None) -> str:
    crudo = valor or os.environ.get("DATABASE_URL", "")
    if not crudo:
        raise SystemExit("falta el DSN: pasa --dsn o exporta DATABASE_URL")
    return crudo.replace("postgresql+psycopg://", "postgresql://")


def main(argv: list[str] | None = None) -> int:
    """``0`` corrida limpia · ``1`` con huérfanos o fallidos · ``2`` no llegó a correr.

    Los tres códigos son distintos a propósito. Un ``1`` dice "el job funcionó y hay
    objetos que no quedaron como debían"; un ``2``, "el job no se fio de la base y no
    empezó". Colapsarlos haría que el cron tratara igual una imagen que sobrevivió y
    una guarda desarmada.
    """
    args = build_parser().parse_args(argv)
    plazos = {t.key: args.days for t in PLAN_DE_VIDEO} if args.days is not None else None
    ajustes = Settings()

    if args.apply and not ajustes.evidence_bucket:
        # Sin bucket, `delete_all_versions` hablaría con `Bucket=''`. Mejor no empezar
        # que descubrirlo objeto a objeto.
        print(
            "PODA ABORTADA · no hay bucket de evidencia configurado "
            "(TAKAB_API_EVIDENCE_BUCKET). Sin él no se puede destruir un objeto.",
            file=sys.stderr,
        )
        return 2

    arranque = datetime.now(UTC)
    with psycopg.connect(_dsn(args.dsn), autocommit=False) as conn:
        try:
            informe = run(conn, settings=ajustes, apply=args.apply, role=args.role, days=plazos)
            conn.commit()
        except (RetentionUnsafe, psycopg.Error) as exc:
            conn.rollback()
            print(f"PODA ABORTADA · {exc}", file=sys.stderr)
            return 2

    print(render(informe))
    print(f"  (arrancó {arranque.isoformat(timespec='seconds')})")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(_informe_json(informe), fh, indent=2, ensure_ascii=False)
    return 0 if informe.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
