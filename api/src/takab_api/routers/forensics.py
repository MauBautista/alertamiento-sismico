"""GET /incidents/{id}/forensics — los hechos medidos del incidente (T-2.40).

Lectura pura: sin acción nueva en la matriz. Quien puede ver el incidente puede ver
sus mediciones — la RLS ya decide qué incidentes existen para cada request, y negar
las mediciones a quien ya ve el incidente no protegería nada.

404 y no 403 cuando el incidente no es visible: un 403 confirmaría que existe.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.auth.deps import require_web_surface
from takab_api.forensics import build_forensics
from takab_api.routers._common import http_error, read_session
from takab_api.schemas.forensics import ForensicsOut

router = APIRouter(dependencies=[Depends(require_web_surface)])


@router.get("/incidents/{incident_id}/forensics", response_model=ForensicsOut)
async def incident_forensics(
    incident_id: UUID,
    conn: AsyncConnection = Depends(read_session),
) -> ForensicsOut:
    """Picos por canal, tiempo de aviso, quórum, catálogo y calibración.

    Alimenta la pantalla y el dictamen PDF con los MISMOS números: dos rutas
    distintas para los mismos hechos acabarían discrepando, y un dictamen que no
    coincide con lo que el operador vio en pantalla es peor que ninguno.
    """
    data = await build_forensics(conn, str(incident_id))
    if data is None:
        raise http_error(404, "incidente no encontrado")
    return data
