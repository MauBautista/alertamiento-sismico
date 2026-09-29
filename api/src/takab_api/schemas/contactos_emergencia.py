"""[T-9.80 · D-48] Contratos de ``/me/emergency-contacts``.

La forma del contacto es ESPEJO de los CHECK de ``emergency_contacts`` (0077): la
base es quien manda, esto sólo evita el viaje de ida y vuelta por un dedazo
evidente y devuelve un 422 legible en vez de un 409 de integridad.
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Tope de contactos por titular. Espejo del ``CHECK (posicion BETWEEN 1 AND 3)``.
MAX_CONTACTOS = 3

#: Mismo patrón que ``schemas/users._EMAIL_RE`` y que el CHECK de la columna. Sin
#: ``EmailStr``: exigiría ``email-validator`` y esta ficha no añade dependencias.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
#: E.164: ``+`` y de 8 a 15 dígitos, el primero no cero. Espejo del CHECK.
_E164_RE = re.compile(r"^\+[1-9][0-9]{7,14}$")


class ContactoIn(BaseModel):
    """Un contacto tal como lo teclea el titular."""

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=254)
    phone: str | None = None

    @field_validator("display_name")
    @classmethod
    def _nombre(cls, v: str) -> str:
        limpio = v.strip()
        if not limpio:
            raise ValueError("el nombre no puede ir vacío")
        return limpio

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        limpio = v.strip().lower()
        if not _EMAIL_RE.match(limpio):
            raise ValueError("correo inválido")
        return limpio

    @field_validator("phone")
    @classmethod
    def _telefono(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        limpio = v.strip()
        if not _E164_RE.match(limpio):
            raise ValueError("teléfono inválido: formato internacional E.164 (+52…)")
        return limpio


class ContactosIn(BaseModel):
    """``PUT``: la lista ENTERA, que reemplaza a la anterior. Vacía = borrarlos."""

    model_config = ConfigDict(extra="forbid")

    #: La versión del aviso que el titular aceptó al guardar. Si no es la vigente,
    #: 409: un consentimiento sobre un texto que ya no se sirve no vale.
    consentimiento_version: str = Field(min_length=1, max_length=64)
    contactos: list[ContactoIn] = Field(default_factory=list, max_length=MAX_CONTACTOS)


class ContactoOut(BaseModel):
    posicion: int
    display_name: str
    email: str
    phone: str | None
    consent_version: str
    consented_at: datetime


class AvisoContactos(BaseModel):
    """El texto que el titular acepta. ``provisional`` viaja hasta la pantalla."""

    version: str
    texto: str
    provisional: bool


class ContactosOut(BaseModel):
    contactos: list[ContactoOut]
    aviso: AvisoContactos
