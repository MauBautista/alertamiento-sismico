"""Contrato de la realidad de los canales de notificación (T-2.75.a).

Deliberadamente MÍNIMO: canal y si entrega. El ``hint`` del provider —qué
variable de entorno falta— se queda en el log del servidor: dice quién es real,
no cómo se configura la infraestructura de TAKAB a un administrador de cliente.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class NotifyChannelOut(BaseModel):
    """Un canal del registro de providers y su realidad, tal como arrancó."""

    channel: str = Field(description="Clave del canal en el registro (webhook, sms, …).")
    simulated: bool = Field(
        description=(
            "true ⇒ este canal NO entrega nada: los jobs quedan 'simulated' y nadie "
            "recibe el aviso. Se deriva del provider (`is_simulated`), y quien no se "
            "declara real se cuenta como simulado."
        )
    )


class NotifyChannelsOut(BaseModel):
    """Registro completo. Un canal AUSENTE de esta lista no existe en el servidor;
    la consola lo pinta ``S/D`` — nunca «real» (regla de oro 7)."""

    channels: list[NotifyChannelOut]
