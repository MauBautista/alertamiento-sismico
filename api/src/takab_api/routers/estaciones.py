"""GET /incidents/{id}/estaciones — cómo lo detectó cada estación (T-7.17).

Lectura pura, sin acción nueva en la matriz: quien ve el incidente ve cómo lo
detectó su red. La RLS ya decidió qué incidentes existen para este request, y
404 —no 403— cuando no es visible, porque un 403 confirmaría que existe.

A diferencia de `/reproduccion`, esta tabla existe para **cualquier** incidente:
lo medido siempre hay, y lo esperado aparece en cuanto el evento tiene epicentro
—lo localice la correlación o lo vista una reproducción—. Un incidente sin
epicentro devuelve la tabla con las columnas teóricas en `null`, que es la
respuesta honesta: se midió esto, y no hay contra qué compararlo.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.auth.deps import require_web_surface
from takab_api.estaciones import build_estaciones
from takab_api.routers._common import http_error, read_session
from takab_api.schemas.estaciones import EstacionesOut

router = APIRouter(dependencies=[Depends(require_web_surface)])


@router.get("/incidents/{incident_id}/estaciones", response_model=EstacionesOut)
async def incident_estaciones(
    incident_id: UUID,
    conn: AsyncConnection = Depends(read_session),
) -> EstacionesOut:
    """Lo medido y lo esperado por estación, en orden de arribo."""
    data = await build_estaciones(conn, str(incident_id))
    if data is None:
        raise http_error(404, "incidente no encontrado")
    return data
