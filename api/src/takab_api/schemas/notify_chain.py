"""La cadena de acuse de un incidente (T-5.15).

`notification_jobs` ya guardaba todo lo que hace falta para contestar *"¿quién
recibió la alerta?"* desde la `0040`, y **no lo leía ningún router**: era una
pregunta contestable en la base y no por la API.

Las dos latencias van SEPARADAS y con significados distintos:

* ``dispatch_latency_s`` — desde que se ABRIÓ el incidente hasta que el proveedor
  aceptó el mensaje. Mismo `t0` que usa el orquestador para su SLA, así que las
  dos cifras se pueden comparar.
* ``delivery_latency_s`` — desde que el proveedor lo aceptó hasta que confirmó la
  entrega. Es el tramo que **no depende de TAKAB** y por eso no se suma al otro:
  un SMS que Twilio tarda tres minutos en entregar no es una tardanza de la
  plataforma, y presentarlos sumados lo parecería.

Las dos son ``None`` cuando el hecho no ocurrió. **Nunca cero**: un cero se lee
«fue instantáneo», que es lo contrario de «no pasó».
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class RecipientOut(BaseModel):
    """Destinatario reducido al mínimo dato (ver ``notify/destino.py``)."""

    kind: str
    count: int | None
    hint: str
    #: `True` = la forma del destino no se reconoció y NO sale nada de ella. Se
    #: declara para que la pantalla lo escriba en vez de dejar un hueco, que se
    #: leería como «no había destinatario».
    unrecognised: bool


class NotificationJobOut(BaseModel):
    """Un envío de la cadena, con su desenlace y su destinatario enmascarado."""

    job_id: UUID
    channel: str
    mode: str
    position: int
    status: str
    #: Solo ``delivered_at IS NOT NULL``. `sent` significa «el proveedor lo
    #: aceptó» y `simulated` «no había proveedor»: ninguno de los dos afirma que
    #: un humano lo tenga en la mano, y colapsarlos aquí desharía la única
    #: distinción por la que la `0040` existe.
    delivered: bool
    created_at: datetime
    due_at: datetime
    deadline_at: datetime | None
    sent_at: datetime | None
    delivered_at: datetime | None
    last_status: str | None
    last_status_at: datetime | None
    attempts: int
    error: str | None
    #: `None` = no salió. Jamás cero.
    dispatch_latency_s: float | None
    #: `None` = el proveedor no confirmó la entrega. Jamás cero.
    delivery_latency_s: float | None
    #: `False` = incumplió su plazo. Se compara contra `sent_at` si salió y
    #: contra AHORA si no ha salido: **el SLA no se cumple por no intentarlo**, y
    #: el job encolado que ya venció es el incumplimiento más grave, no el más
    #: silencioso. `None` solo cuando el canal no tenía plazo que cumplir.
    deadline_met: bool | None
    recipient: RecipientOut
    #: Job disparado por una ACCIÓN (solicitud de dictamen), no por el incidente.
    action_id: UUID | None


class NotifyChainOut(BaseModel):
    """Los envíos de un incidente, en el orden en que se planificaron."""

    incident_id: UUID
    opened_at: datetime
    items: list[NotificationJobOut]
    #: Cuántos de `items` tienen entrega CONFIRMADA. Sale junto al total para
    #: que la pantalla no pueda enseñar uno sin el otro.
    delivered_count: int
