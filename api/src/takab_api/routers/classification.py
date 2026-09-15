"""Clasificar un incidente y leer la tasa de falsos positivos (T-5.12).

**Los simulacros no entran, y no hace falta filtrarlos:** un simulacro JAMÁS crea
incidente (`test_un_drill_jamas_crea_incidentes`), así que la tabla de la que sale
esta tasa no los contiene. Se dice aquí porque es la primera pregunta que hace
quien lee el número.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims
from takab_api.auth.deps import get_session, require_roles, require_web_surface
from takab_api.auth.matrix import roles_with_action
from takab_api.incident.classification import CLASIFICACIONES, EN_LA_TASA, TERMINALES
from takab_api.routers._common import http_error
from takab_api.schemas.classification import (
    ClassificationChainOut,
    ClassificationIn,
    ClassificationOut,
    ClassificationStatsOut,
)

router = APIRouter(dependencies=[Depends(require_web_surface)])

_require_classify = require_roles(*roles_with_action("classify_incident"))

#: Ventana por defecto de la tasa. 90 días es un trimestre: el periodo en que un
#: cliente decide si el sistema le molesta o le sirve.
_VENTANA_DEFECTO_D = 90

_INCIDENTE_VISIBLE = text("SELECT tenant_id, state FROM incidents WHERE incident_id = :i")

#: [T-7.13 · D-33] El cierre por clasificación. Guardado con `state <> 'closed'`
#: en el propio UPDATE: `closed` es terminal, y clasificar otra vez un incidente
#: ya cerrado —corregir es clasificar otra vez— no puede escribir un segundo
#: cierre ni reventar contra la máquina de estados.
_CERRAR = text(
    "UPDATE incidents SET state = 'closed', closed_at = now()"
    " WHERE incident_id = :i AND state <> 'closed'"
)

_ACCION_CIERRE = text(
    "INSERT INTO incident_actions (incident_id, tenant_id, kind, actor, payload)"
    " VALUES (:i, :t, 'close', :actor, :payload)"
)

_CADENA = text("""
SELECT classification_id, incident_id, classification, note, classified_by,
       classified_at, supersedes_id
FROM incident_classifications
WHERE incident_id = :i
ORDER BY classified_at DESC, classification_id DESC
""")

_INSERT = text("""
INSERT INTO incident_classifications
  (tenant_id, incident_id, classification, note, classified_by, supersedes_id)
VALUES (:t, :i, :c, :n, :by, :sup)
RETURNING classification_id, incident_id, classification, note, classified_by,
          classified_at, supersedes_id
""")

# La tasa: incidentes de la ventana y su clasificación VIGENTE (la que nadie
# sustituye). El LEFT JOIN es lo que mantiene visibles a los sin clasificar —
# un INNER los borraría del denominador y el número quedaría precioso y falso.
_STATS = text("""
SELECT i.incident_id,
       (SELECT c.classification
          FROM incident_classifications c
         WHERE c.incident_id = i.incident_id
           AND NOT EXISTS (SELECT 1 FROM incident_classifications s
                            WHERE s.supersedes_id = c.classification_id)
         ORDER BY c.classified_at DESC, c.classification_id DESC
         LIMIT 1) AS vigente
