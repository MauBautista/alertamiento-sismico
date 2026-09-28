"""[T-9.42 · D-48] La pasada del worker `informes`: qué incidente toca informe, y generarlo.

QUIÉN TOCA INFORME
──────────────────
Un incidente toca informe si cumple TODO esto, y cada regla se REUTILIZA de donde
ya vive (una copia sería una segunda definición que diverge):

* se abrió dentro de `informe_ventana_s` (6 h): sin ventana, el primer despliegue
  le mandaría al cliente un correo por cada incidente del histórico;
* NO es sólo cautela: su severidad está en el escalón de DISPARO
  (`notify/circulo.SEVERIDADES_DE_DISPARO`) **o** autoriza evacuar
  (`incident/autoridad.autoriza_evacuacion`, la regla que lee la app);
* su clasificación vigente no es terminal (`incident/classification.TERMINALES`):
  una PRUEBA no le manda un correo al cliente;
* no tiene ya fila en `post_event_reports`.

CUÁNDO
──────
Gana lo que llegue PRIMERO y queda en `trigger`: la cabeza de la cadena firmada
(`firma`), el incidente cerrado (`cierre`) o `informe_plazo_s` desde la apertura
(`plazo`, que sale PRELIMINAR si nadie firmó; el PDF ya lo rotula). Si al mirar se
cumplen dos, gana el que ocurrió antes: la hora de la cabeza, `closed_at` o
`opened_at + plazo`.

La elegibilidad se filtra en PYTHON y el tope se aplica DESPUÉS: `autoriza_evacuacion`
es Python y su gemela SQL habla el dialecto de SQLAlchemy, no el de psycopg. Cortar
antes de filtrar dejaría que veinte cautelas taparan a un SASMEX (la lección de
`T-9.04`). La consulta no lleva `LIMIT`, y no hace falta: la ventana de 6 h la acota.

CÓMO, EN TRES TIEMPOS
─────────────────────
1. **Reclamar**, bajo `pg_try_advisory_xact_lock` y en UNA transacción: se insertan
   las filas nuevas (`ON CONFLICT (incident_id) DO NOTHING`, regla de oro 3) y se
   reclaman los reintentos —`fallido` con `attempts < 3` tras 300 s; `pendiente`
   tras 900 s, que es un worker que murió a medias— tocando su `updated_at`. Ese
   toque ES el reclamo: otra instancia no las verá como reintentables hasta que
   venza otra vez el plazo. COMMIT, y el cerrojo se suelta.
2. **Generar**, fuera del cerrojo (un PDF tarda; el cerrojo no puede durar eso), con
   `asyncio.run` y un engine efímero `NullPool` —el puente de
   `shakemap/servicio.py`—, porque `generar_informe` es async. Por fila, UNA
   transacción: PDF → S3 → evidencia → bitácora → `ok` → acción `post_event_report`.
3. **Si algo lanza**, en una transacción APARTE: `fallido`, `attempts + 1` y la causa
   recortada a 300. **Nunca `ok` sin evidencia**: el CHECK `per_ok_con_evidencia` lo
   garantiza también en la base.

⚠️ DENTRO DEL PUENTE, LAS DOS COSAS DE `shakemap/servicio.py`
─────────────────────────────────────────────────────────────
* `SET LOCAL ROLE takab_ingest`: en la nube el DSN ya es ése; en local es el
  superusuario, y sin esto los tests ejercerían privilegios que la nube no tiene.
* `set_config('app.tenant_id', <tenant del incidente>)`: el builder pregunta
  `current_setting('app.tenant_id')` para decidir si lee la clasificación, y la
  vista segura de features devuelve cero filas sin él. Derivarlo del incidente hace
  que el aislamiento sea por construcción.

SIN FRENO, Y POR QUÉ ES SEGURO
──────────────────────────────
`generar_informe` se llama sin el freno de exportación de `T-5.18`: la clave única
de `post_event_reports` acota a UN informe por incidente (más tres reintentos). Su
`export_pdf` sí cuenta en el techo del EDIFICIO, porque es una generación de verdad.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import psycopg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from takab_api.incident.autoridad import autoriza_evacuacion
from takab_api.incident.classification import TERMINALES
from takab_api.incident.lifecycle import CABEZA_SQL, CLASIFICACION_VIGENTE_SQL
from takab_api.notify.circulo import SEVERIDADES_DE_DISPARO
from takab_api.notify.orchestrator import _node_count
from takab_api.queries import reports as q_reports
from takab_api.routers.reports import InformeGenerado, generar_informe

if TYPE_CHECKING:
    from takab_api.settings import Settings

logger = logging.getLogger("takab_api.informes")

#: Clave del advisory lock de la pasada. De TRANSACCIÓN: sólo cubre el reclamo.
LOCK_KEY = 0x7A942

#: Tope de filas que una pasada RECLAMA (nuevas + reintentos). Lo que sobra entra en
#: la siguiente, y el corte se DECLARA.
MAX_POR_PASADA = 20

#: Reintentos: cuántos, y cada cuánto.
MAX_INTENTOS = 3
REINTENTO_FALLIDO_S = 300.0
#: Un `pendiente` más viejo que esto es un worker que murió entre reclamar y generar.
REINTENTO_PENDIENTE_S = 900.0

#: Quién firma lo que deja el worker, en la bitácora y en la acción.
ACTOR = "system:informes"
#: El `origen` que estampa en `export_pdf`: distingue el informe automático de una
#: exportación de consola y del certificado del móvil.
ORIGEN = "informe_automatico"

#: El `error` de una fila sin bucket: una causa de configuración, no una avería.
ERROR_SIN_BUCKET = "sin_bucket"
_ERROR_MAX = 300

CORTE_POR_TOPE = "tope"
CORTE_POR_CERROJO = "cerrojo"

#: `(conn, incidente, *, settings) -> InformeGenerado`. Inyectable para los tests.
Generador = Callable[..., Awaitable[InformeGenerado]]


class SinBucket(RuntimeError):
    """No hay `evidence_bucket`: no hay dónde dejar el PDF. Se dice, no revienta."""

    def __str__(self) -> str:
        return ERROR_SIN_BUCKET


@dataclass(frozen=True)
class PasadaInformes:
    """Lo que hizo una pasada. ``corte`` es lo que no se calla."""

    generados: tuple[str, ...] = ()
    fallidos: tuple[str, ...] = ()
    #: ``None`` = se reclamó TODO lo que tocaba. Si no, por qué no.
    corte: str | None = None

    @property
    def truncada(self) -> bool:
        return self.corte is not None


async def generar_por_defecto(
    conn: AsyncConnection, incident: Mapping[str, Any], *, settings: Settings
) -> InformeGenerado:
    """El generador de verdad: `generar_informe` con la variante del ajuste."""
    if not settings.evidence_bucket:
        raise SinBucket()
    return await generar_informe(
        conn,
        incident,
        variant=settings.informe_variante,
        actor=ACTOR,
        origen=ORIGEN,
        settings=settings,
    )


# ────────────────────────────────────────────────────────────── el SQL

#: Candidatos SIN fila todavía, con lo que hace falta para decidir en Python.
_CANDIDATOS_SQL = f"""
SELECT i.incident_id, i.tenant_id, i.opened_at, i.closed_at, i.state, i.severity,
       i.trigger, e.meta->>'node_count' AS node_count,
       {CLASIFICACION_VIGENTE_SQL} AS clasificacion,
       {CABEZA_SQL.format(col="signed_by")} AS cabeza_firmada_por,
       {CABEZA_SQL.format(col="created_at")} AS cabeza_creada
  FROM incidents i
  LEFT JOIN seismic_events e ON e.event_id = i.event_id
 WHERE i.opened_at >= %(desde)s
   AND i.opened_at <= %(ahora)s
   AND NOT EXISTS (SELECT 1 FROM post_event_reports r WHERE r.incident_id = i.incident_id)
 ORDER BY i.opened_at, i.incident_id
