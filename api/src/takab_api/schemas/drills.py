"""Modelos del simulacro institucional (T-1.60 · cierra M-1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class DrillCreateIn(BaseModel):
    """Inicio de simulacro. Sin ``site_ids`` = todos los sitios del tenant con
    gateway comandable. La duración acota el banner (30 s..1 h, CHECK de DB).

    [T-2.03·D4c] Con ``scheduled_at`` (futuro) la fila es AGENDA informativa
    ("próximo simulacro" de la app): sin comandos y jamás ``active`` — ejecutar
    a esa hora sigue siendo un acto del operador.
    """

    site_ids: list[UUID] | None = None
    duration_s: int = Field(default=300, ge=30, le=3600)
    note: str | None = Field(default=None, max_length=500)
    scheduled_at: datetime | None = None
    #: [T-2.48] Ejecuta AHORA el simulacro ARMADO con este id: hereda sus sitios,
    #: duración y nota, y consume la agenda (``stop_reason='executed'``). NO es un
    #: temporizador: el disparo lo hace un humano con sesión viva (regla de oro 8),
    #: este campo solo evita que el banner armado siga anunciando lo ya ocurrido.
    from_scheduled: UUID | None = None


class DrillSiteOut(BaseModel):
    """Participación de UN sitio: el acuse se DERIVA del comando firmado."""

    site_id: UUID
    site_name: str | None
    command_id: UUID | None
    command_status: str | None
    ack: dict[str, Any] | None
    #: [T-2.48] ¿el sitio tiene HOY gabinete comandable (no retirado, con
    #: ``iot_thing``)? Se evalúa al LEER, no se congela en el registro: es la
    #: única forma sin DDL nuevo. Existe para no colapsar dos hechos distintos —
    #: "no había a quién mandarle el simulacro" NO es "el sitio no acusó".
    commandable: bool = True
    #: [T-5.14] Cuándo se supo del acuse, con el reloj del SERVIDOR — el mismo que
    #: `issued_at`, y por eso su diferencia significa algo. El `executed_at` que
    #: viaja dentro de `ack` lo pone el gabinete y su reloj es justo lo que el
    #: sistema vigila: mezclarlos daría un «tardó 4 min» que no querría decir nada.
    acked_at: datetime | None = None
    #: Segundos entre la emisión y el acuse. `None` cuando no acusó — y NO cero:
    #: un cero se leería como «acusó al instante», que es lo contrario.
    ack_latency_s: float | None = None
    #: [T-5.17] QUÉ sonó en este sitio: `asset_id`, `sha256`, `will_sound` y, si
    #: no sonó nada, la razón. Sale del acuse del gabinete (`ack.results.audio`),
    #: que es donde el edge lo resuelve. `None` = el acuse no lo trae — un
    #: gabinete con firmware anterior a `T-5.17`, y se distingue de `sha256: null`
    #: (sí lo trae y declara que no había asset).
    audio: dict[str, Any] | None = None


class DrillOut(BaseModel):
    drill_id: UUID
    tenant_id: UUID
    initiated_by: UUID
    note: str | None
    duration_s: int
    started_at: datetime
    stopped_at: datetime | None
    stop_reason: str | None
    #: [T-2.03·D4c] No-NULL = fila de AGENDA (anuncio); jamás deriva active.
    scheduled_at: datetime | None
    #: DERIVADO por el servidor: sin fin manual y dentro de la ventana.
    active: bool
    sites: list[DrillSiteOut]


class DrillList(BaseModel):
    items: list[DrillOut]
    #: [T-2.48] Cursor keyset opaco de la siguiente página; ``None`` = no hay más.
    next_cursor: str | None = None


class ActiveDrillOut(BaseModel):
    """El drill vivo del tenant (o null): la consola pinta el banner NO-real."""

    drill: DrillOut | None


class DrillReportOut(BaseModel):
    """[T-5.14] El documento generado, con lo que hace falta para citarlo.

    Los tres conteos van SEPARADOS y no colapsados: «no tenía gabinete» es un
    problema de inventario y «no acusó» uno de operación, y quien lee el número
    reacciona distinto a cada uno.
    """

    evidence_id: UUID
    sha256: str
    url: str
    expires_in: int
    acked: int
    not_acked: int
    no_gateway: int
    #: `null` si nadie acusó. Los que no acusaron NO entran como cero.
    median_latency_s: float | None
    max_latency_s: float | None
