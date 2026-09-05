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
    #: [T-5.13] COPIA los valores de esa plantilla —sitios, duración y nota— en
    #: este simulacro. Copia y no referencia: editar la plantilla después no
    #: reescribe lo que ya se lanzó. Lo que se manda explícito gana sobre lo
    #: heredado, igual que con ``from_scheduled``. Combinable con
    #: ``scheduled_at`` (armar la agenda desde la plantilla) y excluyente con
    #: ``from_scheduled``, que ya trae sus propios valores heredados: dos
    #: orígenes para el mismo campo acabarían discrepando.
    from_template: UUID | None = None


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
    #: [T-5.13] De qué plantilla se copió. Es PROCEDENCIA: los valores de arriba
    #: son de este simulacro y editar la plantilla no los toca. Por eso aquí va
    #: el id y NO el nombre — pintar el nombre actual sería la reescritura.
    from_template_id: UUID | None = None
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


# ── [T-5.13] Plantillas de simulacro ────────────────────────────────────────
#
# El alta de un simulacro tenía cinco campos y ninguno era una plantilla; lo más
# cercano —ejecutar una agenda armada— **la consume**, así que no se puede
# reutilizar. Para el macrosimulacro de septiembre había que teclear los sitios,
# la duración y la nota a mano, cada vez.

#: Estados de un sitio de la plantilla, evaluados AL LEER y no congelados. Es la
#: misma decisión que ``DrillSiteOut.commandable`` (T-2.48) y por la misma razón:
#: una plantilla se define semanas antes y el inventario se mueve debajo.
SITIO_USABLE = "usable"
SITIO_RETIRADO = "retirado"
SITIO_SIN_GABINETE = "sin_gabinete"
SITIO_NO_VISIBLE = "no_visible"

#: Por qué ese sitio no se puede usar, en una línea que se pueda leer en pantalla.
#: Los tres motivos significan cosas DISTINTAS y colapsarlos en «no disponible»
#: dejaría al operador sin saber a quién llamar: al de inventario, al de campo o
#: al que administra los permisos.
MOTIVO_SITIO: dict[str, str] = {
    SITIO_RETIRADO: "el sitio está dado de baja",
    SITIO_SIN_GABINETE: "el sitio no tiene gabinete comandable",
    SITIO_NO_VISIBLE: "el sitio ya no es visible para este usuario",
}


class TemplateSiteOut(BaseModel):
    """Un sitio de la plantilla, con si HOY se puede usar y por qué no."""

    site_id: UUID
    site_name: str | None = None
    site_code: str | None = None
    #: Uno de los cuatro estados de arriba.
    estado: str
    #: ``None`` cuando el estado es ``usable``.
    motivo: str | None = None


class DrillTemplateIn(BaseModel):
    """Alta o edición de una plantilla.

    ``site_ids`` vacío significa **todos los sitios comandables del tenant**, la
    misma convención que ``DrillCreateIn.site_ids = None`` y que el rótulo del
    modal. Dos convenciones distintas para lo mismo acabarían divergiendo.
    """

    name: str = Field(min_length=1, max_length=120)
    site_ids: list[UUID] = Field(default_factory=list)
    duration_s: int = Field(default=300, ge=30, le=3600)
    note: str | None = Field(default=None, max_length=500)


class DrillTemplateOut(BaseModel):
    template_id: UUID
    tenant_id: UUID
    name: str
    duration_s: int
    note: str | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    sites: list[TemplateSiteOut]
    #: ``True`` si la plantilla no apunta a ningún sitio: se lanzará contra todos
    #: los comandables del tenant en el momento de usarla.
    todos_los_sitios: bool = False
    #: Cuántos de sus sitios NO se pueden usar hoy. Va en la LISTA y no solo en
    #: el detalle: el criterio de la ficha es que se sepa **al usarla**, y quien
    #: la elige está mirando la lista.
    sitios_no_usables: int = 0


class DrillTemplateList(BaseModel):
    items: list[DrillTemplateOut]
