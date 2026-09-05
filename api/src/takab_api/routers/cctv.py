"""CCTV de un incidente: métricas, capturas y descarga del clip (T-3.12.c).

DOS ENDPOINTS Y DOS PERMISOS, PORQUE NO SON EL MISMO ACTO
─────────────────────────────────────────────────────────
Leer que la gente tardó 50 s en salir no es lo mismo que descargar once minutos de vídeo de
personas identificables. `B.4` del blueprint lo pide con esas palabras —«acceso por rol, y
más estrecho que el resto: ver vídeo NO es ver telemetría»— y aquí eso son `cctv_read` y
`cctv_video`.

**Cada descarga deja fila en `audit_log`**, igual que un comando de actuador (`D-14`). No
es simetría con `exports.py`: es que el vídeo, a diferencia del miniSEED, son personas.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims
from takab_api.auth.deps import get_session, require_roles, require_web_surface
from takab_api.auth.matrix import roles_with_action
from takab_api.cctv import build_cctv
from takab_api.queries import cctv as q
from takab_api.routers._common import http_error, read_session
from takab_api.routers._s3 import PRESIGN_TTL_S, presign_get
from takab_api.schemas.cctv import CctvOut
from takab_api.schemas.exports import PresignedDownload
from takab_api.settings import Settings

#: Derivados de la matriz, NUNCA una tupla literal: una lista a mano aquí y otra allá
#: acaban discrepando, y la que gobierna sería la que el router mira.
LECTURA_ROLES = tuple(sorted(roles_with_action("cctv_read")))
VIDEO_ROLES = tuple(sorted(roles_with_action("cctv_video")))
_require_lectura = require_roles(*LECTURA_ROLES)
_require_video = require_roles(*VIDEO_ROLES)

router = APIRouter(dependencies=[Depends(require_web_surface)])


@router.get(
    "/incidents/{incident_id}/cctv",
    response_model=CctvOut,
    dependencies=[Depends(_require_lectura)],
)
async def incident_cctv(
    incident_id: UUID,
    conn: AsyncConnection = Depends(read_session),
) -> CctvOut:
    """Métricas de evacuación, las cuatro capturas y el inventario de clips.

    Sirve el MISMO objeto que consume el PDF: dos rutas distintas para los mismos hechos
    acabarían discrepando, y un reporte que no coincide con lo que el operador vio en
    pantalla es peor que ninguno.

    404 y no 403 cuando el incidente no es visible: un 403 confirmaría que existe.
    """
    datos = await build_cctv(conn, incident_id)
    if datos is None:
        raise http_error(404, "incidente no encontrado")
    return datos


@router.post(
    "/cctv/clips/{clip_id}/download",
    response_model=PresignedDownload,
)
async def download_clip(
    clip_id: UUID,
    claims: Claims = Depends(_require_video),
    conn: AsyncConnection = Depends(get_session),
) -> PresignedDownload:
    """URL pre-firmada del clip, 300 s, **con su huella en `audit_log`**."""
    fila = (await conn.execute(q.CLIP, {"clip_id": clip_id})).mappings().first()
    if fila is None:
        raise http_error(404, "clip no encontrado")
    if not fila["s3_key"]:
        # 410 y no 404, y la diferencia importa: el clip EXISTIÓ y su huella sigue en el
        # reporte. Un 404 diría «nunca hubo nada», que es falso y borra la cadena de
        # custodia; un 410 dice «lo hubo y la retención lo podó», que es lo que pasó.
        raise http_error(
            410,
            "el objeto fue podado por la política de retención de vídeo; "
            "su sha256 y sus horas siguen en el reporte",
        )

    # El bucket se comprueba AQUÍ y no arriba: un clip podado es 410 haya o no S3
    # configurado, porque no hay nada que firmar. Comprobarlo antes convertía «la
    # retención se lo llevó» en «el servicio no está disponible», que manda a mirar
    # la infraestructura en vez de leer la política.
    settings = Settings()
    if not settings.evidence_bucket:
        raise http_error(503, "bucket de evidencia no configurado")
    url = presign_get(settings, fila["s3_key"])
    await audit_async(
        conn,
        tenant_id=fila["tenant_id"],
        actor=f"user:{claims.sub}",
        verb="cctv_download",
        obj=f"cctv_clip:{clip_id}",
        meta={"sha256": fila["sha256"]},
    )
    return PresignedDownload(url=url, expires_in=PRESIGN_TTL_S)
