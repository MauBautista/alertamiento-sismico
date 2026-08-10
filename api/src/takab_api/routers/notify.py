"""[T-2.75.a] ``GET /notify/channels`` — a quién le pregunta la consola.

T-2.75 dejó de mentir en el dato (`simulated` nunca es `sent`) y lo grita al
arrancar el worker. Pero esa verdad **moría en el log**: la consola rotulaba
«SIMULADO en el MVP» como texto estático, de modo que el día que T-2.76.a /
T-2.77.a carguen credenciales el canal sería real y el rótulo seguiría diciendo
que no sirve. Regla de oro 7 al revés.

Tres decisiones que este router deja escritas:

1. **El dato se DERIVA del registro.** ``channel_reality(build_providers(...))``
   — la misma función que arranca el worker. Aquí no hay ninguna lista de
   canales: el sexto que alguien enchufe aparece solo.
2. **Se congela al arrancar** (``app.state.notify_channels``, en ``create_app``)
   porque la realidad de un canal es configuración del PROCESO: cambia con un
   despliegue, no entre dos peticiones. Construirlo por request además cargaría
   el catálogo de plantillas de WhatsApp en cada llamada.
3. **La frontera es una acción de la matriz, no una lista de roles.**
   ``edit_thresholds`` es exactamente la que gatea ``PUT /rule-sets``, que es
   donde se configura esta cascada: quien puede elegir el canal tiene que poder
   saber si ese canal entrega. Quien no la tiene ve ``S/D`` en la consola, que
   es la lectura honesta — nunca «real».

No toca la base de datos ni el tenant: es la misma respuesta para todos, porque
los providers son del despliegue, no del cliente.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from takab_api.auth.deps import require_roles
from takab_api.auth.matrix import roles_with_action
from takab_api.notify.plan import CASCADE_ORDER
from takab_api.schemas.notify import NotifyChannelOut, NotifyChannelsOut

# Roles que administran la cascada (RBAC §2 vía la matriz de acciones). Ni un
# rol enumerado a mano: esa deuda tiene ficha propia (T-2.79.e).
CHANNEL_ROLES: tuple[str, ...] = roles_with_action("edit_thresholds")

_require_channels = require_roles(*CHANNEL_ROLES)

router = APIRouter()


def _ordered(reality: dict[str, bool]) -> list[NotifyChannelOut]:
    """Cascada primero (el orden en que se intenta avisar), resto alfabético.

    El orden no se hereda del ``dict`` del registro: eso ataría el contrato
    publicado al orden en que alguien escribió las líneas de
    ``build_providers``. Un canal fuera de la cascada (hoy ``push``) sale al
    final, y sale — no se filtra: filtrarlo lo dejaría en ``S/D`` para siempre.
    """

    def key(channel: str) -> tuple[int, str]:
        return (
            CASCADE_ORDER.index(channel) if channel in CASCADE_ORDER else len(CASCADE_ORDER),
            channel,
        )

    return [
        NotifyChannelOut(channel=channel, simulated=reality[channel])
        for channel in sorted(reality, key=key)
    ]


@router.get("/notify/channels", response_model=NotifyChannelsOut)
async def list_notify_channels(
    request: Request,
    _claims=Depends(_require_channels),
) -> NotifyChannelsOut:
    """Realidad de cada canal de notificación, según el registro de este proceso."""
    reality: dict[str, bool] = getattr(request.app.state, "notify_channels", {})
    return NotifyChannelsOut(channels=_ordered(reality))