FROM incidents i
WHERE i.opened_at >= :desde AND i.opened_at < :hasta
""")


def _out(row, vigentes: set[UUID]) -> ClassificationOut:
    return ClassificationOut(
        classification_id=row.classification_id,
        incident_id=row.incident_id,
        classification=row.classification,
        note=row.note,
        classified_by=row.classified_by,
        classified_at=row.classified_at,
        supersedes_id=row.supersedes_id,
        current=row.classification_id in vigentes,
    )


def _vigentes(filas) -> set[UUID]:
    """Las que nadie sustituye. Derivado de la cadena, no guardado."""
    sustituidas = {f.supersedes_id for f in filas if f.supersedes_id is not None}
    return {f.classification_id for f in filas if f.classification_id not in sustituidas}


async def _tenant_del_incidente(conn: AsyncConnection, incident_id: UUID) -> tuple[str, str]:
    """Devuelve ``(tenant_id, state)`` del incidente visible."""
    row = (await conn.execute(_INCIDENTE_VISIBLE, {"i": str(incident_id)})).first()
    if row is None:
        # 404 y no 403: «no existe» y «no es tuyo» se contestan igual, que es lo
        # que impide usar esta ruta para saber si un incidente ajeno existe.
        raise http_error(404, "incidente no encontrado")
    return str(row.tenant_id), row.state


@router.get("/incidents/{incident_id}/classifications", response_model=ClassificationChainOut)
async def get_classifications(
    incident_id: UUID,
    conn: AsyncConnection = Depends(get_session),
) -> ClassificationChainOut:
    """La cadena entera, más reciente primero. Vacía = **sin clasificar**."""
    await _tenant_del_incidente(conn, incident_id)
    filas = (await conn.execute(_CADENA, {"i": str(incident_id)})).all()
    vig = _vigentes(filas)
    return ClassificationChainOut(incident_id=incident_id, items=[_out(f, vig) for f in filas])


@router.post(
    "/incidents/{incident_id}/classification",
    response_model=ClassificationOut,
    status_code=201,
)
async def classify_incident(
    incident_id: UUID,
    body: ClassificationIn,
    claims: Claims = Depends(_require_classify),
    conn: AsyncConnection = Depends(get_session),
) -> ClassificationOut:
    """Clasifica. Corregir es clasificar otra vez declarando a cuál sustituye.

    No hay `PUT` ni `DELETE`, y la base tampoco los permitiría: la tabla es
    append-only con sus dos capas. Quien clasificó mal a las 3 de la mañana no
    puede hacer desaparecer su clasificación — la corrige, y las dos quedan.

    **[T-7.13 · D-33] Una clasificación TERMINAL cierra el incidente aquí mismo.**
    Hasta esa ficha esto era inerte: se escribía la fila y el banner seguía puesto
    hasta que alguien mirara. El worker hace lo mismo en su pasada —esto no lo
    sustituye, lo adelanta—, pero la vía normal de cierre tiene que notarse en el
    acto o el operador vuelve a pulsar. La consola se entera por el NOTIFY que
    dispara el propio UPDATE de `incidents`; no hace falta decírselo.
    """
    tenant, estado = await _tenant_del_incidente(conn, incident_id)

    if body.supersedes_id is not None:
        previa = (
            await conn.execute(
                text(
                    "SELECT 1 FROM incident_classifications"
                    " WHERE classification_id = :c AND incident_id = :i"
                ),
                {"c": str(body.supersedes_id), "i": str(incident_id)},
            )
        ).first()
        if previa is None:
            # Sustituir una clasificación de OTRO incidente rompería la cadena de
            # los dos. Se rechaza en vez de ignorar el campo.
            raise http_error(409, "la clasificación que se sustituye no es de este incidente")

    row = (
        await conn.execute(
            _INSERT,
            {
                "t": tenant,
                "i": str(incident_id),
                "c": body.classification,
                "n": body.note,
                "by": claims.sub,
                "sup": str(body.supersedes_id) if body.supersedes_id else None,
            },
        )
    ).one()

    await audit_async(
        conn,
        tenant_id=tenant,
        actor=claims.sub,
        verb="incident_classified",
        obj=f"incident:{incident_id}",
        meta={
            "classification": body.classification,
            "supersedes_id": str(body.supersedes_id) if body.supersedes_id else None,
        },
    )
    if body.classification in TERMINALES:
        await _cerrar_por_clasificacion(
            conn, incident_id, tenant=tenant, desde=estado, valor=body.classification, claims=claims
        )
    return _out(row, {row.classification_id})


async def _cerrar_por_clasificacion(
    conn: AsyncConnection,
    incident_id: UUID,
    *,
    tenant: str,
    desde: str,
    valor: str,
    claims: Claims,
) -> None:
    """Cierra y deja la traza con la CAUSA y con quién la decidió.

    El actor es `user:<sub>` y **no** `system:incident`: el cierre por decisión de
    una persona y el cierre por vencimiento son dos hechos distintos en el
    timeline, y escribirlos igual borra la única traza de que alguien decidió.
    """
    cur = await conn.execute(_CERRAR, {"i": str(incident_id)})
    if cur.rowcount == 0:
        return  # ya estaba cerrado: corregir la clasificación no lo cierra dos veces
    actor = f"user:{claims.sub}"
    detalle = {"from": desde, "to": "closed", "reason": "classification", "classification": valor}
    await conn.execute(
        _ACCION_CIERRE,
        {"i": str(incident_id), "t": tenant, "actor": actor, "payload": json.dumps(detalle)},
    )
    await audit_async(
        conn,
        tenant_id=tenant,
        actor=actor,
        verb="close",
        obj=f"incident:{incident_id}",
        meta=detalle,
    )


@router.get("/classification-stats", response_model=ClassificationStatsOut)
async def classification_stats(
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    conn: AsyncConnection = Depends(get_session),
) -> ClassificationStatsOut:
    """La tasa de falsos positivos del cliente de quien pregunta.

    El aislamiento lo impone la RLS sobre ``incidents``: aquí no hay filtro por
    tenant y no debe haberlo — un filtro de aplicación encima de la RLS invita a
    creer que la RLS es opcional.

    **Los sin clasificar salen aparte y no del denominador.** Un porcentaje
    calculado sobre lo clasificado, con lo no clasificado escondido, es peor que
    no tener el número: se lee como una medición y es una muestra sesgada por
    quién tuvo tiempo de revisar.
    """
    hasta = until or datetime.now(tz=UTC)
    desde = since or (hasta - timedelta(days=_VENTANA_DEFECTO_D))
    if desde >= hasta:
        raise http_error(400, "la ventana empieza después de terminar")

    filas = (await conn.execute(_STATS, {"desde": desde, "hasta": hasta})).all()
    por: dict[str, int] = dict.fromkeys(CLASIFICACIONES, 0)
    sin = 0
    for f in filas:
        if f.vigente is None:
            sin += 1
        else:
            por[f.vigente] = por.get(f.vigente, 0) + 1

    base = sum(n for c, n in por.items() if c in EN_LA_TASA)
    return ClassificationStatsOut(
        since=desde,
        until=hasta,
        total=len(filas),
        unclassified=sin,
        by_classification=por,
        # `None` y no 0: un cero afirmaría que no hubo falsos positivos, y lo que
        # ocurre es que nadie miró.
        false_positive_rate=(por.get("falso_positivo", 0) / base) if base else None,
    )