"""

_RECLAMA_NUEVA_SQL = """
INSERT INTO post_event_reports
       (tenant_id, incident_id, trigger, state, variant, created_at, updated_at)
VALUES (%(tenant)s, %(incident)s, %(trigger)s, 'pendiente', %(variant)s, %(ahora)s, %(ahora)s)
ON CONFLICT (incident_id) DO NOTHING
RETURNING report_id, incident_id, tenant_id, trigger
"""

#: El reclamo de reintentos ES el `updated_at`: tocarlo aparta la fila del plazo.
#: `FOR UPDATE SKIP LOCKED` por si dos instancias llegaran a la vez sin cerrojo.
_RECLAMA_REINTENTOS_SQL = """
UPDATE post_event_reports r SET updated_at = %(ahora)s
 WHERE r.report_id IN (
       SELECT report_id FROM post_event_reports
        WHERE (state = 'fallido' AND attempts < %(max_intentos)s
               AND updated_at < %(fallido_antes_de)s)
           OR (state = 'pendiente' AND updated_at < %(pendiente_antes_de)s)
        ORDER BY updated_at, report_id
        LIMIT %(lim)s
        FOR UPDATE SKIP LOCKED)
RETURNING r.report_id, r.incident_id, r.tenant_id, r.trigger
"""

_OK_SQL = text(
    "UPDATE post_event_reports SET state = 'ok', evidence_id = :evidence, "
    "preliminar = :preliminar, dictamen_vigente = CAST(:vigente AS uuid), "
    "variant = :variant, attempts = attempts + 1, error = NULL, updated_at = :ahora "
    "WHERE report_id = :report"
)

_ACCION_SQL = text(
    "INSERT INTO incident_actions (incident_id, tenant_id, ts, kind, actor, payload) "
    "VALUES (:incident, :tenant, :ahora, 'post_event_report', :actor, CAST(:payload AS jsonb))"
)

_FALLIDO_SQL = text(
    "UPDATE post_event_reports SET state = 'fallido', attempts = attempts + 1, "
    "error = :error, updated_at = :ahora WHERE report_id = :report"
)


# ────────────────────────────────────────────────────────────── la decisión, pura


def disparo(fila: Mapping[str, Any], settings: Settings, *, ahora: datetime) -> str | None:
    """El `trigger` que toca, o ``None`` si todavía no toca (o nunca)."""
    if fila["clasificacion"] in TERMINALES:
        return None
    dispara = fila["severity"] in SEVERIDADES_DE_DISPARO or autoriza_evacuacion(
        fila["trigger"], _node_count(fila["node_count"]), settings.quorum_min_nodes
    )
    if not dispara:
        return None
    llegados: list[tuple[datetime, int, str]] = []
    if fila["cabeza_firmada_por"] is not None:
        llegados.append((fila["cabeza_creada"], 0, "firma"))
    if fila["state"] == "closed":
        # Un cierre sin hora (`cierre_sin_hora`) cuenta como recién llegado.
        llegados.append((fila["closed_at"] or ahora, 1, "cierre"))
    plazo = fila["opened_at"] + timedelta(seconds=settings.informe_plazo_s)
    if plazo <= ahora:
        llegados.append((plazo, 2, "plazo"))
    return min(llegados)[2] if llegados else None


# ────────────────────────────────────────────────────────────── la pasada


def run_informes_pass(
    conn_factory: Callable[[], psycopg.Connection],
    settings: Settings,
    *,
    now: datetime | None = None,
    generar: Generador = generar_por_defecto,
    max_por_pasada: int = MAX_POR_PASADA,
) -> PasadaInformes:
    """Reclama, genera y deja la acción. Ver el encabezado del módulo."""
    ahora = now or datetime.now(tz=UTC)
    conn = conn_factory()
    try:
        reclamadas, corte = _reclama(conn, settings, ahora=ahora, maximo=max_por_pasada)
    finally:
        conn.close()
    if corte == CORTE_POR_CERROJO:
        return PasadaInformes(corte=corte)
    if not reclamadas:
        return PasadaInformes(corte=corte)

    # La acción y el `ok` llevan la hora de SU commit, no la del arranque de la pasada:
    # veinte PDF con narrativa pueden tardar minutos, y una acción fechada antes de
    # existir envejece dentro de la ventana del orquestador (`notify_lookback_s`) sin
    # que nadie la haya visto — el correo no saldría. Con `now` inyectado (tests), el
    # reloj queda fijo.
    reloj: Callable[[], datetime] = (lambda: now) if now is not None else _ahora_utc
    generados, fallidos = asyncio.run(_genera(settings, reclamadas, reloj=reloj, generar=generar))
    logger.info(
        "informes: %d generados, %d fallidos%s",
        len(generados),
        len(fallidos),
        "" if corte is None else f" (PASADA CORTADA POR {corte.upper()})",
    )
    return PasadaInformes(generados=tuple(generados), fallidos=tuple(fallidos), corte=corte)


def _reclama(
    conn: psycopg.Connection, settings: Settings, *, ahora: datetime, maximo: int
) -> tuple[list[dict], str | None]:
    tomado = conn.execute("SELECT pg_try_advisory_xact_lock(%s) AS tomado", (LOCK_KEY,)).fetchone()[
        "tomado"
    ]
    if not tomado:
        logger.info(
            "informes: la pasada no tomó el cerrojo (otra instancia la está corriendo); "
            "no se reclamó ningún informe en esta vuelta"
        )
        conn.rollback()
        return [], CORTE_POR_CERROJO
    try:
        filas = conn.execute(
            _CANDIDATOS_SQL,
            {"desde": ahora - timedelta(seconds=settings.informe_ventana_s), "ahora": ahora},
        ).fetchall()
        tocan = [(f, t) for f in filas if (t := disparo(f, settings, ahora=ahora)) is not None]
        corte = CORTE_POR_TOPE if len(tocan) > maximo else None

        reclamadas: list[dict] = []
        for fila, trigger in tocan[:maximo]:
            nueva = conn.execute(
                _RECLAMA_NUEVA_SQL,
                {
                    "tenant": fila["tenant_id"],
                    "incident": fila["incident_id"],
                    "trigger": trigger,
                    "variant": settings.informe_variante,
                    "ahora": ahora,
                },
            ).fetchone()
            if nueva is not None:
                reclamadas.append(nueva)

        # Los reintentos llenan los huecos que dejaron las nuevas; se piden `+1`
        # para SABER si quedaba alguno fuera, no para reclamarlo.
        hueco = maximo - len(reclamadas)
        if hueco > 0:
            reintentos = conn.execute(
                _RECLAMA_REINTENTOS_SQL,
                {
                    "ahora": ahora,
                    "max_intentos": MAX_INTENTOS,
                    "fallido_antes_de": ahora - timedelta(seconds=REINTENTO_FALLIDO_S),
                    "pendiente_antes_de": ahora - timedelta(seconds=REINTENTO_PENDIENTE_S),
                    "lim": hueco,
                },
            ).fetchall()
            reclamadas.extend(reintentos)
        conn.commit()
        return reclamadas, corte
    except Exception:
        # El cerrojo es de transacción: el rollback lo suelta y no deja la conexión
        # abortada. Nada se pierde: el reclamo se repite en la vuelta siguiente.
        conn.rollback()
        raise


def _ahora_utc() -> datetime:
    return datetime.now(tz=UTC)


async def _genera(
    settings: Settings,
    reclamadas: list[dict],
    *,
    reloj: Callable[[], datetime],
    generar: Generador,
) -> tuple[list[str], list[str]]:
    motor = create_async_engine(settings.database_url, poolclass=NullPool)
    generados: list[str] = []
    fallidos: list[str] = []
    sin_bucket = 0
    try:
        async with motor.connect() as conn:
            for fila in reclamadas:
                incidente = str(fila["incident_id"])
                try:
                    await _genera_uno(conn, settings, fila, reloj=reloj, generar=generar)
                    generados.append(incidente)
                except Exception as exc:  # noqa: BLE001 - se registra y se reintenta
                    await conn.rollback()
                    if isinstance(exc, SinBucket):
                        sin_bucket += 1
                    else:
                        logger.exception("informes: falló el informe del incidente %s", incidente)
                    await _marca_fallido(conn, fila, exc, ahora=reloj())
                    fallidos.append(incidente)
    finally:
        await motor.dispose()
    if sin_bucket:
        # UNA vez por pasada, no una por fila: es configuración, no una avería.
        logger.warning(
            "informes: %d informe(s) sin generar porque no hay evidence_bucket configurado",
            sin_bucket,
        )
    return generados, fallidos


async def _contexto(conn: AsyncConnection, tenant_id: str) -> None:
    """El rol del worker y el tenant del incidente. Ver el encabezado."""
    await conn.execute(text('SET LOCAL ROLE "takab_ingest"'))
    await conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_id})


async def _genera_uno(
    conn: AsyncConnection,
    settings: Settings,
    fila: Mapping[str, Any],
    *,
    reloj: Callable[[], datetime],
    generar: Generador,
) -> None:
    tenant = str(fila["tenant_id"])
    async with conn.begin():
        await _contexto(conn, tenant)
        incidente = (
            (await conn.execute(q_reports.SELECT_INCIDENT, {"incident_id": fila["incident_id"]}))
            .mappings()
            .first()
        )
        if incidente is None:  # pragma: no cover - la FK de la fila lo impide
            raise LookupError(f"incidente {fila['incident_id']} desaparecido")
        informe = await generar(conn, incidente, settings=settings)
        ahora = reloj()
        await conn.execute(
            _OK_SQL,
            {
                "evidence": informe.evidence_id,
                "preliminar": informe.preliminar,
                "vigente": None
                if informe.dictamen_vigente is None
                else str(informe.dictamen_vigente),
                "variant": settings.informe_variante,
                "ahora": ahora,
                "report": fila["report_id"],
            },
        )
        await conn.execute(
            _ACCION_SQL,
            {
                "incident": fila["incident_id"],
                "tenant": tenant,
                "ahora": ahora,
                "actor": ACTOR,
                "payload": json.dumps(
                    {
                        "report_id": str(fila["report_id"]),
                        "evidence_id": str(informe.evidence_id),
                        "variant": settings.informe_variante,
                        "trigger": fila["trigger"],
                        "preliminar": informe.preliminar,
                    }
                ),
            },
        )


async def _marca_fallido(
    conn: AsyncConnection, fila: Mapping[str, Any], exc: Exception, *, ahora: datetime
) -> None:
    error = str(exc) if isinstance(exc, SinBucket) else f"{type(exc).__name__}: {exc}"
    async with conn.begin():
        await _contexto(conn, str(fila["tenant_id"]))
        await conn.execute(
            _FALLIDO_SQL, {"error": error[:_ERROR_MAX], "ahora": ahora, "report": fila["report_id"]}
        )
