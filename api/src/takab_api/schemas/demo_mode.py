"""Contrato del modo demostración (T-5.02 · D-27)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from takab_api.demo_mode import DEFAULT_S, MAX_S


class DemoModeIn(BaseModel):
    """Encender. La ventana se pide en segundos y se acota al techo."""

    model_config = ConfigDict(extra="forbid")

    #: Tope duro también aquí, para que la interfaz no pueda pedir lo imposible y
    #: llevarse un 500. Quien manda de verdad es el CHECK de la tabla.
    duration_s: int = Field(default=DEFAULT_S, ge=60, le=MAX_S)
    #: Para qué. Se guarda y se audita: dentro de seis meses, «¿por qué estuvo
    #: este cliente sin avisos aquella tarde?» tiene que poder contestarse.
    note: str = Field(default="", max_length=200)


class DemoModeOut(BaseModel):
    """Estado del modo para un cliente. ``active=False`` es la respuesta normal."""

    active: bool
    tenant_id: str
    enabled_by: str | None = None
    enabled_at: datetime | None = None
    expires_at: datetime | None = None
    #: Segundos que le quedan. La interfaz lo pinta en cuenta atrás para que nadie
    #: tenga que restar dos horas UTC de cabeza mientras enseña el producto.
    remaining_s: float = 0.0
    note: str = ""
