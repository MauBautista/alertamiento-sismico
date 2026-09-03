"""GET /incidents/{id}/notifications — quién recibió la alerta (T-5.15).

La tabla donde vive el destinatario y la confirmación de entrega existía desde la
`0040` y **no la leía ningún router**: era una pregunta contestable en la base y
no por la API ni por ninguna pantalla. Esto es esa lectura.

Aislamiento: la RLS de ``notification_jobs`` ya acota por tenant (o gobierno con
visibilidad), pero la comprobación de existencia se hace ANTES, sobre el
incidente, para que el vecino reciba un 404 y no una lista vacía — una lista
vacía confirmaría que el incidente existe.

Los datos de contacto NO salen en crudo: ``notify/destino.py`` los reduce al
mínimo dato con una allowlist por forma, y de un webhook sale el host sin la
ruta, porque esa ruta es la credencial.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.auth.deps import require_roles
from takab_api.notify.destino import resumen_destino
from takab_api.routers._common import http_error, read_session
from takab_api.routers.incidents import CONSOLE_ROLES
from takab_api.schemas.notify_chain import NotificationJobOut, NotifyChainOut, RecipientOut

# Mismo círculo que el detalle del incidente: quien puede leer el incidente puede
# leer su cadena. Los datos de contacto van enmascarados, así que esto no abre
# una superficie de PII nueva — la abriría devolver `target` en crudo.
_require_console = require_roles(*CONSOLE_ROLES)

router = APIRouter(dependencies=[Depends(_require_console)])

#: Las latencias se calculan EN SQL, con el reloj de la base y en la misma
#: consulta que trae las columnas: restarlas en Python invitaría a que un
#: `datetime` naive y otro con zona produjeran un número plausible y falso.
#: `NULL` se propaga solo — `sent_at - opened_at` es NULL si no se envió —, que
#: es justo la semántica que hace falta: quien no recibió no tiene latencia.
_SQL = text(
    """
    SELECT j.job_id, j.channel, j.mode, j.position, j.status, j.target,
           j.created_at, j.due_at, j.deadline_at, j.sent_at, j.delivered_at,
           j.last_status, j.last_status_at, j.attempts, j.error, j.action_id,
           EXTRACT(EPOCH FROM (j.sent_at - :opened))          AS dispatch_latency_s,
           EXTRACT(EPOCH FROM (j.delivered_at - j.sent_at))   AS delivery_latency_s,
           -- `COALESCE(sent_at, now())` y no `sent_at` a secas: EL SLA NO SE
           -- CUMPLE POR NO INTENTARLO. Comparando solo contra `sent_at`, el job
           -- encolado hace media hora con plazo de 60 s y sin enviar salía
           -- `NULL` — sin aviso —, y era justo el incumplimiento más grave. El
           -- `NULL` queda para lo único que lo merece: el canal SIN plazo.
           CASE WHEN j.deadline_at IS NULL THEN NULL
                ELSE COALESCE(j.sent_at, now()) <= j.deadline_at END AS deadline_met
      FROM notification_jobs j
     WHERE j.incident_id = :incident
     ORDER BY j.mode, j.position, j.created_at, j.job_id
    """
)


@router.get("/incidents/{incident_id}/notifications", response_model=NotifyChainOut)
async def incident_notifications(
    incident_id: UUID,
    conn: AsyncConnection = Depends(read_session),
) -> NotifyChainOut:
    """Los envíos de un incidente. 404 si el incidente no es visible."""
    inc = (
        await conn.execute(
            text("SELECT incident_id, opened_at FROM incidents WHERE incident_id = :i"),
            {"i": str(incident_id)},
        )
    ).first()
    if inc is None:
        raise http_error(404, "incidente no encontrado")

    rows = (
        await conn.execute(_SQL, {"incident": str(incident_id), "opened": inc.opened_at})
    ).mappings()

    items: list[NotificationJobOut] = []
    for r in rows:
        d = resumen_destino(r["channel"], r["target"])
        items.append(
            NotificationJobOut(
                **{k: r[k] for k in ("job_id", "channel", "mode", "position", "status")},
                **{
                    k: r[k]
                    for k in (
                        "created_at",
                        "due_at",
                        "deadline_at",
                        "sent_at",
                        "delivered_at",
                        "last_status",
                        "last_status_at",
                        "attempts",
                        "error",
                        "action_id",
                        "deadline_met",
                    )
                },
                # NO se deriva de `status`: `delivered_at` es la única columna que
                # afirma que alguien lo tuvo en la mano.
                delivered=r["delivered_at"] is not None,
                dispatch_latency_s=(
                    float(r["dispatch_latency_s"]) if r["dispatch_latency_s"] is not None else None
                ),
                delivery_latency_s=(
                    float(r["delivery_latency_s"]) if r["delivery_latency_s"] is not None else None
                ),
                recipient=RecipientOut(
                    kind=d.kind, count=d.count, hint=d.hint, unrecognised=d.unrecognised
                ),
            )
        )

    return NotifyChainOut(
        incident_id=incident_id,
        opened_at=inc.opened_at,
        items=items,
        delivered_count=sum(1 for j in items if j.delivered),
    )
