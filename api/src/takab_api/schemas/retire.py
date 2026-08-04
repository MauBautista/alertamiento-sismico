"""Contratos del retiro con doble fricción (T-2.36).

Retirar una estación apaga la protección sísmica de un edificio. Estos modelos
codifican los dos factores: teclear el identificador exacto del objeto (visible en
pantalla, primer factor) y el código de retiro del tenant (secreto, segundo factor).

Ningún modelo de SALIDA lleva el código ni su hash: la respuesta y la bitácora
guardan el hecho, jamás la credencial.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RetireCodeRotate(BaseModel):
    """Fija o rota el código del tenant. Solo ``takab_superadmin``.

    Mínimo 8 caracteres: es una credencial tecleada por una persona, no un token
    generado. El hash lo calcula Postgres (bcrypt vía ``pgcrypto``); este texto no se
    guarda ni se registra en ninguna parte.
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=8, max_length=64)


class RetireCodeState(BaseModel):
    """¿Hay código y de cuándo? Nunca el hash.

    La consola lo consulta ANTES de ofrecer el retiro: sin código configurado el
    intento sería un 409 seguro, y prometer un botón que siempre falla es
    exactamente lo que prohíbe la regla de oro 7.
    """

    tenant_id: UUID
    configured: bool
    version: int | None = None
    rotated_at: datetime | None = None


class GatewayRetire(BaseModel):
    """Retiro de gabinete: ``confirm_serial`` (visible) + ``retire_code`` (secreto)."""

    model_config = ConfigDict(extra="forbid")

    confirm_serial: str = Field(min_length=1, max_length=64)
    retire_code: str = Field(min_length=1, max_length=64)


class SiteRetire(BaseModel):
    """Retiro de sitio: ``confirm_code`` (el ``code`` del sitio) + ``retire_code``.

    Se teclea el ``code`` y no el ``name`` porque ``sites.name`` NO es único
    (``db/schema.sql`` solo restringe ``(tenant_id, code)``): confirmar con un rótulo
    ambiguo dejaría al operador creyendo que apagó otra estación.
    """

    model_config = ConfigDict(extra="forbid")

    confirm_code: str = Field(min_length=1, max_length=32)
    retire_code: str = Field(min_length=1, max_length=64)
