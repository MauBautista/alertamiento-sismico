"""GET /incidents/{id}/shakemap — el mini-ShakeMap del evento (T-7.24).

Lectura pura, sin acción nueva en la matriz: quien ve el incidente ve el mapa de
cómo sacudió en su red. La RLS ya decidió qué incidentes existen para este
request, y **404 —no 403— cuando no es visible**, porque un 403 confirmaría que
existe.

⚠️ **Un incidente sin snapshot NO es un 404.** Devuelve 200 con
`estado: "pendiente"`: el mapa no es en vivo —se calcula por evento, en el worker,
cuando hay con qué calcularlo (`§A.4`)— así que «todavía no» es una condición
normal del sistema y tiene que declararse (regla de oro 7). Un 404 ahí haría que
la consola pintara «no existe» sobre un incidente que existe, y un 500 la pondría
en rojo por algo que se resuelve solo en la vuelta siguiente del bucle.

El endpoint **no calcula nada**. Si lo hiciera, dos operadores verían mapas
distintos del mismo sismo según cuándo apretaran F5.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.auth.deps import require_web_surface
from takab_api.routers._common import http_error, read_session
from takab_api.schemas.shakemap import ShakemapOut
from takab_api.shakemap.lectura import leer

router = APIRouter(dependencies=[Depends(require_web_surface)])


@router.get("/incidents/{incident_id}/shakemap", response_model=ShakemapOut)
async def incident_shakemap(
    incident_id: UUID,
    conn: AsyncConnection = Depends(read_session),
) -> ShakemapOut:
    """Las tres capas del mapa de la sacudida, o `pendiente` si aún no se calculó."""
    data = await leer(conn, str(incident_id))
    if data is None:
        raise http_error(404, "incidente no encontrado")
    return data
