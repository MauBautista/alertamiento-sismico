"""T-2.71 · Modelos de la ventana de mantenimiento.

El contrato de entrada es deliberadamente POBRE: quién (token), sobre qué
(``gateway_id``, que la RLS acota), cuánto (``duration_s``, con tope) y por qué
(``reason``, obligatorio). Nada más.

En particular **no hay ``alarm_names`` de entrada**, y no es un olvido: las
alarmas de CloudWatch se identifican por nombre y no llevan dimensión de tenant,
así que aceptarlos convertiría esta superficie en un silenciador universal. Los
nombres se derivan de las filas que el llamante ve bajo RLS
(``ops/muting.mute_names_for_gateways``). ``extra="forbid"`` cierra la puerta
ruidosamente en vez de ignorar en silencio: un cliente que crea que está mandando
nombres tiene que enterarse de que no.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from takab_api.ops.muting import MAX_WINDOW_S, MIN_WINDOW_S

#: Longitud mínima del motivo. Espejo del ``CHECK (length(btrim(reason)) >= 8)``
#: del DDL: una ventana sin motivo escrito es una alarma apagada sin dueño.
MIN_REASON = 8


class MaintenanceWindowIn(BaseModel):
    """Apertura. ``scope='platform'`` no lleva ``gateway_id`` (no tiene dueño)."""

    model_config = ConfigDict(extra="forbid")

    scope: Literal["gateway", "platform"] = "gateway"
    gateway_id: UUID | None = None
    #: El rango vive en TRES sitios que tienen que coincidir: aquí (422 legible),
    #: en el ``CHECK`` del DDL (última línea de defensa) y en
    #: ``iso8601_duration`` (lo que viaja a AWS). Redundante a propósito: es el
    #: número que decide cuánto tiempo un edificio está sin vigilancia.
    duration_s: Annotated[int, Field(ge=MIN_WINDOW_S, le=MAX_WINDOW_S)] = 1800
    reason: Annotated[str, Field(min_length=MIN_REASON, max_length=500)]

    @field_validator("reason")
    @classmethod
    def _reason_no_vacio(cls, v: str) -> str:
        limpio = v.strip()
        if len(limpio) < MIN_REASON:
            raise ValueError(
                "el motivo de una ventana de mantenimiento es obligatorio: "
                "una ventana sin motivo escrito es una alarma apagada sin dueño"
            )
        return limpio

    @field_validator("duration_s")
    @classmethod
    def _duracion_en_minutos(cls, v: int) -> int:
        # `at()` + `Duration` de AWS trabajan en minutos: un valor con segundos
        # sueltos se redondearía en algún sitio y la fila y AWS dejarían de
        # contar desde el mismo borde.
        if v % 60:
            raise ValueError("la duración debe ser múltiplo de 60 s")
        return v


class MaintenanceWindowOut(BaseModel):
    """Lo que la consola pinta. Los cuatro números del acuse van SEPARADOS.

    ``requested``/``silenced``/``missing`` no se colapsan en un solo "ok": una
    ventana que creyó silenciar 3 alarmas y solo silenció 1 tiene que poder
    decirlo (mismo criterio que ``drill_sites.commandable``, T-2.48).
    """

    window_id: UUID
    #: DUEÑO del gabinete intervenido, **no** el tenant de quien abrió la ventana
    #: (regla de oro 5). Un ``takab_*`` interviene inventario ajeno legítimamente;
    #: quien se queda sin vigilancia —y quien tiene que verlo en pantalla y poder
    #: reabrirla— es el dueño del edificio. ``None`` = ventana de PLATAFORMA.
    tenant_id: UUID | None
    gateway_id: UUID | None
    gateway_serial: str | None = None
    site_name: str | None = None
    scope: str
    opened_by: UUID
    reason: str
    duration_s: int
    opened_at: datetime
    #: Minuto en que la mute rule se ACTIVA. La fila y AWS cuentan desde aquí.
    starts_at: datetime
    #: DERIVADO por el servidor: ``starts_at + duration_s``. El navegador no resta
    #: relojes (misma disciplina que ``version_age_s`` de T-2.69).
    ends_at: datetime
    closed_at: datetime | None
    #: DERIVADO por predicado SQL, sin worker de cierre (calcado de ``drills``).
    active: bool
    alarm_names: list[str]
    requested: int
    silenced: int
    missing_names: list[str] = []
    mute_rule: str | None
    #: ¿``requested``/``silenced``/``missing`` se MIDIERON? ``false`` = el
    #: ``PutAlarmMuteRule`` se emitió y su acuse no se pudo leer, así que las
    #: cifras son una suposición deliberadamente pesimista (se asume silencio,
    #: que es el estado peligroso) y ``mute_rule`` es lo único que permite
    #: deshacerlo. Pintar esa cifra sin este flag sería vender una suposición
    #: como una medida — la familia de mentira que T-2.71 existe para no cometer.
    mute_verified: bool = True

    @computed_field  # type: ignore[prop-decorator]
    @property
    def missing(self) -> int:
        """Pedidas que NO quedaron mudas. Sale en el JSON a propósito: si la
        consola tuviera que restar, cada pantalla podría restar distinto."""
        return len(self.missing_names)


class MaintenanceWindowList(BaseModel):
    items: list[MaintenanceWindowOut]
