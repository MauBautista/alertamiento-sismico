"""Contrato del webhook público de estado de entrega (T-2.77.b).

Deliberadamente **CIEGO**, y no por pereza: es la respuesta de una superficie sin
autenticación de sesión, y todo lo que diga de más es un oráculo. No lleva el
job, ni si el estado se aplicó, ni cuántos hechos se casaron — quien llama es un
proveedor que solo necesita saber que dejamos de deberle un reintento. Lo que
pasó de verdad va al log del servidor, donde lo lee quien opera y no quien
llama.

Del cuerpo que MANDAN los proveedores no hay modelo Pydantic a propósito. Meta
manda por el mismo webhook cosas que no son desenlaces nuestros (mensajes
entrantes, cambios de cuenta) y un modelo estricto contestaría 422 a un cuerpo
perfectamente legítimo; se parsea a mano y con tolerancia en
``notify/callbacks.py``, que además es donde se puede probar sin HTTP delante.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class NotifyWebhookAck(BaseModel):
    """«Recibido y no me debes un reintento». Nada más.

    Es la MISMA respuesta para un callback que movió el desenlace de un job y
    para uno que no cambió nada (un reenvío, un estado que no pisa al escrito).
    Distinguirlos le diría a quien llama qué hay al otro lado.
    """

    status: Literal["accepted"] = Field(
        default="accepted",
        description="Acuse fijo. No dice si el desenlace cambió: eso vive en el log.",
    )
