"""Modo demostración — encender, apagar y consultar (T-5.02 · D-27).

**Qué suprime:** las salidas de la NUBE — entregas por cualquier canal y comandos
de actuador firmados. Las dos puertas viven en sus embudos
(``notify/orchestrator`` y ``commands/service``), no aquí: este router solo mueve
el estado.

**Qué no puede tocar:** el gabinete. Este modo no viaja por la config firmada, no
llega al reflejo SASMEX→sirena y no puede desarmar un relé (regla de oro 1).

**Quién.** Asimétrico a propósito —difícil de volver inseguro, fácil de volver
seguro—: lo enciende ``takab_superadmin`` porque la demostración es acto de
plataforma; lo apaga él **o el administrador del cliente**, porque si TAKAB se lo
deja puesto el cliente no puede quedarse esperando a que alguien conteste el
teléfono para recuperar sus avisos.

**Y lo real lo apaga solo.** El primer incidente que entre lo desarma antes de
planificar un solo aviso (``notify/orchestrator``), así que este router no es la
única forma de salir del modo — es la forma *voluntaria*.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api import demo_mode as dm
from takab_api.auth.claims import Claims
from takab_api.auth.deps import get_claims, get_session, require_roles, require_web_surface
from takab_api.auth.matrix import roles_with_action
from takab_api.routers._common import http_error
from takab_api.schemas.demo_mode import DemoModeIn, DemoModeOut

router = APIRouter(dependencies=[Depends(require_web_surface)])

_require_on = require_roles(*roles_with_action("demo_mode_on"))
_require_off = require_roles(*roles_with_action("demo_mode_off"))

_PATH = "/demo-mode"


def _out(tenant_id: str, ventana: dm.Ventana | None) -> DemoModeOut:
    if ventana is None:
        return DemoModeOut(active=False, tenant_id=tenant_id)
    return DemoModeOut(
        active=True,
        tenant_id=ventana.tenant_id,
        enabled_by=ventana.enabled_by,
        enabled_at=ventana.enabled_at,
        expires_at=ventana.expires_at,
        remaining_s=ventana.restante_s,
        note=ventana.note,
    )


@router.get(_PATH, response_model=DemoModeOut)
async def get_demo_mode(
    claims: Claims = Depends(get_claims),
    conn: AsyncConnection = Depends(get_session),
) -> DemoModeOut:
    """El estado del cliente de quien pregunta. Sin acción: no hay secreto.

    Lo consultan las superficies para poder declararlo, y quien no puede
    encenderlo tiene el mismo derecho a saber que está encendido — más, de hecho:
    es quien se va a preguntar por qué no le llegó un aviso.
    """
    return _out(claims.tenant_id, await dm.ventana_viva(conn, claims.tenant_id))


@router.post(_PATH, response_model=DemoModeOut, status_code=201)
async def encender_demo_mode(
    body: DemoModeIn,
    claims: Claims = Depends(_require_on),
    conn: AsyncConnection = Depends(get_session),
) -> DemoModeOut:
    """Enciende la ventana. Re-encender la PISA en vez de sumarse.

    Dos ventanas del mismo cliente serían dos verdades sobre cuándo se apaga.
    """
    try:
        ventana = await dm.encender(
            conn,
            tenant_id=claims.tenant_id,
            actor=claims.sub,
            segundos=body.duration_s,
            note=body.note,
            now=datetime.now(tz=UTC),
        )
    except dm.IncidenteAbierto:
        # La otra mitad de «lo real gana»: con un incidente vivo no se entra al
        # modo. Si se permitiera, el operador creería que está demostrando
        # mientras la cascada de algo REAL sigue en vuelo.
        raise http_error(
            409,
            "hay un incidente abierto: no se entra en modo demostración con un evento vivo",
        ) from None
    return _out(claims.tenant_id, ventana)


@router.delete(_PATH, response_model=DemoModeOut)
async def apagar_demo_mode(
    claims: Claims = Depends(_require_off),
    conn: AsyncConnection = Depends(get_session),
) -> DemoModeOut:
    """Apaga la ventana. Idempotente: apagar lo ya apagado devuelve 200.

    Devolver 404 aquí sería castigar al que hace lo seguro. El estado final es el
    mismo y es el que interesa: este cliente vuelve a recibir sus avisos.
    """
    await dm.apagar(conn, tenant_id=claims.tenant_id, actor=claims.sub)
    return _out(claims.tenant_id, None)
